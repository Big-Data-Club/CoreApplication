import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.schemas import RecommendationInteraction, RecommendationRequest
from app.service import RecommendationService


class RecommendationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.behavior_patch = patch.object(RecommendationService, "behavior_profile", AsyncMock(return_value={"courses": {}}))
        self.behavior_patch.start()
        self.addCleanup(self.behavior_patch.stop)

    async def test_weak_concept_links_to_actual_review_content(self):
        service = RecommendationService()
        service.course_skill_profile = AsyncMock(return_value={
            "skill_states": [{"skill_id": 9, "skill_name": "Loops", "attempt_count": 3, "mastery_score": 0.2}],
            "available_content": [{"content_id": 12, "content_title": "Loops practice", "skill_id": 9, "completed": True, "prerequisites_met": True}],
        })
        response = await service.recommend(RecommendationRequest(user_id=42, context={"course_id": 38}))
        self.assertEqual(response.items[0].action, "review")
        self.assertEqual(response.items[0].href, "/lms/student/courses/38/learn?contentId=12")
        self.assertTrue(service.valid_token(response.items[0].recommendation_id, 42, response.items[0].tracking_token))

    async def test_healthy_learner_gets_only_real_next_lesson(self):
        service = RecommendationService()
        service.course_skill_profile = AsyncMock(return_value={
            "skill_states": [], "available_content": [
                {"content_id": 1, "content_title": "Done", "completed": True},
                {"content_id": 2, "content_title": "Next", "completed": False},
            ],
        })
        response = await service.recommend(RecommendationRequest(user_id=42, context={"course_id": 38}))
        self.assertEqual([item.action for item in response.items], ["learn_new"])
        self.assertEqual(response.items[0].entity["content_id"], 2)

    async def test_profile_failure_does_not_invent_a_task(self):
        service = RecommendationService()
        service.course_skill_profile = AsyncMock(return_value=None)
        response = await service.recommend(RecommendationRequest(user_id=42, context={"course_id": 38}))
        self.assertTrue(response.fallback)
        self.assertEqual(response.items, [])

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

        self.assertEqual(response.policy_version, "behavior-rules-v4")
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

    async def test_ai_goal_matches_machine_learning_title_and_explains_reason(self):
        response = await RecommendationService().recommend(RecommendationRequest(
            user_id=42,
            surface="course_discovery",
            context={"goal": "AI", "profile_resolved": True},
            candidates=[
                {"entity_id": 1, "title": "Machine Learning căn bản", "level": "BEGINNER"},
                {"entity_id": 2, "title": "Kế toán phổ thông", "level": "BEGINNER"},
            ],
        ))
        self.assertEqual(response.items[0].entity["course_id"], 1)
        self.assertIn("mục tiêu", response.items[0].description)
        self.assertNotIn("mục tiêu", response.items[1].description)

    async def test_unmatched_goal_reports_general_fallback(self):
        response = await RecommendationService().recommend(RecommendationRequest(
            user_id=42,
            surface="course_discovery",
            context={"goal": "robotics", "profile_resolved": True},
            candidates=[{"entity_id": 1, "title": "Kế toán phổ thông", "level": "BEGINNER"}],
        ))
        self.assertTrue(response.fallback)
        self.assertNotIn("mục tiêu", response.items[0].description)

    async def test_invalid_tracking_token_is_rejected_before_publication(self):
        service = RecommendationService()
        service._producer_instance = AsyncMock()
        with self.assertRaisesRegex(ValueError, "invalid tracking token"):
            await service.log_interaction(RecommendationInteraction(
                user_id=42,
                event_type="click",
                recommendation_id="rec_fake",
                tracking_token="wrong",
            ))
        service._producer_instance.assert_not_awaited()

    async def test_onboarding_timeout_returns_explicit_general_fallback(self):
        service = RecommendationService()
        with patch("app.service.httpx.AsyncClient") as client:
            client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            response = await service.recommend(RecommendationRequest(
                user_id=42,
                surface="course_discovery",
                candidates=[{"entity_id": 1, "title": "Python cơ bản"}],
            ))
        self.assertTrue(response.fallback)
        self.assertEqual(len(response.items), 1)

    async def test_non_student_does_not_receive_courses(self):
        response = await RecommendationService().recommend(RecommendationRequest(
            user_id=42,
            surface="course_discovery",
            context={"role": "teacher"},
            candidates=[{"entity_id": 1, "title": "Python cơ bản"}],
        ))
        self.assertTrue(response.clarification_needed)
        self.assertEqual(response.items, [])


    async def test_recent_learning_history_beats_unrelated_popularity(self):
        service = RecommendationService()
        response = await service.recommend(RecommendationRequest(
            user_id=42, surface="course_discovery",
            context={"profile_resolved": True, "learning_history": [{"entity_id": 90, "title": "Python", "category": "Python", "progress_percent": 50, "last_activity_at": "2099-01-01T00:00:00Z"}]},
            candidates=[{"entity_id": 1, "title": "Python tiếp theo", "category": "Python"}, {"entity_id": 2, "title": "Unrelated", "enrollment_count": 10000}],
        ))
        self.assertEqual(response.items[0].entity["course_id"], 1)
        self.assertFalse(response.fallback)

    async def test_disinterest_is_scoped_to_user_and_course_and_expires(self):
        service = RecommendationService()
        service.behavior_profile = AsyncMock(return_value={"courses": {"1": {"not_interested": {"at": "2099-01-01T00:00:00Z", "count": 1}}, "2": {"not_interested": {"at": "2000-01-01T00:00:00Z", "count": 1}}}})
        response = await service.recommend(RecommendationRequest(user_id=42, surface="course_discovery", context={"profile_resolved": True}, candidates=[{"entity_id": 1, "title": "Hidden"}, {"entity_id": 2, "title": "Expired"}]))
        self.assertEqual([i.entity["course_id"] for i in response.items], [2])

    async def test_favorite_and_recent_activity_outweigh_old_completion(self):
        service = RecommendationService()
        service.behavior_profile = AsyncMock(return_value={"courses": {"1": {"favorite": {"at": "2099-01-01T00:00:00Z", "count": 1}}}})
        response = await service.recommend(RecommendationRequest(user_id=42, surface="dashboard", context={"profile_resolved": True}, candidates=[{"entity_id": 1, "title": "Focus", "enrolled": True, "progress_percent": 10, "last_activity_at": "2099-01-01T00:00:00Z"}, {"entity_id": 2, "title": "Old", "enrolled": True, "progress_percent": 95, "last_activity_at": "2000-01-01T00:00:00Z"}]))
        self.assertEqual(response.items[0].entity["course_id"], 1)

    async def test_feedback_replay_is_idempotent_and_cannot_change_entity(self):
        service = RecommendationService()
        request = RecommendationRequest(user_id=42, surface="course_discovery", context={"profile_resolved": True}, candidates=[{"entity_id": 1, "title": "Python"}])
        item = service._rank_course_candidates(request)[0]
        producer = AsyncMock()
        service._producer_instance = AsyncMock(return_value=producer)
        event = RecommendationInteraction(event_id="feedback-1", user_id=42, event_type="favorite", recommendation_id=item.recommendation_id, tracking_token=item.tracking_token, course_id=1, entity_type="course", entity_id="1")
        await service.log_interaction(event)
        await service.log_interaction(event)
        self.assertEqual(len(service._feedback), 1)
        self.assertIn("favorite", service.cached_behavior(42)["courses"]["1"])
        self.assertEqual(service.cached_behavior(43)["courses"], {})
        with self.assertRaisesRegex(ValueError, "entity mismatch"):
            await service.log_interaction(event.model_copy(update={"course_id": 2}))

    async def test_request_deadline_returns_fallback_without_waiting_for_dependency(self):
        import asyncio
        from app.main import recommendations
        service = RecommendationService()
        async def slow(_):
            await asyncio.sleep(60)
        service.recommend = slow
        request = RecommendationRequest(user_id=42, surface="course_discovery", candidates=[{"entity_id": 1, "title": "Python"}])
        with patch("app.main.recommendation_service", service), patch("app.main.settings.recommendation_deadline_seconds", 0.01):
            from app.main import settings
            response = await recommendations(request, settings.ai_service_secret)
        self.assertTrue(response.fallback)
        self.assertEqual(len(response.items), 1)
