"""
ai-service/app/api/endpoints/health.py

Extended health endpoint for observability.
GET /health         - basic liveness check (used by Docker HEALTHCHECK)
GET /health/ready   - readiness check (all dependencies reachable)
GET /health/kafka   - Kafka consumer lag per topic
GET /health/cache   - Redis cache stats (hit rate, key counts)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import ORJSONResponse

from app.core.config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["Health"])

# Track service start time for uptime reporting
_START_TIME = time.time()


@router.get("/health")
async def liveness():
    """
    Lightweight liveness probe.
    Returns 200 if the process is alive.
    Used by Docker HEALTHCHECK and Kubernetes liveness probe.
    """
    return {
        "status":  "ok",
        "service": "ai-service",
        "version": "2.2.0",
        "uptime_seconds": int(time.time() - _START_TIME),
    }


@router.get("/health/ready")
async def readiness():
    """
    Readiness probe - checks all dependencies.
    Returns 200 only if the service can handle requests.
    Returns 503 if any critical dependency is unavailable.
    """
    checks: dict[str, Any] = {}
    is_ready = True

    # AI PostgreSQL
    try:
        from app.core.database import get_ai_conn
        async with get_ai_conn() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres_ai"] = "ok"
    except Exception as exc:
        checks["postgres_ai"] = f"error: {exc}"
        is_ready = False

    # Redis
    try:
        from app.core.cache import _get_redis
        await _get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        # Redis is non-critical (cache degrades gracefully)

    # Qdrant
    if settings.use_qdrant:
        try:
            from app.services.qdrant_service import qdrant_service
            q_health = await qdrant_service.health()
            checks["qdrant"] = q_health.get("status", "unknown")
            if q_health.get("status") != "ok":
                is_ready = False
        except Exception as exc:
            checks["qdrant"] = f"error: {exc}"
            is_ready = False

    # Neo4j (non-critical - service works without it)
    if settings.neo4j_enabled:
        try:
            from app.services.neo4j_service import neo4j_service
            neo4j_health = await neo4j_service.health()
            checks["neo4j"] = neo4j_health.get("status", "unknown")
        except Exception as exc:
            checks["neo4j"] = f"error: {exc}"

    status_code = 200 if is_ready else 503
    return ORJSONResponse(
        status_code=status_code,
        content={
            "ready":   is_ready,
            "checks":  checks,
            "service": "ai-service",
        },
    )


@router.get("/health/kafka")
async def kafka_lag():
    """
    Report consumer lag for the ai-worker-group.
    High lag (>100) means the worker is falling behind.
    Requires kafka-python or aiokafka admin client.
    """
    brokers = os.getenv("KAFKA_BROKERS", "kafka:9092")
    group_id = "ai-worker-group"
    topics = [
        "lms.document.uploaded",
        "lms.ai.command",
        "lms.graph.command",
        "lms.maintenance.command",
    ]

    try:
        from aiokafka.admin import AIOKafkaAdminClient
        from aiokafka import TopicPartition

        admin = AIOKafkaAdminClient(bootstrap_servers=brokers)
        await admin.start()

        try:
            lag_info: dict[str, Any] = {}
            total_lag = 0

            for topic in topics:
                try:
                    # Get committed offsets for the consumer group
                    offsets = await admin.list_consumer_group_offsets(
                        group_id, partitions=[TopicPartition(topic, 0)]
                    )
                    committed = offsets.get(TopicPartition(topic, 0))
                    committed_offset = committed.offset if committed else 0

                    # Get end offsets (latest)
                    end_offsets = await admin.list_offsets(
                        {TopicPartition(topic, 0): -1}
                    )
                    end_offset = end_offsets.get(TopicPartition(topic, 0), {})
                    latest = getattr(end_offset, "offset", 0)

                    lag = max(0, latest - committed_offset)
                    total_lag += lag
                    lag_info[topic] = {
                        "committed": committed_offset,
                        "latest":    latest,
                        "lag":       lag,
                        "status":    "ok" if lag < 100 else "warning" if lag < 500 else "critical",
                    }
                except Exception as topic_exc:
                    lag_info[topic] = {"error": str(topic_exc)}

            overall_status = "ok"
            if total_lag > 500:
                overall_status = "critical"
            elif total_lag > 100:
                overall_status = "warning"

            return {
                "group_id":     group_id,
                "total_lag":    total_lag,
                "status":       overall_status,
                "topics":       lag_info,
            }
        finally:
            await admin.close()

    except Exception as exc:
        logger.warning("Kafka lag check failed: %s", exc)
        return {
            "group_id": group_id,
            "status":   "error",
            "error":    str(exc),
            "note":     "Lag monitoring unavailable - check Kafka connectivity",
        }


@router.get("/health/cache")
async def cache_stats():
    """
    Report Redis cache statistics.
    Shows key counts per prefix and approximate hit rates.
    """
    try:
        from app.core.cache import _get_redis
        r = _get_redis()

        # Key counts per cache namespace
        pipe = r.pipeline()
        pipe.execute_command("DBSIZE")
        for prefix in ("emb:*", "diag:*", "graph:*"):
            pipe.execute_command("KEYS", prefix)
        results = await pipe.execute()

        total_keys  = results[0]
        emb_keys    = len(results[1])
        diag_keys   = len(results[2])
        graph_keys  = len(results[3])

        # Redis INFO stats for hit rate
        info = await r.info("stats")
        hits    = info.get("keyspace_hits",   0)
        misses  = info.get("keyspace_misses", 0)
        total   = hits + misses
        hit_rate = round(hits / total * 100, 1) if total > 0 else 0.0

        return {
            "status":   "ok",
            "total_keys": total_keys,
            "namespaces": {
                "embeddings":  emb_keys,
                "diagnoses":   diag_keys,
                "graphs":      graph_keys,
            },
            "hit_rate_pct": hit_rate,
            "hits":   hits,
            "misses": misses,
        }

    except Exception as exc:
        return {"status": "error", "error": str(exc)}
