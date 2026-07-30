"""Memory normalization and prompt selection policy.

Durable agent memory is not a transcript.  Each item carries a type, scope,
confidence, lifecycle status and provenance so the agent can distinguish a
verified course anchor from a tentative conversational preference.
"""
from __future__ import annotations

from typing import Any

from app.agents.core.agentic_protocol import MemoryItem, MemoryKind


_ALLOWED_KINDS = {item.value for item in MemoryKind}
_ALLOWED_SCOPES = {"session", "course", "user"}
_ALLOWED_STATUS = {"active", "completed", "superseded"}


def normalize_memory_items(raw: Any, *, course_id: int | None = None) -> list[dict[str, Any]]:
    """Validate untrusted LLM memory output into a bounded durable schema."""
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        kind = str(item.get("kind") or MemoryKind.DECISION.value)
        scope = str(item.get("scope") or "session")
        status = str(item.get("status") or "active")
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.7))))
        except (TypeError, ValueError):
            confidence = 0.7
        normalized.append({
            "kind": kind if kind in _ALLOWED_KINDS else MemoryKind.DECISION.value,
            "value": value[:500],
            "scope": scope if scope in _ALLOWED_SCOPES else "session",
            "status": status if status in _ALLOWED_STATUS else "active",
            "confidence": confidence,
            "source": str(item.get("source") or "conversation_summary")[:80],
            "course_id": item.get("course_id") if item.get("course_id") is not None else course_id,
        })
    return normalized


def select_memory_for_prompt(
    items: Any,
    *,
    course_id: int | None,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """Select active scoped memory; completed/superseded facts stay in storage."""
    candidates = normalize_memory_items(items)
    selected = [
        item for item in candidates
        if item["status"] == "active"
        and (item["scope"] != "course" or course_id is None or item.get("course_id") in (None, course_id))
    ]
    priority = {
        MemoryKind.ANCHOR.value: 5,
        MemoryKind.PENDING_ACTION.value: 4,
        MemoryKind.PREFERENCE.value: 3,
        MemoryKind.LEARNING_SIGNAL.value: 3,
        MemoryKind.DECISION.value: 2,
        MemoryKind.ARTIFACT.value: 1,
    }
    selected.sort(key=lambda item: (priority.get(item["kind"], 0), item["confidence"]), reverse=True)
    return selected[:max_items]


def migrate_legacy_memory(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Read old MTM summaries without making existing sessions go blank."""
    if not isinstance(context, dict):
        return []
    items: list[dict[str, Any]] = []
    facts = context.get("key_facts") or {}
    if isinstance(facts, dict):
        for key in ("current_topic", "preferred_language", "level"):
            if facts.get(key):
                kind = MemoryKind.ANCHOR.value if key == "current_topic" else MemoryKind.PREFERENCE.value
                items.append({"kind": kind, "value": f"{key}: {facts[key]}", "scope": "session", "confidence": 0.7})
    for value in (context.get("pending_actions") or [])[:4]:
        items.append({"kind": MemoryKind.PENDING_ACTION.value, "value": value, "scope": "session", "confidence": 0.8})
    for value in (context.get("decisions_made") or [])[:4]:
        items.append({"kind": MemoryKind.DECISION.value, "value": value, "scope": "session", "confidence": 0.7})
    return normalize_memory_items(items)


def format_memory_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    return "\n".join(
        f"- [{item['kind']} | {item['scope']} | confidence={item['confidence']:.1f}] {item['value']}"
        for item in items
    )
