"""
ai-service/app/agents/memory/context_builder.py

ContextBuilder - the central orchestrator for the simplified 3-tier memory system:
  1. STM (Short-term dialogue memory): Recent chat history
  2. LTM Episodic: Past session summaries retrieved from Qdrant
  3. LTM Facts: Student concept mastery / struggles / strengths retrieved from Postgres
     and scored dynamically using multi-signal scoring (semantic * recency * structural).
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.embeddings import create_embedding, create_embeddings_batch
from app.agents.memory.stm import stm
from app.agents.memory.mtm import mtm
from app.agents.memory.ltm import ltm
from app.services.mastery_service import mastery_service

logger = logging.getLogger(__name__)

# Intent-based weighting profiles for the 3 memory tiers
WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "knowledge_question": {
        "stm": 0.9,
        "ltm_episodic": 0.5,
        "ltm_facts": 0.6,
    },
    "progress_advice": {
        "stm": 0.6,
        "ltm_episodic": 0.8,
        "ltm_facts": 1.0,
    },
    "content_creation": {
        "stm": 0.9,
        "ltm_episodic": 0.4,
        "ltm_facts": 0.4,
    },
    "general_chat": {
        "stm": 0.9,
        "ltm_episodic": 0.2,
        "ltm_facts": 0.3,
    },
    "interactive_exercise": {
        "stm": 0.8,
        "ltm_episodic": 0.4,
        "ltm_facts": 0.9,
    },
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "stm": 0.8,
    "ltm_episodic": 0.5,
    "ltm_facts": 0.5,
}


class ContextBuilder:
    """
    Assembles weighted context from the 3 simplified memory tiers.
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
        page_context: Optional[dict] = None,
        system_context: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Build a context dict from all active memory tiers.
        """
        settings = get_settings()
        weights = WEIGHT_PROFILES.get(intent_type, DEFAULT_WEIGHTS)

        raw: dict[str, Any] = {}
        sections: list[str] = []
        total_tokens = 0

        # Retrieve prior MTM context for backwards compatibility / active node tracking
        mtm_ctx = {}
        try:
            mtm_ctx = await mtm.get_context(session_id)
            raw["mtm"] = mtm_ctx
        except Exception as exc:
            logger.warning("Failed to fetch MTM context: %s", exc)

        # ── 1. STM: Recent conversation history ──────────────────────────────
        stm_messages: list[dict] = []
        if weights["stm"] >= 0.3:
            n_turns = 30 if weights["stm"] >= 0.7 else 10
            stm_messages = await stm.get_window(session_id, n_turns=n_turns)
            
            # Enforce STM token budget
            max_stm_chars = settings.stm_budget * 4
            running_chars = 0
            truncated_stm = []
            for m in reversed(stm_messages):
                content_len = len(m.get("content", "") or "")
                if running_chars + content_len > max_stm_chars:
                    break
                truncated_stm.append(m)
                running_chars += content_len
            stm_messages = list(reversed(truncated_stm))

            raw["stm"] = {
                "message_count": len(stm_messages),
                "token_estimate": running_chars // 4,
            }
            total_tokens += raw["stm"]["token_estimate"]

        # ── 2. LTM Episodic: Past session episodes ───────────────────────────
        if weights["ltm_episodic"] >= 0.3 and query:
            recall_course_ids: Optional[list[int]] = None
            if course_id is not None:
                recall_course_ids = [course_id]
            elif scope_course_ids:
                recall_course_ids = list(scope_course_ids)

            episodes = await ltm.recall(
                user_id=user_id,
                agent_type=agent_type,
                query=query,
                top_k=2 if weights["ltm_episodic"] >= 0.7 else 1,
                course_ids=recall_course_ids,
            )
            raw["ltm"] = {"episodes": episodes}
            if episodes:
                ltm_section = self._format_ltm_episodic(episodes, settings.ltm_episodic_budget)
                if ltm_section:
                    sections.append(ltm_section)
                    total_tokens += len(ltm_section) // 4

        # ── 3. LTM Facts: Student concept mastery / struggles / strengths ─────
        if weights["ltm_facts"] >= 0.3 and course_id:
            # Determine current active node ID from input contexts or MTM state
            current_node_id = None
            if system_context:
                current_node_id = system_context.get("node_id") or system_context.get("nodeId")
            if not current_node_id and page_context:
                current_node_id = page_context.get("node_id") or page_context.get("nodeId")
            if not current_node_id:
                working_state = mtm_ctx.get("working_state") or {}
                key_facts = mtm_ctx.get("key_facts") or {}
                current_node_id = working_state.get("current_node_id") or key_facts.get("current_node_id")

            # Fetch personalization profile from personalize-service
            import httpx
            personalize_profile = {}
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"http://personalize-service:8082/personalize/student/{user_id}/course/{course_id}",
                        headers={"X-AI-Secret": settings.ai_service_secret},
                        timeout=5.0,
                    )
                    if resp.status_code == 200:
                        personalize_profile = resp.json()
            except Exception as exc:
                logger.warning("Failed to fetch personalization profile in ContextBuilder: %s", exc)

            raw["personalize_profile"] = personalize_profile
            raw["personalize"] = {"scored_concepts": scored_concepts}

            if scored_concepts or personalize_profile:
                facts_section = self._format_ltm_facts(scored_concepts, settings.ltm_facts_budget, personalize_profile)
                if facts_section:
                    sections.append(facts_section)
                    total_tokens += len(facts_section) // 4

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

    # ── Multi-Signal Scoring Heuristics ───────────────────────────────────────

    async def _compute_multi_signal_scoring(
        self,
        user_id: int,
        course_id: int,
        query: str,
        current_node_id: Optional[int] = None,
    ) -> list[dict]:
        """
        Retrieves user concept mastery list and applies multi-signal scoring:
        Score = 0.5 * Semantic + 0.3 * Recency + 0.2 * Structural
        """
        # Fetch all user concept mastery records
        concepts = await mastery_service.get_user_concept_mastery_list(user_id, course_id)
        if not concepts:
            concepts = []

        # Convert current_node_id to int if present, and query knowledge_nodes if missing
        current_node_id_int = None
        if current_node_id is not None:
            try:
                current_node_id_int = int(current_node_id)
            except (ValueError, TypeError):
                current_node_id_int = None

        if current_node_id_int:
            has_active = any(c["concept_id"] == current_node_id_int for c in concepts)
            if not has_active:
                try:
                    async with get_ai_conn() as conn:
                        node_row = await conn.fetchrow(
                            """
                            SELECT id, name, name_vi
                            FROM knowledge_nodes
                            WHERE id = $1 AND course_id = $2
                            """,
                            current_node_id_int,
                            course_id,
                        )
                    if node_row:
                        concepts.append({
                            "concept_id": node_row["id"],
                            "name": node_row["name"],
                            "name_vi": node_row["name_vi"],
                            "mastery_level": 0.0,
                            "struggles": False,
                            "last_interaction": datetime.now(timezone.utc),
                        })
                except Exception as exc:
                    logger.warning("Failed to query active knowledge node: %s", exc)

        if not concepts:
            return []

        # 1. Semantic relevance (Cosine similarity between query and concept name)
        try:
            query_emb = await create_embedding(query)
            concept_names = [c["name"] for c in concepts]
            concept_embs = await create_embeddings_batch(concept_names)
            
            for c, emb in zip(concepts, concept_embs):
                dot = sum(a * b for a, b in zip(query_emb, emb))
                norm1 = math.sqrt(sum(a * a for a in query_emb))
                norm2 = math.sqrt(sum(b * b for b in emb))
                c["semantic_score"] = dot / (norm1 * norm2) if norm1 and norm2 else 0.0
        except Exception as exc:
            logger.warning("Semantic similarity computation failed: %s", exc)
            for c in concepts:
                c["semantic_score"] = 0.5  # Neutral fallback

        # 2. Recency decay score (exponential decay based on last_interaction)
        settings = get_settings()
        half_life = settings.memory_decay_half_life
        now = datetime.now(timezone.utc)
        for c in concepts:
            last_int = c["last_interaction"]
            if last_int.tzinfo is None:
                last_int = last_int.replace(tzinfo=timezone.utc)
            delta_days = max(0.0, (now - last_int).total_seconds() / 86400.0)
            c["recency_score"] = 2.0 ** (-delta_days / half_life)

        # 3. Structural score (relationship to current active node in KG)
        structural_scores = {}
        if current_node_id_int:
            structural_scores[current_node_id_int] = 2.0  # Boost active concept structural score
            try:
                async with get_ai_conn() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT source_node_id, target_node_id, relation_type
                        FROM knowledge_node_relations
                        WHERE course_id = $1 AND (source_node_id = $2 OR target_node_id = $2)
                        """,
                        course_id,
                        current_node_id_int,
                    )
                for r in rows:
                    src, tgt, rel = r["source_node_id"], r["target_node_id"], r["relation_type"]
                    other = src if tgt == current_node_id_int else tgt
                    score = 0.8 if rel == "prerequisite" else (0.7 if rel in ("extends", "equivalent") else 0.5)
                    structural_scores[other] = max(structural_scores.get(other, 0.0), score)
            except Exception as exc:
                logger.warning("Failed to fetch structural relations: %s", exc)
                
        for c in concepts:
            concept_id = c["concept_id"]
            c["structural_score"] = structural_scores.get(concept_id, 0.2)

        # 4. Composite score calculation
        for c in concepts:
            c["composite_score"] = (
                0.5 * c["semantic_score"]
                + 0.3 * c["recency_score"]
                + 0.2 * c["structural_score"]
            )
            
        concepts.sort(key=lambda x: x["composite_score"], reverse=True)
        return concepts

    # ── Formatting Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _format_ltm_episodic(episodes: list[dict], budget_tokens: int) -> str:
        """Format recalled LTM episodes for prompt injection, adhering to budget."""
        if not episodes:
            return ""
        
        parts = ["PAST INTERACTIONS (LTM EPISODIC):"]
        max_chars = budget_tokens * 4
        current_chars = len(parts[0])

        for ep in episodes:
            summary = ep.get("summary", "")
            if len(summary) > 200:
                summary = summary[:200] + "..."
            line = f"  - {summary} (relevance: {ep.get('score', 0):.2f})"
            
            if current_chars + len(line) + 1 > max_chars:
                break
            parts.append(line)
            current_chars += len(line) + 1
            
        return "\n".join(parts)

    @staticmethod
    def _format_ltm_facts(concepts: list[dict], budget_tokens: int, profile: dict | None = None) -> str:
        """Format scored user concept mastery facts, adhering to budget."""
        if not concepts and not profile:
            return ""

        parts = ["STUDENT COGNITIVE PROFILE (LTM FACTS):"]
        max_chars = budget_tokens * 4
        current_chars = len(parts[0])

        if profile:
            comp = profile.get("completed_lessons", 0)
            att = profile.get("attempted_lessons", 0)
            acc = profile.get("check_accuracy", 0.0)
            line = f"  Lakehouse metrics: completed_lessons={comp}/{att}, quick_check_accuracy={acc:.1%}"
            if current_chars + len(line) + 1 <= max_chars:
                parts.append(line)
                current_chars += len(line) + 1

        # Active concept is identified by structural_score == 2.0
        active_concept = next((c for c in concepts if c.get("structural_score") == 2.0), None)
        struggles = [c for c in concepts if c["struggles"] and c.get("structural_score") != 2.0]
        strengths = [c for c in concepts if c["mastery_level"] >= 0.8 and c.get("structural_score") != 2.0]

        # 0. Add active concept
        if active_concept:
            line = "  Active Concept (Student is currently viewing this):"
            if current_chars + len(line) + 1 <= max_chars:
                parts.append(line)
                current_chars += len(line) + 1
                line = f"    - {active_concept['name']} (Mastery: {active_concept['mastery_level']:.1%})"
                if current_chars + len(line) + 1 <= max_chars:
                    parts.append(line)
                    current_chars += len(line) + 1

        # 1. Add struggles
        if struggles:
            line = "  Struggling Concepts (need review/reinforcement):"
            if current_chars + len(line) + 1 <= max_chars:
                parts.append(line)
                current_chars += len(line) + 1
                
                for c in struggles:
                    line = f"    - {c['name']} (Mastery: {c['mastery_level']:.1%})"
                    if current_chars + len(line) + 1 > max_chars:
                        break
                    parts.append(line)
                    current_chars += len(line) + 1

        # 2. Add strengths
        if strengths and current_chars < max_chars:
            line = "  Mastered Concepts (strengths):"
            if current_chars + len(line) + 1 <= max_chars:
                parts.append(line)
                current_chars += len(line) + 1
                
                for c in strengths:
                    line = f"    - {c['name']} (Mastery: {c['mastery_level']:.1%})"
                    if current_chars + len(line) + 1 > max_chars:
                        break
                    parts.append(line)
                    current_chars += len(line) + 1

        return "\n".join(parts)


# Singleton
context_builder = ContextBuilder()
