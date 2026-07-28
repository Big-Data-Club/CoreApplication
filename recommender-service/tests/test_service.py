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
