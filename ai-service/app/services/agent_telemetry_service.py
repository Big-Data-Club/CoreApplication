"""
ai-service/app/services/agent_telemetry_service.py

Saves raw execution traces, prompts, thinking steps, and outputs of the multi-agent
flow into the agent_telemetry_logs table in PostgreSQL for future model training and fine-tuning.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List

from app.core.database import get_ai_conn

logger = logging.getLogger(__name__)

class AgentTelemetryService:
    @staticmethod
    async def log_trace(
        session_id: str,
        turn_id: str,
        user_query: str,
        spawning_score: float,
        spawning_breakdown: Dict[str, Any],
        consolidation: Dict[str, Any] | None,
        multi_agent_logs: List[Dict[str, Any]],
        critique_report: Dict[str, Any] | None,
        final_answer: str
    ) -> None:
        """
        Inserts a complete, structured execution log to the agent_telemetry_logs table.
        This provides queryable, robust storage for LLM training and evaluations.
        """
        try:
            async with get_ai_conn() as conn:
                await conn.execute(
                    """
                    INSERT INTO agent_telemetry_logs (
                        session_id,
                        turn_id,
                        user_query,
                        spawning_score,
                        spawning_breakdown,
                        consolidation,
                        sub_agent_runs,
                        critique_report,
                        final_answer
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    session_id,
                    turn_id,
                    user_query,
                    spawning_score,
                    json.dumps(spawning_breakdown),
                    json.dumps(consolidation) if consolidation else None,
                    json.dumps(multi_agent_logs),
                    json.dumps(critique_report) if critique_report else None,
                    final_answer
                )
            logger.info("Saved database telemetry training trace for turn %s", turn_id)
            
        except Exception as e:
            logger.exception("Failed to write database agent telemetry log: %s", e)

agent_telemetry_service = AgentTelemetryService()
