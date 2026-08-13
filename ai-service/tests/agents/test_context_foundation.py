"""Unit tests for the deterministic per-turn context contract."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.agents.core.context_foundation import (
    resolve_turn_context,
    resume_request_after_course_choice,
)


COURSES = {
    "courses": [
        {"id": 11, "title": "Lập trình Python"},
        {"id": 12, "title": "Cấu trúc dữ liệu"},
        {"id": 31, "title": "LLM Serving, Multi‑Agent Systems, and AI Infrastructure"},
    ]
}


class ContextFoundationTests(unittest.TestCase):
    def test_verified_page_course_wins(self):
        result = resolve_turn_context(
            message="Giải thích bài này",
            page_context={
                "pageType": "lesson", "courseId": 11,
                "courseName": "Lập trình Python", "contentTitle": "Vòng lặp",
            },
            user_context={"role": "STUDENT"},
            active_courses=COURSES,
            agent_type="mentor",
        )
        self.assertEqual(result.status, "current_page")
        self.assertEqual(result.course_id, 11)
        self.assertGreater(result.confidence, 0.95)

    def test_unverified_browser_course_is_not_trusted(self):
        result = resolve_turn_context(
            message="Tạo quiz", page_context={"courseId": 999},
            user_context={"role": "TEACHER"}, active_courses=COURSES,
            agent_type="teacher",
        )
        self.assertEqual(result.status, "needs_course_choice")
        self.assertIsNone(result.course_id)
        self.assertEqual(len(result.clarification_options), len(COURSES["courses"]))

    def test_named_course_is_resolved_without_llm(self):
        result = resolve_turn_context(
            message="Tạo quiz cho Cấu trúc dữ liệu", page_context=None,
            user_context=None, active_courses=COURSES, agent_type="teacher",
        )
        self.assertEqual(result.status, "named_course")
        self.assertEqual(result.course_id, 12)

    def test_named_course_normalises_unicode_punctuation(self):
        result = resolve_turn_context(
            message="LLM Serving, Multi-Agent Systems, and AI Infrastructure",
            page_context=None, user_context=None, active_courses=COURSES,
            agent_type="teacher",
        )
        self.assertEqual(result.status, "named_course")
        self.assertEqual(result.course_id, 31)

    def test_course_can_be_selected_by_standalone_id(self):
        result = resolve_turn_context(
            message="31", page_context=None, user_context=None,
            active_courses=COURSES, agent_type="teacher",
        )
        self.assertEqual(result.status, "named_course")
        self.assertEqual(result.course_id, 31)

    def test_partial_title_uses_catalogue_discrimination(self):
        result = resolve_turn_context(
            message="hãy dùng khóa LLM Serving", page_context=None,
            user_context=None, active_courses=COURSES, agent_type="teacher",
        )
        self.assertEqual(result.status, "named_course")
        self.assertEqual(result.course_id, 31)

    def test_short_acronym_can_contribute_to_partial_title(self):
        courses = {"courses": [
            *COURSES["courses"],
            {"id": 38, "title": "HPC+AI on LANTA"},
            {"id": 29, "title": "AI Workloads on HPC: Resource-Aware GPU Request"},
        ]}
        result = resolve_turn_context(
            message="AI Infrastructure", page_context=None,
            user_context=None, active_courses=courses, agent_type="teacher",
        )
        self.assertEqual(result.status, "named_course")
        self.assertEqual(result.course_id, 31)

    def test_named_course_overrides_incidental_page_course(self):
        result = resolve_turn_context(
            message="Tạo bài học cho LLM Serving", page_context={"courseId": 11},
            user_context=None, active_courses=COURSES, agent_type="teacher",
        )
        self.assertEqual(result.status, "named_course")
        self.assertEqual(result.course_id, 31)

    def test_named_course_overrides_frontend_course_hint(self):
        result = resolve_turn_context(
            message="Tạo bài học cho LLM Serving", page_context=None,
            user_context=None, active_courses=COURSES, agent_type="teacher",
            explicit_course_id=11,
        )
        self.assertEqual(result.status, "named_course")
        self.assertEqual(result.course_id, 31)

    def test_shared_partial_title_remains_ambiguous(self):
        courses = {"courses": [
            {"id": 1, "title": "HPC on LANTA"},
            {"id": 2, "title": "AI on LANTA"},
        ]}
        result = resolve_turn_context(
            message="LANTA", page_context=None, user_context=None,
            active_courses=courses, agent_type="teacher",
        )
        self.assertEqual(result.status, "global")
        self.assertIsNone(result.course_id)

    def test_course_choice_resumes_structured_pending_request(self):
        resolution = resolve_turn_context(
            message="LLM Serving, Multi-Agent Systems, and AI Infrastructure",
            page_context=None, user_context=None, active_courses=COURSES,
            agent_type="teacher",
        )
        effective = resume_request_after_course_choice(
            message="LLM Serving, Multi-Agent Systems, and AI Infrastructure",
            resolution=resolution,
            history=[
                {"role": "user", "content": "tạo 1 bài học tổng quan về khóa học này"},
                {
                    "role": "clarification",
                    "content": "pick one",
                    "metadata": {
                        "kind": "scope",
                        "pending_user_request": "tạo 1 bài học tổng quan về khóa học này",
                    },
                },
            ],
        )
        self.assertIn("tạo 1 bài học tổng quan", effective)
        self.assertIn("course_id=31", effective)

    def test_old_scope_clarification_can_resume_without_metadata(self):
        resolution = resolve_turn_context(
            message="31", page_context=None, user_context=None,
            active_courses=COURSES, agent_type="teacher",
        )
        effective = resume_request_after_course_choice(
            message="31", resolution=resolution,
            history=[
                {"role": "user", "content": "tạo bài học tổng quan"},
                {"role": "clarification", "content": "Bạn chọn khóa nào?"},
            ],
        )
        self.assertIn("tạo bài học tổng quan", effective)
        self.assertIn("course_id=31", effective)

    def test_explicit_scope_is_verified_before_use(self):
        result = resolve_turn_context(
            message="Tạo quiz", page_context=None, user_context=None,
            active_courses=COURSES, agent_type="teacher", explicit_course_id=12,
        )
        self.assertEqual(result.course_id, 12)
        self.assertEqual(result.status, "current_page")

    def test_course_action_without_courses_requires_confirmed_navigation(self):
        result = resolve_turn_context(
            message="Tạo một quiz mới", page_context=None,
            user_context={"role": "STUDENT"}, active_courses={"courses": []},
            agent_type="mentor",
        )
        self.assertEqual(result.status, "needs_course_navigation")
        self.assertEqual(result.navigation, {
            "label": "Mở danh sách khóa học", "href": "/lms/student/courses",
        })

    def test_general_question_remains_global(self):
        result = resolve_turn_context(
            message="Đa hình trong OOP là gì?", page_context=None,
            user_context=None, active_courses={"courses": []}, agent_type="mentor",
        )
        self.assertEqual(result.status, "global")


if __name__ == "__main__":
    unittest.main()
