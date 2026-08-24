"""
ai-service/app/agents/core/learner_context.py

Deterministic learner snapshot for the Mentor agent.

Instead of hoping the LLM will call get_study_plan / diagnose_knowledge_gap
on its own (small models often will not), we fetch the few facts that make
the agent feel like it *knows* the student - due reviews, weakest concepts,
strongest concepts - and hand them to the prompt as verified ground truth.
The model then only has to phrase the advice, not orchestrate tools.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Surfaces where proactive personalization helps instead of distracts.
PROACTIVE_PAGE_TYPES = {"dashboard", "home", "index", "landing", "course_list", ""}


def should_inject_learner_snapshot(
    *,
    agent_type: str,
    personalization_enabled: bool,
    lakehouse_required: bool,
    page_type: str | None,
) -> bool:
    if agent_type != "mentor":
        return False
    return bool(
        personalization_enabled
        or lakehouse_required
        or (page_type or "").lower() in PROACTIVE_PAGE_TYPES
    )


async def fetch_learner_snapshot(user_id: int) -> dict[str, Any]:
    """Best-effort cross-course snapshot; every failure degrades to empty."""
    snap: dict[str, Any] = {"due_count": 0, "due_topics": [], "weak": [], "strong": []}
    try:
        from app.core.database import get_ai_conn

        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """
                SELECT kn.name AS node_name
                FROM flashcard_repetitions fcr
                JOIN flashcards fc ON fcr.flashcard_id = fc.id
                JOIN knowledge_nodes kn ON fc.node_id = kn.id
                WHERE fcr.student_id = $1 AND fcr.next_review_date <= NOW()
                ORDER BY fcr.next_review_date ASC
                LIMIT 20
                """,
                user_id,
            )
        topics: list[str] = []
        for r in rows:
            name = r["node_name"]
            if name and name not in topics:
                topics.append(name)
        snap["due_count"] = len(rows)
        snap["due_topics"] = topics[:4]
    except Exception as exc:
        logger.debug("learner snapshot: due reviews unavailable: %s", exc)

    try:
        from app.services.mastery_service import mastery_service

        def _label(row: dict) -> str:
            return str(row.get("name_vi") or row.get("name") or "").strip()

        weaknesses = [
            dict(w) if isinstance(w, dict) else dict(w._mapping)
            for w in (await mastery_service.get_user_struggles(user_id=user_id)) or []
        ]
        snap["weak"] = [
            {
                "name": label,
                "mastery": round(float(w.get("mastery_level") or 0.0), 2),
            }
            for w in weaknesses[:3]
            if (label := _label(w))
        ]

        strengths = [
            dict(s) if isinstance(s, dict) else dict(s._mapping)
            for s in (await mastery_service.get_user_strengths(user_id=user_id)) or []
        ]
        snap["strong"] = [lbl for s in strengths[:2] if (lbl := _label(s))]
    except Exception as exc:
        logger.debug("learner snapshot: mastery unavailable: %s", exc)

    return snap


def format_learner_snapshot(snap: dict[str, Any]) -> str:
    """Compact ground-truth block (~<900 chars) or a no-op marker."""
    parts: list[str] = ["VERIFIED LEARNER FACTS (from the platform database - treat as true):"]

    if snap.get("due_count"):
        topics = ", ".join(snap.get("due_topics") or [])
        line = f"- Spaced review: {snap['due_count']} flashcard(s) are DUE now"
        if topics:
            line += f" - mainly: {topics}"
        parts.append(line + ".")

    weak = snap.get("weak") or []
    if weak:
        rendered = ", ".join(
            f"{w['name']} (mastery {w['mastery']:.0%})" for w in weak
        )
        parts.append(f"- Weakest concepts: {rendered}.")

    strong = snap.get("strong") or []
    if strong:
        parts.append(f"- Confident concepts: {', '.join(strong)}.")

    if len(parts) == 1:
        parts.append(
            "- No mastery/review data yet (new or inactive student). Do not "
            "invent weaknesses; ask about goals or suggest exploring courses."
        )

    parts.append(
        "Use these facts proactively when relevant, but do NOT dump them "
        "raw - weave them into natural advice."
    )
    return "\n".join(parts)
