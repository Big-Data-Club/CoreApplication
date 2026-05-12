"""
ai-service/app/agents/memory/context_builder.py

ContextBuilder — the central orchestrator for the 5-tier memory system.

This is the ONLY entry point that the ReAct loop uses to get context.
It assembles information from all 5 memory tiers with intelligent
weighting based on the query's intent.

The key insight: NOT all memories are useful for every query.
Fetching everything wastes tokens and dilutes relevance.

Intent-based weighting:
  Type A (knowledge Q)  : System(1.0) + STM(0.9) + Personalize(0.5) + MTM(0.3)
  Type B (progress)     : Personalize(1.0) + MTM(0.7) + LTM(0.8) + STM(0.5)
  Type C (create content): System(1.0) + STM(0.9) + MTM(0.7)
  Type D (general chat)  : STM(0.9) + MTM(0.3)
  Type E (exercise)      : System(0.8) + Personalize(0.9) + STM(0.7)

Weight semantics:
  >= 0.7  : Full retrieval (all available data)
  0.3-0.7 : Summary-only retrieval (condensed)
  < 0.3   : Skip entirely (save tokens)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.agents.memory.stm import stm
from app.agents.memory.mtm import mtm
from app.agents.memory.ltm import ltm
from app.agents.memory.personalize_memory import personalize_memory

logger = logging.getLogger(__name__)

# Weight profiles per intent type
WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "knowledge_question": {
        "stm": 0.9,
        "mtm": 0.5,
        "ltm": 0.5,
        "system": 0.0,
        "personalize": 0.6,
    },
    "progress_advice": {
        "stm": 0.6,
        "mtm": 0.8,
        "ltm": 0.8,
        "system": 0.0,
        "personalize": 1.0,
    },
    "content_creation": {
        "stm": 0.9,
        "mtm": 0.8,
        "ltm": 0.4,
        "system": 0.0,
        "personalize": 0.4,
    },
    "general_chat": {
        "stm": 0.9,
        "mtm": 0.5,
        "ltm": 0.2,
        "system": 0.0,
        "personalize": 0.3,
    },
    "interactive_exercise": {
        "stm": 0.8,
        "mtm": 0.5,
        "ltm": 0.4,
        "system": 0.0,
        "personalize": 0.9,
    },
}

# Default weights if intent is unknown
DEFAULT_WEIGHTS: dict[str, float] = {
    "stm": 0.8,
    "mtm": 0.5,
    "ltm": 0.3,
    "system": 0.0,
    "personalize": 0.5,
}

# Token budget allocation (approximate)
MAX_CONTEXT_TOKENS = 4000
TOKEN_BUDGET: dict[str, int] = {
    "stm": 2000,
    "mtm": 800,
    "ltm": 600,
    "system": 0,
    "personalize": 600,
}


class ContextBuilder:
    """
    Assembles weighted context from the 5-tier memory system.

    Usage:
        builder = ContextBuilder()
        context = await builder.build(
            user_id=1, session_id="abc", agent_type="mentor",
            query="What is polymorphism?", course_id=1,
            intent_type="knowledge_question",
        )
        # context["prompt_section"] -> string ready for system prompt injection
        # context["raw"] -> dict with all raw data from each tier
    """

    async def build(
        self,
        user_id: int,
        session_id: str,
        agent_type: str,
        query: str,
        course_id: Optional[int] = None,
        intent_type: str = "general_chat",
        scope_course_ids: Optional[list[int]] = None,
    ) -> dict[str, Any]:
        """
        Build a context dict from all 5 memory tiers.

        Args:
            scope_course_ids: When the scope resolver picks "multi" or "all",
                pass the candidate course_ids so cross-course tiers (LTM,
                Personalize summary) can union across them rather than
                being forced to a single course. Ignored for single-course
                turns (use `course_id` instead).

        Returns:
            {
                "prompt_section": str,    # formatted for system prompt injection
                "stm_messages": list,     # raw STM messages for chat history
                "raw": {                  # raw data from each tier
                    "stm": {...},
                    "mtm": {...},
                    "ltm": {...},
                    "system": {...},
                    "personalize": {...},
                },
                "weights_used": dict,     # actual weights applied
                "token_estimate": int,    # approximate token usage
            }
        """
        weights = WEIGHT_PROFILES.get(intent_type, DEFAULT_WEIGHTS)

        raw: dict[str, Any] = {}
        sections: list[str] = []
        total_tokens = 0

        # ── 1. STM: Recent conversation history ──────────────────────────────
        stm_messages: list[dict] = []
        if weights["stm"] >= 0.3:
            n_turns = 30 if weights["stm"] >= 0.7 else 10
            stm_messages = await stm.get_window(session_id, n_turns=n_turns)
            raw["stm"] = {
                "message_count": len(stm_messages),
                "token_estimate": sum(
                    len(m.get("content", "") or "") // 4
                    for m in stm_messages
                ),
            }
            # STM is injected as chat history, not in the system prompt
            total_tokens += raw["stm"]["token_estimate"]

        # ── 2. MTM: Compressed session context ───────────────────────────────
        if weights["mtm"] >= 0.3:
            mtm_ctx = await mtm.get_context(session_id)
            raw["mtm"] = mtm_ctx
            if mtm_ctx and any(mtm_ctx.values()):
                mtm_section = self._format_mtm(mtm_ctx, weights["mtm"])
                if mtm_section:
                    sections.append(mtm_section)
                    total_tokens += len(mtm_section) // 4

        # ── 3. LTM: Past session episodes ────────────────────────────────────
        if weights["ltm"] >= 0.3 and query:
            # When the scope resolver locked onto a single course, restrict
            # episode recall to that course (plus untagged/cross-course
            # episodes). Otherwise let the recall span all courses.
            recall_course_ids: Optional[list[int]] = None
            if course_id is not None:
                recall_course_ids = [course_id]
            elif scope_course_ids:
                recall_course_ids = list(scope_course_ids)

            episodes = await ltm.recall(
                user_id=user_id,
                agent_type=agent_type,
                query=query,
                top_k=2 if weights["ltm"] >= 0.7 else 1,
                course_ids=recall_course_ids,
            )
            raw["ltm"] = {"episodes": episodes}
            if episodes:
                ltm_section = self._format_ltm(episodes)
                if ltm_section:
                    sections.append(ltm_section)
                    total_tokens += len(ltm_section) // 4

        # ── 4. System Memory: Course materials ───────────────────────────────
        # Deprecated: The agent now uses `search_course_materials` tool (Pull)
        # instead of automatic RAG injection (Push).
        raw["system"] = {}

        # ── 5. Personalize Memory: User learning profile ─────────────────────
        if weights["personalize"] >= 0.3:
            if agent_type == "teacher" and course_id:
                # Teacher gets class overview for the focused course.
                profile = await personalize_memory.get_class_overview(course_id)
                raw["personalize"] = profile
                if profile.get("weakest_topics"):
                    pers_section = self._format_class_overview(profile)
                    if pers_section:
                        sections.append(pers_section)
                        total_tokens += len(pers_section) // 4
            else:
                # Mentor (and unscoped teacher): pull the per-user profile.
                # When the scope is multi-course, we leave course_id empty so
                # the profile reflects the student's full learning surface.
                effective_course = course_id
                if scope_course_ids and len(scope_course_ids) > 1:
                    effective_course = None
                profile = await personalize_memory.get_user_profile(
                    user_id=user_id, course_id=effective_course,
                )
                raw["personalize"] = profile
                if profile.get("summary"):
                    pers_section = self._format_personalize(
                        profile, weights["personalize"],
                    )
                    if pers_section:
                        sections.append(pers_section)
                        total_tokens += len(pers_section) // 4

        # ── Assemble prompt section ──────────────────────────────────────────
        prompt_section = ""
        if sections:
            prompt_section = (
                "\n--- CONTEXT FROM MEMORY SYSTEM ---\n"
                + "\n\n".join(sections)
                + "\n--- END CONTEXT ---"
            )

        return {
            "prompt_section": prompt_section,
            "stm_messages": stm_messages,
            "raw": raw,
            "weights_used": weights,
            "token_estimate": total_tokens,
            "intent_type": intent_type,
        }

    # ── Formatting helpers ────────────────────────────────────────────────────

    @staticmethod
    def _format_mtm(ctx: dict, weight: float) -> str:
        """Format MTM compressed context for prompt injection."""
        parts = []

        ws = ctx.get("working_state") or {}
        kf = ctx.get("key_facts") or {}
        
        current_course_id = ws.get("current_course_id") or kf.get("current_course_id")
        current_node_id = ws.get("current_node_id") or kf.get("current_node_id")
        current_topic = ws.get("current_topic") or kf.get("current_topic")

        anchor_bits: list[str] = []
        if current_course_id is not None:
            anchor_bits.append(f"course_id={current_course_id}")
        if current_node_id is not None:
            anchor_bits.append(f"node_id={current_node_id}")
        if current_topic:
            anchor_bits.append(f"topic=\"{current_topic}\"")
        if anchor_bits:
            parts.append("CURRENT ANCHOR: " + ", ".join(anchor_bits))
            
        if ws.get("active_learning_goal"):
            parts.append(f"LEARNING GOAL: {ws['active_learning_goal']}")
            
        if ws.get("identified_knowledge_gaps"):
            parts.append(f"IDENTIFIED GAPS: {', '.join(ws['identified_knowledge_gaps'])}")
            
        if ws.get("notes"):
            parts.append(f"NOTES: {ws['notes']}")

        if ctx.get("identified_gaps"):
            gaps = ctx["identified_gaps"]
            if weight >= 0.7:
                parts.append(
                    "KNOWLEDGE GAPS IDENTIFIED: "
                    + ", ".join(str(g) for g in gaps[:8])
                )
            else:
                parts.append(f"Known gaps: {len(gaps)} concepts")

        if ctx.get("pending_actions"):
            actions = ctx["pending_actions"]
            parts.append("PENDING: " + "; ".join(str(a) for a in actions[:3]))

        if ctx.get("content_created"):
            created = ctx["content_created"]
            parts.append(
                "RECENTLY CREATED: " + ", ".join(str(c) for c in created[:5])
            )

        recent_courses = kf.get("recent_courses") if kf else None
        if isinstance(recent_courses, list) and recent_courses:
            # Each entry is {"id": int, "title": str}; we render compactly.
            tags = []
            for rc in recent_courses[:5]:
                if not isinstance(rc, dict):
                    continue
                cid = rc.get("id")
                title = (rc.get("title") or "").strip()
                if cid is None:
                    continue
                tags.append(
                    f"#{cid}" + (f" \"{title}\"" if title else "")
                )
            if tags:
                parts.append("RECENT COURSES: " + ", ".join(tags))

        if kf:
            remaining = {
                k: v for k, v in kf.items()
                if k not in ("current_topic", "recent_courses")
            }
            if remaining:
                fact_str = ", ".join(f"{k}={v}" for k, v in remaining.items())
                parts.append(f"KEY FACTS: {fact_str}")

        if ctx.get("decisions_made") and weight >= 0.5:
            decisions = ctx["decisions_made"]
            parts.append(
                "DECISIONS: " + "; ".join(str(d) for d in decisions[:3])
            )

        if ctx.get("student_progress"):
            sp = ctx["student_progress"]
            if isinstance(sp, dict) and sp:
                bits = []
                if sp.get("avg_mastery") is not None:
                    bits.append(f"mastery={sp['avg_mastery']}")
                if sp.get("notes"):
                    bits.append(str(sp["notes"])[:120])
                if bits:
                    parts.append("PROGRESS: " + ", ".join(bits))
 

        return "\n".join(parts) if parts else ""

    @staticmethod
    def _format_ltm(episodes: list[dict]) -> str:
        """Format LTM episodes for prompt injection."""
        if not episodes:
            return ""
        parts = ["PAST INTERACTIONS:"]
        for ep in episodes:
            summary = ep.get("summary", "")
            if len(summary) > 200:
                summary = summary[:200] + "..."
            parts.append(f"  - {summary} (relevance: {ep.get('score', 0)})")
        return "\n".join(parts)

    @staticmethod
    def _format_system(chunks: list[dict], weight: float) -> str:
        """Format system memory chunks for prompt injection."""
        if not chunks:
            return ""
        parts = ["RELEVANT COURSE MATERIALS:"]
        for i, c in enumerate(chunks):
            text = c.get("text", "")
            # Truncate based on weight
            max_len = 500 if weight >= 0.7 else 200
            if len(text) > max_len:
                text = text[:max_len] + "..."
            parts.append(f"  [{i+1}] {text}")
        return "\n".join(parts)

    @staticmethod
    def _format_personalize(profile: dict, weight: float) -> str:
        """Format personalize memory for prompt injection."""
        parts = ["STUDENT PROFILE:"]
        parts.append(f"  Summary: {profile.get('summary', 'No data')}")

        if weight >= 0.7:
            weaknesses = profile.get("weaknesses", [])
            if weaknesses:
                weak_str = ", ".join(
                    f"{w['name']} ({w['mastery_level']})"
                    for w in weaknesses[:3]
                )
                parts.append(f"  Weak concepts: {weak_str}")

            due = profile.get("due_reviews", [])
            if due:
                parts.append(f"  Reviews due: {len(due)} items")

            errors = profile.get("recent_errors", [])
            if errors:
                error_types = set(
                    e.get("gap_type", "unknown") for e in errors
                )
                parts.append(f"  Error patterns: {', '.join(error_types)}")

        return "\n".join(parts)

    @staticmethod
    def _format_class_overview(overview: dict) -> str:
        """Format class overview for teacher agent."""
        parts = [
            f"CLASS OVERVIEW ({overview.get('total_students', 0)} students):"
        ]
        for topic in overview.get("weakest_topics", [])[:5]:
            parts.append(
                f"  - {topic['name']}: avg mastery {topic['avg_mastery']}, "
                f"{topic['total_errors']} total errors"
            )
        return "\n".join(parts)


# Singleton
context_builder = ContextBuilder()
