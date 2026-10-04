"""Provider-independent prompt packing for the ReAct chat path.

The gateway calls this with the *selected* model and key's input allowance.
Current user input and tool-call protocol are mandatory. Older dialogue is
recoverable from MTM; retrieved evidence is selected explicitly and may be
fetched again instead of silently cutting arbitrary text.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.llm_gateway.errors import ContextLengthError
from app.core.llm_gateway.token_budget import estimate_request_tokens, estimate_tokens

logger = logging.getLogger(__name__)

_EVIDENCE_NOTICE = (
    "Some retrieved evidence did not fit this model/key's input budget. "
    "Do not claim to have read omitted evidence. Narrow or repeat retrieval if it is needed."
)


def _compact_tool_content(content: str, target_tokens: int) -> str:
    """Select bounded evidence entries and state how many were omitted."""
    if estimate_tokens(content) <= target_tokens:
        return content
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        payload = None

    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            for key, text_key in (("chunks", "text"), ("results", "snippet")):
                entries = data.get(key)
                if not isinstance(entries, list):
                    continue
                compact = {k: v for k, v in payload.items() if k != "data"}
                compact_data = {
                    k: v for k, v in data.items()
                    if k not in ("chunks", "results", "graph", "content")
                }
                compact_data[key] = []
                compact_data["_evidence_notice"] = _EVIDENCE_NOTICE
                for item in entries:
                    if not isinstance(item, dict):
                        continue
                    excerpt = dict(item)
                    source_text = excerpt.get(text_key)
                    if isinstance(source_text, str) and len(source_text) > 720:
                        excerpt[text_key] = source_text[:720]
                        excerpt["_excerpted"] = True
                    compact_data[key].append(excerpt)
                    compact_data["_shown"] = len(compact_data[key])
                    compact_data["_total"] = len(entries)
                    compact["data"] = compact_data
                    if estimate_tokens(compact) > target_tokens:
                        compact_data[key].pop()
                        break
                compact_data["_shown"] = len(compact_data[key])
                compact_data["_total"] = len(entries)
                compact["data"] = compact_data
                result = json.dumps(compact, ensure_ascii=False, default=str)
                if estimate_tokens(result) <= target_tokens:
                    return result
                break

    omitted = {
        "status": "evidence_not_in_prompt",
        "message": _EVIDENCE_NOTICE,
    }
    return json.dumps(omitted, ensure_ascii=False)


def pack_agent_messages(
    messages: list[dict[str, Any]],
    extra: dict[str, Any],
    max_input_tokens: int,
    *,
    compact_system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """Fit dialogue and evidence without removing the active request.

    The provider still receives every tool call/result pair. If mandatory
    system/current-user/schema data alone exceed the allowance, fail clearly
    so the gateway can try a larger configured binding.
    """
    packed = [dict(message) for message in messages]
    before = estimate_request_tokens(packed, extra)
    if before <= max_input_tokens:
        return packed

    current_user = max(
        (i for i, message in enumerate(packed) if message.get("role") == "user"),
        default=-1,
    )
    if current_user < 0:
        raise ContextLengthError("Agent request has no current user message")

    removed_history = 0
    while estimate_request_tokens(packed, extra) > max_input_tokens:
        oldest = next(
            (i for i in range(current_user) if packed[i].get("role") in ("user", "assistant")),
            None,
        )
        if oldest is None:
            break
        role = packed[oldest].get("role")
        packed.pop(oldest)
        current_user -= 1
        removed_history += 1
        if role == "user" and oldest < current_user:
            # STM holds plain user/assistant dialogue. Drop the corresponding
            # old answer too, so no orphan reply remains in the prompt.
            if packed[oldest].get("role") == "assistant" and not packed[oldest].get("tool_calls"):
                packed.pop(oldest)
                current_user -= 1
                removed_history += 1

    compact_prompt_used = False
    if compact_system_prompt and estimate_request_tokens(packed, extra) > max_input_tokens:
        system_index = next((i for i, m in enumerate(packed) if m.get("role") == "system"), None)
        if system_index is not None and estimate_tokens(compact_system_prompt) < estimate_tokens(packed[system_index].get("content", "")):
            packed[system_index]["content"] = compact_system_prompt
            compact_prompt_used = True

    # Assistant prose before a tool call is already streamed to the user; it
    # need not be replayed to the model. Keep assistant tool_calls intact.
    if estimate_request_tokens(packed, extra) > max_input_tokens:
        packed = [
            message for i, message in enumerate(packed)
            if i <= current_user or message.get("role") != "assistant" or message.get("tool_calls")
        ]

    compacted_results = 0
    for message in packed:
        if estimate_request_tokens(packed, extra) <= max_input_tokens:
            break
        if message.get("role") != "tool" or not isinstance(message.get("content"), str):
            continue
        excess = estimate_request_tokens(packed, extra) - max_input_tokens
        current = estimate_tokens(message["content"])
        target = max(128, current - excess - 32)
        message["content"] = _compact_tool_content(message["content"], target)
        compacted_results += 1

    # The selected plan's tools are listed first. Under a very small TPM tier,
    # remove lower-priority definitions only after dialogue/evidence packing.
    # The gateway passes a private copy of `extra` for each key attempt.
    referenced_tools = {
        call.get("function", {}).get("name")
        for message in packed for call in (message.get("tool_calls") or [])
    }
    omitted_tools = 0
    while estimate_request_tokens(packed, extra) > max_input_tokens and extra.get("tools"):
        removable = next((
            i for i in reversed(range(len(extra["tools"])))
            if (extra["tools"][i].get("function", {}).get("name")
                or extra["tools"][i].get("name")) not in referenced_tools
        ), None)
        if removable is None:
            break  # Let the gateway try a larger binding, keep protocol valid.
        extra["tools"] = [tool for i, tool in enumerate(extra["tools"]) if i != removable]
        omitted_tools += 1
        if not extra["tools"]:
            extra.pop("tools", None)
            extra.pop("tool_choice", None)

    actual = estimate_request_tokens(packed, extra)
    if actual > max_input_tokens:
        raise ContextLengthError(
            f"Mandatory agent prompt needs {actual} estimated input tokens; "
            f"selected model/key allows {max_input_tokens}. "
            "A larger gateway binding or a narrower request is required."
        )
    logger.info(
        "Agent prompt packed: input_estimate=%d -> %d budget=%d history_removed=%d compact_prompt=%s tool_results_compacted=%d tools_omitted=%d",
        before, actual, max_input_tokens, removed_history, compact_prompt_used,
        compacted_results, omitted_tools,
    )
    return packed
