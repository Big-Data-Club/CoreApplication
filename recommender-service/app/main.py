import logging
import time

from fastapi import FastAPI, Header, HTTPException, status
from prometheus_client import Counter, Histogram, make_asgi_app

from app.config import get_settings
from app.schemas import (
    NextBestLessonRequest,
    NextBestLessonResponse,
    RecommendationInteraction,
    RecommendationRequest,
    RecommendationResponse,
)
from app.service import recommendation_service

settings = get_settings()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="BDC Recommender Service", version="1.0.0")

http_requests_total = Counter(
    "bdc_http_requests_total",
    "HTTP requests completed by BDC services.",
    ("service", "method", "route", "status"),
)
http_request_duration_seconds = Histogram(
    "bdc_http_request_duration_seconds",
    "HTTP request duration in seconds for BDC services.",
    ("service", "method", "route", "status"),
)


@app.middleware("http")
async def prometheus_metrics(request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        labels = ("recommender-service", request.method, route_path, str(status_code))
        http_requests_total.labels(*labels).inc()
        http_request_duration_seconds.labels(*labels).observe(time.perf_counter() - started)


app.mount("/metrics", make_asgi_app())


def verify_secret(secret: str | None) -> None:
    if not secret or secret != settings.ai_service_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/health")
async def health() -> dict:
    return {"status": "healthy", "service": "recommender-service", "policy_version": "heuristic-v1"}


@app.post("/v1/recommendations", response_model=RecommendationResponse)
async def recommendations(body: RecommendationRequest, x_ai_secret: str | None = Header(None, alias="X-AI-Secret")) -> RecommendationResponse:
    verify_secret(x_ai_secret)
    return await recommendation_service.recommend(body)


@app.post("/v1/recommendations/next-best-lesson", response_model=NextBestLessonResponse)
async def next_best_lesson(body: NextBestLessonRequest, x_ai_secret: str | None = Header(None, alias="X-AI-Secret")) -> NextBestLessonResponse:
    """Skill-based next best lesson recommendations for one student in one course."""
    verify_secret(x_ai_secret)
    profile = await recommendation_service.course_skill_profile(body.student_id, body.course_id)
    if not profile:
        return NextBestLessonResponse(student_id=body.student_id, course_id=body.course_id, recommendations=[])
    items = recommendation_service.next_best_lessons(
        body.student_id, body.course_id, profile, body.time_budget_minutes
    )
    return NextBestLessonResponse(
        student_id=body.student_id,
        course_id=body.course_id,
        recommendations=items,
    )


@app.post("/v1/events", status_code=status.HTTP_202_ACCEPTED)
async def recommendation_event(body: RecommendationInteraction, x_ai_secret: str | None = Header(None, alias="X-AI-Secret")) -> dict:
    verify_secret(x_ai_secret)
    try:
        accepted = await recommendation_service.log_interaction(body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"accepted": accepted, "event_id": body.event_id}


@app.on_event("shutdown")
async def shutdown() -> None:
    await recommendation_service.close()
