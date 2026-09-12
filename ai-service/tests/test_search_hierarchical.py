import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.rag_service import rag_service, RetrievedChunk


@pytest.mark.asyncio
async def test_search_hierarchical_accepts_content_ids_and_kwargs():
    """Verify search_hierarchical accepts content_ids and unknown kwargs without TypeError."""
    dummy_chunk = RetrievedChunk(
        chunk_id=1,
        chunk_text="Eligibility traces in TD(lambda)",
        similarity=0.35,
        source_type="document",
        page_number=1,
        start_time_sec=None,
        end_time_sec=None,
        content_id=2840,
        node_id=10,
        language="en",
    )

    with patch.object(rag_service, "search_multilingual", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [dummy_chunk]

        # Call with content_ids and arbitrary kwargs (as graphrag_service does)
        chunks, scope = await rag_service.search_hierarchical(
            query="eligibility traces TD lambda",
            course_id=47,
            content_id=None,
            top_k=5,
            min_similarity=0.25,
            content_ids=[2840, 2841],
            extra_param_should_not_crash=True,
        )

        assert chunks == [dummy_chunk]
        assert scope == "content_ids"
        mock_search.assert_called_once_with(
            query="eligibility traces TD lambda",
            course_id=47,
            content_ids=[2840, 2841],
            top_k=5,
            min_similarity=0.25,
        )


@pytest.mark.asyncio
async def test_search_hierarchical_returns_chunks_on_fallback():
    """Verify search_hierarchical does not discard valid fallback chunks with similarity >= threshold."""
    dummy_chunk = RetrievedChunk(
        chunk_id=2,
        chunk_text="Eligibility traces TD lambda content in course",
        similarity=0.18,
        source_type="document",
        page_number=2,
        start_time_sec=None,
        end_time_sec=None,
        content_id=2845,
        node_id=11,
        language="en",
    )

    with patch.object(rag_service, "search_multilingual", new_callable=AsyncMock) as mock_search:
        # First call (lesson) returns empty, course call returns fallback chunk
        mock_search.side_effect = [[], [dummy_chunk]]

        chunks, scope = await rag_service.search_hierarchical(
            query="eligibility traces TD lambda",
            course_id=47,
            content_id=2840,
            top_k=5,
            min_similarity=0.25,
        )

        assert chunks == [dummy_chunk]
        assert scope == "course"
