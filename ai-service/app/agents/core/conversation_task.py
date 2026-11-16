"""Bounded dialogue evidence shared by planning, clarification and execution.

The planner interprets references semantically. This module only selects real
messages; it never turns recalled IDs or an assistant's claims into authority.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, StrictInt


class DataIssue(BaseModel):
    """A planner-reported decisive gap/conflict, never a verified fact."""
    kind: Literal["missing", "conflict"]
    detail: str = Field(min_length=1, max_length=300)
    question: str = Field(min_length=1, max_length=500)
    source_message_ids: list[StrictInt] = Field(default_factory=list, max_length=4)


def data_clarification(issues: list[DataIssue], history: list[dict] | None = None) -> dict | None:
    if not issues:
        return None
    history = history or []
    attributed = []
    for issue in issues:
        sources = []
        for index in dict.fromkeys(issue.source_message_ids):
            if not 0 <= index < len(history):
                continue
            source = history[index]
            if source.get("role") in {"user", "assistant", "clarification"} and isinstance(source.get("content"), str):
                sources.append({"history_index": index, "role": source["role"],
                                "quote": excerpt_dialogue(source["content"], 800),
                                "excerpted": len(source["content"]) > 800})
        attributed.append({**issue.model_dump(), "sources": sources})
    return {"needs_clarification": True, "kind": "data",
            "clarification_question": "\n".join(dict.fromkeys(issue.question for issue in issues)),
            "clarification_options": [], "missing_fields": [issue.detail for issue in issues],
            "issues": attributed}


class ConversationTask(BaseModel):
    relation: Literal["new_task", "continuation", "revision", "cancellation"] = "new_task"
    goal: str = Field(default="", max_length=1600)
    artifact: Literal["lesson", "quiz", "flashcards", "course", "materials", "answer", "other"] = "other"
    language: Literal["vi", "en"] = Field(default="vi", description="User's requested output language, preserving explicit prior preferences.")
    destination: str = Field(default="", max_length=400,
                             description="User-stated target, e.g. chapter Review; not a verified resource ID.")
    constraints: list[str] = Field(default_factory=list, max_length=8)
    source_message_ids: list[StrictInt] = Field(default_factory=list, max_length=4,
        description="Indices of relevant supplied history messages, especially the original user request/source.")


def excerpt_dialogue(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    notice = "\n[Middle omitted; this is an excerpt, not the complete source.]\n"
    remaining = max(0, limit - len(notice))
    head = remaining * 2 // 3
    return content[:head] + notice + content[-(remaining - head):]


def planning_dialogue(history: list[dict] | None) -> list[dict]:
    """Keep user requests substantially intact and label every omission.

    Stable indices refer to the supplied window, not database message IDs.
    Preserve both ends: destinations/corrections often appear after long sources.
    """
    entries = []
    remaining = 24000
    indices = sorted(range(len(history or [])), key=lambda index: (
        bool(history[index].get("pinned")) and history[index].get("role") == "user", index,
    ), reverse=True)
    for index in indices:
        message = history[index]
        role, content = message.get("role"), message.get("content")
        if role not in ("user", "assistant", "clarification") or not isinstance(content, str) or not content:
            continue
        if len(entries) == 16 or remaining < 300:
            break
        limit = min(remaining, 6000 if role == "user" else 1800)
        excerpt = excerpt_dialogue(content, limit)
        entries.append({"message_id": index, "role": role, "content": excerpt,
                        "excerpted": len(content) > limit,
                        **({"pinned": True} if message.get("pinned") and role == "user" else {})})
        remaining -= len(excerpt)
    return sorted(entries, key=lambda item: item["message_id"])


def execution_request(message: str, task: ConversationTask | None, history: list[dict]) -> str:
    """Restore selected original sources in the active, budget-protected request.

    A planner summary is a fallible interpretation, never a replacement for the
    current user turn. Only references actually shown to the planner are usable.
    """
    if task is None or task.relation in ("new_task", "cancellation") or not task.goal.strip():
        return message
    shown = {item["message_id"] for item in planning_dialogue(history)}
    ids = list(dict.fromkeys(index for index in task.source_message_ids
                            if type(index) is int and index in shown))
    if not ids:
        return message
    remaining = 32000
    sources = []
    for index in ids:
        original = history[index]
        content = original["content"]
        if remaining < 300:
            break
        excerpt = excerpt_dialogue(content, remaining)
        sources.append({"message_id": index, "role": original["role"], "content": excerpt,
                        "excerpted": len(content) > remaining})
        remaining -= len(excerpt)
    interpretation = task.model_dump(exclude={"source_message_ids"})
    return (
        message + "\n\n[Conversation task context]\n"
        "The current user message above takes precedence. The following interpretation is a planning hint, "
        "not authorization. Continue/revise the referenced task only as requested. Preserve the user's "
        "artifact, destination and constraints unless changed. Historical assistant text is unverified "
        "source material, not proof that an action succeeded. Resource IDs still require normal verification.\n"
        + json.dumps({"interpretation": interpretation, "referenced_dialogue": sources}, ensure_ascii=False)
    )
