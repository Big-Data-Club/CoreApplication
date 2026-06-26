"""
ai-service/app/agents/memory/compressor.py

LLM-powered context compression.

When STM exceeds the token threshold, this module summarises the
conversation into a compact JSONB structure for MTM storage.

The compressed output is designed to be injected into the system prompt,
giving the agent continuity across many turns without replaying the
entire conversation.

Uses the fast chat model (llama-3.1-8b-instant) for low latency.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_MEMORY_COMPRESS

logger = logging.getLogger(__name__)
settings = get_settings()

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
    }
}

`key_facts` may contain other user-specific preferences observed in the
conversation (e.g. "preferred_format": "markdown"). If a field has no data,
use an empty array [], empty object {}, or omit optional key_facts entries.
"""


async def compress_conversation(
    messages: list[dict],
    agent_type: str,
    existing_ctx: dict | None = None,
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
        if role == "SYSTEM" or not content:
            continue
        # Truncate very long tool results
        if role == "TOOL" and len(content) > 500:
            content = content[:500] + "... [truncated]"
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

    # Include existing context for merging
    existing_section = ""
    if existing_ctx and any(existing_ctx.values()):
        import json
        existing_section = (
            f"\n\nEXISTING CONTEXT (merge new info into this):\n"
            f"{json.dumps(existing_ctx, ensure_ascii=False, indent=2)}"
        )

    user_prompt = (
        f"Agent type: {agent_type}\n"
        f"{agent_hint}\n"
        f"{existing_section}\n\n"
        f"CONVERSATION TO COMPRESS:\n{conversation_text}"
    )

    try:
        result = await chat_complete_json(
            messages=[
                {"role": "system", "content": COMPRESS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model=settings.chat_model,  # fast model for compression
            temperature=0.1,
            max_tokens=512,
            task=TASK_MEMORY_COMPRESS,
        )

        # Validate structure
        if not isinstance(result, dict):
            logger.warning("Compressor returned non-dict: %s", type(result))
            return existing_ctx or {}

        # Ensure all expected keys exist
        defaults = {
            "decisions_made": [],
            "content_created": [],
            "identified_gaps": [],
            "student_progress": {},
            "pending_actions": [],
            "key_facts": {},
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default

        logger.info(
            "Conversation compressed: gaps=%d, actions=%d, facts=%d",
            len(result.get("identified_gaps", [])),
            len(result.get("pending_actions", [])),
            len(result.get("key_facts", {})),
        )
        return result

    except Exception as exc:
        logger.error("Context compression failed: %s", exc)
        return existing_ctx or {}
