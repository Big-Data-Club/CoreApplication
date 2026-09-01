"""Validate quiz packages authored by an external MCP client model."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.core.config import get_settings

settings = get_settings()


class McpBatchGenerateQuizTool(BaseTool):
    name = "mcp_batch_generate_quiz"
    description = (
        "Validate quiz questions authored by your external AI model against knowledge nodes "
        "in one owned course, save them to the Question Bank, and optionally assemble a complete "
        "scheduled quiz in an LMS section. No BDC LLM is called. Use list_knowledge_nodes first."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {"type": "integer"},
            "quizzes": {
                "type": "array", "minItems": 1, "maxItems": 20,
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "integer"},
                        "title": {"type": "string", "maxLength": 200},
                        "questions": {
                            "type": "array", "minItems": 1, "maxItems": 20,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string", "maxLength": 1000},
                                    "options": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string", "maxLength": 500}},
                                    "correct_index": {"type": "integer", "minimum": 0, "maximum": 5},
                                    "explanation": {"type": "string", "maxLength": 1500},
                                    "bloom_level": {"type": "string", "enum": ["remember", "understand", "apply", "analyze", "evaluate", "create"]},
                                    "difficulty": {"type": "string", "enum": ["EASY", "MEDIUM", "HARD"]},
                                    "points": {"type": "number", "minimum": 0.5, "maximum": 100},
                                    "source_refs": {
                                        "type": "array", "maxItems": 10,
                                        "description": "Lesson/content references supporting this question, for example content:2559#kv-cache.",
                                        "items": {"type": "string", "minLength": 1, "maxLength": 240},
                                    },
                                },
                                "required": ["question", "options", "correct_index"],
                            },
                        },
                    },
                    "required": ["node_id", "title", "questions"],
                },
            },
            "quiz_settings": {
                "type": "object",
                "description": "When supplied, assemble the saved questions into one complete quiz. Omit to save Question Bank drafts only.",
                "properties": {
                    "section_id": {"type": "integer", "minimum": 1},
                    "title": {"type": "string", "minLength": 3, "maxLength": 255, "description": "Optional override when assembling exactly one package; otherwise each package title is used."},
                    "description": {"type": "string", "maxLength": 3000},
                    "instructions": {"type": "string", "maxLength": 3000},
                    "time_limit_minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
                    "max_attempts": {"type": "integer", "minimum": 1, "maximum": 100},
                    "passing_score": {"type": "number", "minimum": 0, "maximum": 100},
                    "available_from": {"type": "string", "description": "RFC3339/ISO-8601 timestamp with timezone."},
                    "available_until": {"type": "string", "description": "RFC3339/ISO-8601 timestamp with timezone."},
                    "shuffle_questions": {"type": "boolean", "default": false},
                    "shuffle_answers": {"type": "boolean", "default": true},
                    "publish": {"type": "boolean", "default": false},
                    "enforce_bloom_ladder": {"type": "boolean", "default": true, "description": "For each quiz: questions 1–4 remember, 5–6 understand, 7 apply, 8+ analyze."},
                    "require_advanced_source_refs": {"type": "boolean", "default": true, "description": "Require questions 8–10 to cite the posted lesson/content evidence used to author them."},
                },
                "required": ["section_id"],
            },
        },
        "required": ["course_id", "quizzes"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        course_id = int(kwargs.get("course_id") or 0)
        quizzes = kwargs.get("quizzes") or []
        if not course_id or not isinstance(quizzes, list) or not 1 <= len(quizzes) <= 20:
            return ToolResult(status="error", data={"error": "invalid_quiz_batch"}, message="Provide 1–20 quiz packages.")

        node_ids = [int(q.get("node_id") or 0) for q in quizzes if isinstance(q, dict)]
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                "SELECT id FROM knowledge_nodes WHERE course_id = $1 AND id = ANY($2::bigint[])",
                course_id, node_ids,
            )
        valid_nodes = {int(row["id"]) for row in rows}
        if set(node_ids) != valid_nodes:
            return ToolResult(status="error", data={"error": "invalid_node_ids"}, message="Every node_id must belong to the selected course.")

        normalized = []
        total = 0
        global_position = 0
        quiz_settings = kwargs.get("quiz_settings")
        assembling = isinstance(quiz_settings, dict)
        enforce_ladder = assembling and bool(quiz_settings.get("enforce_bloom_ladder", True))
        require_advanced_refs = assembling and bool(quiz_settings.get("require_advanced_source_refs", True))
        for quiz in quizzes:
            questions = quiz.get("questions") or []
            if not 1 <= len(questions) <= 20:
                return ToolResult(status="error", data={"error": "invalid_questions"}, message="Each quiz needs 1–20 questions.")
            if enforce_ladder and len(questions) != 10:
                return ToolResult(
                    status="error", data={"error": "bloom_ladder_requires_ten_questions"},
                    message="A complete Bloom-ladder quiz needs exactly 10 questions: 1–4 remember, 5–7 understand/apply, and 8–10 analyze/calculate.",
                )
            clean_questions = []
            for question_position, question in enumerate(questions, 1):
                global_position += 1
                stem = str(question.get("question") or "").strip()[:1000]
                options = [str(v).strip()[:500] for v in (question.get("options") or [])]
                correct = question.get("correct_index")
                if not stem or not 2 <= len(options) <= 6 or not isinstance(correct, int) or not 0 <= correct < len(options) or any(not v for v in options):
                    return ToolResult(status="error", data={"error": "invalid_question"}, message="A question has an invalid stem, options, or correct_index.")
                explanation = str(question.get("explanation") or "").strip()[:1500]
                if assembling and len(explanation) < 3:
                    return ToolResult(status="error", data={"error": "explanation_required"}, message=f"Question {global_position} needs an explanation before quiz assembly.")
                bloom, difficulty = _classification(question, question_position, enforce_ladder=enforce_ladder)
                points = question.get("points", 10)
                if not isinstance(points, (int, float)) or not 0.5 <= float(points) <= 100:
                    return ToolResult(status="error", data={"error": "invalid_points"}, message=f"Question {global_position} has invalid points.")
                raw_refs = question.get("source_refs") or []
                if not isinstance(raw_refs, list):
                    return ToolResult(status="error", data={"error": "invalid_source_refs"}, message=f"Question {global_position} source_refs must be a list.")
                source_refs = list(dict.fromkeys(str(ref).strip()[:240] for ref in raw_refs if str(ref).strip()))[:10]
                if require_advanced_refs and question_position >= 8 and not source_refs:
                    return ToolResult(
                        status="error", data={"error": "advanced_question_source_required"},
                        message=f"Advanced question {question_position} in quiz '{quiz.get('title') or 'Quiz'}' must cite at least one posted lesson/content source_ref.",
                    )
                options, correct = _balance_correct_position(options, correct, question_position - 1)
                clean_questions.append({
                    "question": stem, "options": options, "correct_index": correct,
                    "explanation": explanation, "bloom_level": bloom,
                    "difficulty": difficulty, "points": float(points),
                    "source_refs": source_refs,
                })
            total += len(clean_questions)
            normalized.append({"node_id": int(quiz["node_id"]), "title": str(quiz.get("title") or "Quiz")[:200], "questions": clean_questions})

        if total > 100:
            return ToolResult(status="error", data={"error": "too_many_questions"}, message="One MCP call can save at most 100 questions.")

        try:
            bank_items = await _save_to_question_bank(
                course_id=course_id,
                user_id=int(kwargs.get("_user_id") or 0),
                quizzes=normalized,
            )
        except ValueError as exc:
            return ToolResult(status="error", data={"error": "question_bank_save_failed"}, message=str(exc))
        except Exception:
            return ToolResult(
                status="error", data={"error": "question_bank_save_failed"},
                message="Questions were validated but could not be saved to the LMS Question Bank.",
            )

        ids = [int(item["id"]) for item in bank_items if isinstance(item, dict) and isinstance(item.get("id"), int)]
        if len(ids) != total:
            return ToolResult(
                status="error",
                data={"error": "question_bank_ids_missing", "saved_count": len(bank_items), "bank_item_ids": ids},
                message="LMS saved questions but did not return every Question Bank ID; quiz assembly was stopped to avoid an incomplete quiz.",
            )

        if isinstance(quiz_settings, dict):
            assembled_quizzes: list[dict[str, Any]] = []
            cursor = 0
            for package_index, package in enumerate(normalized, 1):
                package_ids = ids[cursor:cursor + len(package["questions"])]
                cursor += len(package["questions"])
                fallback_title = package["title"]
                if len(normalized) == 1 and str(quiz_settings.get("title") or "").strip():
                    fallback_title = str(quiz_settings["title"]).strip()
                try:
                    payload = _quiz_settings_payload(quiz_settings, package_ids, fallback_title=fallback_title)
                    assembled = await _assemble_quiz(
                        course_id=course_id,
                        user_id=int(kwargs.get("_user_id") or 0),
                        payload=payload,
                    )
                    assembled_quizzes.append(assembled)
                except ValueError as exc:
                    return ToolResult(
                        status="error",
                        data={
                            "error": "quiz_assembly_failed", "bank_item_ids": ids,
                            "created_quizzes": assembled_quizzes, "failed_package": package_index,
                            "state": "PARTIALLY_ASSEMBLED" if assembled_quizzes else "SAVED_TO_QUESTION_BANK_DRAFT",
                        },
                        message=f"Questions are safely stored, but quiz package {package_index} could not be assembled: {exc}",
                    )
            published_count = sum(bool(item.get("is_published")) for item in assembled_quizzes)
            return ToolResult(
                status="success",
                data={
                    "course_id": course_id, "question_count": total, "bank_item_ids": ids,
                    "quizzes": assembled_quizzes,
                    "state": "PUBLISHED" if published_count == len(assembled_quizzes) else "ASSEMBLED_DRAFT",
                    "answer_positions_balanced": True,
                    "bloom_ladder_enforced": enforce_ladder,
                    "advanced_source_refs_recorded": require_advanced_refs,
                },
                message=(
                    f"Created {len(assembled_quizzes)} complete quiz package(s) with {total} questions; "
                    f"{published_count} published and {len(assembled_quizzes) - published_count} kept as reviewable drafts."
                ),
            )

        return ToolResult(
            status="success",
            data={
                "course_id": course_id, "quizzes": normalized,
                "question_count": total, "bank_item_ids": ids,
                "state": "SAVED_TO_QUESTION_BANK_DRAFT",
                "answer_positions_balanced": True,
            },
            message=f"Saved {len(bank_items)} externally authored questions as drafts in the LMS Question Bank. Review and select them to assemble a quiz.",
        )


async def _save_to_question_bank(*, course_id: int, user_id: int, quizzes: list[dict]) -> list[dict]:
    items: list[dict] = []
    for quiz in quizzes:
        for question in quiz["questions"]:
            items.append({
                "node_id": quiz["node_id"],
                "question_type": "SINGLE_CHOICE",
                "question_text": question["question"],
                "explanation": question["explanation"],
                "points": question["points"],
                "difficulty": question["difficulty"],
                "bloom_level": question["bloom_level"],
                "answer_options": [
                    {"option_text": option, "is_correct": index == question["correct_index"], "order_index": index + 1}
                    for index, option in enumerate(question["options"])
                ],
                "correct_answers": [],
                "settings": {"source_refs": question.get("source_refs", [])},
                "tags": ["mcp", "external-ai"],
                "source": "AI_GENERATED",
                "status": "DRAFT",
            })
    headers = {"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)}
    url = f"{settings.lms_service_url.rstrip('/')}/api/v1/courses/{course_id}/question-bank"
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(url, json={"items": items}, headers=headers)
    if response.status_code not in (200, 201):
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or response.text
        except ValueError:
            message = response.text
        raise ValueError(f"LMS Question Bank rejected the draft (HTTP {response.status_code}): {message[:500]}")
    body = response.json()
    data = body.get("data", body) if isinstance(body, dict) else body
    if isinstance(data, dict):
        data = data.get("items", [])
    return data if isinstance(data, list) else []


def _classification(question: dict[str, Any], position: int, *, enforce_ladder: bool = False) -> tuple[str, str]:
    supplied_bloom = str(question.get("bloom_level") or "").lower()
    supplied_difficulty = str(question.get("difficulty") or "").upper()
    if supplied_bloom in {"remember", "understand", "apply", "analyze", "evaluate", "create"} and not enforce_ladder:
        bloom = supplied_bloom
    elif position <= 4:
        bloom = "remember"
    elif position <= 6:
        bloom = "understand"
    elif position == 7:
        bloom = "apply"
    else:
        bloom = "analyze"
    if supplied_difficulty in {"EASY", "MEDIUM", "HARD"} and not enforce_ladder:
        difficulty = supplied_difficulty
    else:
        difficulty = "EASY" if position <= 4 else ("MEDIUM" if position <= 7 else "HARD")
    return bloom, difficulty


def _balance_correct_position(options: list[str], correct_index: int, sequence: int) -> tuple[list[str], int]:
    """Rotate options deterministically so authored batches do not make every answer A."""
    target = sequence % len(options)
    shift = (target - correct_index) % len(options)
    if shift == 0:
        return options, correct_index
    rotated = options[-shift:] + options[:-shift]
    return rotated, target


def _parse_time(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.isoformat()


def _quiz_settings_payload(settings_obj: dict[str, Any], item_ids: list[int], *, fallback_title: str) -> dict[str, Any]:
    section_id = settings_obj.get("section_id")
    title = str(fallback_title or "").strip()
    if not isinstance(section_id, int) or section_id <= 0 or not 3 <= len(title) <= 255:
        raise ValueError("quiz_settings requires a valid section_id and a 3–255 character title")
    available_from = _parse_time(settings_obj.get("available_from"), "available_from")
    available_until = _parse_time(settings_obj.get("available_until"), "available_until")
    if available_from and available_until and datetime.fromisoformat(available_until) <= datetime.fromisoformat(available_from):
        raise ValueError("available_until must be after available_from")
    max_attempts = settings_obj.get("max_attempts", 3)
    time_limit = settings_obj.get("time_limit_minutes")
    passing = settings_obj.get("passing_score", 80)
    if not isinstance(max_attempts, int) or not 1 <= max_attempts <= 100:
        raise ValueError("max_attempts must be between 1 and 100")
    if time_limit is not None and (not isinstance(time_limit, int) or not 1 <= time_limit <= 1440):
        raise ValueError("time_limit_minutes must be between 1 and 1440")
    if not isinstance(passing, (int, float)) or not 0 <= float(passing) <= 100:
        raise ValueError("passing_score must be between 0 and 100")
    return {
        "section_id": section_id,
        "title": title,
        "description": str(settings_obj.get("description") or "")[:3000],
        "instructions": str(settings_obj.get("instructions") or "")[:3000],
        "item_ids": item_ids,
        "time_limit_minutes": time_limit,
        "max_attempts": max_attempts,
        "passing_score": float(passing),
        "available_from": available_from,
        "available_until": available_until,
        "shuffle_questions": bool(settings_obj.get("shuffle_questions", False)),
        "shuffle_answers": bool(settings_obj.get("shuffle_answers", True)),
        "auto_grade": True,
        "is_published": bool(settings_obj.get("publish", False)),
    }


async def _assemble_quiz(*, course_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"X-API-Secret": settings.ai_service_secret, "X-User-Id": str(user_id)}
    url = f"{settings.lms_service_url.rstrip('/')}/api/v1/courses/{course_id}/question-bank/create-quiz"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload, headers=headers)
    if response.status_code not in (200, 201):
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or response.text
        except ValueError:
            message = response.text
        raise ValueError(f"LMS rejected quiz assembly (HTTP {response.status_code}): {str(message)[:500]}")
    body = response.json()
    data = body.get("data", body) if isinstance(body, dict) else body
    if not isinstance(data, dict) or not isinstance(data.get("quiz_id"), int):
        raise ValueError("LMS did not return the assembled quiz ID")
    return data
