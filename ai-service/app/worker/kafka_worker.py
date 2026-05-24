import asyncio
import json
import os
import traceback
from aiokafka import AIOKafkaConsumer

# Configure structured logging before other imports
from app.core.logging_config import configure_logging
configure_logging()

import logging
from app.core.config import get_settings
from app.core.database import init_ai_pool, close_ai_pool
from app.services.qdrant_service import qdrant_service
from app.services.neo4j_service import neo4j_service
from app.worker.kafka_producer import close_kafka_producer, publish_ai_job_status

logger   = logging.getLogger("kafka_worker")
settings = get_settings()


# ── Document indexing ─────────────────────────────────────────────────────────

async def process_document_event(payload: dict):
    content_id   = payload.get("content_id")
    course_id    = payload.get("course_id")
    file_url     = payload.get("file_url", "")
    content_type = payload.get("content_type", "")

    logger.info("Document event received",
                extra={"content_id": content_id, "course_id": course_id,
                       "content_type": content_type})

    from app.services.auto_index_service import auto_index_service
    await auto_index_service._update_content_status(content_id, "processing")

    try:
        if content_type in ("text/markdown", "TEXT"):
            await auto_index_service.auto_index_text(
                content_id=content_id, course_id=course_id,
                title=payload.get("title", ""),
                text_content=payload.get("text_content", ""),
            )
        elif _is_youtube(file_url):
            await auto_index_service.auto_index(
                content_id=content_id, course_id=course_id,
                file_url=file_url, content_type="video/youtube", file_bytes=b"",
            )
        else:
            file_bytes = await auto_index_service._download_bytes(file_url)
            await auto_index_service.auto_index(
                content_id=content_id, course_id=course_id,
                file_url=file_url, content_type=content_type, file_bytes=file_bytes,
            )

        logger.info("Document indexed successfully",
                    extra={"content_id": content_id, "course_id": course_id})

    except Exception as exc:
        logger.error("Document indexing failed",
                     extra={"content_id": content_id, "error": str(exc),
                            "traceback": traceback.format_exc()})
        await auto_index_service._update_content_status(content_id, "failed", str(exc))


# ── Graph maintenance ─────────────────────────────────────────────────────────

async def process_graph_command(payload: dict):
    command = payload.get("command")
    logger.info("Graph command received", extra={"command": command})

    from app.worker.kafka_producer import publish_graph_event
    try:
        if command == "GLOBAL_LINK":
            from app.services.graph_linker import link_global_graph
            await publish_graph_event(command, "processing")
            count = await link_global_graph()
            await publish_graph_event(command, "completed", result_count=count)
            logger.info("Global linking complete", extra={"edges_created": count})
        elif command == "CONSOLIDATE_GRAPH":
            from app.services.graph_consolidation_service import consolidate_graph
            course_id    = payload.get("course_id")
            triggered_by = payload.get("triggered_by")
            if course_id is None:
                await publish_graph_event(command, "failed", error="missing course_id")
                return
            await publish_graph_event(command, "processing")
            result = await consolidate_graph(int(course_id), triggered_by)
            await publish_graph_event(
                command, "completed",
                result_count=result.get("absorbed_nodes", 0),
            )
            logger.info(
                "Graph consolidation complete",
                extra={"course_id": course_id,
                       "merged_groups": result.get("merged_groups", 0),
                       "absorbed_nodes": result.get("absorbed_nodes", 0)},
            )
        else:
            logger.warning("Unknown graph command", extra={"command": command})
    except Exception as exc:
        logger.error("Graph command failed",
                     extra={"command": command, "error": str(exc)})
        await publish_graph_event(command, "failed", error=str(exc))


# ── Maintenance tasks ─────────────────────────────────────────────────────────

async def process_maintenance_command(payload: dict):
    command = payload.get("command")
    logger.info("Maintenance command received", extra={"command": command})
    try:
        if command == "REINDEX_CONTENT":
            from app.services.reindex_service import reindex_service
            content_id = payload.get("content_id")
            course_id  = payload.get("course_id")
            result = await reindex_service.reindex_content_sync(content_id, course_id)
            logger.info("Reindex complete",
                        extra={"content_id": content_id, "chunks": result.get("chunks")})
        elif command == "DELETE_COURSE":
            from app.services.auto_index_service import auto_index_service
            course_id = payload.get("course_id")
            if course_id is not None:
                await auto_index_service.delete_course_data(int(course_id))
                logger.info("Course data deleted", extra={"course_id": course_id})
            else:
                logger.warning("DELETE_COURSE received with missing course_id")
        elif command == "DELETE_CONTENT":
            from app.services.auto_index_service import auto_index_service
            content_id = payload.get("content_id")
            if content_id is not None:
                await auto_index_service.delete_content_data(int(content_id))
                logger.info("Content data deleted", extra={"content_id": content_id})
            else:
                logger.warning("DELETE_CONTENT received with missing content_id")
        else:
            logger.warning("Unknown maintenance command", extra={"command": command})
    except Exception as exc:
        logger.error("Maintenance command failed",
                     extra={"command": command, "error": str(exc)})


# ── AI commands ───────────────────────────────────────────────────────────────

async def process_ai_command(payload: dict):
    job_id       = payload.get("job_id")
    command_type = payload.get("command_type")
    job_payload  = payload.get("payload", {})

    if not job_id or not command_type:
        logger.error("Invalid ai.command payload — missing job_id or command_type",
                     extra={"payload_keys": list(payload.keys())})
        return

    logger.info("AI command received",
                extra={"job_id": job_id, "command_type": command_type})

    try:
        await publish_ai_job_status(job_id=job_id, status="processing")
        result = None

        if command_type == "GENERATE_QUIZ":
            from app.services.quiz_service import quiz_gen_service
            result = await quiz_gen_service.generate_for_node(
                node_id=job_payload.get("node_id"),
                course_id=job_payload.get("course_id"),
                created_by=job_payload.get("created_by"),
                bloom_levels=job_payload.get("bloom_levels"),
                language=job_payload.get("language", "vi"),
                questions_per_level=job_payload.get("questions_per_level", 1),
            )

        elif command_type == "GENERATE_FLASHCARD":
            from app.services.flashcard_service import flashcard_srv
            flashcards = await flashcard_srv.generate_flashcards_with_llm(
                student_id=job_payload.get("student_id"),
                node_id=job_payload.get("node_id"),
                lesson_id=job_payload.get("lesson_id"),
                content_id=job_payload.get("content_id"),
                course_id=job_payload.get("course_id"),
                count=job_payload.get("count", 5),
                language=job_payload.get("language", "vi"),
            )
            result = {"flashcards": flashcards, "count": len(flashcards)}

        elif command_type == "DIAGNOSE_ERROR":
            from app.services.diagnosis_service import diagnosis_service
            dr = await diagnosis_service.diagnose(
                student_id=job_payload.get("student_id"),
                attempt_id=job_payload.get("attempt_id"),
                question_id=job_payload.get("question_id"),
                wrong_answer=job_payload.get("wrong_answer"),
                course_id=job_payload.get("course_id"),
                question_text=job_payload.get("question_text", ""),
                question_type=job_payload.get("question_type", "SINGLE_CHOICE"),
                explanation=job_payload.get("explanation", ""),
                correct_answer=job_payload.get("correct_answer", ""),
                answer_options=job_payload.get("answer_options", []),
                node_id=job_payload.get("node_id"),
            )
            result = {
                "explanation":         dr.explanation,
                "gap_type":            dr.gap_type,
                "knowledge_gap":       dr.knowledge_gap,
                "study_suggestion":    dr.study_suggestion,
                "confidence":          dr.confidence,
                "source_chunk_id":     dr.source_chunk_id,
                "suggested_documents": dr.suggested_documents,
                "language":            dr.language,
            }

        elif command_type == "CONSOLIDATE_SESSION":
            from app.services.consolidation_service import consolidation_service
            from app.agents.memory.ltm import ltm

            session_id = job_payload.get("session_id")
            user_id = job_payload.get("user_id")
            messages = job_payload.get("messages", [])
            context = job_payload.get("context", {})
            course_id = context.get("course_id")
            agent_type = context.get("agent_type", "mentor")

            # 1. Deep entity extraction (updates postgres user_concept_mastery)
            deep_res = await consolidation_service.extract_entities_deep(messages, context)

            # 2. Episode summary generation
            summary = await consolidation_service.create_episode_summary(messages)

            # 3. Store episode in Qdrant + PG
            episode_id = None
            if summary and user_id and session_id:
                episode_id = await ltm.store_episode(
                    session_id=session_id,
                    user_id=int(user_id),
                    agent_type=agent_type,
                    summary_text=summary,
                    course_id=int(course_id) if course_id is not None else None,
                )

            result = {
                "deep_extraction": deep_res,
                "episode_summary": summary,
                "episode_id": episode_id,
            }

        else:
            logger.warning("Unknown AI command type",
                           extra={"command_type": command_type, "job_id": job_id})
            await publish_ai_job_status(
                job_id=job_id, status="failed",
                error=f"Unknown command: {command_type}",
            )
            return

        logger.info("AI command completed",
                    extra={"job_id": job_id, "command_type": command_type})
        await publish_ai_job_status(job_id=job_id, status="completed", result=result)

    except Exception as exc:
        logger.error("AI command failed",
                     extra={"job_id": job_id, "command_type": command_type,
                            "error": str(exc)})
        await publish_ai_job_status(job_id=job_id, status="failed", error=str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_youtube(url: str) -> bool:
    import re
    return bool(url and re.search(r"(youtube\.com|youtu\.be)", url))


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main():
    logger.info("Initializing AI Kafka Worker", extra={"event": "startup"})

    await init_ai_pool()
    logger.info("AI PostgreSQL pool ready")

    if getattr(settings, "neo4j_enabled", True):
        for attempt in range(1, 11):
            try:
                await neo4j_service.init()
                logger.info("Neo4j ready")
                break
            except Exception as exc:
                logger.warning("Neo4j init attempt failed",
                               extra={"attempt": attempt, "error": str(exc)})
                if attempt == 10:
                    logger.error("Neo4j init failed after 10 attempts — continuing without it")
                else:
                    await asyncio.sleep(min(attempt * 3, 30))

    if settings.use_qdrant:
        await qdrant_service.init_collections()
        logger.info("Qdrant collections ready")

    from app.core.embeddings import warm_up_models
    import concurrent.futures
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        await loop.run_in_executor(pool, warm_up_models)
    logger.info("Embedding models ready")

    brokers  = os.getenv("KAFKA_BROKERS", "kafka:9092")
    consumer = AIOKafkaConsumer(
        "lms.document.uploaded",
        "lms.graph.command",
        "lms.maintenance.command",
        "lms.ai.command",
        bootstrap_servers=brokers,
        group_id="ai-worker-group",
        value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        auto_offset_reset="earliest",
        # ── Tuned for long-running document processing (95+ image PDFs) ───
        # Default max_poll_interval_ms=300s is too tight: heavy PDFs can
        # take 5+ min for image extraction + VLM calls. Raising to 10 min
        # prevents Kafka from ejecting the worker mid-job.
        max_poll_interval_ms=600_000,    # 10 minutes
        session_timeout_ms=60_000,       # 60 seconds (default 10s)
        heartbeat_interval_ms=10_000,    # 10 seconds (default 3s)
        request_timeout_ms=70_000,       # must be > session_timeout_ms
    )

    await consumer.start()
    logger.info("Kafka Worker ready",
                extra={"group_id": "ai-worker-group", "brokers": brokers})

    try:
        async for msg in consumer:
            if not msg.value:
                continue
            logger.debug("Kafka message received",
                         extra={"topic": msg.topic, "partition": msg.partition,
                                "offset": msg.offset})
            payload = msg.value

            if msg.topic == "lms.document.uploaded":
                if "content_id" in payload:
                    await process_document_event(payload)
            elif msg.topic == "lms.graph.command":
                await process_graph_command(payload)
            elif msg.topic == "lms.ai.command":
                await process_ai_command(payload)
            elif msg.topic == "lms.maintenance.command":
                await process_maintenance_command(payload)

    except asyncio.CancelledError:
        logger.info("Worker cancelled", extra={"event": "shutdown"})
    finally:
        await consumer.stop()
        await close_kafka_producer()
        await close_ai_pool()
        if getattr(settings, "neo4j_enabled", True):
            await neo4j_service.close()
        if settings.use_qdrant:
            await qdrant_service.close()
        logger.info("Kafka Worker shut down cleanly", extra={"event": "shutdown"})


if __name__ == "__main__":
    asyncio.run(main())
