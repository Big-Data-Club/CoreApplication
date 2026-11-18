"""Course boundaries must hold before any retrieval backend is contacted."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import get_settings
from app.services.graphrag_service import GraphRAGService
from app.services.qdrant_service import QdrantService
from app.services.rag_service import RAGService, RetrievedChunk


@pytest.mark.asyncio
@pytest.mark.parametrize("course_id", [None, 0, -1, True, "27"])
@pytest.mark.parametrize("method", ["search", "search_multilingual", "search_hierarchical"])
async def test_invalid_course_rejected_before_embeddings_or_search(monkeypatch, method, course_id):
    service = RAGService()
    embedding = AsyncMock()
    monkeypatch.setattr(service, "_get_query_embedding", embedding)
    with pytest.raises(ValueError, match="course_id"):
        await getattr(service, method)("MPI", course_id=course_id)
    embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_and_neighbor_search_require_course():
    with pytest.raises(ValueError, match="course_id"):
        await GraphRAGService().retrieve("MPI")
    with pytest.raises(ValueError, match="course_id"):
        await RAGService().search_by_node_ids([1])


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["search_chunks", "search_nodes"])
async def test_vector_backend_rejects_missing_course_before_client(monkeypatch, method):
    service = QdrantService()
    client = Mock()
    monkeypatch.setattr(service, "_get_client", client)
    with pytest.raises(ValueError, match="course_id"):
        await getattr(service, method)(query_vector=[.1], course_id=None)
    client.assert_not_called()


@pytest.mark.asyncio
async def test_vector_filter_preserves_course_and_empty_content_scope(monkeypatch):
    service = QdrantService()
    client = AsyncMock()
    client.search.return_value = []
    monkeypatch.setattr(service, "_get_client", lambda: client)
    await service.search_chunks([.1], course_id=27, content_ids=[1770])
    conditions = client.search.call_args.kwargs["query_filter"].must
    assert {c.key: c.match.model_dump() for c in conditions} == {
        "status": {"value": "ready"}, "course_id": {"value": 27},
        "content_id": {"any": [1770]},
    }
    client.search.reset_mock()
    assert await service.search_chunks([.1], course_id=27, content_ids=[]) == []
    client.search.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("use_qdrant", [True, False])
async def test_vector_and_keyword_channels_receive_same_course(monkeypatch, use_qdrant):
    from app.services.qdrant_service import qdrant_service
    monkeypatch.setattr(get_settings(), "use_qdrant", use_qdrant)
    service = RAGService()
    monkeypatch.setattr(service, "_get_query_embedding", AsyncMock(return_value=[.1]))
    vector, keyword = AsyncMock(return_value=[]), AsyncMock(return_value=[])
    monkeypatch.setattr(qdrant_service, "search_chunks", vector)
    monkeypatch.setattr(service, "_pgvector_search", vector)
    monkeypatch.setattr(service, "_verified_vector_chunks", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_keyword_search", keyword)
    assert await service.search("MPI", course_id=27) == []
    assert vector.call_args.kwargs["course_id"] == 27
    assert keyword.call_args.kwargs["course_id"] == 27


@pytest.mark.asyncio
@pytest.mark.parametrize("reference_course, expected_ids", [(99, []), (27, [1])])
async def test_quiz_reference_cannot_bypass_course(monkeypatch, reference_course, expected_ids):
    service = RAGService()
    reference = {"id": 1, "course_id": reference_course, "chunk_text": "MPI",
                 "source_type": "document", "page_number": 1, "start_time_sec": None,
                 "end_time_sec": None, "content_id": 1770, "node_id": 2, "language": "en"}
    monkeypatch.setattr(service, "get_chunk", AsyncMock(return_value=reference))
    monkeypatch.setattr(service, "search_multilingual", AsyncMock(return_value=[]))
    result = await service.search_for_question("MPI", course_id=27, reference_chunk_id=1)
    assert [c.chunk_id for c in result] == expected_ids


@pytest.mark.asyncio
async def test_graph_enrichment_bounds_both_ends_of_relations(monkeypatch):
    conn = AsyncMock()
    conn.fetch.return_value = []
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr("app.services.rag_service.get_ai_conn", connection)
    chunk = RetrievedChunk(1, "MPI", .9, "document", 1, None, None, 1770, 2, "en")
    await RAGService().enrich_chunks_with_graph_context([chunk], course_id=27)
    nodes, relations = conn.fetch.call_args_list
    assert "course_id = $2" in nodes.args[0]
    assert "src.course_id = $2 AND tgt.course_id = $2" in relations.args[0]
    assert nodes.args[1:] == relations.args[1:] == ([2], 27)


@pytest.mark.asyncio
async def test_concept_check_without_course_returns_validation_error(monkeypatch):
    from fastapi import HTTPException
    from app.api.endpoints import concept_check
    monkeypatch.setattr(concept_check, "_verify_internal", lambda request: None)
    with pytest.raises(HTTPException) as error:
        await concept_check.generate_concept_check(concept_check.ConceptCheckRequest(node_id=2), None)
    assert error.value.status_code == 400
    assert "course_id" in error.value.detail
