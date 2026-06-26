"""Usage logging for the LLM gateway.
 
Writes one row to llm_usage_log per call attempt (including failed ones). The
function is fire-and-forget from the gateway's perspective - logging errors
are swallowed so they never break a user-visible LLM call.
"""
from __future__ import annotations
 
import logging
from typing import Optional
 
from app.core.database import get_ai_conn
from app.core.llm_gateway.types import Model
 
logger = logging.getLogger(__name__)
 
 
async def record_usage(
    *,
    task_code: str,
    model: Optional[Model],
    api_key_id: Optional[int],
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    success: bool,
    fallback_used: bool,
    attempt_no: int,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    total = (prompt_tokens or 0) + (completion_tokens or 0)
    try:
        async with get_ai_conn() as conn:
            await conn.execute(
                """
                INSERT INTO llm_usage_log
                  (task_code, model_id, api_key_id, provider_code, model_name,
                   prompt_tokens, completion_tokens, total_tokens,
                   latency_ms, success, fallback_used, attempt_no,
                   error_code, error_message, request_id)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                """,
                task_code,
                model.id if model else None,
                api_key_id,
                model.provider_code if model else None,
                model.model_name if model else None,
                int(prompt_tokens or 0),
                int(completion_tokens or 0),
                int(total),
                int(latency_ms or 0),
                bool(success),
                bool(fallback_used),
                int(attempt_no or 1),
                (error_code[:60] if error_code else None),
                (error_message[:2000] if error_message else None),
                (request_id[:120] if request_id else None),
            )
    except Exception as exc:
        # Never let logging break a real call.
        logger.debug("usage log failed: %s", exc)
 
 
async def aggregate_usage(
    *,
    since_hours: int = 24,
    task_code: Optional[str] = None,
) -> list[dict]:
    """Totals grouped by (provider, model) for the admin dashboard."""
    cond = "created_at >= NOW() - ($1 || ' hours')::interval"
    args: list = [str(since_hours)]
    if task_code:
        cond += " AND task_code = $2"
        args.append(task_code)
    q = f"""
        SELECT provider_code, model_name, task_code,
               COUNT(*)                                    AS calls,
               COUNT(*) FILTER (WHERE success)             AS successes,
               COUNT(*) FILTER (WHERE NOT success)         AS failures,
               COUNT(*) FILTER (WHERE fallback_used)       AS fallbacks,
               COALESCE(SUM(prompt_tokens), 0)             AS prompt_tokens,
               COALESCE(SUM(completion_tokens), 0)         AS completion_tokens,
               COALESCE(SUM(total_tokens), 0)              AS total_tokens,
               COALESCE(AVG(latency_ms) FILTER (WHERE success), 0)::int AS avg_latency_ms
        FROM llm_usage_log
        WHERE {cond}
        GROUP BY provider_code, model_name, task_code
        ORDER BY total_tokens DESC
    """
    async with get_ai_conn() as conn:
        rows = await conn.fetch(q, *args)
    return [dict(r) for r in rows]