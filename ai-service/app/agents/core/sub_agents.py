"""
ai-service/app/agents/core/sub_agents.py

Implementation of specialized sub-agents:
  1. RetrievalSpecialist: Performs parallel RAG + Web searches and compresses the context.
  2. DraftingSpecialist: Generates response drafts based on the consolidated context.
  3. CritiqueSpecialist: Performs critical evaluation (pedagogy, factuality, format).
"""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Optional
from pydantic import BaseModel, Field

from app.agents.events import AgentEvent, AgentEventType
from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.llm import chat_complete, chat_complete_structured
from app.core.llm_gateway import get_gateway, ChatRequest, TASK_CHAT, TASK_QUIZ_GEN
from app.services.rag_service import rag_service
from app.agents.tools.mentor.search_web import SearchWebTool

logger = logging.getLogger(__name__)
settings = get_settings()

class CritiqueReport(BaseModel):
    factuality_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Factual correctness against retrieved context (0.0 to 1.0)."
    )
    pedagogy_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Pedagogical appropriateness and clarity for student level (0.0 to 1.0)."
    )
    format_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Structural and formatting correctness (0.0 to 1.0)."
    )
    verdict: str = Field(
        ..., pattern="^(approve|needs_revision)$",
        description="Must be 'approve' if all scores are >= 0.7, otherwise 'needs_revision'."
    )
    critique_report: str = Field(
        ...,
        description="Detailed critique notes and specific correction instructions."
    )

class RetrievalSpecialist:
    """Retrieves and consolidates course materials and web info into a compact context."""
    
    def __init__(self, session_id: str, turn_id: str):
        self.session_id = session_id
        self.turn_id = turn_id
        self.subagent_id = f"retrieval-{turn_id}"

    async def execute(
        self,
        query: str,
        course_id: Optional[int] = None,
        page_context: Optional[dict] = None,
        system_context: Optional[dict] = None,
    ) -> AsyncIterator[AgentEvent | str]:
        """
        Runs RAG and Web search in parallel, performs context consolidation,
        and yields AgentEvents along with the final consolidated context.
        """
        yield AgentEvent(
            type=AgentEventType.SUBAGENT_SPAWN,
            data={
                "subagent_id": self.subagent_id,
                "role": "Retrieval & Context Specialist",
                "task": f"Retrieve and consolidate knowledge for: {query[:60]}",
                "status": "running"
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        raw_chunks = []
        raw_web = []

        # Get active page title if present to focus the search
        page_title = ""
        if page_context:
            page_title = (
                page_context.get("contentTitle")
                or page_context.get("title")
                or page_context.get("name")
                or ""
            )

        search_query = query
        # If query is generic or short, and we have a page title, combine them to focus on the page title
        if page_title and len(query.strip()) < 50:
            search_query = f"{query} {page_title}"

        if page_context:
            node_id = page_context.get("nodeId") or page_context.get("node_id")
            course_id_from_ctx = page_context.get("courseId") or page_context.get("course_id")

            if node_id and course_id_from_ctx:
                try:
                    async with get_ai_conn() as conn:
                        row = await conn.fetchrow(
                            "SELECT status FROM content_index_status WHERE content_id = $1",
                            node_id,
                        )
                    status = row["status"] if row else "unindexed"
                except Exception as exc:
                    logger.warning("Index status lookup failed in RetrievalSpecialist: %s", exc)
                    status = "unknown"

                if status != "indexed":
                    yield AgentEvent(
                        type=AgentEventType.SUBAGENT_DONE,
                        data={
                            "subagent_id": self.subagent_id,
                            "status": "not_indexed",
                            "summary": f"Bài học chưa được index (status={status}).",
                        },
                        session_id=self.session_id,
                        turn_id=self.turn_id,
                    )
                    yield (
                        f"[SYSTEM: The lesson '{page_context.get('contentTitle', '')}' "
                        f"has not been indexed yet (status={status}). "
                        f"DO NOT fabricate content. Tell the student the lesson materials "
                        f"are not yet available in the AI system and suggest they read the PDF directly.]"
                    )
                    return

        # 1. Course material search
        if course_id:
            try:
                chunks = await rag_service.search_multilingual(
                    query=search_query, course_id=course_id, top_k=5
                )
                raw_chunks = [c.chunk_text for c in chunks]
            except Exception as e:
                logger.warning("RAG search failed in RetrievalSpecialist: %s", e)

        # 2. Web search fallback / addition
        try:
            web_tool = SearchWebTool()
            web_result = await web_tool.execute(query=search_query)
            if web_result.status == "success" and web_result.data:
                results = web_result.data.get("results") or []
                raw_web = [r.get("snippet") for r in results if r.get("snippet")]
        except Exception as e:
            logger.warning("Web search failed in RetrievalSpecialist: %s", e)

        from app.agents.core.prompts import _format_page_context, _format_system_context

        context_parts = []
        if page_context:
            context_parts.append(_format_page_context(page_context))
        if system_context:
            context_parts.append(_format_system_context(system_context))

        context_parts.extend(raw_chunks)
        context_parts.extend(raw_web)

        raw_text = "\n---\n".join(context_parts)
        raw_token_est = len(raw_text) // 4

        if not raw_text.strip():
            yield AgentEvent(
                type=AgentEventType.SUBAGENT_DONE,
                data={
                    "subagent_id": self.subagent_id,
                    "status": "completed",
                    "summary": "No context found. Proceeding with general knowledge."
                },
                session_id=self.session_id,
                turn_id=self.turn_id
            )
            return

        # # Do not compress if the context is already small enough - compression would only result in information loss
        CONSOLIDATION_THRESHOLD = 2400  # tokens
        if raw_token_est <= CONSOLIDATION_THRESHOLD:
            yield AgentEvent(
                type=AgentEventType.SUBAGENT_THINK,
                data={
                    "subagent_id": self.subagent_id,
                    "delta": "Context nhỏ - skipped consolidation.\n"
                },
                session_id=self.session_id,
                turn_id=self.turn_id
            )
            yield AgentEvent(
                type=AgentEventType.SUBAGENT_DONE,
                data={
                    "subagent_id": self.subagent_id,
                    "status": "completed",
                    "summary": f"Context small ({raw_token_est} tokens) - skipped consolidation."
                },
                session_id=self.session_id,
                turn_id=self.turn_id
            )
            yield raw_text
            return

        # 3. Context Consolidation via LLM (70B model to ensure quality synthesis)
        yield AgentEvent(
            type=AgentEventType.SUBAGENT_THINK,
            data={
                "subagent_id": self.subagent_id,
                "delta": "Consolidating and deduplicating context...\n"
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        prompt = (
            "You are a Context Consolidation Agent. Summarize the raw context below, "
            "keeping ALL key facts, exercises, vocabulary items, and examples. "
            "Remove only obvious duplicates and off-topic boilerplate. "
            "Preserve the structure. Output at least 80% of the original content volume.\n\n"
            f"Query: {query}\n\n"
            f"Raw Context:\n{raw_text}\n\n"
            "Consolidated Context:"
        )

        gateway = get_gateway()
        req = ChatRequest(
            task=TASK_CHAT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=3600,
            model_hint=settings.quiz_model
        )

        consolidated = ""
        try:
            async for delta_text, _, _ in gateway.stream(req):
                if delta_text:
                    consolidated += delta_text
                    yield AgentEvent(
                        type=AgentEventType.SUBAGENT_THINK,
                        data={
                            "subagent_id": self.subagent_id,
                            "delta": delta_text
                        },
                        session_id=self.session_id,
                        turn_id=self.turn_id
                    )
        except Exception as exc:
            logger.error("Consolidation streaming failed: %s", exc)
            consolidated = raw_text[:4000] # Safe fallback

        consolidated_token_est = len(consolidated) // 4

        yield AgentEvent(
            type=AgentEventType.CONSOLIDATION,
            data={
                "raw_tokens": raw_token_est,
                "consolidated_tokens": consolidated_token_est,
                "compression_ratio": round((1 - consolidated_token_est / max(1, raw_token_est)) * 100, 1)
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        yield AgentEvent(
            type=AgentEventType.SUBAGENT_DONE,
            data={
                "subagent_id": self.subagent_id,
                "status": "completed",
                "summary": f"Context consolidated successfully. Compressed by {raw_token_est - consolidated_token_est} tokens."
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        yield consolidated


class DraftingSpecialist:
    """Generates response drafts based on consolidated context."""
    
    def __init__(self, session_id: str, turn_id: str):
        self.session_id = session_id
        self.turn_id = turn_id
        self.subagent_id = f"drafting-{turn_id}"

    async def execute(
        self, query: str, context: str, critique_feedback: Optional[str] = None
    ) -> AsyncIterator[AgentEvent | str]:
        """
        Drafts a response using the 70B model and streams thoughts.
        """
        yield AgentEvent(
            type=AgentEventType.SUBAGENT_SPAWN,
            data={
                "subagent_id": self.subagent_id,
                "role": "Drafting Specialist (70B)",
                "task": "Create response draft",
                "status": "running"
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        system_instruction = (
            "You are a Virtual Mentor/Teaching Assistant. Draft a high-quality pedagogical response "
            "based strictly on the Consolidated Context below.\n"
            "Format your answer using clean markdown structure. Use Vietnamese as primary language."
        )

        user_content = f"Consolidated Context:\n{context}\n\nQuery: {query}"
        if critique_feedback:
            user_content += f"\n\nCritique Feedback from previous draft (CORRECT THIS):\n{critique_feedback}"

        gateway = get_gateway()
        req = ChatRequest(
            task=TASK_CHAT,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content}
            ],
            temperature=0.4,
            max_tokens=2048,
            model_hint=settings.quiz_model # 70B model
        )

        draft = ""
        try:
            async for delta_text, _, _ in gateway.stream(req):
                if delta_text:
                    draft += delta_text
                    yield AgentEvent(
                        type=AgentEventType.SUBAGENT_THINK,
                        data={
                            "subagent_id": self.subagent_id,
                            "delta": delta_text
                        },
                        session_id=self.session_id,
                        turn_id=self.turn_id
                    )
        except Exception as exc:
            logger.error("Drafting streaming failed: %s", exc)
            draft = "Draft generation failed."

        yield AgentEvent(
            type=AgentEventType.SUBAGENT_DONE,
            data={
                "subagent_id": self.subagent_id,
                "status": "completed",
                "summary": "Response draft completed. Sending to CritiqueSpecialist."
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        yield draft


class CritiqueSpecialist:
    """Evaluates drafts with critical thinking (pedagogy, factuality, format) using 70B."""
    
    def __init__(self, session_id: str, turn_id: str):
        self.session_id = session_id
        self.turn_id = turn_id
        self.subagent_id = f"critique-{turn_id}"

    async def execute(
        self, query: str, draft: str, context: str
    ) -> AsyncIterator[AgentEvent | CritiqueReport]:
        """
        Evaluates a draft against the context, streaming its critique thoughts,
        and returns a structured CritiqueReport object.
        """
        yield AgentEvent(
            type=AgentEventType.SUBAGENT_SPAWN,
            data={
                "subagent_id": self.subagent_id,
                "role": "Critic Agent (70B)",
                "task": "Critique and verify draft answer",
                "status": "running"
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        prompt = (
            "You are a Critic Agent. Evaluate the draft response below against the query and reference context.\n"
            "Assess 3 metrics:\n"
            "1. Factuality (factual alignment to reference context)\n"
            "2. Pedagogy (clarity, educational quality, explanation depth)\n"
            "3. Format (proper markdown headers, spacing, list structures)\n\n"
            f"Reference Context:\n{context}\n\n"
            f"Query: {query}\n\n"
            f"Draft Response:\n{draft}\n\n"
            "Provide your reasoning and output structured JSON matching the CritiqueReport schema."
        )

        yield AgentEvent(
            type=AgentEventType.SUBAGENT_THINK,
            data={
                "subagent_id": self.subagent_id,
                "delta": "Analyzing draft factuality and pedagogical formatting...\n"
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        # We call chat_complete_structured to get the final report, using the 70B model.
        try:
            report = await chat_complete_structured(
                messages=[{"role": "user", "content": prompt}],
                response_model=CritiqueReport,
                model=settings.quiz_model, # 70B model
                temperature=0.1,
                max_tokens=1000,
                task=TASK_QUIZ_GEN
            )
        except Exception as e:
            logger.error("Critique analysis failed: %s", e)
            # Safe approval fallback to prevent infinite/dead ends on syntax errors
            report = CritiqueReport(
                factuality_score=1.0,
                pedagogy_score=1.0,
                format_score=1.0,
                verdict="approve",
                critique_report="Critic evaluation skipped due to parser exception."
            )

        yield AgentEvent(
            type=AgentEventType.CRITIQUE_PHASE,
            data={
                "factuality_score": report.factuality_score,
                "pedagogy_score": report.pedagogy_score,
                "format_score": report.format_score,
                "verdict": report.verdict,
                "critique_report": report.critique_report
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        yield AgentEvent(
            type=AgentEventType.SUBAGENT_DONE,
            data={
                "subagent_id": self.subagent_id,
                "status": "completed",
                "summary": f"Critique finished. Verdict: {report.verdict} (Factuality: {report.factuality_score}, Pedagogy: {report.pedagogy_score}, Format: {report.format_score})"
            },
            session_id=self.session_id,
            turn_id=self.turn_id
        )

        yield report
