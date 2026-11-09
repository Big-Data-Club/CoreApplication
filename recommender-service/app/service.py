from __future__ import annotations

import asyncio
import copy
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
        self._client: httpx.AsyncClient | None = None
        self._feedback: dict[str, dict] = {}
        self._behavior_cache: dict[int, tuple[float, dict]] = {}

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
        return self._client

    async def behavior_profile(self, user_id: int) -> dict:
        cached = self._behavior_cache.get(user_id)
        if cached and time.monotonic() - cached[0] < 5:
            return self.cached_behavior(user_id)
        try:
            response = await self._http().get(
                f"{settings.personalize_service_url}/personalize/student/{user_id}/recommendation-profile",
                headers={"X-AI-Secret": settings.ai_service_secret},
            )
            response.raise_for_status()
            self._behavior_cache[user_id] = (time.monotonic(), response.json())
            if len(self._behavior_cache) > 1024:
                self._behavior_cache.pop(next(iter(self._behavior_cache)))
        except Exception:
            pass
        return self.cached_behavior(user_id)

    def cached_behavior(self, user_id: int) -> dict:
        cached = self._behavior_cache.get(user_id)
        profile = copy.deepcopy(cached[1]) if cached and time.monotonic() - cached[0] < 3600 else {"courses": {}}
        profile["_stale"] = cached is None or time.monotonic() - cached[0] >= 5
        courses = profile.setdefault("courses", {})
        # Read-your-feedback while the durable Kafka projection catches up.
        now = datetime.now(timezone.utc)
        self._feedback = {k: v for k, v in self._feedback.items()
                          if (now - v["event_time"]).total_seconds() < 300}
        for event in self._feedback.values():
            if event["user_id"] != user_id or not event.get("course_id"):
                continue
            actions = courses.setdefault(str(event["course_id"]), {})
            current = actions.get(event["event_type"], {})
            at = event["event_time"].isoformat()
            if not current.get("at") or current["at"] < at:
                actions[event["event_type"]] = {"at": at, "count": 1}
        return profile

    @staticmethod
    def _signal(actions: dict, name: str, days: float = 21) -> float:
        evidence = actions.get(name)
        if not evidence or not evidence.get("at"):
            return 0.0
        try:
            at = datetime.fromisoformat(evidence["at"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            age = max(0.0, (datetime.now(timezone.utc) - at).total_seconds() / 86400)
            return math.exp(-age / days)
        except (ValueError, TypeError):
            return 0.0

    def _history_match(self, request: RecommendationRequest, candidate: RecommendationCandidate, courses: dict) -> float:
        target = self._tokens(candidate.category or candidate.title)
        best = 0.0
        history = {item.entity_id: item for item in request.candidates}
        history.update({item.entity_id: item for item in request.context.learning_history})
        for learned in history.values():
            evidence = courses.get(str(learned.entity_id), {})
            meaningful = max((self._signal(evidence, key) for key in
                ("started", "completed", "lesson_completed", "lesson_complete", "answer_submitted", "favorite")), default=0.0)
            activity = self._activity_recency(learned) if learned.last_activity_at else 0.0
            strength = max(meaningful, activity if (learned.progress_percent or 0) > 0 else 0.0)
            # Enrollment alone is weak evidence of interest, not proof of learning.
            if strength == 0 and (learned.progress_percent or 0) > 0:
                strength = 0.35
            source = self._tokens(learned.category or learned.title)
            similarity = len(source & target) / max(1, len(source | target))
            best = max(best, similarity * strength)
        return best

    def _token(self, recommendation_id: str, user_id: int, entity: dict | None = None) -> str:
        if entity is not None:
            claims = {"recommendation_id": recommendation_id, "user_id": user_id, "entity": entity}
            encoded = base64.urlsafe_b64encode(json.dumps(claims, sort_keys=True).encode()).decode().rstrip("=")
            secret = settings.tracking_secret or settings.ai_service_secret
            signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()).decode().rstrip("=")
            return f"{encoded}.{signature}"
        message = f"{recommendation_id}:{user_id}".encode()
        secret = settings.tracking_secret or settings.ai_service_secret
        signature = hmac.new(secret.encode(), message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def valid_token(self, recommendation_id: str, user_id: int, token: str) -> bool:
        if "." in token:
            try:
                encoded, signature = token.split(".", 1)
                claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
                return (claims["recommendation_id"] == recommendation_id and claims["user_id"] == user_id
                        and hmac.compare_digest(self._token(recommendation_id, user_id, claims["entity"]), token))
            except (ValueError, KeyError, TypeError):
                return False
        # Compatibility for tokens issued before the entity-bound format.
        return hmac.compare_digest(self._token(recommendation_id, user_id), token)

    async def profile(self, user_id: int, course_id: int) -> tuple[dict[str, Any], bool]:
        key = (user_id, course_id)
        cached = self._profile_cache.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < settings.profile_cache_seconds:
            return cached[1], False

        url = f"{settings.personalize_service_url}/personalize/student/{user_id}/course/{course_id}"
        try:
            response = await self._http().get(url, headers={"X-AI-Secret": settings.ai_service_secret})
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
            response = await self._http().get(url, headers={"X-AI-Secret": settings.ai_service_secret})
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
            response = await self._http().get(
                url, params={"course_id": course_id},
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
        from app.next_action import next_actions
        return next_actions(profile, time_budget_minutes)

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
        entity = {
            "type": "course" if candidate else "course_action",
            "id": str(course_id) if candidate else f"{course_id}:{action}",
            "course_id": course_id,
        }
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
            tracking_token=self._token(recommendation_id, request.user_id, entity),
        )

    @staticmethod
    def _tokens(value: str | None) -> set[str]:
        if not value:
            return set()
        stopwords = {"khóa", "học", "cơ", "bản", "nâng", "cao", "nhập", "môn", "và", "the", "and", "for", "course", "introduction"}
        return {token for token in re.findall(r"[\wÀ-ỹ]+", value.lower()) if len(token) > 1 and token not in stopwords}

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
        # A few common course-label aliases make explicit goals useful even
        # when a learner writes "AI" and an author titles the course
        # "Machine Learning". This is an explainable lexical rule, not a
        # model-derived probability.
        aliases = {
            "ai": {"ai", "artificial", "intelligence", "machine", "learning", "ml"},
            "ml": {"ml", "machine", "learning", "ai"},
            "data": {"data", "dữ", "liệu"},
            "python": {"python"},
        }
        matched = sum(bool(aliases.get(token, {token}) & course_tokens) for token in interests)
        return matched / max(1, len(interests))

    @staticmethod
    def _level_fit(request: RecommendationRequest, candidate: RecommendationCandidate) -> float:
        desired = (request.context.experience_level or "").upper()
        actual = (candidate.level or "ALL_LEVELS").upper()
        if not desired:
            return 0.65 if actual in {"BEGINNER", "ALL_LEVELS"} else 0.45
        aliases = {"NEW": "BEGINNER", "BASIC": "BEGINNER", "EXPERIENCED": "ADVANCED"}
        desired = aliases.get(desired, desired)
        return 1.0 if actual in {desired, "ALL_LEVELS"} else 0.35

    def _rank_course_candidates(self, request: RecommendationRequest, behavior: dict | None = None) -> list[RecommendationItem]:
        discovery = request.surface == "course_discovery"
        courses = (behavior or {}).get("courses", {})
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
            evidence = courses.get(str(candidate.entity_id), {})
            # Explicit disinterest suppresses this course for 30 days.
            if self._signal(evidence, "not_interested", 30) > math.exp(-1):
                continue
            match = self._profile_match(request, candidate)
            history_match = self._history_match(request, candidate, courses)
            favorite = self._signal(evidence, "favorite", 90)
            positive = max(self._signal(evidence, "click") * 0.2,
                           self._signal(evidence, "started") * 0.7,
                           self._signal(evidence, "completed"))
            penalty = 0.10 * max(self._signal(evidence, "reject", 7), self._signal(evidence, "dismiss", 7))
            freshness = self._freshness(candidate)
            activity_recency = self._activity_recency(candidate)
            popularity = math.log1p(candidate.enrollment_count) / math.log1p(max(1, max_enrollments))
            exploration = self._exploration(request.user_id, candidate.entity_id)
            facts: list[ReasonFact] = []
            badges: list[RecommendationBadge] = []

            if discovery:
                level_fit = self._level_fit(request, candidate)
                score = 0.62 * max(match, history_match * 0.9) + 0.16 * level_fit + 0.06 * popularity + 0.04 * freshness + 0.02 * exploration + 0.35 * favorite + 0.10 * positive - penalty
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
                    0.20 * continuity
                    + 0.08 * completion_momentum
                    + 0.05 * new_content
                    + 0.25 * match
                    + 0.35 * activity_recency
                    + 0.35 * favorite
                    + 0.10 * positive - penalty
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

            if history_match > 0:
                facts.append(ReasonFact(code="learning_history_match", value=round(history_match, 3)))
            if favorite > 0:
                facts.append(ReasonFact(code="explicit_course_preference", value=round(favorite, 3)))
            if positive > 0:
                facts.append(ReasonFact(code="recommendation_feedback", value=round(positive, 3)))
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
                        entry[0] - 0.02 * category_counts.get((entry[1].category or "").lower(), 0),
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
            matched_goal = any(fact.code == "goal_topic_match" for fact in facts)
            level_fit = next((fact.value for fact in facts if fact.code == "level_fit"), None)
            if any(f.code == "explicit_course_preference" for f in facts):
                explanation = "Bạn đã chọn quan tâm khóa học này."
            elif discovery and any(f.code == "learning_history_match" for f in facts):
                explanation = "Chủ đề liên quan đến các khóa bạn đã học hoặc đang học gần đây."
            elif discovery and matched_goal:
                explanation = "Chủ đề khóa học liên quan đến lĩnh vực hoặc mục tiêu bạn đã lưu."
            elif discovery and request.context.experience_level and level_fit == 1.0:
                explanation = "Trình độ khóa học phù hợp với trình độ bạn đã chọn."
            elif discovery:
                explanation = "Gợi ý dựa trên trình độ, độ mới và mức độ quan tâm chung của khóa học."
            else:
                explanation = "Tiếp tục khóa học dựa trên tiến độ học hiện tại."
            items.append(self._item(
                request,
                rank,
                score,
                action="explore_course" if discovery else ("continue_course" if (candidate.progress_percent or 0) > 0 else "start_course"),
                title=candidate.title,
                description=explanation,
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
            response.policy_version = "behavior-rules-v4"
            response.model_version = "rules-2026-11"
            behavior = await self.behavior_profile(request.user_id)
            response.items = self._rank_course_candidates(request, behavior)
            has_effective_profile = any(
                any(fact.code in {"goal_topic_match", "learning_history_match", "explicit_course_preference", "recommendation_feedback"} for fact in item.why_facts)
                or (
                    bool(request.context.experience_level)
                    and any(fact.code == "level_fit" and fact.value == 1.0 for fact in item.why_facts)
                )
                for item in response.items
            )
            has_behavioral_profile = request.surface == "dashboard" and any(
                (candidate.progress_percent or 0) > 0
                or candidate.last_activity_at is not None
                or candidate.new_content_count > 0
                for candidate in request.candidates
            )
            response.fallback = bool(behavior.get("_stale")) or not (has_effective_profile or has_behavioral_profile)
            return response
        if not course_id:
            response.clarification_needed = True
            response.clarification_message = "Bạn muốn nhận gợi ý cho khóa học nào? Hãy mở một khóa học hoặc chọn khóa học trong chat."
            return response

        profile = await self.course_skill_profile(request.user_id, course_id)
        response.fallback = profile is None
        if profile is None:
            return response
        from app.next_action import next_actions
        tasks = next_actions(profile, request.context.time_budget_minutes or 20,
                             request.conversation.constraints.get("prefer_format", "mixed"))
        for rank, task in enumerate(tasks[:request.limit], 1):
            item = self._item(
                request, rank, task["score"], task["action"], task["title"],
                task["reason"], "Hoàn thành nội dung được gợi ý.", task["estimated_minutes"],
                [ReasonFact(code="skill_gap" if task["action"] == "review" else "curriculum_progress", value=task["skill_name"])],
            )
            item.entity.update({"type": "content", "id": str(task["content_id"]), "content_id": task["content_id"]})
            item.href = f"/lms/student/courses/{course_id}/learn?contentId={task['content_id']}"
            item.tracking_token = self._token(item.recommendation_id, request.user_id, item.entity)
            response.items.append(item)
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
        if "." in event.tracking_token:
            encoded = event.tracking_token.split(".", 1)[0]
            entity = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["entity"]
            if entity.get("course_id") != event.course_id or entity.get("id") != event.entity_id or entity.get("type") != event.entity_type:
                raise ValueError("tracking token entity mismatch")
        payload = event.model_dump(mode="json")
        try:
            producer = await self._producer_instance()
            key = f"{event.user_id}:{event.course_id or 0}".encode()
            await producer.send_and_wait(settings.recommendation_event_topic, value=payload, key=key)
            # Bounded read-your-feedback cache, durable source remains Kafka.
            self._feedback[event.event_id] = event.model_dump()
            if len(self._feedback) > 4096:
                self._feedback.pop(next(iter(self._feedback)))
            return True
        except Exception as exc:
            # Analytics must not break a human action. The client may retry with the same event_id.
            logger.warning("recommendation event publish failed: %s", exc)
            return False

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None


recommendation_service = RecommendationService()
