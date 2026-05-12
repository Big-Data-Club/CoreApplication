"""
ai-service/app/agents/memory/personalize_memory.py

Personalize Memory — user-specific learning profile.

Extracts the student's learning state from existing AI database tables:
  - student_knowledge_progress: mastery levels per knowledge node
  - spaced_repetitions: items due for review
  - ai_diagnoses: recent error patterns and misconceptions
  - flashcards: active flashcard sets

This data lets the agent personalise its responses:
  - Struggling student → simpler explanations, more hints
  - Strong student → challenging extensions, deeper questions
  - Teacher → class-wide analytics, at-risk students
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)


class PersonalizeMemory:
    """User-specific learning profile from AI database tables."""

    async def get_user_profile(
        self,
        user_id: int,
        course_id: Optional[int] = None,
    ) -> dict:
        """
        Get a comprehensive learning profile for a student.

        Combines weakness, strengths, due reviews, and recent errors
        into a single profile dict suitable for prompt injection.
        """
        weaknesses = await self.get_weaknesses(user_id, course_id)
        strengths = await self.get_strengths(user_id, course_id)
        due_reviews = await self.get_due_reviews(user_id, course_id)
        recent_errors = await self.get_recent_errors(user_id, course_id, limit=5)

        return {
            "weaknesses": weaknesses,
            "strengths": strengths,
            "due_reviews": due_reviews,
            "recent_errors": recent_errors,
            "summary": self._build_summary(
                weaknesses, strengths, due_reviews, recent_errors,
            ),
        }

    async def get_weaknesses(
        self,
        user_id: int,
        course_id: Optional[int] = None,
        threshold: float = 0.5,
        limit: int = 5,
    ) -> list[dict]:
        """Get knowledge nodes where the student is struggling."""
        try:
            async with get_ai_conn() as conn:
                if course_id:
                    rows = await conn.fetch(
                        """SELECT kn.id AS node_id, kn.name, kn.name_vi,
                                  skp.mastery_level, skp.wrong_count,
                                  skp.total_attempts, skp.last_tested_at
                           FROM student_knowledge_progress skp
                           JOIN knowledge_nodes kn ON kn.id = skp.node_id
                           WHERE skp.student_id = $1
                             AND skp.course_id = $2
                             AND skp.mastery_level < $3
                           ORDER BY skp.mastery_level ASC
                           LIMIT $4""",
                        user_id, course_id, threshold, limit,
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT kn.id AS node_id, kn.name, kn.name_vi,
                                  skp.mastery_level, skp.wrong_count,
                                  skp.total_attempts, skp.last_tested_at,
                                  skp.course_id
                           FROM student_knowledge_progress skp
                           JOIN knowledge_nodes kn ON kn.id = skp.node_id
                           WHERE skp.student_id = $1
                             AND skp.mastery_level < $2
                           ORDER BY skp.mastery_level ASC
                           LIMIT $3""",
                        user_id, threshold, limit,
                    )
            return [
                {
                    "node_id": r["node_id"],
                    "name": r["name"],
                    "name_vi": r.get("name_vi"),
                    "mastery_level": round(float(r["mastery_level"]), 2),
                    "wrong_count": r["wrong_count"],
                    "total_attempts": r["total_attempts"],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("Failed to get user weaknesses: %s", exc)
            return []

    async def get_strengths(
        self,
        user_id: int,
        course_id: Optional[int] = None,
        threshold: float = 0.8,
        limit: int = 5,
    ) -> list[dict]:
        """Get knowledge nodes where the student excels."""
        try:
            async with get_ai_conn() as conn:
                if course_id:
                    rows = await conn.fetch(
                        """SELECT kn.id AS node_id, kn.name, kn.name_vi,
                                  skp.mastery_level, skp.correct_count
                           FROM student_knowledge_progress skp
                           JOIN knowledge_nodes kn ON kn.id = skp.node_id
                           WHERE skp.student_id = $1
                             AND skp.course_id = $2
                             AND skp.mastery_level >= $3
                           ORDER BY skp.mastery_level DESC
                           LIMIT $4""",
                        user_id, course_id, threshold, limit,
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT kn.id AS node_id, kn.name, kn.name_vi,
                                  skp.mastery_level, skp.correct_count
                           FROM student_knowledge_progress skp
                           JOIN knowledge_nodes kn ON kn.id = skp.node_id
                           WHERE skp.student_id = $1
                             AND skp.mastery_level >= $2
                           ORDER BY skp.mastery_level DESC
                           LIMIT $3""",
                        user_id, threshold, limit,
                    )
            return [
                {
                    "node_id": r["node_id"],
                    "name": r["name"],
                    "name_vi": r.get("name_vi"),
                    "mastery_level": round(float(r["mastery_level"]), 2),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("Failed to get user strengths: %s", exc)
            return []

    async def get_due_reviews(
        self,
        user_id: int,
        course_id: Optional[int] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Get spaced repetition items due for review today."""
        try:
            async with get_ai_conn() as conn:
                if course_id:
                    rows = await conn.fetch(
                        """SELECT sr.question_id, sr.node_id,
                                  kn.name AS node_name,
                                  sr.next_review_date, sr.interval_days,
                                  sr.easiness_factor
                           FROM spaced_repetitions sr
                           LEFT JOIN knowledge_nodes kn ON kn.id = sr.node_id
                           WHERE sr.student_id = $1
                             AND sr.course_id = $2
                             AND sr.next_review_date <= CURRENT_DATE
                           ORDER BY sr.next_review_date ASC
                           LIMIT $3""",
                        user_id, course_id, limit,
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT sr.question_id, sr.node_id,
                                  kn.name AS node_name,
                                  sr.next_review_date, sr.interval_days,
                                  sr.course_id
                           FROM spaced_repetitions sr
                           LEFT JOIN knowledge_nodes kn ON kn.id = sr.node_id
                           WHERE sr.student_id = $1
                             AND sr.next_review_date <= CURRENT_DATE
                           ORDER BY sr.next_review_date ASC
                           LIMIT $2""",
                        user_id, limit,
                    )
            return [
                {
                    "question_id": r["question_id"],
                    "node_id": r["node_id"],
                    "node_name": r.get("node_name", ""),
                    "next_review_date": str(r["next_review_date"]),
                    "interval_days": r["interval_days"],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("Failed to get due reviews: %s", exc)
            return []

    async def get_recent_errors(
        self,
        user_id: int,
        course_id: Optional[int] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Get recent diagnosis results to understand error patterns."""
        try:
            async with get_ai_conn() as conn:
                if course_id:
                    rows = await conn.fetch(
                        """SELECT ad.gap_type, ad.knowledge_gap,
                                  ad.study_suggestion, ad.confidence,
                                  kn.name AS node_name,
                                  ad.created_at
                           FROM ai_diagnoses ad
                           LEFT JOIN knowledge_nodes kn ON kn.id = ad.node_id
                           WHERE ad.student_id = $1 AND kn.course_id = $2
                           ORDER BY ad.created_at DESC
                           LIMIT $3""",
                        user_id, course_id, limit,
                    )
                else:
                    rows = await conn.fetch(
                        """SELECT ad.gap_type, ad.knowledge_gap,
                                  ad.study_suggestion, ad.confidence,
                                  kn.name AS node_name,
                                  ad.created_at
                           FROM ai_diagnoses ad
                           LEFT JOIN knowledge_nodes kn ON kn.id = ad.node_id
                           WHERE ad.student_id = $1
                           ORDER BY ad.created_at DESC
                           LIMIT $2""",
                        user_id, limit,
                    )
            return [
                {
                    "gap_type": r["gap_type"],
                    "knowledge_gap": r["knowledge_gap"],
                    "study_suggestion": r["study_suggestion"],
                    "node_name": r.get("node_name", ""),
                    "confidence": round(float(r["confidence"]), 2)
                        if r["confidence"] else 0,
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("Failed to get recent errors: %s", exc)
            return []

    async def get_unstudied_topics(
        self,
        user_id: int,
        course_id: int,
        limit: int = 3,
    ) -> list[dict]:
        """Get knowledge nodes that the student hasn't started yet, ordered by curriculum flow."""
        try:
            async with get_ai_conn() as conn:
                rows = await conn.fetch(
                    """SELECT id AS node_id, name, name_vi
                       FROM knowledge_nodes
                       WHERE course_id = $1
                         AND id NOT IN (
                             SELECT node_id FROM student_knowledge_progress WHERE student_id = $2
                         )
                       ORDER BY level ASC, order_index ASC
                       LIMIT $3""",
                    course_id, user_id, limit,
                )
            return [
                {
                    "node_id": r["node_id"],
                    "name": r["name"],
                    "name_vi": r.get("name_vi"),
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("Failed to get unstudied topics: %s", exc)
            return []

    async def get_class_overview(
        self,
        course_id: int,
        limit: int = 10,
    ) -> dict:
        """
        Get class-wide performance overview (for teacher agent).

        Aggregates across all students in a course.
        """
        try:
            async with get_ai_conn() as conn:
                # Average mastery per node
                node_stats = await conn.fetch(
                    """SELECT kn.name, kn.name_vi,
                              AVG(skp.mastery_level) AS avg_mastery,
                              COUNT(DISTINCT skp.student_id) AS student_count,
                              SUM(skp.wrong_count) AS total_errors
                       FROM student_knowledge_progress skp
                       JOIN knowledge_nodes kn ON kn.id = skp.node_id
                       WHERE skp.course_id = $1
                       GROUP BY kn.id, kn.name, kn.name_vi
                       ORDER BY avg_mastery ASC
                       LIMIT $2""",
                    course_id, limit,
                )

                # Total students with progress
                total = await conn.fetchrow(
                    """SELECT COUNT(DISTINCT student_id) AS count
                       FROM student_knowledge_progress
                       WHERE course_id = $1""",
                    course_id,
                )

            return {
                "course_id": course_id,
                "total_students": total["count"] if total else 0,
                "weakest_topics": [
                    {
                        "name": r["name"],
                        "name_vi": r.get("name_vi"),
                        "avg_mastery": round(float(r["avg_mastery"]), 2),
                        "student_count": r["student_count"],
                        "total_errors": r["total_errors"],
                    }
                    for r in node_stats
                ],
            }
        except Exception as exc:
            logger.error("Failed to get class overview: %s", exc)
            return {"course_id": course_id, "error": str(exc)}

    @staticmethod
    def _build_summary(
        weaknesses: list, strengths: list,
        due_reviews: list, recent_errors: list,
    ) -> str:
        """Build a human-readable summary for prompt injection."""
        parts = []

        if weaknesses:
            weak_names = [w["name"] for w in weaknesses[:3]]
            parts.append(f"Weak areas: {', '.join(weak_names)}")

        if strengths:
            strong_names = [s["name"] for s in strengths[:3]]
            parts.append(f"Strong areas: {', '.join(strong_names)}")

        if due_reviews:
            parts.append(f"{len(due_reviews)} items due for review")

        if recent_errors:
            gap_types = set(e["gap_type"] for e in recent_errors if e.get("gap_type"))
            if gap_types:
                parts.append(f"Common error types: {', '.join(gap_types)}")

        return "; ".join(parts) if parts else "No learning data available yet."


# Singleton
personalize_memory = PersonalizeMemory()
