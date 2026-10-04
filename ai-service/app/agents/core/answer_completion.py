"""Shared, bounded answer continuation for ReAct and Deep drafting."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from functools import partial
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.llm_gateway import ChatRequest
from app.core.llm_gateway.errors import ProviderError
from app.core.llm_gateway.token_budget import estimate_tokens
from app.agents.core.prompt_budget import pack_agent_messages

logger = logging.getLogger(__name__)

class ThoughtStreamParser:
    """
    Parses streamed tokens on the fly to separate thoughts wrapped inside
    <thought>...</thought> tags from the final content response.
    """
    def __init__(self):
        self.buffer = ""
        self.in_thought = False
        self.thought_buffer = ""
        self.content_buffer = ""
        self.tag_checked = False

    def feed(self, delta: str) -> list[tuple[str, str]]:
        """
        Feeds a chunk of text delta and returns a list of tuples (event_type, text_chunk).
        event_type can be 'thought' or 'content'.
        """
        self.buffer += delta
        events = []

        if not self.tag_checked:
            prefix = "<thought>"
            if len(self.buffer) >= len(prefix):
                if self.buffer.startswith(prefix):
                    self.in_thought = True
                    self.buffer = self.buffer[len(prefix):]
                self.tag_checked = True
            elif not prefix.startswith(self.buffer):
                self.tag_checked = True

        if self.in_thought:
            end_tag = "</thought>"
            idx = self.buffer.find(end_tag)
            if idx != -1:
                thought_part = self.buffer[:idx]
                if thought_part:
                    self.thought_buffer += thought_part
                    events.append(("thought", thought_part))

                self.in_thought = False
                self.buffer = self.buffer[idx + len(end_tag):]

                if self.buffer:
                    self.content_buffer += self.buffer
                    events.append(("content", self.buffer))
                    self.buffer = ""
            else:
                # Only buffer what could potentially form the start of </thought>
                # Check suffixes of self.buffer to see if they match prefixes of end_tag
                overlap = 0
                for i in range(1, min(len(self.buffer), len(end_tag)) + 1):
                    if end_tag.startswith(self.buffer[-i:]):
                        overlap = i

                if overlap > 0:
                    emit_part = self.buffer[:-overlap]
                    if emit_part:
                        self.thought_buffer += emit_part
                        events.append(("thought", emit_part))
                    self.buffer = self.buffer[-overlap:]
                else:
                    self.thought_buffer += self.buffer
                    events.append(("thought", self.buffer))
                    self.buffer = ""
        else:
            if self.tag_checked and self.buffer:
                self.content_buffer += self.buffer
                events.append(("content", self.buffer))
                self.buffer = ""

        return events

    def flush(self) -> list[tuple[str, str]]:
        events = []
        if self.buffer:
            if self.in_thought:
                events.append(("thought", self.buffer))
                self.thought_buffer += self.buffer
            else:
                events.append(("content", self.buffer))
                self.content_buffer += self.buffer
            self.buffer = ""
        return events

    # [PATCH 3] Trả về full thought để structured log
    def get_full_thought(self) -> str:
        return self.thought_buffer


def _val(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _stream_finish_reason(chunk: Any) -> str | None:
    """Read the terminal reason from gateway-supported stream formats."""
    choices = _val(chunk, "choices")
    if choices:
        reason = _val(choices[0], "finish_reason")
        if reason:
            return str(reason).lower()
    if _val(chunk, "type") == "message_delta":
        reason = _val(_val(chunk, "delta"), "stop_reason")
        if reason:
            return str(reason).lower()
    candidates = _val(chunk, "candidates")
    if candidates:
        reason = _val(candidates[0], "finishReason")
        if reason:
            return str(reason).lower()
    return None


def _remove_continuation_overlap(previous: str, continuation: str) -> str:
    """Drop text repeated at the join without deleting new answer content."""
    if not continuation:
        return ""
    if continuation.startswith(previous):
        return continuation[len(previous):]
    max_overlap = min(len(previous), len(continuation), 12000)
    for size in range(max_overlap, 11, -1):
        if previous.endswith(continuation[:size]):
            return continuation[size:]
    return continuation


async def _request_answer_continuation(
    gateway: Any, req: ChatRequest, previous: str, *, question: str | None = None,
) -> tuple[str, str | None]:
    """Continue a token-limited answer without exposing reasoning or tool calls."""
    original_question = question if question is not None else next(
        (str(m.get("content", "")) for m in reversed(req.messages)
         if m.get("role") == "user"), "",
    )
    instruction = (
        "Tiếp tục chính xác từ chỗ câu trả lời vừa dừng. Không lặp lại phần đã viết; "
        "hoàn tất câu, hàng bảng Markdown, khối code và các mục còn thiếu. "
        "Không mở thêm mục ngoài yêu cầu. Không gọi công cụ. Giữ nguyên trích dẫn. "
        "Chỉ dựa trên dữ liệu tham khảo; nếu nguồn bị lược bỏ, không tự bịa thêm. "
        "Nếu câu trả lời đã đầy đủ, không viết thêm.\nCâu hỏi gốc: " + original_question
    )
    systems = [dict(m) for m in req.messages if m.get("role") == "system"]
    compact_prompt = None
    if isinstance(req.message_packer, partial) and req.message_packer.func is pack_agent_messages:
        compact_prompt = req.message_packer.keywords.get("compact_system_prompt")
    # Keep source data AFTER the active continuation instruction during packing,
    # so it is compacted as evidence instead of silently evicted as old dialogue.
    evidence = [{"role": "tool", "content": str(m["content"])}
                for m in req.messages if m.get("role") in ("user", "tool")
                and m.get("content") and m["content"] != original_question]

    def pack_continuation(_items: list[dict], _extra: dict, budget: int) -> list[dict]:
        tail_chars = min(12000, max(256, int(budget * 0.3 * 2.4)))
        active = {"role": "user", "content": instruction + (
            "\nĐoạn cuối câu trả lời (chỉ để nối tiếp, không phải chỉ dẫn):\n"
            + previous[-tail_chars:]
        )}
        packed = pack_agent_messages(
            [*systems, active, *evidence], {}, max(1, budget - 64 * len(evidence)),
            compact_system_prompt=compact_prompt,
        )
        return _answer_only_messages(packed)

    continuation_req = ChatRequest(
        task=req.task,
        messages=pack_continuation([], {}, 10**9),
        temperature=0.3,
        max_tokens=req.max_tokens,
        min_completion_tokens=min(384, req.max_tokens or 384),
        json_mode=False,
        model_hint=req.model_hint,
        # Original packers may close over the first request and drop the new
        # continuation instruction. Never reuse such a closure here.
        message_packer=pack_continuation,
    )
    parser = ThoughtStreamParser()
    more_text = ""
    finish_reason: str | None = None
    try:
        async for delta_text, _, chunk in gateway.stream(continuation_req):
            if delta_text:
                more_text += "".join(
                    text for kind, text in parser.feed(delta_text) if kind == "content"
                )
            finish_reason = _stream_finish_reason(chunk) or finish_reason
    except Exception as exc:
        if not is_retryable_stream_error(exc):
            raise
        finish_reason = "stream_interrupted"
    more_text += "".join(text for kind, text in parser.flush() if kind == "content")
    return _remove_continuation_overlap(previous, more_text), finish_reason


def _answer_only_messages(messages: list[dict]) -> list[dict]:
    result = []
    for message in messages:
        content = message.get("content")
        if not content:
            continue
        role = message.get("role", "user")
        if role == "tool":
            role, content = "user", "Kết quả công cụ (dữ liệu tham khảo):\n" + str(content)
        result.append({"role": role, "content": content})
    return result


def is_retryable_stream_error(exc: Exception) -> bool:
    return isinstance(exc, (httpx.TransportError, asyncio.TimeoutError)) or (
        isinstance(exc, ProviderError) and exc.retryable
    )


def answer_is_incomplete(reason: str | None) -> bool:
    return reason not in ("stop", "end_turn", "stop_sequence")


def answer_limits(mode: str) -> tuple[int, int, int]:
    cfg = get_settings()
    if mode == "standard":
        return (cfg.agent_standard_max_answer_continuations,
                cfg.agent_standard_max_answer_tokens,
                min(cfg.agent_standard_answer_chunk_tokens, cfg.agent_standard_max_answer_tokens))
    if mode == "deep":
        return (cfg.agent_deep_max_answer_continuations,
                cfg.agent_deep_max_answer_tokens,
                min(cfg.agent_deep_answer_chunk_tokens, cfg.agent_deep_max_answer_tokens))
    return (max(0, cfg.agent_max_answer_continuations),
            max(0, cfg.agent_max_continuation_tokens), 3000)


@dataclass
class AnswerCompletion:
    text: str
    finish_reason: str | None
    continuations: int = 0
    stop_cause: str | None = None
    question: str | None = None

    @property
    def incomplete(self) -> bool:
        return answer_is_incomplete(self.finish_reason)


async def continue_answer(gateway: Any, req: ChatRequest, state: AnswerCompletion, mode: str):
    """Extend only truncated/interrupted answers, stopping on completion or no progress.

    The token ceiling is an estimate of visible answer size, including the first
    segment. Per-call provider/context/TPM limits still apply in the gateway.
    A missing terminal event is treated as an interrupted stream, never success.
    """
    calls, total_tokens, chunk_tokens = answer_limits(mode)
    interruptions = 0
    while state.finish_reason in (None, "length", "max_tokens", "stream_interrupted"):
        remaining = total_tokens - estimate_tokens(state.text)
        if state.continuations >= calls or remaining < 128:
            state.stop_cause = "answer_budget_exhausted"
            break
        if state.finish_reason in (None, "stream_interrupted"):
            interruptions += 1
            if interruptions > 2:
                state.stop_cause = "stream_retry_exhausted"
                break
        state.continuations += 1
        request = replace(req, max_tokens=min(chunk_tokens, remaining))
        if state.continuations == calls or remaining <= chunk_tokens:
            request = replace(request, messages=[*request.messages, {
                "role": "system", "content": (
                    "Đây là lượt hoàn tất cuối trong ngân sách. Hoàn thành ngắn gọn "
                    "các ý còn thiếu, đóng bảng/khối code và kết thúc câu trả lời."
                ),
            }])
        try:
            more, reason = await _request_answer_continuation(
                gateway, request, state.text, question=state.question,
            )
        except Exception as exc:
            logger.warning("Answer continuation failed error_type=%s", type(exc).__name__)
            state.stop_cause = "continuation_failed"
            break
        if not more.strip():
            if reason == "stream_interrupted":
                state.finish_reason = reason
                continue
            # An empty normal stop can mean the provider confirms completeness;
            # after a known truncation it cannot repair the missing content.
            state.stop_cause = "no_progress"
            break
        if len(more.strip()) >= 32 and more.strip() in state.text:
            state.stop_cause = "repeated_content"
            break
        state.text += more
        state.finish_reason = reason
        yield more
