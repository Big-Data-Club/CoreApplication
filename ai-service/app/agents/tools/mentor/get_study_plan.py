"""
ai-service/app/agents/tools/mentor/get_study_plan.py

Mentor Tool: get_study_plan

Builds a personalized study plan based on the student's spaced repetition
schedule, knowledge gaps, and course structure - across ALL enrolled courses,
since the Mentor agent operates at the global level, not per-course.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class GetStudyPlanTool(BaseTool):
    name = "get_study_plan"
    description = (
        "Get a personalized study plan for the student across ALL their courses. "
        "Combines spaced repetition due items, knowledge gaps, and strengths to "
        "recommend what to study next. Use when the student asks 'what should I "
        "study?', 'what do I need to review?', 'giúp tôi ôn tập', or wants a "
        "learning roadmap. Do NOT require a course_id - this tool fetches data "
        "globally across all the student's enrolled courses."
    )
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "integer",
                "description": (
                    "Optional: filter results to a specific course. "
                    "Leave omitted to get a global plan across all courses."
                ),
            },
        },
        "required": [],  # course_id is OPTIONAL - Mentor is cross-course
    }

    async def execute(self, **kwargs) -> ToolResult:


        student_id = kwargs.get("_user_id", 0)
        # course_id is optional - if not supplied by the LLM or context, use None
        course_id: int | None = (
            kwargs.get("_course_id")
            or kwargs.get("course_id")
        )

        try:
            from app.core.database import get_ai_conn
            from app.services.mastery_service import mastery_service

            # 1. Due reviews across all courses (or filtered if course_id given)
            async with get_ai_conn() as conn:
                if course_id is not None:
                    rows = await conn.fetch(
                        """
                        SELECT fcr.flashcard_id, fc.node_id, kn.name AS node_name, fcr.next_review_date
                        FROM flashcard_repetitions fcr
                        JOIN flashcards fc ON fcr.flashcard_id = fc.id
                        JOIN knowledge_nodes kn ON fc.node_id = kn.id
                        WHERE fcr.student_id = $1 AND fcr.course_id = $2 AND fcr.next_review_date <= NOW()
                        ORDER BY fcr.next_review_date ASC
                        LIMIT $3
                        """,
                        student_id,
                        course_id,
                        10,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT fcr.flashcard_id, fc.node_id, kn.name AS node_name, fcr.next_review_date
                        FROM flashcard_repetitions fcr
                        JOIN flashcards fc ON fcr.flashcard_id = fc.id
                        JOIN knowledge_nodes kn ON fc.node_id = kn.id
                        WHERE fcr.student_id = $1 AND fcr.next_review_date <= NOW()
                        ORDER BY fcr.next_review_date ASC
                        LIMIT $2
                        """,
                        student_id,
                        10,
                    )
            due_reviews = [dict(r) for r in rows]

            # 2. Weak areas
            weaknesses = await mastery_service.get_user_struggles(
                user_id=student_id,
                course_id=course_id,
            )
            weaknesses = weaknesses[:5]

            # 3. Strengths (for positive reinforcement)
            strengths = await mastery_service.get_user_strengths(
                user_id=student_id,
                course_id=course_id,
            )
            strengths = strengths[:3]

            # 4. Recent errors
            async with get_ai_conn() as conn:
                if course_id is not None:
                    rows = await conn.fetch(
                        """
                        SELECT d.id, d.gap_type, d.knowledge_gap, d.wrong_answer, d.correct_answer, d.explanation, d.study_suggestion, d.created_at, kn.name AS node_name
                        FROM ai_diagnoses d
                        JOIN knowledge_nodes kn ON d.node_id = kn.id
                        WHERE d.student_id = $1 AND kn.course_id = $2
                        ORDER BY d.created_at DESC
                        LIMIT $3
                        """,
                        student_id,
                        course_id,
                        5,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT d.id, d.gap_type, d.knowledge_gap, d.wrong_answer, d.correct_answer, d.explanation, d.study_suggestion, d.created_at, kn.name AS node_name
                        FROM ai_diagnoses d
                        LEFT JOIN knowledge_nodes kn ON d.node_id = kn.id
                        WHERE d.student_id = $1
                        ORDER BY d.created_at DESC
                        LIMIT $2
                        """,
                        student_id,
                        5,
                    )
            recent_errors = [dict(r) for r in rows]

            # 5. Unstudied topics
            unstudied_topics = []
            if course_id:
                async with get_ai_conn() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT kn.id AS node_id, kn.name, kn.name_vi
                        FROM knowledge_nodes kn
                        LEFT JOIN user_concept_mastery ucm ON kn.id = ucm.concept_id AND ucm.user_id = $1
                        WHERE kn.course_id = $2 AND ucm.concept_id IS NULL
                        ORDER BY kn.id ASC
                        LIMIT $3
                        """,
                        student_id,
                        course_id,
                        3,
                    )
                unstudied_topics = [dict(r) for r in rows]

            # 5. Build study plan items
            plan_items = []

            # Priority 1: Overdue reviews
            if due_reviews:
                plan_items.append({
                    "priority": 1,
                    "type": "review",
                    "title": "Ôn tập các câu hỏi quá hạn",
                    "description": f"{len(due_reviews)} câu hỏi cần ôn tập hôm nay",
                    "items": [
                        {
                            "question_id": r.get("question_id"),
                            "node_name": r.get("node_name", ""),
                            "next_review_date": r.get("next_review_date", ""),
                        }
                        for r in due_reviews[:5]
                    ],
                })

            # Priority 2: Weak concepts
            if weaknesses:
                plan_items.append({
                    "priority": 2,
                    "type": "study",
                    "title": "Củng cố kiến thức yếu",
                    "description": f"{len(weaknesses)} chủ đề cần ôn tập thêm",
                    "items": [
                        {
                            "node_name": w.get("name_vi") or w["name"],
                            "mastery": w["mastery_level"],
                            "suggestion": (
                                "Cần ôn kỹ" if w["mastery_level"] < 0.3
                                else "Cần luyện thêm"
                            ),
                        }
                        for w in weaknesses
                    ],
                })

            # Priority 3: Recent error patterns
            if recent_errors:
                plan_items.append({
                    "priority": 3,
                    "type": "error_pattern",
                    "title": "Lỗi thường gặp gần đây",
                    "description": f"{len(recent_errors)} lỗi cần chú ý",
                    "items": [
                        {
                            "node_name": e.get("node_name", ""),
                            "knowledge_gap": e.get("knowledge_gap", ""),
                            "suggestion": e.get("study_suggestion", ""),
                        }
                        for e in recent_errors[:3]
                    ],
                })

            # Priority 4: Strengths (positive reinforcement)
            if strengths:
                plan_items.append({
                    "priority": 4,
                    "type": "strength",
                    "title": "Điểm mạnh của bạn",
                    "description": "Giữ vững phong độ!",
                    "items": [
                        {
                            "node_name": s.get("name_vi") or s["name"],
                            "mastery": s["mastery_level"],
                        }
                        for s in strengths
                    ],
                })

            # Priority 5: Unstudied topics
            if unstudied_topics:
                plan_items.append({
                    "priority": 5,
                    "type": "new_topic",
                    "title": "Kiến thức mới",
                    "description": "Bắt đầu hành trình học tập của bạn",
                    "items": [
                        {
                            "node_name": u.get("name_vi") or u["name"],
                            "suggestion": "Bắt đầu học",
                        }
                        for u in unstudied_topics
                    ],
                })

            due_today = len(due_reviews)
            scope_label = f"khóa học {course_id}" if course_id else "tất cả khóa học"

            if not plan_items:
                return ToolResult(
                    status="success",
                    data={"plan": [], "review_stats": {"due_today": 0, "total_tracked": 0}},
                    message=(
                        f"Bạn chưa có dữ liệu học tập nào được ghi nhận cho {scope_label}. "
                        "Hãy bắt đầu làm bài kiểm tra để hệ thống theo dõi tiến độ của bạn!"
                    ),
                    ui_instruction={
                        "component": "StudyPlanWidget",
                        "props": {"plan": [], "due_today": 0},
                    },
                )

            return ToolResult(
                status="success",
                data={
                    "plan": plan_items,
                    "review_stats": {
                        "due_today": due_today,
                        "total_tracked": len(due_reviews) + len(weaknesses),
                    },
                    "scope": scope_label,
                },
                message=(
                    f"Kế hoạch hôm nay ({scope_label}): {due_today} bài ôn tập, "
                    f"{len(weaknesses)} chủ đề cần cải thiện."
                ),
                ui_instruction={
                    "component": "StudyPlanWidget",
                    "props": {
                        "plan": plan_items,
                        "due_today": due_today,
                    },
                },
            )

        except Exception as e:
            logger.error("get_study_plan failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi tạo kế hoạch: {e}",
            )
