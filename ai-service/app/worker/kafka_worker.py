import asyncio
import os
import traceback
import signal
from aiokafka import AIOKafkaConsumer
from app.worker.partition_consumer import PartitionConsumer, InvalidEnvelope
from app.worker.health import serve_health
from app.worker.contracts import MEMORY_TOPIC, MEMORY_GROUP, BATCH_GROUP

# Configure structured logging before other imports
from app.core.logging_config import configure_logging

configure_logging()

import logging
from app.core.config import get_settings
from app.core.database import init_ai_pool, close_ai_pool
from app.services.qdrant_service import qdrant_service
from app.services.neo4j_service import neo4j_service
from app.worker.kafka_producer import close_kafka_producer, publish_ai_job_status

logger = logging.getLogger("kafka_worker")
settings = get_settings()


# ── Document indexing ─────────────────────────────────────────────────────────


async def process_document_event(payload: dict):
    content_id = payload.get("content_id")
    course_id = payload.get("course_id")
    file_url = payload.get("file_url", "")
    content_type = payload.get("content_type", "")

    logger.info(
        "Document event received",
        extra={
            "content_id": content_id,
            "course_id": course_id,
            "content_type": content_type,
        },
    )

    from app.services.auto_index_service import auto_index_service

    await auto_index_service._update_content_status(content_id, "processing")

    async def _heartbeat() -> None:
        # Long documents may legitimately run for well over an hour. Refresh
        # both AI and LMS status so stale-job recovery never races a live job.
        while True:
            await asyncio.sleep(300)
            await auto_index_service._update_content_status(content_id, "processing")

    heartbeat_task = asyncio.create_task(
        _heartbeat(), name=f"index-heartbeat:{content_id}"
    )

    try:
        async with asyncio.timeout(settings.document_index_timeout_minutes * 60):
            if content_type in ("text/markdown", "TEXT"):
                await auto_index_service.auto_index_text(
                    content_id=content_id,
                    course_id=course_id,
                    title=payload.get("title", ""),
                    text_content=payload.get("text_content", ""),
                )
            elif _is_youtube(file_url):
                await auto_index_service.auto_index(
                    content_id=content_id,
                    course_id=course_id,
                    file_url=file_url,
                    content_type="video/youtube",
                    file_bytes=b"",
                )
            else:
                file_bytes = await auto_index_service._download_bytes(file_url)
                await auto_index_service.auto_index(
                    content_id=content_id,
                    course_id=course_id,
                    file_url=file_url,
                    content_type=content_type,
                    file_bytes=file_bytes,
                )

        logger.info(
            "Document indexed successfully",
            extra={"content_id": content_id, "course_id": course_id},
        )

    except asyncio.TimeoutError:
        error = f"Indexing exceeded the {settings.document_index_timeout_minutes}-minute limit; retry is available"
        logger.error("Document indexing timed out", extra={"content_id": content_id})
        await auto_index_service._update_content_status(content_id, "failed", error)
    except asyncio.CancelledError:
        # Mark the durable state before Kubernetes stops the process. The
        # Kafka offset remains uncommitted, so the next worker can replay it.
        await auto_index_service._update_content_status(
            content_id,
            "failed",
            "Indexing was interrupted; retry is available",
        )
        raise
    except Exception as exc:
        logger.error(
            "Document indexing failed",
            extra={
                "content_id": content_id,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        await auto_index_service._update_content_status(content_id, "failed", str(exc))
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)


# ── Graph maintenance ─────────────────────────────────────────────────────────


async def process_graph_command(payload: dict):
    command = payload.get("command")
    course_id = payload.get("course_id")
    job_id = payload.get("job_id")
    logger.info(
        "Graph command received", extra={"command": command, "course_id": course_id}
    )

    from app.worker.kafka_producer import publish_graph_event

    try:
        if command == "GLOBAL_LINK":
            from app.services.graph_linker import link_global_graph

            await publish_graph_event(command, "processing", job_id=job_id)
            count = await link_global_graph()
            await publish_graph_event(
                command, "completed", result_count=count, job_id=job_id
            )
            logger.info("Global linking complete", extra={"edges_created": count})

        elif command == "CONSOLIDATE_GRAPH":
            from app.services.graph_consolidation_service import consolidate_graph

            triggered_by = payload.get("triggered_by")
            selected_survivor_ids = payload.get("selected_survivor_ids")
            if course_id is None:
                await publish_graph_event(
                    command,
                    "failed",
                    error="missing course_id",
                    course_id=course_id,
                    job_id=job_id,
                )
                return
            await publish_graph_event(
                command, "processing", course_id=course_id, job_id=job_id
            )
            result = await consolidate_graph(
                int(course_id), triggered_by, selected_survivor_ids
            )
            await publish_graph_event(
                command,
                "completed",
                result_count=(
                    result.get("absorbed_nodes", 0)
                    + result.get("orphaned_nodes_removed", 0)
                ),
                course_id=course_id,
                job_id=job_id,
            )
            logger.info(
                "Graph consolidation complete",
                extra={
                    "course_id": course_id,
                    "merged_groups": result.get("merged_groups", 0),
                    "absorbed_nodes": result.get("absorbed_nodes", 0),
                    "orphaned_nodes_removed": result.get("orphaned_nodes_removed", 0),
                },
            )

        elif command == "LINK_ISOLATED_NODES":
            from app.services.graph_linker import link_isolated_nodes_for_course
            from app.services.graph_job_tracker import set_job_status

            if course_id is None:
                await publish_graph_event(
                    command,
                    "failed",
                    error="missing course_id",
                    course_id=course_id,
                    job_id=job_id,
                )
                return
            cid = int(course_id)
            set_job_status(cid, job_id, "processing")
            await publish_graph_event(
                command, "processing", course_id=cid, job_id=job_id
            )
            try:
                count = await link_isolated_nodes_for_course(cid)
                set_job_status(cid, job_id, "completed", edges_created=count)
                await publish_graph_event(
                    command,
                    "completed",
                    result_count=count,
                    course_id=cid,
                    job_id=job_id,
                )
                logger.info(
                    "Link-isolated complete",
                    extra={"course_id": cid, "edges_created": count},
                )
            except Exception as exc:
                set_job_status(cid, job_id, "failed", error=str(exc))
                raise

        elif command == "LINK_ALL_NODES":
            from app.services.graph_linker import link_all_nodes_for_course
            from app.services.graph_job_tracker import set_job_status

            if course_id is None:
                await publish_graph_event(
                    command,
                    "failed",
                    error="missing course_id",
                    course_id=course_id,
                    job_id=job_id,
                )
                return
            cid = int(course_id)
            set_job_status(cid, job_id, "processing")
            await publish_graph_event(
                command, "processing", course_id=cid, job_id=job_id
            )
            try:
                count = await link_all_nodes_for_course(cid)
                set_job_status(cid, job_id, "completed", edges_created=count)
                await publish_graph_event(
                    command,
                    "completed",
                    result_count=count,
                    course_id=cid,
                    job_id=job_id,
                )
                logger.info(
                    "Link-all complete",
                    extra={"course_id": cid, "edges_created": count},
                )
            except Exception as exc:
                set_job_status(cid, job_id, "failed", error=str(exc))
                raise

        else:
            logger.warning("Unknown graph command", extra={"command": command})

    except Exception as exc:
        logger.error(
            "Graph command failed", extra={"command": command, "error": str(exc)}
        )
        await publish_graph_event(
            command, "failed", error=str(exc), course_id=course_id, job_id=job_id
        )


# ── Maintenance tasks ─────────────────────────────────────────────────────────


async def process_maintenance_command(payload: dict):
    command = payload.get("command")
    logger.info("Maintenance command received", extra={"command": command})
    try:
        if command == "REINDEX_CONTENT":
            from app.services.reindex_service import reindex_service

            content_id = payload.get("content_id")
            course_id = payload.get("course_id")
            result = await reindex_service.reindex_content_sync(content_id, course_id)
            logger.info(
                "Reindex complete",
                extra={"content_id": content_id, "chunks": result.get("chunks")},
            )
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
        logger.error(
            "Maintenance command failed", extra={"command": command, "error": str(exc)}
        )
        # Do not let the main loop commit a failed destructive command. The
        # worker will restart and Kafka will replay the uncommitted message.
        raise


# ── AI commands ───────────────────────────────────────────────────────────────


async def process_ai_command(payload: dict):
    job_id = payload.get("job_id")
    command_type = payload.get("command_type")
    job_payload = payload.get("payload", {})

    if not job_id or not command_type:
        logger.error(
            "Invalid ai.command payload - missing job_id or command_type",
            extra={"payload_keys": list(payload.keys())},
        )
        return

    logger.info(
        "AI command received", extra={"job_id": job_id, "command_type": command_type}
    )

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

        elif command_type == "INDEX_QUIZ":
            from app.services.quiz_index_service import process_serialized

            result = await process_serialized(job_id, int(job_payload["quiz_id"]))

        elif command_type == "ANALYZE_QUIZ_RESULTS":
            from app.services.quiz_insights_service import process_quiz_insights

            result = await process_quiz_insights(job_id, job_payload)

        elif command_type == "PERSONAL_FLASHCARD":
            from app.services.personal_flashcard_service import (
                process_personal_flashcard_job,
            )

            status = await process_personal_flashcard_job(job_id)
            if status != "completed":
                await publish_ai_job_status(
                    job_id=job_id,
                    status="failed",
                    error="Personal flashcard job failed",
                )
                return
            result = {"job_id": job_id}

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
                "explanation": dr.explanation,
                "gap_type": dr.gap_type,
                "knowledge_gap": dr.knowledge_gap,
                "study_suggestion": dr.study_suggestion,
                "confidence": dr.confidence,
                "source_chunk_id": dr.source_chunk_id,
                "suggested_documents": dr.suggested_documents,
                "language": dr.language,
            }

        elif command_type == "CONSOLIDATE_SESSION":
            from app.agents.memory.consolidation_pipeline import consolidate_session_job

            result = await consolidate_session_job(job_payload)

        else:
            logger.warning(
                "Unknown AI command type",
                extra={"command_type": command_type, "job_id": job_id},
            )
            await publish_ai_job_status(
                job_id=job_id,
                status="failed",
                error=f"Unknown command: {command_type}",
            )
            return

        logger.info(
            "AI command completed",
            extra={"job_id": job_id, "command_type": command_type},
        )
        await publish_ai_job_status(job_id=job_id, status="completed", result=result)

    except Exception as exc:
        logger.error(
            "AI command failed",
            extra={"job_id": job_id, "command_type": command_type, "error": str(exc)},
        )
        await publish_ai_job_status(job_id=job_id, status="failed", error=str(exc))
        if command_type == "CONSOLIDATE_SESSION":
            from app.agents.memory.consolidation_pipeline import ConsolidationRejected

            if isinstance(exc, ConsolidationRejected):
                return  # Persisted authorization rejection is terminal.
        if command_type == "INDEX_QUIZ":
            # The quiz row records terminal failure or a bounded scheduled retry.
            # Recovery owns retries, rather than two independent retry loops.
            return
        raise


async def process_personalize_profile_update(payload: dict):
    user_id = payload.get("user_id")
    course_id = payload.get("course_id")
    profile = payload.get("profile", {})
    if not user_id or not course_id:
        logger.warning("Received personalization profile update with missing keys")
        return

    logger.info(
        "Personalization profile update received",
        extra={"user_id": user_id, "course_id": course_id},
    )
    from app.services.mastery_service import mastery_service

    try:
        await mastery_service.sync_duckdb_personalization_profile(
            int(user_id), int(course_id), profile
        )
    except Exception as e:
        logger.error(
            "Failed to sync personalization profile to Postgres",
            extra={"error": str(e)},
        )
        raise


# ── Helpers ───────────────────────────────────────────────────────────────────


def _is_youtube(url: str) -> bool:
    import re

    return bool(url and re.search(r"(youtube\.com|youtu\.be)", url))


# ── Main loop ─────────────────────────────────────────────────────────────────

BATCH_TOPICS = (
    "lms.document.uploaded",
    "lms.graph.command",
    "lms.maintenance.command",
    "lms.ai.command",
    "personalize.profile.updated",
)
INTERACTIVE_TOPIC = os.getenv("AI_INTERACTIVE_TOPIC", "lms.ai.interactive")
INTERACTIVE_GROUP = os.getenv("AI_INTERACTIVE_GROUP", "ai-worker-interactive")
DEFAULT_INTERACTIVE_CONCURRENCY = 2


def _build_consumer(topics: tuple[str, ...], group_id: str) -> AIOKafkaConsumer:
    return AIOKafkaConsumer(
        *topics,
        bootstrap_servers=os.getenv("KAFKA_BROKERS", "kafka:9092"),
        group_id=group_id,
        # Decode inside the handler so malformed bytes can be quarantined.
        value_deserializer=None,
        client_id=os.getenv("HOSTNAME", "ai-worker") + ":" + group_id,
        auto_offset_reset="earliest",
        # A document can take many minutes to extract, embed and persist. Auto
        # commit used to acknowledge the record while that work was still in
        # flight, so a worker/broker restart could permanently lose the job.
        # Commit only after the handler has reached a terminal state.
        enable_auto_commit=False,
        max_poll_interval_ms=settings.document_index_max_poll_interval_ms,
        session_timeout_ms=60_000,
        heartbeat_interval_ms=10_000,
        request_timeout_ms=70_000,
    )


async def _dispatch_batch(msg) -> None:
    payload = msg.value
    if msg.topic == "lms.document.uploaded":
        if "content_id" in payload:
            await process_document_event(payload)
    elif msg.topic == "lms.graph.command":
        await process_graph_command(payload)
    elif msg.topic == "lms.ai.command":
        if payload.get("command_type") == "CONSOLIDATE_SESSION":
            # Drain legacy producers/backlog. Acknowledge source only after the
            # dedicated memory topic has durably accepted the same job identity.
            from app.worker.kafka_producer import get_kafka_producer

            session_id = (payload.get("payload") or {}).get("session_id")
            if not isinstance(session_id, str) or not session_id:
                raise InvalidEnvelope("Memory command requires a session ID")
            producer = await get_kafka_producer()
            await producer.send_and_wait(
                MEMORY_TOPIC, key=session_id.encode(), value=payload
            )
            logger.info(
                "Legacy memory command forwarded",
                extra={
                    "job_id": payload.get("job_id"),
                    "destination_topic": MEMORY_TOPIC,
                },
            )
        else:
            await _dispatch_command(msg, memory=False)
    elif msg.topic == "lms.maintenance.command":
        await process_maintenance_command(payload)
    elif msg.topic == "personalize.profile.updated":
        await process_personalize_profile_update(payload)


async def _dispatch_command(msg, *, memory=False):
    payload = msg.value
    command = payload.get("command_type")
    version = payload.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise InvalidEnvelope("Unsupported AI command schema version")
    if not isinstance(command, str) or command not in {
        "GENERATE_QUIZ",
        "INDEX_QUIZ",
        "ANALYZE_QUIZ_RESULTS",
        "PERSONAL_FLASHCARD",
        "GENERATE_FLASHCARD",
        "DIAGNOSE_ERROR",
        "CONSOLIDATE_SESSION",
    }:
        raise InvalidEnvelope("Unsupported AI command")
    if (
        not isinstance(command, str)
        or not isinstance(payload.get("job_id"), str)
        or not payload.get("job_id", "").strip()
        or not isinstance(payload.get("payload"), dict)
    ):
        raise InvalidEnvelope("AI command requires job_id, command_type and payload")
    if memory and command != "CONSOLIDATE_SESSION":
        raise InvalidEnvelope("Memory lane accepts consolidation only")
    if not memory and command == "CONSOLIDATE_SESSION":
        raise InvalidEnvelope("Memory command must use the memory lane")
    async with asyncio.timeout(
        120 if memory else 180 if msg.topic == INTERACTIVE_TOPIC else 600
    ):
        await process_ai_command(payload)


async def _dispatch_interactive(msg):
    # Keep the existing diagnosis-only contract explicit.
    if msg.value.get("command_type") != "DIAGNOSE_ERROR":
        raise InvalidEnvelope("Unsupported interactive command")
    await _dispatch_command(msg)


async def _dispatch_memory(msg):
    await _dispatch_command(msg, memory=True)


async def main():
    mode = os.getenv("AI_WORKER_MODE", "batch").strip().lower()
    if mode not in {"batch", "interactive", "memory", "all"}:
        raise SystemExit(f"Unsupported AI_WORKER_MODE={mode!r}")
    consumers, lanes, tasks, background = [], [], [], []
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stopping.set)
    server = await serve_health(
        lambda: bool(lanes) and not stopping.is_set() and all(l.ready for l in lanes)
    )
    stop_task = asyncio.create_task(stopping.wait(), name="worker-stop")
    try:
        logger.info("Initializing AI Kafka Worker", extra={"mode": mode})
        await init_ai_pool()
        if mode in {"batch", "all"}:
            if settings.neo4j_enabled:
                await neo4j_service.init()
            if settings.use_qdrant:
                await qdrant_service.init_collections()
            from app.core.embeddings import warm_up_models

            await asyncio.to_thread(warm_up_models)
        # Interactive/memory load optional model clients lazily. They do not
        # wait for document extraction models before joining their own group.
        definitions = []
        if mode in {"batch", "all"}:
            definitions.append((BATCH_TOPICS, BATCH_GROUP, _dispatch_batch, 1))
            from app.services.studio.jobs import serve as serve_studio_jobs
            from app.services.speech_service import serve_speech
            from app.services.studio.temporary_media import serve_cleanup
            from app.services.studio.youtube_publishing import serve_uploads
            from app.services.quiz_index_service import serve_recovery

            for name, serve in (
                ("studio", serve_studio_jobs),
                ("speech", serve_speech),
                ("cleanup", serve_cleanup),
                ("uploads", serve_uploads),
                ("quiz-recovery", serve_recovery),
            ):
                background.append(asyncio.create_task(serve(), name=name))
        if mode in {"interactive", "all"}:
            concurrency = min(
                6,
                max(
                    1,
                    int(
                        os.getenv(
                            "AI_INTERACTIVE_CONCURRENCY",
                            str(DEFAULT_INTERACTIVE_CONCURRENCY),
                        )
                    ),
                ),
            )
            definitions.append(
                (
                    (INTERACTIVE_TOPIC,),
                    INTERACTIVE_GROUP,
                    _dispatch_interactive,
                    concurrency,
                )
            )
        if mode in {"memory", "all"}:
            definitions.append(((MEMORY_TOPIC,), MEMORY_GROUP, _dispatch_memory, 1))
        for topics, group, handler, concurrency in definitions:
            consumer = _build_consumer(topics, group)
            lane = PartitionConsumer(
                consumer, topics, group, handler, concurrency=concurrency
            )
            consumers.append(consumer)
            lanes.append(lane)
            await consumer.start()
            tasks.append(asyncio.create_task(lane.run(), name=group))
        logger.info("Kafka Worker started", extra={"mode": mode})
        done, _ = await asyncio.wait(
            [*tasks, *background, stop_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            if task is not stop_task:
                task.result()
                raise RuntimeError(
                    f"Worker task stopped unexpectedly: {task.get_name()}"
                )
    finally:
        stopping.set()
        # Quiesce recovery/background work before draining Kafka handlers.
        for task in [*background, stop_task]:
            task.cancel()
        await asyncio.gather(*background, stop_task, return_exceptions=True)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for consumer in consumers:
            await consumer.stop()
        await close_kafka_producer()
        await close_ai_pool()
        if settings.neo4j_enabled:
            await neo4j_service.close()
        if settings.use_qdrant:
            await qdrant_service.close()
        server.close()
        await server.wait_closed()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)
        logger.info("Kafka Worker stopped", extra={"mode": mode})


if __name__ == "__main__":
    asyncio.run(main())
