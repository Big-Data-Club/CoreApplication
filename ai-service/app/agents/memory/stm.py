"""
ai-service/app/agents/memory/stm.py

Short-Term Memory (STM) - Redis-backed conversation history.

Stores the most recent messages in OpenAI chat format as a Redis List.
Each session has its own key with a 24-hour TTL.

Key pattern:  lms:agent:stm:{session_id}
Data format:  JSON strings in OpenAI message format:
    {"role": "user|assistant|tool|clarification",
     "content": "...",
     "tool_calls": [...],  # optional
     "ts": 1713598800}     # unix timestamp

Token counting uses a character-based approximation (1 token ~= 4 chars)
to avoid adding tiktoken as a dependency. When the token count exceeds
the threshold, the caller (react_loop) should trigger MTM compression.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from app.core.cache import _get_redis

logger = logging.getLogger(__name__)

STM_TTL = 86400  # 24 hours
STM_OVERFLOW_THRESHOLD = 3000  # ~3000 tokens -> trigger agent-driven cleanup
CHARS_PER_TOKEN = 4  # approximation for multilingual text


class STMemory:
    """Short-Term Memory backed by Redis Lists."""

    def _key(self, session_id: str) -> str:
        return f"lms:agent:stm:{session_id}"

    async def append(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[list] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Append a message to the session's STM."""
        r = _get_redis()
        msg: dict = {
            "role": role,
            "content": content,
            "ts": int(time.time()),
        }
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id

        key = self._key(session_id)
        await r.rpush(key, json.dumps(msg, ensure_ascii=False))
        await r.expire(key, STM_TTL)

    async def get_window(
        self,
        session_id: str,
        n_turns: int = 20,
    ) -> list[dict]:
        """
        Get the last N messages from STM.

        Returns messages in chronological order (oldest first).
        """
        r = _get_redis()
        raw = await r.lrange(self._key(session_id), -n_turns, -1)
        messages = []
        for item in raw:
            try:
                messages.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse STM message: %s", item[:100])
        return messages

    async def get_all(self, session_id: str) -> list[dict]:
        """Get all messages in STM (for compression)."""
        r = _get_redis()
        raw = await r.lrange(self._key(session_id), 0, -1)
        messages = []
        for item in raw:
            try:
                messages.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                continue
        return messages

    async def count_tokens(self, session_id: str) -> int:
        """
        Approximate token count of all messages in STM.

        Uses character-based approximation: 1 token ~= 4 characters.
        This avoids adding tiktoken as a heavy dependency.
        """
        messages = await self.get_all(session_id)
        total_chars = sum(
            len(m.get("content", "") or "")
            for m in messages
        )
        return total_chars // CHARS_PER_TOKEN

    async def check_token_overflow(self, session_id: str) -> bool:
        """Check if STM has exceeded the overflow threshold."""
        tokens = await self.count_tokens(session_id)
        return tokens > STM_OVERFLOW_THRESHOLD

    async def summarize_and_replace(
        self,
        session_id: str,
        summary_text: str,
        keep_last: int = 2,
    ) -> None:
        """
        Replace older messages with a single summary message, 
        keeping the `keep_last` most recent messages.
        """
        r = _get_redis()
        key = self._key(session_id)
        length = await r.llen(key)
        
        if length <= keep_last:
            return
            
        # Get the messages we want to keep
        recent = await r.lrange(key, -keep_last, -1)
        
        # Build the summary message
        summary_msg = {
            "role": "assistant",
            "content": f"[System: Tóm tắt các trao đổi cũ] {summary_text}",
            "ts": int(time.time()),
        }
        
        # Transaction: clear list, push summary, push recent
        pipe = r.pipeline()
        pipe.delete(key)
        pipe.rpush(key, json.dumps(summary_msg, ensure_ascii=False))
        if recent:
            pipe.rpush(key, *recent)
        pipe.expire(key, STM_TTL)
        await pipe.execute()
        
        logger.info("STM summarized: session=%s, kept_last=%d", session_id, keep_last)

    async def remove_messages_by_index(self, session_id: str, indices: list[int]) -> int:
        """
        Remove specific messages from STM by their index (0-indexed).
        Returns the number of messages removed.
        """
        if not indices:
            return 0
            
        r = _get_redis()
        key = self._key(session_id)
        raw = await r.lrange(key, 0, -1)
        
        if not raw:
            return 0
            
        indices_set = set(indices)
        kept_messages = [
            msg for i, msg in enumerate(raw) 
            if i not in indices_set
        ]
        
        if len(kept_messages) == len(raw):
            return 0
            
        # Transaction: clear and push kept messages
        pipe = r.pipeline()
        pipe.delete(key)
        if kept_messages:
            pipe.rpush(key, *kept_messages)
            pipe.expire(key, STM_TTL)
        await pipe.execute()
        
        removed_count = len(raw) - len(kept_messages)
        logger.info("STM filtered: session=%s, removed=%d", session_id, removed_count)
        return removed_count

    async def clear(self, session_id: str) -> None:
        """Clear all STM for a session."""
        await _get_redis().delete(self._key(session_id))

    async def length(self, session_id: str) -> int:
        """Number of messages in STM."""
        return await _get_redis().llen(self._key(session_id))


# Singleton
stm = STMemory()
