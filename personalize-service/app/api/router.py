from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.lakehouse import lakehouse_service

settings = get_settings()
router = APIRouter()


class NotebookSaveRequest(BaseModel):
    user_id: int
    title: str
    content: str
    course_id: Optional[int] = None
    node_id: Optional[int] = None


def verify_secret(x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")):
    """Ensure internal calls are securely authenticated."""
    if not x_ai_secret or x_ai_secret != settings.ai_service_secret:
        raise HTTPException(status_code=401, detail="Unauthorized - invalid X-AI-Secret")


# ── Personalization Profile Endpoint ────────────────────────────────────────

@router.get("/personalize/student/{user_id}/course/{course_id}")
async def get_student_profile(user_id: int, course_id: int, x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")):
    verify_secret(x_ai_secret)
    profile = lakehouse_service.get_student_profile(user_id, course_id)
    return profile


# ── Notebook CRUD Endpoints ───────────────────────────────────────────

@router.get("/personalize/notebook")
async def list_notebook(
    user_id: int = Query(..., description="The user ID to load notes for"),
    course_id: Optional[int] = Query(None, description="Optional course filter"),
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")
):
    verify_secret(x_ai_secret)
    return lakehouse_service.list_notebook_entries(user_id, course_id)


@router.post("/personalize/notebook")
async def save_notebook(
    body: NotebookSaveRequest,
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")
):
    verify_secret(x_ai_secret)
    try:
        entry = lakehouse_service.save_notebook_entry(
            user_id=body.user_id,
            title=body.title,
            content=body.content,
            course_id=body.course_id,
            node_id=body.node_id
        )
        return entry
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/personalize/notebook/{entry_id}")
async def delete_notebook(
    entry_id: str,
    user_id: int = Query(..., description="The user ID who owns the note"),
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")
):
    verify_secret(x_ai_secret)
    try:
        lakehouse_service.delete_notebook_entry(entry_id, user_id)
        return {"status": "success", "message": "Notebook entry deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
