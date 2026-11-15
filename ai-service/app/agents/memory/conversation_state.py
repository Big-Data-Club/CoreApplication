"""Session-local dialogue anchors. Stored text is evidence, never authorization."""
from __future__ import annotations

import hashlib
from typing import Any

from app.agents.core.conversation_task import ConversationTask, excerpt_dialogue, planning_dialogue


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sources(state: Any, course_id: int | None) -> list[dict]:
    if not isinstance(state, dict) or state.get("version") != 1 or state.get("course_id") != course_id:
        return []
    sources = state.get("sources")
    if not isinstance(sources, list):
        return []
    return [item for item in sources[:4]
            if isinstance(item, dict) and isinstance(item.get("content"), str)
            and isinstance(item.get("digest"), str) and len(item["content"]) <= 6000]


def restore_dialogue(state: Any, history: list[dict], course_id: int | None) -> list[dict]:
    """Restore only this session/course's user statements, with original order."""
    sources = _sources(state, course_id)
    by_digest = {item["digest"]: item for item in sources}
    present = {_digest(str(item.get("content") or "")) for item in history if item.get("role") == "user"}
    missing = [{"role": "user", "content": item["content"], "pinned": True}
               for item in sources if item["digest"] not in present]
    return missing + [
        {**item, "pinned": True} if item.get("role") == "user" and _digest(str(item.get("content") or "")) in by_digest else dict(item)
        for item in history
    ]


def advance_dialogue(
    previous: Any, message: str, task: ConversationTask | None,
    history: list[dict], course_id: int | None,
) -> dict:
    """Pin exact user sources, not assistant answers or a planner's invented facts.

    New topics/cancellation reset anchors. On planner failure retain evidence
    without inventing a semantic task. The current statement is always last.
    """
    sources = _sources(previous, course_id) if task is None or task.relation in {"continuation", "revision"} else []
    shown = {item["message_id"] for item in planning_dialogue(history)}
    if task is not None and task.relation != "cancellation":
        for index in task.source_message_ids:
            if index in shown and history[index].get("role") == "user":
                text = str(history[index].get("content") or "")
                existing = next((item for item in sources if item["content"] == text), None)
                sources.append(existing or {"content": excerpt_dialogue(text, 6000), "digest": _digest(text), "excerpted": len(text) > 6000})
    sources.append({"content": excerpt_dialogue(message, 6000), "digest": _digest(message), "excerpted": len(message) > 6000})
    unique = {}
    for item in sources:
        unique.pop(item["digest"], None)
        unique[item["digest"]] = item
    selected = list(unique.values())
    if len(selected) > 4:
        selected = selected[:1] + selected[-3:]
    return {"version": 1, "course_id": course_id,
            "task": task.model_dump() if task is not None else None, "sources": selected}
