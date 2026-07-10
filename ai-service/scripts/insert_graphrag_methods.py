"""
Script to insert GraphRAG methods into rag_service.py
"""
import re

path = r'd:\CodeSpace\BDCApp\ai-service\app\services\rag_service.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

new_methods = '''
    # -- GraphRAG: Fetch chunks for expanded graph nodes ----------------------

    async def search_by_node_ids(
        self,
        node_ids: list[int],
        top_k: int = 3,
        course_id: int | None = None,
    ) -> list[RetrievedChunk]:
        """Fetch chunks belonging to graph-expanded neighbor node_ids.

        Called by graphrag_service after Neo4j expansion to retrieve textual
        evidence for graph-neighbor concepts.  Results are merged and re-ranked
        in graphrag_service together with the primary vector/keyword results.
        """
        if not node_ids:
            return []
        results: list[RetrievedChunk] = []
        if settings.use_qdrant:
            from app.services.qdrant_service import qdrant_service
            from qdrant_client.http.models import Filter, FieldCondition, MatchAny
            try:
                client = qdrant_service._get_client()
                must_conditions: list = [
                    FieldCondition(key="node_id", match=MatchAny(any=node_ids)),
                ]
                if course_id is not None:
                    from qdrant_client.http.models import MatchValue
                    must_conditions.append(
                        FieldCondition(key="course_id", match=MatchValue(value=course_id))
                    )
                qfilter = Filter(must=must_conditions)
                scroll_results, _ = await client.scroll(
                    collection_name="document_chunks",
                    scroll_filter=qfilter,
                    limit=top_k * len(node_ids),
                    with_payload=True,
                    with_vectors=False,
                )
                seen: set[int] = set()
                for point in scroll_results:
                    cid = int(point.id)
                    if cid in seen:
                        continue
                    seen.add(cid)
                    p = point.payload or {}
                    results.append(RetrievedChunk(
                        chunk_id=cid,
                        chunk_text=p.get("chunk_text", ""),
                        similarity=0.70,
                        source_type=p.get("source_type", "document"),
                        page_number=p.get("page_number"),
                        start_time_sec=p.get("start_time_sec"),
                        end_time_sec=p.get("end_time_sec"),
                        content_id=p.get("content_id"),
                        node_id=p.get("node_id"),
                        language=p.get("language", "vi"),
                    ))
            except Exception as exc:
                logger.warning("search_by_node_ids (Qdrant) failed: %s", exc)
        else:
            try:
                params: list = [node_ids]
                idx = 2
                extra_cond = ""
                if course_id is not None:
                    extra_cond = f" AND course_id = ${idx}"
                    params.append(course_id)
                    idx += 1
                params.append(top_k * len(node_ids))
                sql = (
                    "SELECT id, chunk_text, content_id, node_id, "
                    "source_type, page_number, start_time_sec, end_time_sec, language "
                    f"FROM document_chunks "
                    f"WHERE status = \'ready\' AND node_id = ANY($1){extra_cond} "
                    f"LIMIT ${idx}"
                )
                async with get_ai_conn() as conn:
                    rows = await conn.fetch(sql, *params)
                results = [
                    RetrievedChunk(
                        chunk_id=r["id"], chunk_text=r["chunk_text"], similarity=0.70,
                        source_type=r["source_type"], page_number=r["page_number"],
                        start_time_sec=r["start_time_sec"], end_time_sec=r["end_time_sec"],
                        content_id=r["content_id"], node_id=r["node_id"],
                        language=r["language"] or "vi",
                    )
                    for r in rows
                ]
            except Exception as exc:
                logger.warning("search_by_node_ids (pgvector) failed: %s", exc)
        return results[:top_k * len(node_ids)]

    # -- GraphRAG: Prerequisite-aware re-ranking ------------------------------

    @staticmethod
    def graph_boost_rerank(
        chunks: list[RetrievedChunk],
        prereq_path_node_ids: list[int],
        boost_factor: float = 1.3,
    ) -> list[RetrievedChunk]:
        """Apply a multiplicative score boost to chunks on the prerequisite path.

        Surfaces foundational prerequisite content earlier in the context window,
        helping the LLM explain from first principles when the user has gaps.

        Args:
            chunks:               Ranked list of RetrievedChunk objects.
            prereq_path_node_ids: Ordered prerequisite node IDs (earliest first).
            boost_factor:         Multiplier. Default 1.3 = 30 percent boost.

        Returns the re-sorted list (highest similarity first).
        """
        if not prereq_path_node_ids or boost_factor == 1.0:
            return chunks
        prereq_set = set(prereq_path_node_ids)
        for chunk in chunks:
            if chunk.node_id and chunk.node_id in prereq_set:
                chunk.similarity = min(chunk.similarity * boost_factor, 1.0)
        return sorted(chunks, key=lambda c: c.similarity, reverse=True)

'''

# Find insertion point: between end of _rrf_merge and _search_and_rerank
marker = '        return [items[cid] for cid in sorted_ids[:top_k]]'
search_and_rerank = '    async def _search_and_rerank('

idx = content.find(marker)
if idx == -1:
    print("MARKER NOT FOUND")
else:
    # Find the _search_and_rerank after this marker
    after_marker = content[idx + len(marker):]
    sr_idx = after_marker.find(search_and_rerank)
    if sr_idx == -1:
        print("search_and_rerank NOT FOUND")
    else:
        # Insert between end of _rrf_merge and start of _search_and_rerank
        insertion_point = idx + len(marker) + sr_idx
        content = (
            content[:idx + len(marker)]
            + new_methods
            + content[idx + len(marker) + sr_idx:]
        )
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("SUCCESS: methods inserted")
        # Verify
        if 'search_by_node_ids' in open(path, encoding='utf-8').read():
            print("VERIFIED: search_by_node_ids found in file")
        if 'graph_boost_rerank' in open(path, encoding='utf-8').read():
            print("VERIFIED: graph_boost_rerank found in file")
