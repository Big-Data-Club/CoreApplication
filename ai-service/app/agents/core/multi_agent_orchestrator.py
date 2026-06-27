"""
ai-service/app/agents/core/multi_agent_orchestrator.py

Orchestrates multi-agent execution and manages the complete lifecycle of sub-agents.

Key Features & Workflow:
  1. Spawning Score Calculation (v2): Computes the spawning score mathematically by incorporating 
     `p_ctx` (page_context) and `depth_signal`, while removing the `d_intent=0` penalty for short sentences.
  2. Context Integration: Accepts `page_context`, `system_context`, and `stm_turn_count` as parameters 
     to deeply contextualize agent execution.
  3. Execution Pipeline: Runs the standard multi-agent flow: Retrieval -> Consolidation -> Drafting -> Critique -> Revision.
  4. Observability & Logging: 
     - Automatically records event streams for database persistence.
     - Captures `triggered_by` in the breakdown to explicitly log the exact reason for spawning sub-agents.
     - Includes granular timing logs for each phase within `run_multi_agent_flow`.
  5. Error Boundary: Ensures system resilience by providing a safe fallback to parent-only execution 
     if the multi-agent routing or execution fails.
"""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Optional, Tuple, Dict, Any, List

from app.agents.events import AgentEvent, AgentEventType
from app.agents.core.sub_agents import (
    RetrievalSpecialist, DraftingSpecialist, CritiqueSpecialist, CritiqueReport,
)

logger = logging.getLogger(__name__)

class MultiAgentOrchestrator:
    def __init__(self, session_id: str, turn_id: str):
        self.session_id = session_id
        self.turn_id = turn_id
        self.multi_agent_logs: List[Dict[str, Any]] = []
        self.critique_report: Optional[Dict[str, Any]] = None
        self.consolidation: Optional[Dict[str, Any]] = None
        self.spawning_score: float = 0.0
        self.spawning_breakdown: Dict[str, Any] = {}

    def calculate_spawning_score(
        self,
        user_message: str,
        intent_type: str,
        parent_context_length: int,
        max_context_limit: int = 32768,
        page_context: Optional[Dict[str, Any]] = None,
        system_context: Optional[Dict[str, Any]] = None,
        stm_turn_count: int = 0,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Spawning score v2.

        S = w_c*c_ratio + w_d*d_intent + w_r*r_docs + w_v*v_need + w_p*p_ctx + w_depth*depth_signal

        Additions compared to v1:
          p_ctx         = signal that the learner is viewing a specific lesson
          depth_signal  = signal that the question requires deep reasoning (keywords + history length)

        Modifications:
          d_intent for knowledge_question no longer depends on len(user_message)
          d_intent fallback is no longer = 0.0
        """
        msg_lower = user_message.lower()
        triggered_by: List[str] = []

        # -- 1. Context Pressure (c_ratio) -------------------------------------
        c_ratio = min(1.0, parent_context_length / max(1, max_context_limit))

        # -- 2. Intent Complexity (d_intent) -----------------------------------
        if intent_type in ("content_creation", "interactive_exercise"):
            d_intent = 1.0
        elif intent_type == "knowledge_question":
            # No longer checking len(user_message) > 100
            # A short question like "what is a pointer?" still requires deep reasoning
            d_intent = 0.7
        elif intent_type == "progress_advice":
            d_intent = 0.5
        else:
            # general_chat still has some value, not 0.0
            d_intent = 0.1

        # -- 3. Retrieval Volume (r_docs) --------------------------------------
        r_docs = 1.0 if intent_type in (
            "knowledge_question", "content_creation", "interactive_exercise"
        ) else 0.0

        # -- 4. Verification Need (v_need) -------------------------------------
        verification_keywords = (
            # Vietnamese
            "trắc nghiệm", "tạo", "quiz", "bài tập", "dịch", "lập trình",
            "code", "viết", "implement", "thiết kế", "phân tích", "so sánh",
            "giải thích chi tiết", "ôn tập", "tóm tắt", "mô tả", "liệt kê",
            # English
            "json", "format", "generate", "create", "build", "design",
            "compare", "analyze", "summarize", "explain", "implement",
            "deep dive", "in depth", "step by step",
        )
        v_need = 1.0 if any(kw in msg_lower for kw in verification_keywords) else 0.0
        if v_need > 0:
            triggered_by.append("verification_keyword")

        # -- 5. Page Context Signal (p_ctx) ----------------------------
        # When the learner is reading a specific lesson, multi-agent grounding is more effective
        has_page_ctx = bool(
            page_context and (
                page_context.get("contentBody")
                or page_context.get("body")
                or page_context.get("contentTitle")
            )
        )
        has_sys_ctx = bool(
            system_context and (
                system_context.get("lesson_text")
                or system_context.get("lesson_title")
            )
        )
        p_ctx = 1.0 if (has_page_ctx or has_sys_ctx) else 0.0
        if p_ctx > 0:
            triggered_by.append("page_context_active")

        # -- 6. Depth Signal -------------------------------------------
        depth_keywords = (
            "tại sao", "how does", "why", "vì sao", "như thế nào",
            "explain", "giải thích", "phân tích", "so sánh", "khác nhau",
            "ưu nhược điểm", "pros cons", "trade-off", "deep dive",
            "cơ chế", "hoạt động như thế nào", "chi tiết", "in detail",
        )
        has_depth_kw = any(kw in msg_lower for kw in depth_keywords)
        if has_depth_kw:
            depth_signal = 0.8
            triggered_by.append("depth_keyword")
        elif stm_turn_count > 3:
            # After a few turns, multi-agent helps synthesize better
            depth_signal = 0.4
            triggered_by.append("conversation_depth")
        else:
            depth_signal = 0.0

        # -- Weights (sum = 1.0) ----------------------------------------------
        w_c, w_d, w_r, w_v, w_p, w_depth = 0.15, 0.30, 0.10, 0.15, 0.20, 0.10

        score = (
            w_c * c_ratio
            + w_d * d_intent
            + w_r * r_docs
            + w_v * v_need
            + w_p * p_ctx
            + w_depth * depth_signal
        )
        score = min(1.0, score)

        breakdown = {
            "c_ratio": round(c_ratio, 3),
            "d_intent": round(d_intent, 3),
            "r_docs": round(r_docs, 3),
            "v_need": round(v_need, 3),
            "p_ctx": round(p_ctx, 3),
            "depth_signal": round(depth_signal, 3),
            "score": round(score, 3),
            "triggered_by": triggered_by,
        }

        self.spawning_score = round(score, 3)
        self.spawning_breakdown = breakdown

        logger.debug(
            "SpawningScore v2: %.3f | c=%.2f d=%.2f r=%.2f v=%.2f p=%.2f depth=%.2f | triggers=%s",
            score, c_ratio, d_intent, r_docs, v_need, p_ctx, depth_signal,
            triggered_by,
        )

        return score, breakdown

    def _record_event(self, ev: AgentEvent):
        """Unchanged."""
        if ev.type == AgentEventType.SUBAGENT_SPAWN:
            sub_id = ev.data.get("subagent_id")
            for log in self.multi_agent_logs:
                if log["subagentId"] == sub_id:
                    return
            self.multi_agent_logs.append({
                "subagentId": sub_id,
                "role": ev.data.get("role"),
                "task": ev.data.get("task"),
                "status": "running",
                "thinking": "",
            })
        elif ev.type == AgentEventType.SUBAGENT_THINK:
            sub_id = ev.data.get("subagent_id")
            for log in self.multi_agent_logs:
                if log["subagentId"] == sub_id:
                    log["thinking"] += ev.data.get("delta", "")
        elif ev.type == AgentEventType.SUBAGENT_DONE:
            sub_id = ev.data.get("subagent_id")
            for log in self.multi_agent_logs:
                if log["subagentId"] == sub_id:
                    log["status"] = "completed"
                    log["summary"] = ev.data.get("summary")
        elif ev.type == AgentEventType.SUBAGENT_ERROR:
            sub_id = ev.data.get("subagent_id")
            for log in self.multi_agent_logs:
                if log["subagentId"] == sub_id:
                    log["status"] = "failed"
                    log["error"] = ev.data.get("error")
        elif ev.type == AgentEventType.CRITIQUE_PHASE:
            self.critique_report = ev.data
        elif ev.type == AgentEventType.CONSOLIDATION:
            self.consolidation = ev.data

    async def run_multi_agent_flow(
        self,
        query: str,
        course_id: Optional[int],
        intent_type: str,
        score_breakdown: Dict[str, Any],
        page_context: Optional[Dict[str, Any]] = None,
        system_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[AgentEvent | str]:
        """
        Multi-agent pipeline: Retrieval -> Draft -> Critique -> (Revision) -> Final.
        Add timing logs for each phase.
        """
        t_start = time.monotonic()

        try:
            # -- Phase 1: Retrieval --------------------------------------------
            logger.info(
                "[MultiAgent] Starting Retrieval | session=%s score=%.3f triggers=%s",
                self.session_id[:8],
                score_breakdown.get("score", 0),
                score_breakdown.get("triggered_by", []),
            )
            retrieval_agent = RetrievalSpecialist(self.session_id, self.turn_id)
            consolidated_context = ""
            async for ev in retrieval_agent.execute(
                query=query,
                course_id=course_id,
                page_context=page_context,
                system_context=system_context,
            ):
                if isinstance(ev, AgentEvent):
                    self._record_event(ev)
                    yield ev
                else:
                    consolidated_context = ev

            if not consolidated_context:
                consolidated_context = "No specific reference materials were found."

            t1 = time.monotonic()
            logger.info(
                "[MultiAgent] Retrieval done in %.0fms | ctx_len=%d",
                (t1 - t_start) * 1000, len(consolidated_context),
            )

            # -- Phase 2: Initial Draft ----------------------------------------
            logger.info("[MultiAgent] Starting Draft phase")
            draft_agent = DraftingSpecialist(self.session_id, self.turn_id)
            draft = ""
            async for ev in draft_agent.execute(query, consolidated_context):
                if isinstance(ev, AgentEvent):
                    self._record_event(ev)
                    yield ev
                else:
                    draft = ev

            t2 = time.monotonic()
            logger.info(
                "[MultiAgent] Draft done in %.0fms | draft_len=%d",
                (t2 - t1) * 1000, len(draft),
            )

            # -- Phase 3: Critique ---------------------------------------------
            logger.info("[MultiAgent] Starting Critique phase")
            critique_agent = CritiqueSpecialist(self.session_id, self.turn_id)
            critique_report: Optional[CritiqueReport] = None
            async for ev in critique_agent.execute(query, draft, consolidated_context):
                if isinstance(ev, AgentEvent):
                    self._record_event(ev)
                    yield ev
                else:
                    critique_report = ev

            t3 = time.monotonic()
            logger.info(
                "[MultiAgent] Critique done in %.0fms | verdict=%s",
                (t3 - t2) * 1000,
                critique_report.verdict if critique_report else "N/A",
            )

            # -- Phase 4: Revision (max 1 cycle) -------------------------------
            if critique_report and critique_report.verdict == "needs_revision":
                logger.info("[MultiAgent] Critique rejected draft, starting revision")
                revised_draft = ""
                async for ev in draft_agent.execute(
                    query, consolidated_context,
                    critique_feedback=critique_report.critique_report,
                ):
                    if isinstance(ev, AgentEvent):
                        self._record_event(ev)
                        yield ev
                    else:
                        revised_draft = ev
                draft = revised_draft

                async for ev in critique_agent.execute(query, draft, consolidated_context):
                    if isinstance(ev, AgentEvent):
                        self._record_event(ev)
                        yield ev
                    else:
                        critique_report = ev

            t_end = time.monotonic()
            logger.info(
                "[MultiAgent] Pipeline complete in %.0fms total",
                (t_end - t_start) * 1000,
            )

            yield draft

        except Exception as exc:
            logger.exception("Multi-agent workflow failed: %s", exc)
            err_ev = AgentEvent(
                type=AgentEventType.SUBAGENT_ERROR,
                data={"error": str(exc), "stage": "workflow"},
                session_id=self.session_id,
                turn_id=self.turn_id,
            )
            self._record_event(err_ev)
            yield err_ev
            raise exc