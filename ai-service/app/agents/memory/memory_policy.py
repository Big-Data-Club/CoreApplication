"""Memory normalization and prompt selection policy.

Durable agent memory is not a transcript.  Each item carries a type, scope,
confidence, lifecycle status and provenance so the agent can distinguish a
verified course anchor from a tentative conversational preference.
"""
from __future__ import annotations

import math
from typing import Any

from app.agents.core.agentic_protocol import MemoryKind


_ALLOWED_KINDS = {item.value for item in MemoryKind}
_ALLOWED_SCOPES = {"session", "course", "user"}
_ALLOWED_STATUS = {"active", "completed", "superseded"}
PREFERENCE_KEYS = {"preferred_language", "preferred_format", "response_style", "learning_goal", "experience_level"}


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
            confidence = float(item.get("confidence", 0.7))
            if not math.isfinite(confidence):
                continue
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.7
        supplied_course = item.get("course_id", course_id)
        bound_course = supplied_course if type(supplied_course) is int and supplied_course > 0 else None
        source_id = item.get("source_message_id")
        normalized.append({
            "kind": kind if kind in _ALLOWED_KINDS else MemoryKind.DECISION.value,
            "value": value[:500],
            "scope": scope if scope in _ALLOWED_SCOPES else "session",
            "status": status if status in _ALLOWED_STATUS else "active",
            "confidence": confidence,
            "source": str(item.get("source") or "conversation_summary")[:80],
            "course_id": bound_course,
            "key": str(item.get("key") or "")[:80],
            "source_quote": str(item.get("source_quote") or "")[:500],
            "source_message_id": source_id if type(source_id) is int and source_id > 0 else None,
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
        if item["status"] == "active" and item["confidence"] >= 0.5
        and (item["scope"] != "course" or (course_id is not None and item["course_id"] == course_id))
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
    lines = []
    for item in items:
        attributed = item["source"] == "user_statement" and item["source_message_id"] and item["source_quote"]
        source = f"user statement #{item['source_message_id']} (unverified claim)" if attributed else "unverified summary/inference"
        value = item["source_quote"] if attributed else item["value"]
        lines.append(f"- [{item['kind']} | {item['scope']} | {source}] {value}")
    return "\n".join(lines)


def bind_memory_sources(items: Any, messages: list[dict], course_id: int | None) -> list[dict]:
    """Only exact owned user statements can become cross-session preferences."""
    users = {m["id"]: m["content"] for m in messages if m.get("role") == "user"
             and type(m.get("id")) is int and isinstance(m.get("content"), str)}
    bound = []
    for item in normalize_memory_items(items):
        quote = item["source_quote"]
        statement = users.get(item["source_message_id"], "")
        verified = bool(quote and quote in statement)
        item["source"] = "user_statement" if verified else "conversation_summary"
        if not verified:
            item["source_message_id"] = None
            item["source_quote"] = ""
        if item["scope"] == "user" and not (
            verified and item["kind"] == "preference" and item["key"] in PREFERENCE_KEYS
        ):
            item["scope"] = "session"
        item["course_id"] = course_id if item["scope"] == "course" else None
        if item["scope"] == "course" and course_id is None:
            item["scope"] = "session"
        bound.append(item)
    return bound


def merge_memory_items(previous: Any, updates: Any, limit: int = 20) -> list[dict]:
    """Latest value/status wins per semantic key, including deletion tombstones."""
    merged = {}
    for item in normalize_memory_items(previous) + normalize_memory_items(updates):
        identity = (item["scope"], item["course_id"], item["kind"], item["key"] or item["value"].casefold())
        old = merged.get(identity)
        if (old and item["scope"] == "user" and old["source_message_id"]
                and (item["source_message_id"] or 0) < old["source_message_id"]):
            continue
        merged.pop(identity, None)
        merged[identity] = item
    # Preserve the five preference keys (including tombstones) when noisy
    # session facts roll off; eviction must not resurrect an older preference.
    preferences, local = [], []
    for item in merged.values():
        target = preferences if (item["scope"] == "user" and item["kind"] == "preference"
                                  and item["key"] in PREFERENCE_KEYS) else local
        target.append(item)
    capacity = max(0, limit - len(preferences))
    return (local[-capacity:] if capacity else []) + preferences[-limit:]
