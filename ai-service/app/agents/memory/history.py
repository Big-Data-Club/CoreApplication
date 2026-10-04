"""Resolve a bounded history window without confusing an outage with a new chat."""
import logging
from app.agents.memory.message_store import message_store
from app.agents.memory.stm import stm

logger = logging.getLogger(__name__)


async def load_history(session_id: str, user_id: int, limit: int = 30) -> dict:
    cached, durable = [], []
    cache_ok = durable_ok = False
    try:
        cached = await stm.get_window(session_id, n_turns=limit)
        cache_ok = True
    except Exception as exc:
        logger.warning("History cache unavailable error_type=%s", type(exc).__name__)
    try:
        durable = await message_store.get_recent_context(session_id, user_id, limit)
        durable_ok = True
    except Exception as exc:
        logger.warning("Durable history unavailable error_type=%s", type(exc).__name__)
    if durable:
        # Redis retains richer clarification metadata. Reuse only when its tail
        # agrees with durable history and it has at least as many messages.
        if (cached and len(cached) >= len(durable)
                and cached[-1].get("role") == durable[-1].get("role")
                and cached[-1].get("content") == durable[-1].get("content")):
            return {"messages": cached, "source": "cache", "status": "available"}
        return {"messages": durable, "source": "persistent", "status": "available"}
    if cached:
        return {"messages": cached, "source": "cache", "status": "available"}
    return {"messages": [], "source": "none",
            "status": "empty" if durable_ok and cache_ok else "unavailable"}
