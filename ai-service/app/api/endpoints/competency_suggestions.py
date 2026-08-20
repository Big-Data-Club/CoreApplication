"""Review-first AI suggestions for universal competency frameworks."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.llm import chat_complete_structured
from app.core.llm_gateway import TASK_COURSE_BLUEPRINT

router = APIRouter(prefix="/competency-suggestions", tags=["Competency suggestions"])
settings = get_settings()


class CompetencyDraft(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{1,99}$")
    name: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=1, max_length=1000)
    competency_type: str = Field(default="SKILL", pattern=r"^(KNOWLEDGE|SKILL|ATTITUDE|OUTCOME)$")
    prerequisite_codes: list[str] = Field(default_factory=list, max_length=10)


class CompetencySuggestionRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    subject: str = Field(default="", max_length=100)
    audience: str = Field(default="", max_length=255)
    language: str = Field(default="vi", max_length=10)
    source_text: str = Field(default="", max_length=12000)
    max_competencies: int = Field(default=8, ge=3, le=20)

    @field_validator("source_text")
    @classmethod
    def normalise_source(cls, value: str) -> str:
        return " ".join(value.split())


class CompetencySuggestionResponse(BaseModel):
    framework_name: str = Field(min_length=3, max_length=255)
    framework_code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{1,99}$")
    competencies: list[CompetencyDraft] = Field(min_length=1, max_length=20)
    review_required: bool = True


def _verify(request: Request) -> None:
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized internal call")


@router.post("", response_model=CompetencySuggestionResponse)
async def suggest_competencies(body: CompetencySuggestionRequest, request: Request):
    """Return a draft only. LMS owns permissions and persistence."""
    _verify(request)
    result = await chat_complete_structured(
        messages=[
            {"role": "system", "content": (
                "You are a curriculum designer. Create a concise, reusable competency framework draft. "
                "Return only competencies that can be assessed or observed. Use stable uppercase codes. "
                "Prerequisite codes must reference another returned code and must not form a cycle. "
                "Never claim the draft is approved; a human will review it."
            )},
            {"role": "user", "content": (
                f"Title: {body.title}\nSubject: {body.subject}\nAudience: {body.audience}\n"
                f"Language: {body.language}\nMaximum competencies: {body.max_competencies}\n"
                f"Source material (may be empty):\n{body.source_text or '(none)'}"
            )},
        ],
        response_model=CompetencySuggestionResponse,
        task=TASK_COURSE_BLUEPRINT,
        max_tokens=2200,
    )
    if len(result.competencies) > body.max_competencies:
        result.competencies = result.competencies[:body.max_competencies]
    codes = {item.code for item in result.competencies}
    for item in result.competencies:
        item.prerequisite_codes = [code for code in item.prerequisite_codes if code in codes and code != item.code]
    return result
