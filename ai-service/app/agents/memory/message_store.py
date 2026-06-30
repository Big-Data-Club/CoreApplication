"""
ai-service/app/agents/memory/message_store.py

Persistent Message Store for Agent Chat History.
Saves exact conversation turns to PostgreSQL so they survive beyond Redis TTL.
Used purely for displaying history in the UI, not for LLM context injection.
"""
import json
import logging
from typing import Optional

from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)


def _custom_json_serializer(obj):
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return obj.model_dump()
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()
    try:
        return str(obj)
    except Exception:
        return "<Unserializable Object>"


class MessageStore:
    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> None:
        """Save a single message to persistent history."""
        try:
            async with get_ai_conn() as conn:
                await conn.execute(
                    """INSERT INTO agent_messages (session_id, role, content, metadata)
                       VALUES ($1, $2, $3, $4::jsonb)""",
                    session_id,
                    role,
                    content,
                    json.dumps(metadata, ensure_ascii=False, default=_custom_json_serializer) if metadata else '{}'
                )
        except Exception as exc:
            logger.error("Failed to save message to persistent store: %s", exc)

    async def get_messages(self, session_id: str, limit: int = 100) -> list[dict]:
        """Retrieve recent persistent messages for a session."""
        try:
            async with get_ai_conn() as conn:
                rows = await conn.fetch(
                    """SELECT id, role, content, metadata, created_at
                       FROM agent_messages
                       WHERE session_id = $1
                       ORDER BY created_at ASC
                       LIMIT $2""",
                    session_id,
                    limit
                )
            
            result = []
            for row in rows:
                meta = row["metadata"]
                if isinstance(meta, str):
                    meta = json.loads(meta)
                
                result.append({
                    "id": str(row["id"]),
                    "role": row["role"],
                    "content": row["content"],
                    "metadata": meta or {},
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                })
            return result
        except Exception as exc:
            logger.error("Failed to fetch persistent messages: %s", exc)
            return []


# Singleton
message_store = MessageStore()
