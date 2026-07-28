from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from uuid import uuid4

import httpx
from aiokafka import AIOKafkaProducer

from app.config import get_settings
from app.schemas import (
    ReasonFact,
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
    ) -> RecommendationItem:
        recommendation_id = f"rec_{uuid4().hex}"
        course_id = request.context.course_id
        return RecommendationItem(
            recommendation_id=recommendation_id,
            entity={"type": "course_action", "id": f"{course_id}:{action}", "course_id": course_id},
            action=action,
            title=title,
            description=description,
            href=f"/lms/student/courses/{course_id}/learn" if course_id else "/lms/student",
            rank=rank,
            score=round(max(0.0, min(score, 1.0)), 3),
            estimated_minutes=minutes,
            confidence="medium" if facts else "low",
            why_facts=facts,
            expected_outcome=expected_outcome,
            tracking_token=self._token(recommendation_id, request.user_id),
        )

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
