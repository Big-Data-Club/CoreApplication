from __future__ import annotations

import logging
import json
import re
from typing import Any, Optional
from datetime import datetime, timezone

from app.core.database import get_ai_conn
from app.core.llm import chat_complete_json, chat_complete
from app.services.mastery_service import mastery_service

logger = logging.getLogger(__name__)

class ConsolidationService:
    """
    ConsolidationService implements the background memory consolidation pipeline.
    It extracts episodic summaries and updates student mastery states based on chat sessions.
    """

    def compute_importance_heuristic(self, message: str, context: dict) -> int:
        """
        Deterministically rates the importance of a chat turn from 1 to 5.
        No LLM call, fast and cheap.
        """
        text = (message or "").lower()
        
        # 1. Trigger terms indicating struggles (High Importance = 5)
        struggle_keywords = [
            "kém", "yếu", "khó", "không hiểu", "quên", "thất bại", "sai", 
            "lẫn lộn", "struggle", "confused", "fail", "hard", "difficult", "stuck"
        ]
        if any(kw in text for kw in struggle_keywords):
            return 5

        # 2. Source/Intent indicators
        source = context.get("source")
        intent = context.get("intent")
        
        if source == "quiz_diagnosis":
            return 5
        elif intent == "knowledge_question" or source == "challenge":
            return 4
        elif intent == "general_chat":
            return 1
        
        # Default fallback
        return 3

    async def extract_entities_heuristic(self, messages: list[dict], context: dict) -> list[dict]:
        """
        Fast, synchronous heuristic check of concept references.
        Queries concept names for the course and does case-insensitive string checking.
        """
        course_id = context.get("course_id")
        if not course_id or not messages:
            return []

        # Gather all user/assistant text
        combined_text = " ".join([m.get("content", "") or "" for m in messages]).lower()

        try:
            async with get_ai_conn() as conn:
                rows = await conn.fetch(
                    "SELECT id, name, name_vi FROM knowledge_nodes WHERE course_id = $1",
                    course_id
                )
            
            matched = []
            for r in rows:
                c_id, name, name_vi = r["id"], r["name"], r["name_vi"]
                # Match English name or Vietnamese name
                if (name and name.lower() in combined_text) or (name_vi and name_vi.lower() in combined_text):
                    matched.append({
                        "concept_id": c_id,
                        "name": name,
                        "name_vi": name_vi
                    })
            return matched
        except Exception as exc:
            logger.warning("Heuristic entity extraction failed: %s", exc)
            return []

    async def extract_entities_deep(self, messages: list[dict], context: dict) -> dict:
        """
        LLM-based extraction of student concept mastery updates from chat.
        Updates user_concept_mastery database table via mastery_service.
        """
        course_id = context.get("course_id")
        user_id = context.get("user_id")
        if not course_id or not user_id or not messages:
            return {"status": "skipped", "reason": "Missing course_id, user_id, or messages"}

        # Fetch knowledge nodes for mapping name -> id
        try:
            async with get_ai_conn() as conn:
                nodes = await conn.fetch(
                    "SELECT id, name, name_vi FROM knowledge_nodes WHERE course_id = $1",
                    course_id
                )
            node_map = {}
            for n in nodes:
                if n["name"]:
                    node_map[n["name"].lower().strip()] = n["id"]
                if n["name_vi"]:
                    node_map[n["name_vi"].lower().strip()] = n["id"]
        except Exception as exc:
            logger.error("Failed to fetch course nodes for mapping: %s", exc)
            return {"status": "error", "error": f"Node mapping query failed: {exc}"}

        # Build prompt for LLM extraction
        chat_transcript = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            chat_transcript += f"{role.upper()}: {content}\n"

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert cognitive assessor analyzing a student learning session.\n"
                    "Your goal is to extract updates to the student's mastery level and struggle states for concepts.\n"
                    "Identify concepts mentioned or tested in the transcript.\n"
                    "For each concept, determine if the student demonstrated understanding/correct application (mastered) "
                    "or struggled/made mistakes (struggled).\n"
                    "Return a JSON object containing a list of 'updates' with this exact schema:\n"
                    "{\n"
                    "  \"updates\": [\n"
                    "    {\n"
                    "      \"concept_name\": \"Name of the concept in English or Vietnamese\",\n"
                    "      \"status\": \"mastered\" or \"struggled\",\n"
                    "      \"explanation\": \"Brief explanation of why this status was determined\"\n"
                    "    }\n"
                    "  ]\n"
                    "}\n"
                    "IMPORTANT: Only extract concepts that were actually discussed and shown in the transcript."
                )
            },
            {
                "role": "user",
                "content": f"Transcript:\n{chat_transcript}"
            }
        ]

        try:
            res = await chat_complete_json(messages=prompt_messages)
            updates = res.get("updates", []) if isinstance(res, dict) else []
            
            applied = []
            for u in updates:
                c_name = u.get("concept_name", "").strip().lower()
                status = u.get("status")
                
                # Try exact/substring mapping
                concept_id = None
                for name_key, nid in node_map.items():
                    if c_name == name_key or name_key in c_name or c_name in name_key:
                        concept_id = nid
                        break
                
                if concept_id:
                    if status == "mastered":
                        delta = 0.10
                        struggles = False
                    elif status == "struggled":
                        delta = -0.15
                        struggles = True
                    else:
                        continue
                        
                    await mastery_service.update_mastery(
                        user_id=user_id,
                        concept_id=concept_id,
                        delta=delta,
                        struggles=struggles
                    )
                    applied.append({
                        "concept_id": concept_id,
                        "concept_name": c_name,
                        "delta": delta,
                        "struggles": struggles
                    })
            
            return {
                "status": "success",
                "updates_extracted": len(updates),
                "updates_applied": applied
            }
        except Exception as exc:
            logger.error("Deep entity extraction failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    async def create_episode_summary(self, messages: list[dict]) -> str:
        """
        Uses the LLM to generate a concise, one-sentence summary of the conversation turn/episode.
        This summary is later embedded and stored in Qdrant episodic memory.
        """
        if not messages:
            return ""

        chat_transcript = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            chat_transcript += f"{role.upper()}: {content}\n"

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Summarize the following learning session transcript in exactly one concise sentence.\n"
                    "Focus on what main topic or concept was discussed, and the student's overall understanding.\n"
                    "Do not use generic intros like 'The student discussed...'. Write the summary directly."
                )
            },
            {
                "role": "user",
                "content": f"Transcript:\n{chat_transcript}"
            }
        ]

        try:
            summary = await chat_complete(messages=prompt_messages, temperature=0.3, max_tokens=150)
            return summary.strip()
        except Exception as exc:
            logger.error("Failed to generate episode summary: %s", exc)
            return "Trò chuyện về các khái niệm bài học."


consolidation_service = ConsolidationService()
