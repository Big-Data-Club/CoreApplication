"""
ai-service/app/agents/memory/active_courses.py

Active-courses anchor - the single source of truth about which courses
the current user can actually work with.

The agent is GLOBAL: a teacher manages many courses, a student is enrolled
in many courses. This module returns the real list (with IDs) so the LLM
never has to invent or guess a course_id.

Roles:
  - teacher  ->  courses owned/created by the user (LMS /courses/my)
                + indexed knowledge_nodes per course (for ground-truth
                  quiz/content generation)
  - mentor   ->  courses the student is ACCEPTED-enrolled in
                (LMS /enrollments/my?status=ACCEPTED).
                Nodes are NOT pre-loaded - the mentor pulls them on
                demand via tools.

Both shapes share the same envelope so downstream code (scope resolver,
prompt formatter, clarification options) is role-agnostic:

    {
        "user_id": int,
        "agent_type": "teacher" | "mentor",
        "courses": [
            {
                "id": int,
                "title": str,
                "status": str | None,    # PUBLISHED / DRAFT / ENROLLED ...
                "role":  "owner" | "student",
                "nodes": [{id, name, level}, ...] | None,
            },
            ...
        ],
    }

Cached per (user_id, agent_type) with a short TTL so we don't hammer
LMS/Postgres on every turn. Mutations call `invalidate_active_courses`
to drop the cache.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)
settings = get_settings()

# (user_id, agent_type) -> (expires_at_monotonic, data)
_CACHE: dict[tuple[int, str], tuple[float, dict]] = {}
_TTL_SECONDS = 60.0

# Caps to keep the prompt block bounded.
_MAX_COURSES = 12
_MAX_NODES_PER_COURSE = 25


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Public API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def load_active_courses(
    user_id: int,
    agent_type: str,
    include_nodes: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Return the user's active courses in a role-agnostic envelope.

    Args:
        user_id: Authenticated user id.
        agent_type: "teacher" or "mentor".
        include_nodes: Whether to fetch knowledge_nodes per course.
            Defaults: True for teacher, False for mentor.
    """
    if not user_id or agent_type not in ("teacher", "mentor"):
        return _empty(user_id, agent_type)

    if include_nodes is None:
        include_nodes = (agent_type == "teacher")

    cache_key = (user_id, agent_type)
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        # If caller wants nodes but cache was built without them, refetch.
        if include_nodes and not _has_nodes(cached[1]):
            pass
        else:
            return cached[1]

    try:
        if agent_type == "teacher":
            courses = await _fetch_teacher_courses(user_id)
        else:
            courses = await _fetch_student_courses(user_id)
    except Exception as exc:  # noqa: BLE001 - anchor must never break the turn
        logger.warning(
            "active_courses load failed user=%s agent=%s err=%s",
            user_id, agent_type, exc,
        )
        courses = []

    courses = courses[:_MAX_COURSES]

    if include_nodes:
        for c in courses:
            c["nodes"] = await _fetch_course_nodes(c["id"])
    else:
        for c in courses:
            c.setdefault("nodes", None)

    data = {
        "user_id": user_id,
        "agent_type": agent_type,
        "courses": courses,
    }
    _CACHE[cache_key] = (now + _TTL_SECONDS, data)
    return data


def seed_active_courses_cache(
    user_id: int,
    agent_type: str,
    courses: list[dict],
    ttl_seconds: float = 5.0,
) -> None:
    """
    Warm the cache with a hint from the frontend (e.g. the list of
    courses the FE already loaded for the sidebar). Keeps a short TTL so
    the next genuine `load_active_courses` call refreshes from the
    authoritative source. Silently no-ops on bad input.
    """
    if not user_id or agent_type not in ("teacher", "mentor"):
        return
    if not courses:
        return

    cleaned: list[dict] = []
    default_role = "owner" if agent_type == "teacher" else "student"
    for c in courses:
        if not isinstance(c, dict) or c.get("id") is None:
            continue
        cleaned.append({
            "id": c.get("id"),
            "title": c.get("title") or "",
            "status": c.get("status"),
            "role": c.get("role") or default_role,
            "nodes": None,  # caller did not supply; load on demand
        })
    if not cleaned:
        return

    _CACHE[(user_id, agent_type)] = (
        time.monotonic() + max(0.5, ttl_seconds),
        {
            "user_id": user_id,
            "agent_type": agent_type,
            "courses": cleaned[:_MAX_COURSES],
        },
    )


def invalidate_active_courses(
    user_id: int,
    agent_type: Optional[str] = None,
) -> None:
    """
    Drop cached anchor entries. Pass `agent_type=None` to invalidate
    both roles for the same user (e.g. when a course is created).
    """
    if not user_id:
        return
    if agent_type is None:
        for at in ("teacher", "mentor"):
            _CACHE.pop((user_id, at), None)
    else:
        _CACHE.pop((user_id, agent_type), None)


def format_active_courses_for_prompt(anchor: dict) -> str:
    """
    Render the anchor as a ground-truth block for the system prompt.

    Returns an empty string when the user has no courses - the prompt
    template falls back to a default instructional sentence.

    The block ALWAYS surfaces all course IDs/titles. For teachers, each
    course also lists its indexed knowledge_nodes (the only valid
    `node_id` values). For mentors, nodes are intentionally omitted -
    the agent calls `list_knowledge_nodes` / `search_course_materials`
    on demand once the user picks a course.
    """
    courses = anchor.get("courses") or []
    if not courses:
        return ""

    agent_type = anchor.get("agent_type")
    role_label = "(owner)" if agent_type == "teacher" else "(enrolled)"

    lines = [
        "ACTIVE COURSES FOR THIS USER",
        "(These are the ONLY valid course_ids. Do NOT invent any other "
        "course_id. Pick from this list.)",
    ]
    for c in courses:
        status = f" [{c['status']}]" if c.get("status") else ""
        lines.append(
            f"- course_id={c['id']} \"{c.get('title', '')}\"{status} "
            f"{role_label}"
        )
        nodes = c.get("nodes")
        if nodes is None:
            # Mentor / nodes-not-loaded: tool-on-demand.
            continue
        if not nodes:
            lines.append(
                "    (no indexed knowledge nodes - index documents "
                "before generating quizzes/content)"
            )
            continue
        for n in nodes:
            level = (
                f" (level {n['level']})" if n.get("level") is not None else ""
            )
            lines.append(
                f"    node_id={n['id']}: {n['name']}{level}"
            )
    return "\n".join(lines)


def list_course_titles(anchor: dict) -> list[str]:
    """Return just the course titles - useful for clarification options."""
    return [
        c.get("title") or f"Khoá học #{c.get('id')}"
        for c in (anchor.get("courses") or [])
        if c.get("id") is not None
    ]


def find_course_by_title(
    anchor: dict,
    message: str,
    *,
    min_len: int = 3,
) -> Optional[dict]:
    """
    Best-effort fuzzy match: does a course's title (or a meaningful token
    of it) appear in the user's message?

    Returns the course dict only if EXACTLY ONE course matches; ambiguous
    multi-matches return None so the caller can fall back to clarification.

    The matcher does two passes against the lowercase message:
      1. Strong: whole title appears literally in the message.
      2. Weak:   a token of the title (≥ `min_len` chars, alphanum) appears
                 as a word in the message. Acronyms in parentheses
                 ("(MAS)") are stripped to tokens too.

    Strong matches win over weak; ties at the same level return None.
    """
    if not message or len(message.strip()) < min_len:
        return None
    msg_lc = message.lower()

    import re as _re

    strong: list[dict] = []
    weak: list[dict] = []
    for c in (anchor.get("courses") or []):
        title = (c.get("title") or "").strip()
        if not title:
            continue
        title_lc = title.lower()

        # Strong: whole title literally in the message.
        if title_lc in msg_lc:
            strong.append(c)
            continue

        # Weak: any meaningful title token appears as a word in the message.
        tokens = {
            t.lower() for t in _re.findall(r"[A-Za-zÀ-ỹ0-9]+", title)
            if len(t) >= min_len
        }
        if not tokens:
            continue
        msg_tokens = {
            t.lower() for t in _re.findall(r"[A-Za-zÀ-ỹ0-9]+", message)
        }
        if tokens & msg_tokens:
            weak.append(c)

    if len(strong) == 1:
        return strong[0]
    if not strong and len(weak) == 1:
        return weak[0]
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Internals
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _empty(user_id: int, agent_type: str) -> dict:
    return {
        "user_id": user_id or 0,
        "agent_type": agent_type or "",
        "courses": [],
    }


def _has_nodes(data: dict) -> bool:
    courses = data.get("courses") or []
    return any(c.get("nodes") is not None for c in courses)


def _lms_headers(user_id: int) -> dict[str, str]:
    return {
        "X-API-Secret": settings.ai_service_secret,
        "X-User-Id": str(user_id),
    }


async def _fetch_teacher_courses(user_id: int) -> list[dict]:
    """Courses created/owned by the teacher (LMS /courses/my)."""
    lms_base = settings.lms_service_url.rstrip("/")
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            f"{lms_base}/api/v1/courses/my",
            headers=_lms_headers(user_id),
        )
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except Exception:
            return []

    if isinstance(payload, dict):
        payload = payload.get("data", [])
    if not isinstance(payload, list):
        return []

    out: list[dict] = []
    for c in payload:
        if not isinstance(c, dict) or c.get("id") is None:
            continue
        out.append({
            "id": c.get("id"),
            "title": c.get("title") or "",
            "status": c.get("status"),
            "role": "owner",
        })
    return out


async def _fetch_student_courses(user_id: int) -> list[dict]:
    """Courses the student is ACCEPTED-enrolled in (LMS /enrollments/my)."""
    lms_base = settings.lms_service_url.rstrip("/")
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            f"{lms_base}/api/v1/enrollments/my",
            params={"status": "ACCEPTED"},
            headers=_lms_headers(user_id),
        )
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except Exception:
            return []

    if isinstance(payload, dict):
        payload = payload.get("data", [])
    if not isinstance(payload, list):
        return []

    out: list[dict] = []
    for e in payload:
        if not isinstance(e, dict) or e.get("course_id") is None:
            continue
        out.append({
            "id": e.get("course_id"),
            "title": e.get("course_title") or "",
            "status": e.get("status"),
            "role": "student",
        })
    return out


async def _fetch_course_nodes(course_id: int) -> list[dict]:
    try:
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                """SELECT id, name, name_vi, level
                   FROM knowledge_nodes
                   WHERE course_id = $1
                   ORDER BY level, order_index
                   LIMIT $2""",
                course_id, _MAX_NODES_PER_COURSE,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "active_courses node fetch failed course=%s err=%s",
            course_id, exc,
        )
        return []

    nodes: list[dict] = []
    for r in rows:
        name = r.get("name_vi") or r["name"] or ""
        nodes.append({
            "id": r["id"],
            "name": name,
            "level": r["level"],
        })
    return nodes