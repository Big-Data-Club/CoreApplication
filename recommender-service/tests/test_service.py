import unittest
from unittest.mock import AsyncMock

from app.schemas import RecommendationRequest
from app.service import RecommendationService


class RecommendationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_weak_concept_is_ranked_before_course_continuation(self):
        service = RecommendationService()
        service.profile = AsyncMock(return_value=({
            "struggle_nodes": [914],
            "check_accuracy": 0.4,
            "completed_lessons": 2,
        }, False))
        response = await service.recommend(RecommendationRequest(
            user_id=42,
            context={"course_id": 38, "role": "student", "time_budget_minutes": 20},
        ))

        self.assertFalse(response.fallback)
        self.assertEqual(response.items[0].action, "review_weak_concept")
        self.assertTrue(service.valid_token(
            response.items[0].recommendation_id,
            42,
            response.items[0].tracking_token,
        ))

    async def test_missing_course_requests_clarification(self):
        response = await RecommendationService().recommend(RecommendationRequest(user_id=42))
        self.assertTrue(response.clarification_needed)
        self.assertEqual(response.items, [])

    async def test_discovery_filters_enrolled_courses_and_uses_cold_start(self):
        service = RecommendationService()
        service.onboarding_profile = AsyncMock(return_value={})
        response = await service.recommend(RecommendationRequest(
            user_id=42,
            surface="course_discovery",
            limit=3,
            candidates=[
                {"entity_id": 1, "title": "Python cơ bản", "level": "BEGINNER", "enrollment_count": 20},
                {"entity_id": 2, "title": "Python nâng cao", "level": "ADVANCED", "enrolled": True},
                {"entity_id": 3, "title": "Nhập môn dữ liệu", "level": "BEGINNER", "enrollment_count": 5},
            ],
        ))

        self.assertEqual(response.policy_version, "hybrid-rules-v2")
        self.assertTrue(response.fallback)
        self.assertEqual({item.entity["course_id"] for item in response.items}, {1, 3})
        self.assertTrue(all(item.action == "explore_course" for item in response.items))

    async def test_dashboard_prefers_active_course_and_excludes_completed(self):
        service = RecommendationService()
        service.onboarding_profile = AsyncMock(return_value={})
        response = await service.recommend(RecommendationRequest(
            user_id=42,
            surface="dashboard",
            limit=10,
            candidates=[
                {"entity_id": 1, "title": "Chưa bắt đầu", "enrolled": True, "progress_percent": 0},
                {"entity_id": 2, "title": "Đang học", "enrolled": True, "progress_percent": 70},
                {"entity_id": 3, "title": "Đã xong", "enrolled": True, "progress_percent": 100},
            ],
        ))

        self.assertEqual([item.entity["course_id"] for item in response.items], [2, 1])
        self.assertEqual(response.items[0].action, "continue_course")
        self.assertTrue(any(badge.type == "continue_learning" for badge in response.items[0].badges))

    async def test_dashboard_surfaces_verified_new_content_badge(self):
        service = RecommendationService()
        service.onboarding_profile = AsyncMock(return_value={})
        response = await service.recommend(RecommendationRequest(
            user_id=42,
            surface="dashboard",
            candidates=[{
                "entity_id": 7,
                "title": "Khoa học dữ liệu",
                "enrolled": True,
                "progress_percent": 25,
                "new_content_count": 2,
            }],
        ))

        badge = next(badge for badge in response.items[0].badges if badge.type == "new_content")
        self.assertEqual(badge.text, "Có 2 bài mới")

    async def test_explicit_interest_overrides_popularity(self):
        response = await RecommendationService().recommend(RecommendationRequest(
            user_id=42,
            surface="course_discovery",
            context={"interested_categories": ["robotics"], "profile_resolved": True},
            candidates=[
                {"entity_id": 1, "title": "Robotics nhập môn", "level": "BEGINNER"},
                {"entity_id": 2, "title": "Khóa học phổ biến", "level": "BEGINNER", "enrollment_count": 1000},
            ],
        ))

        self.assertEqual(response.items[0].entity["course_id"], 1)
        self.assertFalse(response.fallback)
        self.assertTrue(any(badge.type == "goal_match" for badge in response.items[0].badges))
