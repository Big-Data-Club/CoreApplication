import time
from typing import Dict, Any

# In-memory status tracker for course graph maintenance jobs
# Map course_id -> { "job_id": str, "status": str, "updated_at": float, "edges_created": int, "error": str }
_GRAPH_JOBS: Dict[int, Dict[str, Any]] = {}

def set_job_status(course_id: int, job_id: str, status: str, edges_created: int = 0, error: str = "") -> None:
    _GRAPH_JOBS[course_id] = {
        "job_id": job_id,
        "status": status,
        "updated_at": time.time(),
        "edges_created": edges_created,
        "error": error,
    }

def get_job_status(course_id: int) -> Dict[str, Any]:
    job = _GRAPH_JOBS.get(course_id)
    if not job:
        return {"status": "idle", "job_id": "", "edges_created": 0, "error": ""}
    # Auto-expire completed or failed jobs after 10 minutes
    if job["status"] in ("completed", "failed") and (time.time() - job["updated_at"] > 600):
        return {"status": "idle", "job_id": "", "edges_created": 0, "error": ""}
    return job
