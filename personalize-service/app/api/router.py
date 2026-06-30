from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.lakehouse import lakehouse_service
from app.api.dashboard_html import DASHBOARD_HTML

settings = get_settings()
router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)


@router.get("/personalize-dashboard", response_class=HTMLResponse)
async def serve_personalize_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)



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


# ── Gold Medallion Analytics Endpoints ────────────────────────────────────

@router.get("/personalize/analytics/gold/student-metrics")
async def get_gold_student_metrics(x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")):
    verify_secret(x_ai_secret)
    return lakehouse_service.get_gold_student_metrics()


@router.get("/personalize/analytics/gold/concept-struggles")
async def get_gold_concept_struggles(x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")):
    verify_secret(x_ai_secret)
    return lakehouse_service.get_gold_concept_struggles()


@router.get("/personalize/analytics/gold/interaction-matrix")
async def get_gold_user_item_matrix(x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")):
    verify_secret(x_ai_secret)
    return lakehouse_service.get_gold_user_item_matrix()


@router.get("/personalize/analytics/gold/struggle-alerts")
async def get_gold_struggle_alerts(
    user_id: Optional[int] = Query(None, description="Filter alerts by user ID"),
    x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")
):
    verify_secret(x_ai_secret)
    return lakehouse_service.get_gold_struggle_alerts(user_id)


@router.post("/personalize/analytics/gold/export")
async def export_gold_tables(x_ai_secret: Optional[str] = Header(None, alias="X-AI-Secret")):
    verify_secret(x_ai_secret)
    try:
        exported_files = lakehouse_service.export_gold_tables()
        return {"status": "success", "message": "Gold views successfully exported to Parquet", "files": exported_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
