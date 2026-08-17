"""
ai-service/app/api/endpoints/auto_index.py

POST /ai/auto-index              - trigger auto-indexing via Kafka
POST /ai/auto-index/text         - trigger text content indexing via Kafka
GET  /ai/auto-index/{id}/status  - poll status from AI DB (no Celery)

POST /ai/knowledge-graph/global          - trigger global cross-course linking
GET  /ai/knowledge-graph/global          - get full graph (admin)
GET  /ai/knowledge-graph/{course_id}     - get course graph
DELETE /ai/knowledge-graph/node/{node_id}
GET  /ai/knowledge-graph/node/{node_id}/neighbors
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import get_ai_conn

logger   = logging.getLogger(__name__)
settings = get_settings()
_STALE_INDEX_AFTER_MINUTES = max(15, settings.document_index_stale_after_minutes)

router       = APIRouter(prefix="/auto-index",      tags=["Auto-Index"])
graph_router = APIRouter(prefix="/knowledge-graph", tags=["Knowledge Graph"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class AutoIndexRequest(BaseModel):
    content_id: int
    course_id: int
    file_url: str
    content_type: str = "application/pdf"
    force: bool = False


class AutoIndexTextRequest(BaseModel):
    content_id: int
    course_id: int
    title: str
    text_content: str
    force: bool = False


class AutoIndexResponse(BaseModel):
    job_id: str
    content_id: int
    status: str = "queued"
    message: str = "Document queued for auto-indexing"


class AutoIndexStatusResponse(BaseModel):
    content_id: int
    status: str
    nodes_created: int = 0
    chunks_created: int = 0
    progress: int = 0
    stage: str = ""
    error: Optional[str] = None


class GraphNode(BaseModel):
    id: int
    name: str
    name_vi: Optional[str]
    name_en: Optional[str]
    description: Optional[str]
    source_content_id: Optional[int]
    source_content_title: Optional[str]
    course_id: Optional[int] = None
    auto_generated: bool
    chunk_count: int
    level: int


class GraphEdge(BaseModel):
    source: int
    target: int
    relation_type: str
    strength: float
    auto_generated: bool


class KnowledgeGraphResponse(BaseModel):
    course_id: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _upsert_content_status(content_id: int, course_id: int, status: str, title: str = ""):
    async with get_ai_conn() as conn:
        await conn.execute(
            """
            INSERT INTO content_index_status (content_id, course_id, title, status, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (content_id) DO UPDATE
                SET status = $4, updated_at = NOW()
            """,
            content_id, course_id, title, status,
        )


async def _get_content_status(content_id: int) -> dict | None:
    async with get_ai_conn() as conn:
        await conn.execute(
            """
            UPDATE content_index_status
               SET status = 'failed',
                   error = 'Indexing was interrupted; retry is available',
                   updated_at = NOW()
             WHERE content_id = $1
               AND status IN ('pending', 'processing')
               AND updated_at < NOW() - ($2::int * INTERVAL '1 minute')
            """,
            content_id, _STALE_INDEX_AFTER_MINUTES,
        )
        row = await conn.fetchrow(
            "SELECT status, error FROM content_index_status WHERE content_id=$1",
            content_id,
        )
    return dict(row) if row else None


async def _build_title_map(content_ids: list[int]) -> dict[int, str]:
    if not content_ids:
        return {}
    async with get_ai_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT source_content_id, source_content_title
            FROM knowledge_nodes
            WHERE source_content_id = ANY($1)
              AND source_content_title IS NOT NULL
              AND source_content_title != ''
            """,
            content_ids,
        )
    return {r["source_content_id"]: r["source_content_title"] for r in rows}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", response_model=AutoIndexResponse)
async def trigger_auto_index(body: AutoIndexRequest, request: Request):
    _verify(request)

    if not body.force:
        status_data = await _get_content_status(body.content_id)
        if status_data and status_data.get("status") in ("pending", "processing"):
            return AutoIndexResponse(job_id=f"content-{body.content_id}", content_id=body.content_id)

    if body.force:
        from app.services.auto_index_service import auto_index_service
        await auto_index_service.delete_content_data(body.content_id)

    await _upsert_content_status(body.content_id, body.course_id, "processing")

    from app.worker.kafka_producer import get_kafka_producer
    producer = await get_kafka_producer()
    await producer.send_and_wait("lms.document.uploaded", value={
        "content_id":   body.content_id,
        "course_id":    body.course_id,
        "file_url":     body.file_url,
        "content_type": body.content_type,
        "force":        body.force,
    })

    return AutoIndexResponse(job_id=f"content-{body.content_id}", content_id=body.content_id)


@router.post("/text", response_model=AutoIndexResponse)
async def trigger_auto_index_text(body: AutoIndexTextRequest, request: Request):
    _verify(request)

    if not body.force:
        status_data = await _get_content_status(body.content_id)
        if status_data and status_data.get("status") in ("pending", "processing"):
            return AutoIndexResponse(job_id=f"content-{body.content_id}", content_id=body.content_id)

    if body.force:
        from app.services.auto_index_service import auto_index_service
        await auto_index_service.delete_content_data(body.content_id)

    await _upsert_content_status(body.content_id, body.course_id, "processing")

    from app.worker.kafka_producer import get_kafka_producer
    producer = await get_kafka_producer()
    await producer.send_and_wait("lms.document.uploaded", value={
        "content_id":   body.content_id,
        "course_id":    body.course_id,
        "title":        body.title,
        "text_content": body.text_content,
        "content_type": "TEXT",
        "force":        body.force,
    })

    return AutoIndexResponse(job_id=f"content-{body.content_id}", content_id=body.content_id)


@router.get("/{content_id}/status", response_model=AutoIndexStatusResponse)
async def get_auto_index_status(content_id: int, request: Request):
    _verify(request)

    status_data = await _get_content_status(content_id)
    ai_status   = status_data["status"] if status_data else "unindexed"

    async with get_ai_conn() as conn:
        nodes_row  = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM knowledge_nodes WHERE source_content_id=$1", content_id,
        )
        chunks_row = await conn.fetchrow(
            "SELECT COUNT(*) AS n FROM document_chunks WHERE content_id=$1 AND status='ready'", content_id,
        )

    # Map status -> rough progress percentage (no Celery task to query)
    progress_map = {"pending": 5, "processing": 50, "indexed": 100, "failed": 0}
    progress = progress_map.get(ai_status, 0)

    return AutoIndexStatusResponse(
        content_id=content_id,
        status=ai_status,
        nodes_created=nodes_row["n"]  or 0,
        chunks_created=chunks_row["n"] or 0,
        progress=progress,
        error=status_data.get("error") if status_data else None,
    )


class BatchStatusRequest(BaseModel):
    content_ids: list[int]


@router.post("/batch-status")
async def batch_get_auto_index_status(body: BatchStatusRequest, request: Request):
    """
    Batch-fetch index status for multiple content IDs in ONE round-trip.
    This replaces N individual /status calls, eliminating rate limiting
    when a teacher has many documents being indexed simultaneously.
    """
    _verify(request)

    ids = body.content_ids[:100]  # cap at 100 to prevent abuse
    if not ids:
        return {}

    async with get_ai_conn() as conn:
        # Surface abandoned work as retryable instead of leaving the UI in an
        # endless "processing" state after a Kafka/worker restart.
        await conn.execute(
            """
            UPDATE content_index_status
               SET status = 'failed',
                   error = 'Indexing was interrupted; retry is available',
                   updated_at = NOW()
             WHERE content_id = ANY($1)
               AND status IN ('pending', 'processing')
               AND updated_at < NOW() - ($2::int * INTERVAL '1 minute')
            """,
            ids, _STALE_INDEX_AFTER_MINUTES,
        )
        # 1. Batch-fetch statuses
        status_rows = await conn.fetch(
            "SELECT content_id, status, error FROM content_index_status WHERE content_id = ANY($1)",
            ids,
        )
        status_map = {r["content_id"]: dict(r) for r in status_rows}

        # 2. Batch-fetch node counts
        node_rows = await conn.fetch(
            """SELECT source_content_id, COUNT(*) AS n
               FROM knowledge_nodes
               WHERE source_content_id = ANY($1)
               GROUP BY source_content_id""",
            ids,
        )
        node_map = {r["source_content_id"]: r["n"] for r in node_rows}

        # 3. Batch-fetch chunk counts
        chunk_rows = await conn.fetch(
            """SELECT content_id, COUNT(*) AS n
               FROM document_chunks
               WHERE content_id = ANY($1) AND status = 'ready'
               GROUP BY content_id""",
            ids,
        )
        chunk_map = {r["content_id"]: r["n"] for r in chunk_rows}

    progress_map = {"pending": 5, "processing": 50, "indexed": 100, "failed": 0}
    result = {}
    for cid in ids:
        sd = status_map.get(cid)
        st = sd["status"] if sd else "unindexed"
        result[str(cid)] = {
            "content_id": cid,
            "status": st,
            "nodes_created": node_map.get(cid, 0),
            "chunks_created": chunk_map.get(cid, 0),
            "progress": progress_map.get(st, 0),
            "error": sd.get("error") if sd else None,
        }

    return result


# ── Knowledge Graph endpoints ──────────────────────────────────────────────────

@graph_router.get("/global")
async def get_global_knowledge_graph(
    request: Request,
    min_strength: float = 0.5,
    limit: int = 2000,
):
    _verify(request)

    if not settings.neo4j_enabled:
        raise HTTPException(status_code=501, detail="Neo4j not enabled")

    from app.services.neo4j_service import neo4j_service
    graph = await neo4j_service.get_global_graph(limit_nodes=limit, min_strength=min_strength)

    content_ids = [n["source_content_id"] for n in graph["nodes"] if n.get("source_content_id")]
    title_map   = await _build_title_map(content_ids)

    node_ids = [n["id"] for n in graph["nodes"]]
    chunk_counts: dict[int, int] = {}
    if node_ids:
        async with get_ai_conn() as conn:
            rows = await conn.fetch(
                "SELECT node_id, COUNT(*) AS n FROM document_chunks WHERE node_id = ANY($1) AND status = 'ready' GROUP BY node_id",
                node_ids,
            )
            chunk_counts = {r["node_id"]: r["n"] for r in rows}

    nodes = [
        GraphNode(
            id=n["id"], name=n.get("name", ""),
            name_vi=n.get("name_vi"), name_en=n.get("name_en"),
            description=n.get("description"),
            source_content_id=n.get("source_content_id"),
            source_content_title=title_map.get(n["source_content_id"]) if n.get("source_content_id") else None,
            course_id=n.get("course_id"),
            auto_generated=bool(n.get("auto_generated", True)),
            chunk_count=chunk_counts.get(n["id"], 0), level=0,
        )
        for n in graph["nodes"]
    ]
    edges = [
        GraphEdge(
            source=e["source"], target=e["target"],
            relation_type=e.get("relation_type", "RELATED").lower(),
            strength=float(e.get("strength", 0.5)),
            auto_generated=bool(e.get("auto_generated", True)),
        )
        for e in graph["edges"]
    ]
    return KnowledgeGraphResponse(course_id=0, nodes=nodes, edges=edges)


@graph_router.post("/link-global")
async def trigger_global_link(request: Request):
    _verify(request)

    from app.worker.kafka_producer import get_kafka_producer
    producer = await get_kafka_producer()
    await producer.send_and_wait("lms.graph.command", value={"command": "GLOBAL_LINK"})
    return {"ok": True, "message": "Global linking command queued via Kafka"}


# ── Compact Graph (intelligent node consolidation) ─────────────────────────────

class ConsolidateRequest(BaseModel):
    triggered_by: Optional[int] = None
    selected_survivor_ids: Optional[list[int]] = None


@graph_router.get("/{course_id}/consolidate/preview")
async def preview_graph_consolidation(course_id: int, request: Request):
    """Synchronous dry-run: returns the proposed merge plan, mutates nothing."""
    _verify(request)

    from app.services.graph_consolidation_service import graph_consolidation_service
    plan = await graph_consolidation_service.analyze_graph(course_id)
    return plan.to_dict()


@graph_router.post("/{course_id}/consolidate")
async def trigger_graph_consolidation(
    course_id: int,
    body: ConsolidateRequest,
    request: Request,
):
    """Fire-and-forget: enqueue the merge job on Kafka. Returns 202."""
    _verify(request)

    from app.worker.kafka_producer import get_kafka_producer
    producer = await get_kafka_producer()
    await producer.send_and_wait("lms.graph.command", value={
        "command":      "CONSOLIDATE_GRAPH",
        "course_id":    course_id,
        "triggered_by": body.triggered_by,
        "selected_survivor_ids": body.selected_survivor_ids,
    })
    return {
        "ok":      True,
        "status":  "queued",
        "job_id":  f"consolidate-{course_id}",
        "message": "Graph consolidation queued via Kafka",
    }


@graph_router.get("/{course_id}", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(course_id: int, request: Request):
    _verify(request)

    if settings.neo4j_enabled:
        from app.services.neo4j_service import neo4j_service
        graph = await neo4j_service.get_course_graph(course_id)

        content_ids = [n["source_content_id"] for n in graph["nodes"] if n.get("source_content_id")]
        title_map   = await _build_title_map(content_ids)

        node_ids = [n["id"] for n in graph["nodes"]]
        chunk_counts: dict[int, int] = {}
        if node_ids:
            async with get_ai_conn() as conn:
                rows = await conn.fetch(
                    "SELECT node_id, COUNT(*) AS n FROM document_chunks WHERE node_id = ANY($1) AND status = 'ready' GROUP BY node_id",
                    node_ids,
                )
                chunk_counts = {r["node_id"]: r["n"] for r in rows}

        nodes = [
            GraphNode(
                id=n["id"], name=n.get("name", ""),
                name_vi=n.get("name_vi"), name_en=n.get("name_en"),
                description=n.get("description"),
                source_content_id=n.get("source_content_id"),
                source_content_title=title_map.get(n["source_content_id"]) if n.get("source_content_id") else None,
                course_id=n.get("course_id", course_id),
                auto_generated=bool(n.get("auto_generated", True)),
                chunk_count=chunk_counts.get(n["id"], 0), level=0,
            )
            for n in graph["nodes"]
        ]
        edges = [
            GraphEdge(
                source=e["source"], target=e["target"],
                relation_type=e.get("relation_type", "RELATED").lower(),
                strength=float(e.get("strength", 0.5)),
                auto_generated=bool(e.get("auto_generated", True)),
            )
            for e in graph["edges"]
        ]
        return KnowledgeGraphResponse(course_id=course_id, nodes=nodes, edges=edges)

    # Fallback: PostgreSQL path
    async with get_ai_conn() as conn:
        node_rows = await conn.fetch(
            """
            SELECT kn.id, kn.course_id, kn.name, kn.name_vi, kn.name_en, kn.description,
                   kn.source_content_id, kn.source_content_title,
                   kn.auto_generated, kn.level,
                   COUNT(DISTINCT dc.id) AS chunk_count
            FROM knowledge_nodes kn
            LEFT JOIN document_chunks dc ON dc.node_id = kn.id
            WHERE kn.course_id = $1
            GROUP BY kn.id, kn.course_id, kn.name, kn.name_vi, kn.name_en, kn.description,
                     kn.source_content_id, kn.source_content_title, kn.auto_generated, kn.level
            ORDER BY kn.level, kn.order_index
            """,
            course_id,
        )
        edge_rows = await conn.fetch(
            """
            SELECT source_node_id, target_node_id, relation_type, strength, auto_generated
            FROM knowledge_node_relations WHERE course_id = $1 ORDER BY strength DESC
            """,
            course_id,
        )

    nodes = [
        GraphNode(
            id=r["id"], name=r["name"], name_vi=r["name_vi"], name_en=r["name_en"],
            description=r["description"], source_content_id=r["source_content_id"],
            source_content_title=r["source_content_title"] if r["source_content_id"] else None,
            course_id=r["course_id"], auto_generated=r["auto_generated"],
            chunk_count=r["chunk_count"] or 0, level=r["level"],
        )
        for r in node_rows
    ]
    edges = [
        GraphEdge(
            source=r["source_node_id"], target=r["target_node_id"],
            relation_type=r["relation_type"], strength=float(r["strength"]),
            auto_generated=r["auto_generated"],
        )
        for r in edge_rows
    ]
    return KnowledgeGraphResponse(course_id=course_id, nodes=nodes, edges=edges)


@graph_router.delete("/node/{node_id}")
async def delete_knowledge_node(node_id: int, request: Request):
    _verify(request)

    from app.services.auto_index_service import auto_index_service
    await auto_index_service.delete_nodes_bulk([node_id])

    return {"ok": True, "deleted_node_id": node_id}


@graph_router.get("/node/{node_id}/neighbors")
async def get_node_neighbors(
    node_id: int,
    request: Request,
    depth: int = 2,
    max_nodes: int = 50,
):
    _verify(request)

    if not settings.neo4j_enabled:
        raise HTTPException(status_code=501, detail="Neo4j not enabled")

    from app.services.neo4j_service import neo4j_service
    result = await neo4j_service.get_node_neighbors(
        node_id=node_id, max_depth=min(depth, 4), max_nodes=min(max_nodes, 200),
    )

    all_nodes = [result.get("center")] if result.get("center") else []
    all_nodes.extend(result.get("neighbors", []))
    content_ids = [n["source_content_id"] for n in all_nodes if n and n.get("source_content_id")]
    title_map   = await _build_title_map(content_ids)

    nodes = [
        GraphNode(
            id=n["id"], name=n.get("name", ""),
            name_vi=n.get("name_vi"), name_en=n.get("name_en"),
            description=n.get("description"),
            source_content_id=n.get("source_content_id"),
            source_content_title=title_map.get(n["source_content_id"]) if n.get("source_content_id") else None,
            course_id=n.get("course_id"),
            auto_generated=bool(n.get("auto_generated", True)),
            chunk_count=0, level=0,
        )
        for n in all_nodes if n
    ]
    edges = [
        GraphEdge(
            source=e["source"], target=e["target"],
            relation_type=e.get("relation_type", "RELATED").lower(),
            strength=float(e.get("strength", 0.5)),
            auto_generated=bool(e.get("auto_generated", True)),
        )
        for e in result.get("edges", [])
    ]
    return KnowledgeGraphResponse(course_id=0, nodes=nodes, edges=edges)


@router.delete("/course/{course_id}")
async def delete_course_index(course_id: int, request: Request):
    _verify(request)
    from app.services.auto_index_service import auto_index_service
    await auto_index_service.delete_course_data(course_id)
    return {"ok": True, "message": f"Course {course_id} data deleted successfully"}


@router.delete("/content/{content_id}")
async def delete_content_index(content_id: int, request: Request):
    _verify(request)
    from app.services.auto_index_service import auto_index_service
    await auto_index_service.delete_content_data(content_id)
    return {"ok": True, "message": f"Content {content_id} data deleted successfully"}


# ── Graph Teacher Tools ────────────────────────────────────────────────────────

_VALID_RELATION_TYPES = {"prerequisite", "extends", "related", "equivalent", "contrasts_with"}


class LinkIsolatedResponse(BaseModel):
    job_id: str
    course_id: int
    status: str = "queued"
    message: str = "Isolated node linking queued. You will be notified when complete."


class EdgeUpsertRequest(BaseModel):
    source_node_id: int
    target_node_id: int
    relation_type: str          # prerequisite | extends | related | equivalent | contrasts_with
    strength: float = 0.85      # 0.6 – 1.0
    reason: str = ""
    bidirectional: bool = False  # if True, also create the reverse edge


class EdgeUpsertResponse(BaseModel):
    source_node_id: int
    target_node_id: int
    relation_type: str
    strength: float
    auto_generated: bool = False


class EdgeDeleteRequest(BaseModel):
    source_node_id: int
    target_node_id: int
    relation_type: Optional[str] = None  # None → delete ALL edges between the pair


@graph_router.post("/{course_id}/link-isolated", response_model=LinkIsolatedResponse)
async def trigger_link_isolated_nodes(course_id: int, request: Request):
    """Trigger an async Kafka job that finds zero-edge (isolated) nodes and
    connects them to the nearest semantically related nodes using LLM enrichment.

    Returns 202 immediately. Prevents duplicate concurrent executions for the same course.
    """
    _verify(request)

    from app.services.graph_job_tracker import get_job_status, set_job_status
    current = get_job_status(course_id)
    if current["status"] in ("queued", "processing"):
        return LinkIsolatedResponse(
            job_id=current["job_id"],
            course_id=course_id,
            status=current["status"],
            message="Isolated node linking job is already in progress for this course.",
        )

    import uuid
    job_id = f"link-isolated-{course_id}-{uuid.uuid4().hex[:8]}"
    set_job_status(course_id, job_id, "queued")

    from app.worker.kafka_producer import get_kafka_producer
    producer = await get_kafka_producer()
    await producer.send_and_wait(
        "lms.graph.command",
        value={
            "command":   "LINK_ISOLATED_NODES",
            "course_id": course_id,
            "job_id":    job_id,
        },
    )

    return LinkIsolatedResponse(job_id=job_id, course_id=course_id, status="queued")


@graph_router.get("/{course_id}/link-isolated/status")
async def get_link_isolated_status(course_id: int, request: Request):
    """Check the status of the isolated node linking job for a course."""
    _verify(request)
    from app.services.graph_job_tracker import get_job_status
    return get_job_status(course_id)


@graph_router.post("/edge", response_model=EdgeUpsertResponse)
async def upsert_graph_edge(body: EdgeUpsertRequest, request: Request):
    """Create a new edge or update the relation_type / strength of an existing edge.

    Writes to both PostgreSQL (knowledge_node_relations) and Neo4j synchronously.
    Idempotent: calling with the same (source, target, relation_type) updates the
    existing row rather than duplicating it.

    Set ``bidirectional=true`` to also create the reverse edge (target→source)
    with the same type and strength.
    """
    _verify(request)

    rel_type = body.relation_type.lower().strip()
    if rel_type not in _VALID_RELATION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid relation_type '{rel_type}'. "
                   f"Valid values: {sorted(_VALID_RELATION_TYPES)}",
        )
    strength = max(0.0, min(1.0, body.strength))

    # Resolve course_id from source node
    async with get_ai_conn() as conn:
        node_row = await conn.fetchrow(
            "SELECT course_id FROM knowledge_nodes WHERE id = $1",
            body.source_node_id,
        )
    if not node_row:
        raise HTTPException(status_code=404, detail=f"Source node {body.source_node_id} not found")
    course_id = node_row["course_id"]

    pairs = [(body.source_node_id, body.target_node_id)]
    if body.bidirectional:
        pairs.append((body.target_node_id, body.source_node_id))

    async with get_ai_conn() as conn:
        async with conn.transaction():
            for src, tgt in pairs:
                await conn.execute(
                    """
                    INSERT INTO knowledge_node_relations
                        (course_id, source_node_id, target_node_id,
                         relation_type, strength, auto_generated)
                    VALUES ($1, $2, $3, $4, $5, false)
                    ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE
                        SET strength       = EXCLUDED.strength,
                            auto_generated = false
                    """,
                    course_id, src, tgt, rel_type, round(strength, 3),
                )

    # Sync to Neo4j
    if settings.neo4j_enabled:
        try:
            from app.services.neo4j_service import neo4j_service, RELATIONSHIP_TYPES
            neo4j_rel = RELATIONSHIP_TYPES.get(rel_type, "RELATED")
            edges = [
                {
                    "source_id": src, "target_id": tgt,
                    "rel_type": neo4j_rel, "strength": round(strength, 3),
                    "auto_generated": False, "cross_course": False,
                    "reason": body.reason,
                }
                for src, tgt in pairs
            ]
            await neo4j_service.upsert_relationships_batch(edges)
        except Exception as exc:
            logger.warning("Neo4j edge upsert failed (PG already committed): %s", exc)

    return EdgeUpsertResponse(
        source_node_id=body.source_node_id,
        target_node_id=body.target_node_id,
        relation_type=rel_type,
        strength=round(strength, 3),
        auto_generated=False,
    )


@graph_router.delete("/edge")
async def delete_graph_edge(body: EdgeDeleteRequest, request: Request):
    """Delete one or all edges between two nodes.

    - If ``relation_type`` is provided, only that specific directed edge is deleted.
    - If ``relation_type`` is omitted, ALL edges between the pair are deleted
      (both directions).

    Also removes the corresponding relationship from Neo4j.
    """
    _verify(request)

    async with get_ai_conn() as conn:
        if body.relation_type:
            rel_type = body.relation_type.lower().strip()
            deleted = await conn.execute(
                """
                DELETE FROM knowledge_node_relations
                WHERE source_node_id = $1
                  AND target_node_id = $2
                  AND relation_type  = $3
                """,
                body.source_node_id, body.target_node_id, rel_type,
            )
        else:
            # Delete all edges in both directions
            deleted = await conn.execute(
                """
                DELETE FROM knowledge_node_relations
                WHERE (source_node_id = $1 AND target_node_id = $2)
                   OR (source_node_id = $2 AND target_node_id = $1)
                """,
                body.source_node_id, body.target_node_id,
            )

    # Sync to Neo4j
    if settings.neo4j_enabled:
        try:
            from app.services.neo4j_service import neo4j_service
            await neo4j_service.delete_relationship(
                source_id=body.source_node_id,
                target_id=body.target_node_id,
                relation_type=body.relation_type,
            )
        except Exception as exc:
            logger.warning("Neo4j edge delete failed (PG already committed): %s", exc)

    return {"ok": True, "deleted": deleted}


def _verify(request: Request):
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
