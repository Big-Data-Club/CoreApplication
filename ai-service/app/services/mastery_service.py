from __future__ import annotations

import logging
from typing import Optional

from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)


class MasteryService:

    async def get_user_struggles(self, user_id: int, course_id: Optional[int] = None) -> list[dict]:
        """
        Return concepts where struggles = TRUE for the user in a course or globally.
        """
        async with get_ai_conn() as conn:
            if course_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT ucm.concept_id, kn.name, kn.name_vi, ucm.mastery_level, ucm.struggles
                    FROM user_concept_mastery ucm
                    JOIN knowledge_nodes kn ON ucm.concept_id = kn.id
                    WHERE ucm.user_id = $1 AND kn.course_id = $2 AND ucm.struggles = TRUE
                    ORDER BY ucm.mastery_level ASC, ucm.last_interaction DESC
                    """,
                    user_id,
                    course_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ucm.concept_id, kn.name, kn.name_vi, ucm.mastery_level, ucm.struggles
                    FROM user_concept_mastery ucm
                    JOIN knowledge_nodes kn ON ucm.concept_id = kn.id
                    WHERE ucm.user_id = $1 AND ucm.struggles = TRUE
                    ORDER BY ucm.mastery_level ASC, ucm.last_interaction DESC
                    """,
                    user_id,
                )
        return [dict(r) for r in rows]

    async def get_user_strengths(self, user_id: int, course_id: Optional[int] = None) -> list[dict]:
        """
        Return concepts with mastery_level >= 0.8 for the user in a course or globally.
        """
        async with get_ai_conn() as conn:
            if course_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT ucm.concept_id, kn.name, kn.name_vi, ucm.mastery_level, ucm.struggles
                    FROM user_concept_mastery ucm
                    JOIN knowledge_nodes kn ON ucm.concept_id = kn.id
                    WHERE ucm.user_id = $1 AND kn.course_id = $2 AND ucm.mastery_level >= 0.8
                    ORDER BY ucm.mastery_level DESC, ucm.last_interaction DESC
                    """,
                    user_id,
                    course_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ucm.concept_id, kn.name, kn.name_vi, ucm.mastery_level, ucm.struggles
                    FROM user_concept_mastery ucm
                    JOIN knowledge_nodes kn ON ucm.concept_id = kn.id
                    WHERE ucm.user_id = $1 AND ucm.mastery_level >= 0.8
                    ORDER BY ucm.mastery_level DESC, ucm.last_interaction DESC
                    """,
                    user_id,
                )
        return [dict(r) for r in rows]

    async def get_user_concept_mastery_list(self, user_id: int, course_id: Optional[int] = None) -> list[dict]:
        """
        Return all concept mastery records for a user in a course or globally.
        """
        async with get_ai_conn() as conn:
            if course_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT ucm.concept_id, kn.name, kn.name_vi, ucm.mastery_level, ucm.struggles, ucm.last_interaction
                    FROM user_concept_mastery ucm
                    JOIN knowledge_nodes kn ON ucm.concept_id = kn.id
                    WHERE ucm.user_id = $1 AND kn.course_id = $2
                    ORDER BY ucm.last_interaction DESC
                    """,
                    user_id,
                    course_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ucm.concept_id, kn.name, kn.name_vi, ucm.mastery_level, ucm.struggles, ucm.last_interaction
                    FROM user_concept_mastery ucm
                    JOIN knowledge_nodes kn ON ucm.concept_id = kn.id
                    WHERE ucm.user_id = $1
                    ORDER BY ucm.last_interaction DESC
                    """,
                    user_id,
                )
        return [dict(r) for r in rows]

    async def update_mastery(
        self, user_id: int, concept_id: int, delta: float, struggles: bool
    ) -> None:
        """
        Upsert user mastery data for a concept.
        Clamps mastery level between 0.0 and 1.0.
        """
        async with get_ai_conn() as conn:
            await conn.execute(
                """
                INSERT INTO user_concept_mastery (
                    user_id, concept_id, mastery_level, struggles, interaction_count, last_interaction
                )
                VALUES ($1, $2, LEAST(GREATEST($3, 0.0), 1.0), $4, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, concept_id) DO UPDATE SET
                    mastery_level = LEAST(GREATEST(user_concept_mastery.mastery_level + EXCLUDED.mastery_level, 0.0), 1.0),
                    struggles = EXCLUDED.struggles,
                    interaction_count = user_concept_mastery.interaction_count + 1,
                    last_interaction = CURRENT_TIMESTAMP
                """,
                user_id,
                concept_id,
                delta,
                struggles,
            )
        logger.info(
            "Updated user concept mastery: user=%d, concept=%d, delta=%.2f, struggles=%s",
            user_id,
            concept_id,
            delta,
            struggles,
        )

    async def sync_duckdb_personalization_profile(self, user_id: int, course_id: int, profile: dict) -> None:
        """
        Synchronizes the DuckDB calculated personalization profile with the Postgres AI database.
        Sets concept struggles and writes learning progress summary facts.
        """
        struggle_nodes = profile.get("struggle_nodes", [])
        
        async with get_ai_conn() as conn:
            # 1. Update concept struggles flags in user_concept_mastery
            rows = await conn.fetch("SELECT id FROM knowledge_nodes WHERE course_id = $1", course_id)
            all_node_ids = [r["id"] for r in rows]
            
            for node_id in all_node_ids:
                is_struggling = node_id in struggle_nodes
                # Upsert struggles and update last interaction
                await conn.execute(
                    """
                    INSERT INTO user_concept_mastery (
                        user_id, concept_id, mastery_level, struggles, interaction_count, last_interaction
                    )
                    VALUES ($1, $2, $3, $4, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, concept_id) DO UPDATE SET
                        struggles = EXCLUDED.struggles,
                        last_interaction = CURRENT_TIMESTAMP
                    """,
                    user_id, node_id, 0.3 if is_struggling else 0.7, is_struggling
                )
                
            # 2. Update general student learning progress in student_facts
            completed_count = profile.get("completed_lessons", 0)
            attempted_count = profile.get("attempted_lessons", 0)
            accuracy = profile.get("check_accuracy", 0.0)
            
            fact_text = f"Đã hoàn thành {completed_count}/{attempted_count} bài học, độ chính xác quick check {accuracy * 100}%."
            
            existing_fact = await conn.fetchrow(
                "SELECT id FROM student_facts WHERE user_id = $1 AND course_id = $2 AND category = 'progress'",
                user_id, course_id
            )
            if existing_fact:
                await conn.execute(
                    "UPDATE student_facts SET fact = $1, updated_at = NOW() WHERE id = $2",
                    fact_text, existing_fact["id"]
                )
            else:
                await conn.execute(
                    "INSERT INTO student_facts (user_id, fact, category, course_id) VALUES ($1, $2, 'progress', $3)",
                    user_id, fact_text, course_id
                )
            logger.info(f"Synced personalization profile in Postgres for user={user_id} course={course_id}")


mastery_service = MasteryService()
