import logging

from fastapi import FastAPI, Header, HTTPException, status

from app.config import get_settings
from app.schemas import RecommendationInteraction, RecommendationRequest, RecommendationResponse
from app.service import recommendation_service

settings = get_settings()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="BDC Recommender Service", version="1.0.0")


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
