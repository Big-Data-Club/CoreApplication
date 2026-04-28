from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

# Configure structured logging before any other imports that use logging
from app.core.logging_config import configure_logging
configure_logging()

import logging
from app.core.config import get_settings
from app.core.database import init_ai_pool, close_ai_pool
from app.api.endpoints.process    import router as process_router
from app.api.endpoints.diagnose   import router as diagnose_router, nodes_router
from app.api.endpoints.quiz_gen   import router as quiz_router, sr_router
from app.api.endpoints.flashcards import router as flashcards_router
from app.api.endpoints.auto_index import router as auto_index_router, graph_router
from app.api.endpoints.micro_lessons import router as micro_lessons_router
from app.api.endpoints.concept_check import router as concept_check_router
from app.api.endpoints.admin      import router as admin_router
from app.api.endpoints.admin_llm  import router as admin_llm_router
from app.api.endpoints.health     import router as health_router
from app.core.llm_gateway.bootstrap import bootstrap_llm_registry
from app.api.agent_router         import router as agent_router

settings = get_settings()
logger   = logging.getLogger(__name__)


app = FastAPI(
    title="BDC AI Service",
    description=(
        "AI engine for LMS — Phase 1 (Error Diagnosis & Deep Linking) "
        "and Phase 2 (Smart Quiz & Spaced Repetition). "
        "Internal microservice — not exposed to public internet."
    ),
    version="2.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=ORJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://lms-backend:8081", "http://localhost:8081"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    logger.info("Starting AI Service", extra={"version": "2.2.0", "event": "startup"})

    await init_ai_pool()
    logger.info("AI PostgreSQL pool ready",
                extra={"min_conn": settings.ai_db_min_connections,
                       "max_conn": settings.ai_db_max_connections})

    try:
        await bootstrap_llm_registry()
        logger.info("LLM registry bootstrapped successfully")
    except Exception as exc:
        logger.error("LLM registry bootstrap failed (non-fatal): %s", exc)

    if settings.use_qdrant:
        try:
            from app.services.qdrant_service import qdrant_service
            await qdrant_service.init_collections()
            logger.info("Qdrant ready", extra={"backend": "qdrant"})
        except Exception as exc:
            logger.error("Qdrant init failed (non-fatal)", extra={"error": str(exc)})

    if settings.neo4j_enabled:
        try:
            from app.services.neo4j_service import neo4j_service
            await neo4j_service.init()
            logger.info("Neo4j ready")
        except Exception as exc:
            logger.error("Neo4j init failed (non-fatal)", extra={"error": str(exc)})

    loop = asyncio.get_event_loop()

    def _init_models():
        import subprocess, sys
        subprocess.run([sys.executable, "/app/scripts/download_models.py"], check=True)
        from app.core.embeddings import warm_up_models
        warm_up_models()

    loop.run_in_executor(None, _init_models)
    logger.info("Model warm-up queued")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down AI Service", extra={"event": "shutdown"})

    from app.core.cache import close_cache
    await close_cache()

    if settings.use_qdrant:
        try:
            from app.services.qdrant_service import qdrant_service
            await qdrant_service.close()
        except Exception:
            pass

    if settings.neo4j_enabled:
        try:
            from app.services.neo4j_service import neo4j_service
            await neo4j_service.close()
        except Exception:
            pass

    await close_ai_pool()
    logger.info("AI Service shut down cleanly")


# ── Routers ────────────────────────────────────────────────────────────────────

# Health endpoints registered at root (no /ai prefix) for Docker HEALTHCHECK
app.include_router(health_router)

app.include_router(process_router,    prefix="/ai")
app.include_router(diagnose_router,   prefix="/ai")
app.include_router(nodes_router,      prefix="/ai")
app.include_router(quiz_router,       prefix="/ai")
app.include_router(sr_router,         prefix="/ai")
app.include_router(flashcards_router, prefix="/ai")
app.include_router(auto_index_router, prefix="/ai")
app.include_router(graph_router,      prefix="/ai")
app.include_router(micro_lessons_router, prefix="/ai")
app.include_router(concept_check_router, prefix="/ai")
app.include_router(admin_router,      prefix="/ai")
app.include_router(admin_llm_router,  prefix="/ai")
app.include_router(agent_router,      prefix="/ai")
