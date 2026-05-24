"""
ai-service/app/services/graph_linker.py

Smart cross-course knowledge graph linker.

Pipeline (called after every auto_index run):
  1. Take new node embeddings + all existing nodes (from Qdrant).
  2. Compute cosine similarity against nodes from OTHER courses.
  3. For pairs above CROSS_COURSE_THRESHOLD, call LLM to:
       a. Confirm the connection is real (not coincidental term overlap).
       b. Classify the relationship type.
       c. Write a human-readable reason.
  4. Write edges to Neo4j.

Why LLM enrichment matters:
  "Array" in a programming course vs "Array" in a math course may be
  similar vectors but are NOT the same concept.
  The LLM reads descriptions and decides: EQUIVALENT, RELATED, or no link.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import numpy as np

from app.core.config import get_settings
from app.core.database import get_ai_conn
from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_GRAPH_LINK
from app.services.neo4j_service import (
    neo4j_service,
    INTRA_COURSE_THRESHOLD,
    CROSS_COURSE_THRESHOLD,
    EQUIVALENT_THRESHOLD,
    RELATIONSHIP_TYPES,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Max cross-course pairs to send to LLM per indexing run
# (prevents token/cost explosion on large knowledge graphs)
MAX_LLM_ENRICHMENT_PAIRS = 30
MAX_GLOBAL_LLM_PAIRS       = 200  # Higher limit for manual global runs

LINKER_SYSTEM_PROMPT = """\
Bạn là chuyên gia phân tích mối quan hệ giữa các khái niệm học thuật và thiết kế chương trình đào tạo.
Nhiệm vụ: Xác định mối quan hệ logic giữa hai khái niệm từ hai lĩnh vực/khóa học khác nhau.
Chỉ trả về JSON hợp lệ, không thêm text khác.\
"""

LINKER_PROMPT_TEMPLATE = """\
PHÂN TÍCH MỐI QUAN HỆ KIẾN THỨC XUYÊN KHÓA HỌC:

[KHÁI NIỆM A] (Thuộc khóa học: {course_a})
- Tên: {name_a}
- Mô tả: {desc_a}

[KHÁI NIỆM B] (Thuộc khóa học: {course_b})
- Tên: {name_b}
- Mô tả: {desc_b}

Nhiệm vụ: Dựa trên mô tả, hãy xác định xem hai khái niệm này có mối liên hệ chuyên môn nào không?

Nếu CÓ, hãy phân loại:
- relation_type: 
    * "equivalent"    : Là cùng một khái niệm, chỉ khác tên gọi hoặc ngữ cảnh (VD: "Array" vs "Mảng").
    * "prerequisite"  : A là kiến thức nền tảng cần có trước khi học B (A -> B).
    * "extends"       : B là phần nâng cao, mở rộng hoặc chuyên sâu của A (A -> B).
    * "related"       : Có liên quan về mặt chủ đề nhưng không có thứ tự học tập rõ ràng.
    * "contrasts_with": Hai khái niệm đối lập hoặc thường được mang ra so sánh (VD: "SQL" vs "NoSQL").

- direction: "a_to_b" | "b_to_a" | "bidirectional"
- strength: 0.6 -> 1.0 (mức độ tin cậy của liên kết)
- reason: Giải thích ngắn gọn lý do bằng tiếng Việt (1 câu).

Nếu KHÔNG liên quan thực sự (chỉ là trùng lặp từ vựng ngẫu nhiên), trả về "connected": false.

Trả về kiểu JSON:
{{
  "connected": true,
  "relation_type": "...",
  "strength": 0.0,
  "reason": "...",
  "direction": "..."
}}
"""


@dataclass
class NodeInfo:
    id: int
    course_id: int
    name: str
    description: str
    embedding: list[float]


async def link_cross_course(
    new_nodes: list[NodeInfo],
    new_course_id: int,
) -> int:
    """
    Main entry point for real-time indexing.
    Analyzes connections between NEW nodes and EVERYTHING else in other courses.
    """
    if not new_nodes:
        return 0

    from app.services.qdrant_service import qdrant_service
    
    # 1. High-speed batch search candidate discovery via Qdrant
    node_embeddings = [n.embedding for n in new_nodes]
    batch_results = await qdrant_service.search_nodes_batch(
        query_vectors=node_embeddings,
        exclude_course_id=new_course_id,
        top_k=8,
        score_threshold=CROSS_COURSE_THRESHOLD,
    )

    # Validate candidate IDs against PostgreSQL to prevent references to deleted nodes
    candidate_ids = [int(p.id) for scored_points in batch_results for p in scored_points]
    valid_ids = set()
    if candidate_ids:
        async with get_ai_conn() as conn:
            rows = await conn.fetch("SELECT id FROM knowledge_nodes WHERE id = ANY($1)", candidate_ids)
            valid_ids = {r["id"] for r in rows}
        dangling_ids = [rid for rid in candidate_ids if rid not in valid_ids]
        if dangling_ids:
            logger.warning("Found %d dangling nodes in Qdrant batch search. Cleaning them up...", len(dangling_ids))
            from app.services.auto_index_service import auto_index_service
            asyncio.create_task(auto_index_service.delete_nodes_bulk(dangling_ids))

    candidate_pairs = []
    for i, scored_points in enumerate(batch_results):
        node_a = new_nodes[i]
        for p in scored_points:
            if int(p.id) not in valid_ids:
                continue
            payload = p.payload or {}
            node_b = NodeInfo(
                id=int(p.id),
                course_id=payload.get("course_id", 0),
                name=payload.get("name", ""),
                description=payload.get("description", ""),
                embedding=[], # not needed for LLM stage
            )
            candidate_pairs.append((node_a, node_b, p.score))

    if not candidate_pairs:
        logger.info("No cross-course candidates found in Qdrant")
        return 0

    return await _process_and_upsert_pairs(candidate_pairs, limit=MAX_LLM_ENRICHMENT_PAIRS)


async def link_global_graph() -> int:
    """
    Maintenance task: perform a full scan of the entire knowledge graph 
    to find links between all courses.
    """
    from app.services.qdrant_service import qdrant_service
    from app.services.neo4j_service import neo4j_service
    
    logger.info("Starting Global Knowledge Discovery...")
    
    # 1. Get all courses
    async with neo4j_service._get_driver().session() as s:
        res = await s.run("MATCH (n:KnowledgeNode) RETURN DISTINCT n.course_id AS cid")
        course_ids = [r["cid"] async for r in res]
        
    total_new_edges = 0
    
    # 2. Iterate course by course to find outbound links
    for cid in course_ids:
        nodes = await _fetch_nodes_for_course(cid)
        if not nodes: continue
        
        logger.info("Analyzing course %d (%d nodes) against global graph...", cid, len(nodes))
        
        # Batch search for current course nodes
        embs = [n.embedding for n in nodes]
        # Process in chunks of 50 query nodes to avoid Qdrant timeouts
        CHUNK_SIZE = 50
        all_candidates = []
        
        for i in range(0, len(embs), CHUNK_SIZE):
            batch_resp = await qdrant_service.search_nodes_batch(
                query_vectors=embs[i:i+CHUNK_SIZE],
                exclude_course_id=cid,
                top_k=5,
                score_threshold=CROSS_COURSE_THRESHOLD + 0.05, # Higher threshold for global
            )
            
            # Validate candidate IDs against PostgreSQL to prevent references to deleted nodes
            candidate_ids = [int(p.id) for scored_points in batch_resp for p in scored_points]
            valid_ids = set()
            if candidate_ids:
                async with get_ai_conn() as conn:
                    rows = await conn.fetch("SELECT id FROM knowledge_nodes WHERE id = ANY($1)", candidate_ids)
                    valid_ids = {r["id"] for r in rows}
                dangling_ids = [rid for rid in candidate_ids if rid not in valid_ids]
                if dangling_ids:
                    logger.warning("Found %d dangling nodes in Qdrant search. Cleaning them up...", len(dangling_ids))
                    from app.services.auto_index_service import auto_index_service
                    asyncio.create_task(auto_index_service.delete_nodes_bulk(dangling_ids))

            for j, scored_points in enumerate(batch_resp):
                node_a = nodes[i+j]
                for p in scored_points:
                    if int(p.id) not in valid_ids:
                        continue
                    pay = p.payload or {}
                    node_b = NodeInfo(
                        id=int(p.id),
                        course_id=pay.get("course_id", 0),
                        name=pay.get("name", ""),
                        description=pay.get("description", ""),
                        embedding=[],
                    )
                    all_candidates.append((node_a, node_b, p.score))
        
        if all_candidates:
            count = await _process_and_upsert_pairs(all_candidates, limit=MAX_GLOBAL_LLM_PAIRS // len(course_ids))
            total_new_edges += count
            
    logger.info("Global Knowledge Discovery complete. Created %d new cross-course edges.", total_new_edges)
    return total_new_edges


async def _process_and_upsert_pairs(
    candidate_pairs: list[tuple[NodeInfo, NodeInfo, float]], 
    limit: int
) -> int:
    """Classify pairs via LLM and write to Neo4j."""
    # Pick top scoring candidates
    top_pairs = sorted(candidate_pairs, key=lambda x: x[2], reverse=True)[:limit]
    
    semaphore = asyncio.Semaphore(10) # Parallelize LLM calls
    
    async def enrich(node_a, node_b, sim):
        async with semaphore:
            return await _llm_enrich_pair(node_a, node_b, sim)

    results = await asyncio.gather(
        *[enrich(a, b, sim) for a, b, sim in top_pairs],
        return_exceptions=True
    )

    edges_to_create = []
    for (node_a, node_b, sim), result in zip(top_pairs, results):
        if isinstance(result, Exception) or not result or not result.get("connected"):
            continue

        rel_type_raw = result.get("relation_type", "related").lower()
        rel_type     = RELATIONSHIP_TYPES.get(rel_type_raw, "RELATED")
        strength     = float(result.get("strength", sim))
        reason       = result.get("reason", "")
        direction    = result.get("direction", "bidirectional")

        source, target = node_a, node_b
        if direction == "b_to_a":
            source, target = node_b, node_a

        if direction == "bidirectional":
            for src_id, tgt_id in [(node_a.id, node_b.id), (node_b.id, node_a.id)]:
                edges_to_create.append({
                    "source_id": src_id, "target_id": tgt_id,
                    "rel_type": rel_type, "strength": strength,
                    "auto_generated": True, "cross_course": True, "reason": reason
                })
        else:
            edges_to_create.append({
                "source_id": source.id, "target_id": target.id,
                "rel_type": rel_type, "strength": strength,
                "auto_generated": True, "cross_course": True, "reason": reason
            })

    if edges_to_create:
        await neo4j_service.upsert_relationships_batch(edges_to_create)
    return len(edges_to_create)


async def link_intra_course(
    new_nodes: list[NodeInfo],
    existing_nodes: list[NodeInfo],
    course_id: int,
    llm_relations: list[dict] | None = None,
) -> int:
    """Build intra-course graph edges."""
    edges: list[dict] = []

    # 1. LLM-derived relations
    if llm_relations:
        for rel in llm_relations:
            src_idx = rel.get("source_index")
            tgt_idx = rel.get("target_index")
            if not (isinstance(src_idx, int) and isinstance(tgt_idx, int)):
                continue
            if src_idx >= len(new_nodes) or tgt_idx >= len(new_nodes):
                continue
            rel_type = RELATIONSHIP_TYPES.get(rel.get("relation_type", "related"), "RELATED")
            edges.append({
                "source_id":     new_nodes[src_idx].id,
                "target_id":     new_nodes[tgt_idx].id,
                "rel_type":      rel_type,
                "strength":      round(float(rel.get("strength", 0.85)), 3),
                "auto_generated": True,
                "cross_course":  False,
                "reason":        rel.get("reason", ""),
            })

    # 2. Similarity-based edges
    all_pairs = _find_candidate_pairs(new_nodes, existing_nodes, threshold=INTRA_COURSE_THRESHOLD)
    all_pairs += _find_candidate_pairs(new_nodes, new_nodes, threshold=INTRA_COURSE_THRESHOLD, skip_same_id=True)

    for node_a, node_b, sim in all_pairs:
        if node_a.id == node_b.id: continue
        rel_type = "EQUIVALENT" if sim >= EQUIVALENT_THRESHOLD else "RELATED"
        edges.append({
            "source_id":     node_a.id,
            "target_id":     node_b.id,
            "rel_type":      rel_type,
            "strength":      round(sim, 3),
            "auto_generated": True,
            "cross_course":  False,
            "reason":        f"Similarity={sim:.3f}",
        })

    if edges:
        await neo4j_service.upsert_relationships_batch(edges)
    return len(edges)


async def _fetch_nodes_for_course(course_id: int) -> list[NodeInfo]:
    from app.services.qdrant_service import qdrant_service
    records = await qdrant_service.scroll_nodes_for_course(course_id)
    return [
        NodeInfo(
            id=int(r.id),
            course_id=course_id,
            name=r.payload.get("name", ""),
            description=r.payload.get("description", ""),
            embedding=r.vector,
        )
        for r in records if r.vector
    ]


async def _fetch_other_course_nodes(course_id: int) -> list[NodeInfo]:
    from app.services.qdrant_service import qdrant_service
    client = qdrant_service._get_client()
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue
    
    records, _ = await client.scroll(
        collection_name="knowledge_nodes",
        scroll_filter=Filter(must_not=[FieldCondition(key="course_id", match=MatchValue(value=course_id))]),
        limit=1000,
        with_vectors=True,
    )
    return [
        NodeInfo(
            id=int(r.id),
            course_id=r.payload.get("course_id", 0),
            name=r.payload.get("name", ""),
            description=r.payload.get("description", ""),
            embedding=r.vector,
            task=TASK_GRAPH_LINK,
        )
        for r in records if r.vector
    ]


def _find_candidate_pairs(
    nodes_a: list[NodeInfo],
    nodes_b: list[NodeInfo],
    threshold: float = CROSS_COURSE_THRESHOLD,
    skip_same_id: bool = False,
) -> list[tuple[NodeInfo, NodeInfo, float]]:
    if not nodes_a or not nodes_b: return []
    emb_a = np.array([n.embedding for n in nodes_a], dtype=np.float32)
    emb_b = np.array([n.embedding for n in nodes_b], dtype=np.float32)
    norm_a = emb_a / (np.linalg.norm(emb_a, axis=1, keepdims=True) + 1e-8)
    norm_b = emb_b / (np.linalg.norm(emb_b, axis=1, keepdims=True) + 1e-8)
    sims = norm_a @ norm_b.T
    
    pairs = []
    for i, node_a in enumerate(nodes_a):
        for j, node_b in enumerate(nodes_b):
            if skip_same_id and node_a.id == node_b.id: continue
            sim = float(sims[i, j])
            if sim >= threshold:
                pairs.append((node_a, node_b, sim))
    return pairs


async def _llm_enrich_pair(node_a: NodeInfo, node_b: NodeInfo, sim: float) -> dict | None:
    prompt = LINKER_PROMPT_TEMPLATE.format(
        course_a=f"Course ID {node_a.course_id}", 
        name_a=node_a.name, 
        desc_a=(node_a.description or "")[:400],
        course_b=f"Course ID {node_b.course_id}", 
        name_b=node_b.name, 
        desc_b=(node_b.description or "")[:400],
    )
    try:
        return await chat_complete_json(
            messages=[{"role": "system", "content": LINKER_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            model=settings.chat_model,
            temperature=0.05,
        )
    except Exception as exc:
        logger.warning("_llm_enrich_pair failed: %s", exc)
        return None