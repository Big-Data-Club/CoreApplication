"""
ai-service/app/agents/core/multi_agent_orchestrator.py

Orchestrates multi-agent execution:
  1. Computes spawning score mathematically.
  2. Runs Retrieval -> Consolidation -> Drafting -> Critique -> Revision.
  3. Records event streams automatically for database persistence.
  4. Provides an error boundary to fall back to parent-only execution.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Optional, Tuple, Dict, Any, List

from app.agents.events import AgentEvent, AgentEventType
from app.agents.core.sub_agents import RetrievalSpecialist, DraftingSpecialist, CritiqueSpecialist, CritiqueReport

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
        max_context_limit: int = 32768
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates the decision score for spawning sub-agents.
        S = 0.3 * c_ratio + 0.4 * d_intent + 0.1 * r_docs + 0.2 * v_need
        """
        # 1. Context Pressure (c_ratio)
        c_ratio = parent_context_length / max(1, max_context_limit)
        c_ratio = min(1.0, c_ratio)

        # 2. Intent Complexity (d_intent)
        if intent_type in ("content_creation", "interactive_exercise"):
            d_intent = 1.0
        elif intent_type == "knowledge_question" and len(user_message) > 100:
            d_intent = 0.6
        else:
            d_intent = 0.0

        # 3. Retrieval Volume (r_docs)
        r_docs = 1.0 if intent_type in ("knowledge_question", "content_creation", "interactive_exercise") else 0.0

        # 4. Verification Need (v_need)
        verification_keywords = ("trắc nghiệm", "tạo", "quiz", "code", "json", "bài tập", "dịch", "format", "lập trình")
        msg_lower = user_message.lower()
        v_need = 1.0 if any(kw in msg_lower for kw in verification_keywords) else 0.0

        # Formula weights
        w_c, w_d, w_r, w_v = 0.3, 0.4, 0.1, 0.2
        score = w_c * c_ratio + w_d * d_intent + w_r * r_docs + w_v * v_need

        breakdown = {
            "c_ratio": c_ratio,
            "d_intent": d_intent,
            "r_docs": r_docs,
            "v_need": v_need,
            "score": round(score, 3)
        }

        self.spawning_score = round(score, 3)
        self.spawning_breakdown = breakdown

        return score, breakdown

    def _record_event(self, ev: AgentEvent):
        """Builds multiAgentLogs list from SSE events stream to save to database metadata."""
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
        score_breakdown: Dict[str, Any]
    ) -> AsyncIterator[AgentEvent | str]:
        """
        Runs the multi-agent pipeline:
        1. RetrievalSpecialist (RAG + web + consolidate)
        2. DraftingSpecialist -> draft response
        3. CritiqueSpecialist -> evaluate
        4. If revision needed, Draft again -> final response
        """
        try:
            # Step 1: Retrieval & Consolidation
            retrieval_agent = RetrievalSpecialist(self.session_id, self.turn_id)
            consolidated_context = ""
            async for ev in retrieval_agent.execute(query, course_id):
                if isinstance(ev, AgentEvent):
                    self._record_event(ev)
                    yield ev
                else:
                    consolidated_context = ev

            if not consolidated_context:
                consolidated_context = "No specific reference materials were found."

            # Step 2: Initial Draft
            draft_agent = DraftingSpecialist(self.session_id, self.turn_id)
            draft = ""
            async for ev in draft_agent.execute(query, consolidated_context):
                if isinstance(ev, AgentEvent):
                    self._record_event(ev)
                    yield ev
                else:
                    draft = ev

            # Step 3: Critique Check
            critique_agent = CritiqueSpecialist(self.session_id, self.turn_id)
            critique_report: Optional[CritiqueReport] = None
            async for ev in critique_agent.execute(query, draft, consolidated_context):
                if isinstance(ev, AgentEvent):
                    self._record_event(ev)
                    yield ev
                else:
                    critique_report = ev

            # Step 4: Revision Loop (1 cycle max)
            if critique_report and critique_report.verdict == "needs_revision":
                logger.info("Critique rejected the initial draft, starting revision cycle.")
                revised_draft = ""
                async for ev in draft_agent.execute(
                    query, consolidated_context, critique_feedback=critique_report.critique_report
                ):
                    if isinstance(ev, AgentEvent):
                        self._record_event(ev)
                        yield ev
                    else:
                        revised_draft = ev
                draft = revised_draft

                # Verify again (will be final check)
                async for ev in critique_agent.execute(query, draft, consolidated_context):
                    if isinstance(ev, AgentEvent):
                        self._record_event(ev)
                        yield ev
                    else:
                        critique_report = ev

            # Return the final text content of the draft
            yield draft

        except Exception as exc:
            logger.exception("Multi-agent workflow failed with exception: %s", exc)
            err_ev = AgentEvent(
                type=AgentEventType.SUBAGENT_ERROR,
                data={"error": str(exc), "stage": "workflow"},
                session_id=self.session_id,
                turn_id=self.turn_id
            )
            self._record_event(err_ev)
            yield err_ev
            raise exc
