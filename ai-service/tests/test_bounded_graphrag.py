"""Retrieval deadlines, scope and model-specific evidence regression tests."""
import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from app.agents.core.prompt_budget import _compact_tool_content
from app.core.config import get_settings
from app.core.llm_gateway.token_budget import estimate_tokens
from app.services.graphrag_service import GraphRAGService
from app.services.rag_service import RetrievedChunk, rag_service


def chunk(index, text="Matched child", node_id=1):
    return RetrievedChunk(index, text, .8, "document", 2, None, None, 10, node_id, "vi")


@pytest.fixture
def retrieval(monkeypatch):
    for key, value in {
        "graphrag_enabled": True, "neo4j_enabled": True,
        "use_reranker": False, "use_hierarchical_chunks": False,
        "graph_retrieval_timeout_sec": .03,
    }.items():
        monkeypatch.setattr(get_settings(), key, value)
    service = GraphRAGService()
    monkeypatch.setattr(service, "_expand_graph", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_get_prereq_chain", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_fetch_node_metadata", AsyncMock(return_value=[]))
    monkeypatch.setattr(rag_service, "search_hierarchical", AsyncMock(return_value=([chunk(1)], "content")))
    monkeypatch.setattr(rag_service, "enrich_chunks_with_graph_context", AsyncMock())
    return service


@pytest.mark.asyncio
async def test_optional_graph_timeout_cancels_work_and_keeps_base_hits(retrieval, monkeypatch):
    started, cancelled = set(), set()
    def blocked(label):
        async def run(*args):
            started.add(label)
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add(label)
        return run
    for name in ("_expand_graph", "_get_prereq_chain", "_fetch_node_metadata"):
        monkeypatch.setattr(retrieval, name, blocked(name))
    result = await asyncio.wait_for(retrieval.retrieve("query"), timeout=.5)
    assert len(started) == 3
    assert cancelled == started
    assert [c.chunk_id for c in result.ranked_chunks] == [1]
    assert not result.graph_expanded
    rag_service.enrich_chunks_with_graph_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_evidence_reaches_reranker_without_broadening_content_scope(retrieval, monkeypatch):
    base = [chunk(i) for i in range(1, 7)]
    neighbor = chunk(99, node_id=2)
    rag_service.search_hierarchical.return_value = (base, "content")
    retrieval._expand_graph.return_value = {"expanded_nodes": [{"id": 2, "name": "Prerequisite"}], "edges": []}
    neighbor_search = AsyncMock(return_value=[neighbor])
    monkeypatch.setattr(rag_service, "search_by_node_ids", neighbor_search)
    monkeypatch.setattr(get_settings(), "use_reranker", True)
    async def rerank(**kwargs):
        assert 99 in [c.chunk_id for c in kwargs["chunks"]]
        return [neighbor]
    monkeypatch.setattr("app.core.embeddings.rerank_chunks", rerank)
    result = await retrieval.retrieve("query", course_id=7, content_id=10, content_ids=[10], top_k=2)
    assert result.ranked_chunks == [neighbor]
    assert neighbor_search.call_args.kwargs["content_id"] == 10
    assert neighbor_search.call_args.kwargs["content_ids"] == [10]
    assert neighbor_search.call_args.kwargs["course_id"] == 7
    rag_service.enrich_chunks_with_graph_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_reranker_and_hydration_timeout_keep_original_children(retrieval, monkeypatch):
    for key, value in {"use_reranker": True, "use_hierarchical_chunks": True,
                       "retrieval_rerank_timeout_sec": .01, "retrieval_hydration_timeout_sec": .01}.items():
        monkeypatch.setattr(get_settings(), key, value)
    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()
    monkeypatch.setattr("app.core.embeddings.rerank_chunks", blocked)
    monkeypatch.setattr(rag_service, "hydrate_parents", blocked)
    result = await asyncio.wait_for(retrieval.retrieve("query", graph_enabled=False), timeout=.5)
    assert result.ranked_chunks[0].chunk_text == "Matched child"
    retrieval._expand_graph.assert_not_awaited()


def test_small_model_retains_child_anchors_citations_and_graph_relations():
    payload = {"status": "success", "data": {
        "chunks": [{"chunk_id": i, "parent_chunk_id": 4, "page_number": 2,
                    "ref_index": i, "text": "Parent introduction. " * 400,
                    "child_text": f"Important matching evidence {i}."} for i in range(1, 4)],
        "graph": {"graph_expanded": True, "prereq_path": ["Derivative", "Gradient"],
                  "concept_relationships": [{"concept": "Gradient", "related_to": [
                      {"name": "Derivative", "relation": "PREREQUISITE"}]}]},
    }}
    packed = _compact_tool_content(json.dumps(payload), 700)
    data = json.loads(packed)["data"]
    assert estimate_tokens(packed) <= 700
    assert len(data["chunks"]) == 3
    assert data["graph"]["concept_relationships"][0]["related_to"][0]["relation"] == "PREREQUISITE"
    for i, entry in enumerate(data["chunks"], 1):
        assert entry["text"] == f"Important matching evidence {i}."
        assert entry["ref_index"] == i
        assert entry["parent_chunk_id"] == 4
    assert payload["data"]["chunks"][0]["child_text"]


@pytest.mark.asyncio
async def test_parent_hydration_retains_exact_child_metadata(monkeypatch):
    conn = AsyncMock()
    conn.fetch.return_value = [{"child_id": 1, "parent_id": 4,
                               "parent_text": "Intro. Matching evidence. Explanation."}]
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr("app.services.rag_service.get_ai_conn", connection)
    result = await rag_service.hydrate_parents([chunk(1, "Matching evidence.")])
    assert result[0].child_text == "Matching evidence."
    assert result[0].parent_chunk_id == 4
    assert "Explanation" in result[0].chunk_text
    conn.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_neighbor_pg_query_filters_scope_and_excludes_parent_rows(monkeypatch):
    monkeypatch.setattr(get_settings(), "use_qdrant", False)
    conn = AsyncMock()
    conn.fetch.return_value = []
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr("app.services.rag_service.get_ai_conn", connection)
    await rag_service.search_by_node_ids([2], course_id=7, content_id=10, content_ids=[10, 11])
    sql, *params = conn.fetch.call_args.args
    assert "chunk_level = 'child'" in sql
    assert "course_id = $2" in sql and "content_id = $3" in sql
    assert "content_id = ANY($4)" in sql
    assert params == [[2], 7, 10, [10, 11], 3]
    conn.fetch.reset_mock()
    assert await rag_service.search_by_node_ids([2], content_ids=[]) == []
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_explicit_scope_never_searches_global(retrieval):
    result = await retrieval.retrieve("query", content_ids=[])
    assert result.ranked_chunks == []
    rag_service.search_hierarchical.assert_not_awaited()


@pytest.mark.asyncio
async def test_reranker_lazy_loading_runs_in_executor(monkeypatch):
    from app.core import embeddings
    monkeypatch.setattr(get_settings(), "use_reranker", True)
    loads = []
    def load_model():
        loads.append(True)
        return None
    async def executor(compute, *args):
        # The loader must only run inside the executor compute callback.
        assert not loads
        return compute(*args)
    monkeypatch.setattr(embeddings, "get_reranker", load_model)
    offload = AsyncMock(side_effect=executor)
    monkeypatch.setattr(embeddings, "_run_in_thread", offload)
    results = await embeddings.rerank_chunks("query", [chunk(1)], lambda c: c.chunk_text, 1)
    assert results[0].chunk_id == 1
    assert loads == [True]
    offload.assert_awaited_once()


@pytest.mark.asyncio
async def test_qdrant_neighbors_preserve_document_and_course_filters(monkeypatch):
    from app.services.qdrant_service import qdrant_service
    monkeypatch.setattr(get_settings(), "use_qdrant", True)
    client = AsyncMock()
    client.scroll.return_value = ([], None)
    monkeypatch.setattr(qdrant_service, "_get_client", lambda: client)
    await rag_service.search_by_node_ids([2, 3], course_id=7, content_id=10, content_ids=[10, 11])
    conditions = client.scroll.call_args.kwargs["scroll_filter"].must
    assert [(c.key, c.match.model_dump()) for c in conditions] == [
        ("node_id", {"any": [2, 3]}), ("course_id", {"value": 7}),
        ("content_id", {"value": 10}), ("content_id", {"any": [10, 11]}),
    ]
    assert client.scroll.call_args.kwargs["limit"] == 6


@pytest.mark.asyncio
async def test_neo4j_queries_bound_depth_edges_scope_and_server_time(monkeypatch):
    from unittest.mock import MagicMock
    from app.services.neo4j_service import Neo4jService
    monkeypatch.setattr(get_settings(), "neo4j_enabled", True)

    class Records:
        def __init__(self, rows):
            self.rows = rows
        async def __aiter__(self):
            for row in self.rows:
                yield row

    session = AsyncMock()
    session.run.side_effect = [Records([{"id": 2, "hops": 1}]), Records([]), Records([])]
    context = AsyncMock()
    context.__aenter__.return_value = session
    driver = MagicMock()
    driver.session.return_value = context
    service = Neo4jService()
    monkeypatch.setattr(service, "_get_driver", lambda: driver)
    await service.get_concept_context([1], depth=100, max_nodes=12, max_edges=32, course_id=7)
    await service.get_prerequisite_chain(1, max_depth=100, course_id=7)
    expansion, edges, prereqs = session.run.call_args_list
    assert "*1..2" in expansion.args[0].text
    assert "$depth" not in expansion.args[0].text
    assert expansion.kwargs["course_id"] == 7
    assert expansion.kwargs["limit"] == 12
    assert "LIMIT $edge_limit" in edges.args[0].text
    assert edges.kwargs["edge_limit"] == 32
    assert "*1..4" in prereqs.args[0].text
    assert prereqs.kwargs["course_id"] == 7
    assert expansion.args[0].timeout == get_settings().graph_retrieval_timeout_sec
    assert edges.args[0].timeout == prereqs.args[0].timeout == expansion.args[0].timeout


@pytest.mark.asyncio
async def test_disabled_reranker_keeps_base_before_placeholder_neighbor_scores(retrieval, monkeypatch):
    base, neighbor = chunk(1), chunk(99, node_id=2)
    base.similarity = .2
    neighbor.similarity = .7  # Graph lookup score does not measure query relevance.
    rag_service.search_hierarchical.return_value = ([base], "course")
    retrieval._expand_graph.return_value = {"expanded_nodes": [{"id": 2}], "edges": []}
    monkeypatch.setattr(rag_service, "search_by_node_ids", AsyncMock(return_value=[neighbor]))
    result = await retrieval.retrieve("query", top_k=1)
    assert result.ranked_chunks == [base]
