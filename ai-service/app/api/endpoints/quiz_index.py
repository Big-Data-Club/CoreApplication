"""Service-authenticated assessment index. LMS authorizes every user operation."""

import hmac

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services import quiz_index_service as service

router = APIRouter(prefix="/quiz-index", tags=["Quiz index"])


class IndexRequest(BaseModel):
    force: bool = False
    quiz_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    requester_id: int = Field(gt=0)
    revision: str = Field(pattern=r"^[a-f0-9]{32}$")
    total: int = Field(default=0, ge=0)
    query: str = Field(default="", max_length=2000)
    question_id: int = Field(default=0, ge=0)
    node_id: int = Field(default=0, ge=0)
    source_hash: str = Field(default="", max_length=32)
    name: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=1500)
    offset: int = Field(default=0, ge=0, le=100000)


@router.post("/{action}")
async def handle(action: str, body: IndexRequest, request: Request):
    secret = get_settings().ai_service_secret
    if secret in ("", "None", "ai-service-secret-change-me") or not hmac.compare_digest(
        request.headers.get("X-AI-Secret", ""), secret
    ):
        raise HTTPException(403, "Service authentication required")
    actions = {
        "queue": service.queue,
        "state": service.state,
        "search": service.search,
        "node": service.resolve_node,
        "suggest": service.suggest,
    }
    if action not in actions:
        raise HTTPException(404, "Unknown operation")
    if action == "search" and not body.query.strip():
        raise HTTPException(422, "Search query required")
    if action in ("node", "suggest") and (
        body.question_id <= 0 or len(body.source_hash) != 32
    ):
        raise HTTPException(422, "Question and source hash required")
    try:
        return await actions[action](body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
