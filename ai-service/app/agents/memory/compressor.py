"""
ai-service/app/agents/memory/compressor.py

LLM-powered context compression.

When STM exceeds the token threshold, this module summarises the
conversation into a compact JSONB structure for MTM storage.

The compressed output is designed to be injected into the system prompt,
giving the agent continuity across many turns without replaying the
entire conversation.

The memory-compression task binding is selected by the LLM gateway.
"""
from __future__ import annotations

import logging

from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_MEMORY_COMPRESS, get_gateway
from app.core.llm_gateway.token_budget import estimate_tokens, split_text_preserving_content

logger = logging.getLogger(__name__)

COMPRESS_SYSTEM_PROMPT = """\
You are a conversation compressor for an AI teaching/mentoring system.
Your job is to extract ONLY valuable long-term information from a conversation
so the agent can keep coherent context across many turns.

RULES:
1. KEEP:
   - Decisions made and their reasoning in one sentence each
   - Content IDs created (quiz_id, flashcard_set_id, plan_id, etc.)
   - Knowledge gaps and concepts the student is weak at
   - Pending tasks not yet completed
   - Student progress signals (mastery, scores, error patterns)
   - The CURRENT topic/thread the conversation is on (critical for continuity)
   - Key preferences (language, difficulty level, learning style)
2. DISCARD: greetings, confirmations, repeated information, filler chitchat,
   raw tool JSON, debugging output.
3. Output MUST be valid JSON matching the schema below - no extra fields,
   no prose before or after.
4. Keep the output compact - target under 300 tokens.
5. Preserve the user's language. If conversation is in Vietnamese, write
   the JSON values in Vietnamese.
6. When merging with EXISTING CONTEXT, preserve still-relevant facts and
   only append/refine based on the new conversation. Don't duplicate.
7. Also emit memory_items for facts worth recalling. Each item must be a
   concise, attributable claim; never store raw lesson text, credentials, or
   hidden reasoning. Use status='completed' when a pending action was done.

Output JSON schema:
{
    "decisions_made": ["string"],
    "content_created": ["string - include IDs if available"],
    "identified_gaps": ["concept names the student is weak at"],
    "student_progress": {
        "avg_mastery": 0.0,
        "recent_scores": [],
        "notes": "string"
    },
    "pending_actions": ["things not yet completed"],
    "key_facts": {
        "current_topic": "the topic actively being discussed, or empty",
        "preferred_language": "vi | en | ...",
        "level": "beginner | intermediate | advanced (if inferrable)"
    },
    "memory_items": [
        {"kind": "anchor|preference|decision|pending_action|learning_signal|artifact",
         "value": "compact fact", "scope": "session|course|user",
         "status": "active|completed|superseded", "confidence": 0.0,
         "source": "conversation_summary", "course_id": null}
    ]
}

`key_facts` may contain other user-specific preferences observed in the
conversation (e.g. "preferred_format": "markdown"). If a field has no data,
use an empty array [], empty object {}, or omit optional key_facts entries.
"""


async def compress_conversation(
    messages: list[dict],
    agent_type: str,
    existing_ctx: dict | None = None,
    *,
    strict: bool = False,
) -> dict:
    """
    Compress a conversation history into a compact JSONB summary.

    Args:
        messages: List of messages in OpenAI format from STM.
        agent_type: "teacher" or "mentor" - affects what to prioritise.
        existing_ctx: Previous compressed context to merge with.

    Returns:
        Compressed context dict matching the schema above.
    """
    # Build conversation text (skip system messages)
    conversation_lines = []
    for m in messages:
        role = m.get("role", "unknown").upper()
        content = m.get("content", "")
        if role in ("SYSTEM", "TOOL") or not content:
            continue
        conversation_lines.append(f"{role}: {content}")

    conversation_text = "\n".join(conversation_lines)

    if not conversation_text.strip():
        return existing_ctx or {}

    # Add context about what to prioritise
    agent_hint = (
        "Focus on: content created, quiz IDs, course decisions."
        if agent_type == "teacher"
        else "Focus on: student knowledge gaps, mastery levels, study progress."
    )

    try:
        import json
        from app.agents.memory.memory_policy import normalize_memory_items

        result = existing_ctx or {}
        try:
            request_budget = await get_gateway().preview_request_budget(TASK_MEMORY_COMPRESS)
        except Exception:
            request_budget = 4000
        # Leave room for instructions, the previous compact state, provider
        # accounting headroom, and a useful completion on the selected tier.
        state_tokens = estimate_tokens(result)
        fixed_tokens = estimate_tokens(COMPRESS_SYSTEM_PROMPT) + state_tokens + 700
        segment_budget = min(1200, max(200, int((request_budget - fixed_tokens) * 0.65)))
        # A long session is processed in bounded, ordered segments. No raw
        # transcript is sent in one oversized compression request.
        for segment in split_text_preserving_content(conversation_text, segment_budget):
            existing_section = (
                "\nEXISTING CONTEXT (merge, do not duplicate):\n"
                + json.dumps(result, ensure_ascii=False, separators=(",", ":"))
                if result else ""
            )
            next_result = await chat_complete_json(
                messages=[
                    {"role": "system", "content": COMPRESS_SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Agent type: {agent_type}\n{agent_hint}\n"
                        f"{existing_section}\nCONVERSATION TO COMPRESS:\n{segment}"
                    )},
                ],
                temperature=0.1,
                max_tokens=512,
                task=TASK_MEMORY_COMPRESS,
            )
            if not isinstance(next_result, dict):
                raise ValueError("Memory compressor returned a non-object response")
            defaults = {
                "decisions_made": [], "content_created": [], "identified_gaps": [],
                "student_progress": {}, "pending_actions": [], "key_facts": {},
                "memory_items": [],
            }
            for key, default in defaults.items():
                next_result.setdefault(key, default)
            for key in ("decisions_made", "content_created", "identified_gaps", "pending_actions"):
                values = next_result.get(key)
                next_result[key] = [str(value)[:240] for value in values[:8]] if isinstance(values, list) else []
            facts = next_result.get("key_facts")
            next_result["key_facts"] = {
                str(key)[:80]: value if isinstance(value, (int, float, bool)) else str(value)[:160]
                for key, value in list(facts.items())[:10]
            } if isinstance(facts, dict) else {}
            progress = next_result.get("student_progress")
            if isinstance(progress, dict):
                next_result["student_progress"] = {
                    str(key)[:80]: value if isinstance(value, (int, float, bool)) else str(value)[:160]
                    for key, value in list(progress.items())[:8]
                }
            else:
                next_result["student_progress"] = {}
            # Keep prior attributable facts unless this segment explicitly
            # updates the same item (for example pending -> completed).
            prior_items = normalize_memory_items(result.get("memory_items"))
            current_items = normalize_memory_items(next_result.get("memory_items"))
            merged_items: dict[tuple, dict] = {}
            for item in prior_items + current_items:
                identity = (
                    item["kind"], item["scope"], item.get("course_id"),
                    item["value"].strip().casefold(),
                )
                merged_items[identity] = {**item, "value": item["value"][:240]}
            next_result["memory_items"] = list(merged_items.values())[-12:]
            old_facts = result.get("key_facts") or {}
            for pinned_key in (
                "current_course_id", "current_course_title", "current_node_id",
                "recent_courses",
            ):
                if pinned_key in old_facts and pinned_key not in next_result["key_facts"]:
                    next_result["key_facts"][pinned_key] = old_facts[pinned_key]
            result = next_result

        logger.info(
            "Conversation compressed: gaps=%d, actions=%d, facts=%d",
            len(result.get("identified_gaps", [])),
            len(result.get("pending_actions", [])),
            len(result.get("key_facts", {})),
        )
        return result

    except Exception as exc:
        logger.error("Context compression failed: %s", exc)
        if strict:
            raise
        return existing_ctx or {}
