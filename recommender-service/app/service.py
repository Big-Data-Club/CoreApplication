from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from aiokafka import AIOKafkaProducer

from app.config import get_settings
from app.schemas import (
    ReasonFact,
    RecommendationBadge,
    RecommendationCandidate,
    RecommendationInteraction,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class RecommendationService:
    """Fast rules baseline with an explicit boundary for future retrieval/ranking."""

    def __init__(self) -> None:
        self._profile_cache: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}
        self._onboarding_cache: dict[int, tuple[float, dict[str, Any]]] = {}
        self._producer: AIOKafkaProducer | None = None
        self._producer_lock = asyncio.Lock()

    def _token(self, recommendation_id: str, user_id: int) -> str:
        message = f"{recommendation_id}:{user_id}".encode()
        secret = settings.tracking_secret or settings.ai_service_secret
        signature = hmac.new(secret.encode(), message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def valid_token(self, recommendation_id: str, user_id: int, token: str) -> bool:
        return hmac.compare_digest(self._token(recommendation_id, user_id), token)

    async def profile(self, user_id: int, course_id: int) -> tuple[dict[str, Any], bool]:
        key = (user_id, course_id)
        cached = self._profile_cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < settings.profile_cache_seconds:
            return cached[1], False

        url = f"{settings.personalize_service_url}/personalize/student/{user_id}/course/{course_id}"
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                response = await client.get(url, headers={"X-AI-Secret": settings.ai_service_secret})
                response.raise_for_status()
                profile = response.json()
                self._profile_cache[key] = (now, profile)
                return profile, False
        except Exception as exc:
            logger.warning("profile lookup failed for user=%s course=%s: %s", user_id, course_id, exc)
            return {}, True

    async def onboarding_profile(self, user_id: int) -> dict[str, Any]:
        cached = self._onboarding_cache.get(user_id)
        now = time.monotonic()
        if cached and now - cached[0] < settings.profile_cache_seconds:
            return cached[1]

        url = f"{settings.personalize_service_url}/personalize/student/{user_id}/onboarding"
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                response = await client.get(url, headers={"X-AI-Secret": settings.ai_service_secret})
                response.raise_for_status()
                profile = response.json()
                self._onboarding_cache[user_id] = (now, profile)
                return profile
        except Exception as exc:
            logger.warning("onboarding profile lookup failed for user=%s: %s", user_id, exc)
            return {}

    async def course_skill_profile(self, student_id: int, course_id: int) -> dict[str, Any] | None:
        """Fetch mastery states + eligible content from the LMS internal API."""
        url = f"{settings.lms_service_url}/api/v1/internal/students/{student_id}/skill-profile"
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds + 1.5) as client:
                response = await client.get(
                    url,
                    params={"course_id": course_id},
                    headers={"X-API-Secret": settings.ai_service_secret},
                )
                response.raise_for_status()
                body = response.json()
                return body.get("data") or body
        except Exception as exc:
            logger.warning("skill profile lookup failed for student=%s course=%s: %s", student_id, course_id, exc)
            return None

    def next_best_lessons(self, student_id: int, course_id: int, profile: dict[str, Any], time_budget_minutes: int) -> list[dict[str, Any]]:
        """Run the skill-based engine over an LMS skill profile payload."""
        from app.skill_recommender import skill_based_recommender

        skill_states = [
            {
                "skill_id": state.get("skill_id"),
                "mastery_score": float(state.get("mastery_score") or 0.0),
                "attempt_count": int(state.get("attempt_count") or 0),
                "recommended_difficulty": (
                    float(state["recommended_difficulty"])
                    if state.get("recommended_difficulty") is not None
                    else 0.5
                ),
                "skill_name": state.get("skill_name") or f"Skill {state.get('skill_id')}",
            }
            for state in profile.get("skill_states") or []
        ]
        available_content = [
            {
                "id": item.get("content_id"),
                "title": item.get("content_title"),
                "skill_id": item.get("skill_id"),
                "skill_name": item.get("skill_name"),
                "difficulty": float(item.get("difficulty") if item.get("difficulty") is not None else 0.5),
                "completed": bool(item.get("completed")),
            }
            for item in profile.get("available_content") or []
        ]

        recommendations = skill_based_recommender.get_next_best_lesson(
            student_id=student_id,
            course_id=course_id,
            skill_states=skill_states,
            available_content=available_content,
            time_budget_minutes=time_budget_minutes,
        )
        budget_per_item = max(5, time_budget_minutes // max(1, len(recommendations)))
        return [
            {
                "content_id": rec.content_id,
                "skill_id": rec.skill_id,
                "skill_name": rec.skill_name,
                "difficulty": round(max(0.0, min(rec.difficulty, 1.0)), 3),
                "reason": rec.reason,
                "score": round(max(0.0, min(rec.score, 1.0)), 3),
                "action": rec.action,
                "estimated_minutes": budget_per_item,
            }
            for rec in recommendations
        ]

    def _item(
        self,
        request: RecommendationRequest,
        rank: int,
        score: float,
        action: str,
        title: str,
        description: str,
        expected_outcome: str,
        minutes: int,
        facts: list[ReasonFact],
        *,
        candidate: RecommendationCandidate | None = None,
        badges: list[RecommendationBadge] | None = None,
    ) -> RecommendationItem:
        recommendation_id = f"rec_{uuid4().hex}"
        course_id = candidate.entity_id if candidate else request.context.course_id
        return RecommendationItem(
            recommendation_id=recommendation_id,
            entity={
                "type": "course" if candidate else "course_action",
                "id": str(course_id) if candidate else f"{course_id}:{action}",
                "course_id": course_id,
            },
            action=action,
            title=title,
            description=description,
            href=(candidate.href if candidate else None) or (f"/lms/student/courses/{course_id}/learn" if course_id else "/lms/student"),
            rank=rank,
            score=round(max(0.0, min(score, 1.0)), 3),
            estimated_minutes=minutes,
            confidence=(
                "low"
                if candidate and request.surface == "course_discovery"
                and not (request.context.interested_categories or request.context.goal or request.context.experience_level)
                else "medium" if facts else "low"
            ),
            why_facts=facts,
            badges=badges or [],
            expected_outcome=expected_outcome,
            tracking_token=self._token(recommendation_id, request.user_id),
        )

    @staticmethod
    def _tokens(value: str | None) -> set[str]:
        if not value:
            return set()
        return {token for token in re.findall(r"[\wÀ-ỹ]+", value.lower()) if len(token) > 1}

    @staticmethod
    def _freshness(candidate: RecommendationCandidate) -> float:
        timestamp = candidate.updated_at or candidate.published_at
        if not timestamp:
            return 0.25
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds() / 86400)
        return math.exp(-age_days / 90.0)

    @staticmethod
    def _activity_recency(candidate: RecommendationCandidate) -> float:
        timestamp = candidate.last_activity_at
        if not timestamp:
            return 0.15
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds() / 86400)
        return math.exp(-age_days / 21.0)

    @staticmethod
    def _exploration(user_id: int, course_id: int) -> float:
        # Stable per learner/course: exploration without a visibly jumping UI.
        digest = hashlib.sha256(f"{user_id}:{course_id}:hybrid-v2".encode()).digest()
        return int.from_bytes(digest[:2], "big") / 65535.0

    def _profile_match(self, request: RecommendationRequest, candidate: RecommendationCandidate) -> float:
        interests = set()
        for category in request.context.interested_categories:
            interests |= self._tokens(category)
        interests |= self._tokens(request.context.goal)
        if not interests:
            return 0.0
        course_tokens = self._tokens(" ".join(filter(None, [candidate.title, candidate.description, candidate.category])))
        return len(interests & course_tokens) / max(1, len(interests))

    @staticmethod
    def _level_fit(request: RecommendationRequest, candidate: RecommendationCandidate) -> float:
        desired = (request.context.experience_level or "").upper()
        actual = (candidate.level or "ALL_LEVELS").upper()
        if not desired:
            return 0.65 if actual in {"BEGINNER", "ALL_LEVELS"} else 0.45
        aliases = {"NEW": "BEGINNER", "BASIC": "BEGINNER", "EXPERIENCED": "ADVANCED"}
        desired = aliases.get(desired, desired)
        return 1.0 if actual in {desired, "ALL_LEVELS"} else 0.35

    def _rank_course_candidates(self, request: RecommendationRequest) -> list[RecommendationItem]:
        discovery = request.surface == "course_discovery"
        candidates = [
            candidate for candidate in request.candidates
            if (not discovery or not candidate.enrolled)
            and (discovery or candidate.enrolled)
            and (discovery or (candidate.progress_percent or 0) < 100)
        ]
        if not candidates:
            return []

        max_enrollments = max((candidate.enrollment_count for candidate in candidates), default=0)
        scored: list[tuple[float, RecommendationCandidate, list[ReasonFact], list[RecommendationBadge]]] = []
        for candidate in candidates:
            match = self._profile_match(request, candidate)
            freshness = self._freshness(candidate)
            activity_recency = self._activity_recency(candidate)
            popularity = math.log1p(candidate.enrollment_count) / math.log1p(max(1, max_enrollments))
            exploration = self._exploration(request.user_id, candidate.entity_id)
            facts: list[ReasonFact] = []
            badges: list[RecommendationBadge] = []

            if discovery:
                level_fit = self._level_fit(request, candidate)
                score = 0.30 * match + 0.22 * level_fit + 0.20 * popularity + 0.18 * freshness + 0.10 * exploration
                if match > 0:
                    facts.append(ReasonFact(code="goal_topic_match", value=round(match, 3)))
                    badges.append(RecommendationBadge(type="goal_match", text="Phù hợp mục tiêu"))
                if candidate.enrollment_count > 0 and popularity >= 0.75:
                    facts.append(ReasonFact(code="quality_adjusted_popularity", value=candidate.enrollment_count))
                    badges.append(RecommendationBadge(type="popular", text="Được nhiều học viên quan tâm"))
                if freshness >= 0.75:
                    facts.append(ReasonFact(code="recently_published_or_updated"))
                    badges.append(RecommendationBadge(type="new_course", text="Mới cập nhật"))
                facts.append(ReasonFact(code="level_fit", value=round(level_fit, 3)))
            else:
                progress = candidate.progress_percent or 0.0
                continuity = 0.85 if 0 < progress < 100 else 0.35
                completion_momentum = min(progress / 100.0, 1.0)
                new_content = min(candidate.new_content_count / 3.0, 1.0)
                score = (
                    0.28 * continuity
                    + 0.22 * completion_momentum
                    + 0.18 * new_content
                    + 0.12 * match
                    + 0.10 * freshness
                    + 0.10 * activity_recency
                )
                facts.append(ReasonFact(code="course_progress", value=progress))
                if candidate.last_activity_at:
                    facts.append(ReasonFact(code="learning_activity_recency", value=round(activity_recency, 3)))
                if candidate.new_content_count > 0:
                    facts.append(ReasonFact(code="new_content_since_learning_activity", value=candidate.new_content_count))
                    badges.append(RecommendationBadge(
                        type="new_content",
                        text=f"Có {candidate.new_content_count} bài mới",
                        value=candidate.new_content_count,
                    ))
                if progress >= 75:
                    badges.append(RecommendationBadge(type="almost_done", text="Sắp hoàn thành"))
                if progress > 0:
                    badges.append(RecommendationBadge(type="continue_learning", text="Học tiếp"))
                if match > 0:
                    facts.append(ReasonFact(code="goal_topic_match", value=round(match, 3)))

            scored.append((score, candidate, facts, badges))

        scored.sort(key=lambda entry: (-entry[0], entry[1].entity_id))
        if discovery:
            # Greedy diversity re-ranking prevents a single category from
            # occupying the whole slate while retaining the base relevance.
            remaining = list(scored)
            diversified: list[tuple[float, RecommendationCandidate, list[ReasonFact], list[RecommendationBadge]]] = []
            category_counts: dict[str, int] = {}
            while remaining:
                best = max(
                    remaining,
                    key=lambda entry: (
                        entry[0] - 0.08 * category_counts.get((entry[1].category or "").lower(), 0),
                        -entry[1].entity_id,
                    ),
                )
                remaining.remove(best)
                diversified.append(best)
                category_key = (best[1].category or "").lower()
                if category_key:
                    category_counts[category_key] = category_counts.get(category_key, 0) + 1
            scored = diversified
        items: list[RecommendationItem] = []
        for rank, (score, candidate, facts, badges) in enumerate(scored[: request.limit], start=1):
            items.append(self._item(
                request,
                rank,
                score,
                action="explore_course" if discovery else ("continue_course" if (candidate.progress_percent or 0) > 0 else "start_course"),
                title=candidate.title,
                description=(
                    (
                        "Khóa học được chọn theo mục tiêu và trình độ bạn đã cung cấp."
                        if request.context.interested_categories or request.context.goal or request.context.experience_level
                        else "Khóa học được chọn theo cấp độ, độ mới và mức độ quan tâm chung."
                    )
                    if discovery else
                    "Tiếp tục đúng lộ trình có khả năng giúp bạn duy trì nhịp học tốt nhất."
                ),
                expected_outcome=(
                    "Khám phá hoặc đăng ký một khóa học phù hợp."
                    if discovery else
                    "Bắt đầu hoặc tiếp tục khóa học ưu tiên."
                ),
                minutes=request.context.time_budget_minutes or 25,
                facts=facts,
                candidate=candidate,
                badges=badges,
            ))
        return items

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        course_id = request.context.course_id
        response = RecommendationResponse(
            request_id=request.request_id,
            recommendation_set_id=f"rs_{uuid4().hex}",
        )
        if request.context.role.lower() != "student":
            response.clarification_needed = True
            response.clarification_message = "Gợi ý học tập hiện chỉ dành cho vai trò học viên."
            return response
        if request.surface in {"dashboard", "course_discovery"} and request.candidates:
            if (
                not request.context.profile_resolved
                and not request.context.interested_categories
                and not request.context.goal
            ):
                onboarding = await self.onboarding_profile(request.user_id)
                request.context.interested_categories = onboarding.get("interested_categories") or []
                request.context.goal = onboarding.get("target_career") or None
                request.context.experience_level = (
                    request.context.experience_level or onboarding.get("experience_level") or None
                )
            response.policy_version = "hybrid-rules-v2"
            response.model_version = "hybrid-2026-08"
            response.items = self._rank_course_candidates(request)
            has_explicit_profile = bool(
                request.context.interested_categories
                or request.context.goal
                or request.context.experience_level
            )
            has_behavioral_profile = request.surface == "dashboard" and any(
                (candidate.progress_percent or 0) > 0
                or candidate.last_activity_at is not None
                or candidate.new_content_count > 0
                for candidate in request.candidates
            )
            response.fallback = not (has_explicit_profile or has_behavioral_profile)
            return response
        if not course_id:
            response.clarification_needed = True
            response.clarification_message = "Bạn muốn nhận gợi ý cho khóa học nào? Hãy mở một khóa học hoặc chọn khóa học trong chat."
            return response

        profile, fallback = await self.profile(request.user_id, course_id)
        response.fallback = fallback
        accuracy = float(profile.get("check_accuracy") or 0.0)
        completed = int(profile.get("completed_lessons") or 0)
        struggles = [int(node) for node in profile.get("struggle_nodes") or [] if node is not None]
        minutes = request.context.time_budget_minutes or 20
        prefer_practice = request.conversation.constraints.get("prefer_format") == "practice"

        candidates: list[RecommendationItem] = []
        if struggles:
            candidates.append(self._item(
                request, 1, 0.86, "review_weak_concept",
                "Củng cố chủ đề đang yếu",
                "Ôn nhanh nội dung liên quan rồi làm một Quick Check để kiểm tra lại.",
                "Củng cố một điểm yếu và hoàn thành một lượt tự kiểm tra.",
                min(minutes, 20),
                [ReasonFact(code="struggle_detected", node_id=struggles[0]), ReasonFact(code="time_budget", value=minutes)],
            ))
        if accuracy < 0.60 and completed > 0:
            candidates.append(self._item(
                request, len(candidates) + 1, 0.76, "practice_quick_check",
                "Làm Quick Check ngắn",
                "Thực hành một lượt kiểm tra ngắn trước khi chuyển sang nội dung mới.",
                "Xác định phần cần ôn thêm qua kết quả Quick Check.",
                min(minutes, 15),
                [ReasonFact(code="low_quick_check_accuracy", value=accuracy)],
            ))
        candidates.append(self._item(
            request, len(candidates) + 1, 0.58 if completed else 0.70, "continue_course",
            "Tiếp tục lộ trình của khóa học",
            "Mở nội dung kế tiếp trong khóa học và tiếp tục theo trình tự giáo trình.",
            "Hoàn thành hoặc bắt đầu một nội dung phù hợp trong giáo trình.",
            min(minutes, 25),
            [ReasonFact(code="course_progress", value=completed)],
        ))
        if not prefer_practice:
            candidates.append(self._item(
                request, len(candidates) + 1, 0.52, "ask_mentor",
                "Trao đổi với AI Mentor",
                "Yêu cầu giải thích một phần bạn đang vướng trước khi thực hành tiếp.",
                "Làm rõ một khái niệm bằng ví dụ phù hợp với khóa học.",
                min(minutes, 10),
                [ReasonFact(code="guided_support_available")],
            ))
        response.items = candidates[: request.limit]
        return response

    async def _producer_instance(self) -> AIOKafkaProducer:
        async with self._producer_lock:
            if self._producer is None:
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=settings.kafka_brokers,
                    value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
                )
                await self._producer.start()
            return self._producer

    async def log_interaction(self, event: RecommendationInteraction) -> bool:
        if not self.valid_token(event.recommendation_id, event.user_id, event.tracking_token):
            raise ValueError("invalid tracking token")
        payload = event.model_dump(mode="json")
        try:
            producer = await self._producer_instance()
            key = f"{event.user_id}:{event.course_id or 0}".encode()
            await producer.send_and_wait(settings.recommendation_event_topic, value=payload, key=key)
            return True
        except Exception as exc:
            # Analytics must not break a human action. The client may retry with the same event_id.
            logger.warning("recommendation event publish failed: %s", exc)
            return False

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None


recommendation_service = RecommendationService()
