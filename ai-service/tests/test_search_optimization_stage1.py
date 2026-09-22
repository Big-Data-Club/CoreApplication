import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.rag_service import rag_service, RetrievedChunk


@pytest.mark.asyncio
async def test_search_multilingual_respects_skip_rerank_and_skip_hydration():
    """Verify skip_rerank prevents running rerank_chunks and skip_hydration prevents hydrate_parents."""
    dummy_chunk = RetrievedChunk(
        chunk_id=1,
        chunk_text="Short child text",
        similarity=0.40,
        source_type="document",
        page_number=1,
        start_time_sec=None,
        end_time_sec=None,
        content_id=101,
        node_id=1,
        language="vi",
    )

    with patch.object(rag_service, "search", new_callable=AsyncMock) as mock_search, \
         patch("app.core.embeddings.rerank_chunks", new_callable=AsyncMock) as mock_rerank, \
         patch.object(rag_service, "hydrate_parents", new_callable=AsyncMock) as mock_hydrate:

        mock_search.return_value = [dummy_chunk]

        # Call with skip_rerank=True, skip_hydration=True
        results = await rag_service.search_multilingual(
            query="Học máy là gì?",
            top_k=3,
            skip_rerank=True,
            skip_hydration=True,
        )

        assert len(results) == 1
        assert results[0].chunk_text == "Short child text"
        mock_rerank.assert_not_called()
        mock_hydrate.assert_not_called()


def test_rrf_merge_with_keyword_weight_boost():
    """Verify RRF merge boosts keyword results when keyword_weight > 1.0."""
    chunk_v = RetrievedChunk(
        chunk_id=1,
        chunk_text="General semantic passage about databases",
        similarity=0.30,
        source_type="document",
        page_number=1,
        start_time_sec=None,
        end_time_sec=None,
        content_id=1,
        node_id=1,
        language="vi",
    )
    chunk_k = RetrievedChunk(
        chunk_id=2,
        chunk_text="PostgreSQL default port is 5432",
        similarity=3.5,
        source_type="document",
        page_number=1,
        start_time_sec=None,
        end_time_sec=None,
        content_id=1,
        node_id=1,
        language="vi",
    )

    # Standard weight: equal rank
    merged_std = rag_service._rrf_merge(
        vector_results=[chunk_v],
        keyword_results=[chunk_k],
        top_k=2,
        keyword_weight=1.0,
    )
    # With equal weight, vector at rank 0 and keyword at rank 0 have identical score 1/(60+1)
    assert len(merged_std) == 2

    # Boosted weight (e.g. exact factual query with 5432): keyword result should be top 1
    merged_boosted = rag_service._rrf_merge(
        vector_results=[chunk_v],
        keyword_results=[chunk_k],
        top_k=2,
        keyword_weight=1.5,
    )
    assert merged_boosted[0].chunk_id == 2
    assert "5432" in merged_boosted[0].chunk_text


@pytest.mark.asyncio
async def test_graphrag_retrieve_avoids_double_rerank():
    """Verify GraphRAG Phase 1 calls search_hierarchical with skip_rerank=True, skip_hydration=True."""
    from app.services.graphrag_service import graphrag_service
    from app.core.config import get_settings
    settings = get_settings()

    orig_neo4j = settings.neo4j_enabled
    orig_reranker = settings.use_reranker
    orig_hierarchical = settings.use_hierarchical_chunks

    settings.neo4j_enabled = False  # fast path without Neo4j
    settings.use_reranker = False
    settings.use_hierarchical_chunks = False

    dummy_chunk = RetrievedChunk(
        chunk_id=10,
        chunk_text="Child passage text",
        similarity=0.45,
        source_type="document",
        page_number=1,
        start_time_sec=None,
        end_time_sec=None,
        content_id=200,
        node_id=5,
        language="vi",
    )

    try:
        with patch.object(rag_service, "search_hierarchical", new_callable=AsyncMock) as mock_hierarchical:
            mock_hierarchical.return_value = ([dummy_chunk], "content")

            ctx = await graphrag_service.retrieve(query="cổng postgresql", top_k=3)

            mock_hierarchical.assert_called_once()
            call_kwargs = mock_hierarchical.call_args.kwargs
            assert call_kwargs.get("skip_rerank") is True
            assert call_kwargs.get("skip_hydration") is True
            assert len(ctx.ranked_chunks) == 1
    finally:
        settings.neo4j_enabled = orig_neo4j
        settings.use_reranker = orig_reranker
        settings.use_hierarchical_chunks = orig_hierarchical
