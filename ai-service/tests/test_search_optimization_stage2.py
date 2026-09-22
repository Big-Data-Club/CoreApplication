import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.rag_service import rag_service, RetrievedChunk, _extract_parent_context_window
from app.agents.core.react_loop import _trim_text_at_sentence_boundary, _smart_truncate_tool_result


def test_extract_parent_context_window_short_text():
    """Verify short text under target chars is returned as is without truncation."""
    short_text = "Kafka is a distributed event streaming platform."
    child = "event streaming"
    window = _extract_parent_context_window(short_text, child, target_window_chars=1200)
    assert window == short_text


def test_extract_parent_context_window_sentence_boundary():
    """Verify long parent text is snapped to natural sentence/paragraph boundaries around the child."""
    sentence1 = "Sentence one introduces the overall architecture of distributed systems."
    sentence2 = "Sentence two explains that PostgreSQL listens on default port 5432 for incoming client connections."
    sentence3 = "Sentence three discusses connection pooling via PgBouncer and max connections tuning."
    sentence4 = "Sentence four covers replication strategies and write-ahead logs."
    parent = f"{sentence1} {sentence2} {sentence3} {sentence4}"

    # Child chunk is about port 5432 in sentence2
    child = "PostgreSQL listens on default port 5432"

    # Set window size so it doesn't fit all sentences (e.g. 150 chars)
    window = _extract_parent_context_window(parent, child, target_window_chars=150)

    # Must contain the child text
    assert child in window
    # Must not cut in the middle of a word or sentence arbitrarily
    assert not window.endswith("defa")
    assert not window.startswith("chitecture")


def test_trim_text_at_sentence_boundary():
    """Verify _trim_text_at_sentence_boundary snaps to punctuation."""
    text = "First sentence of the lecture. Second sentence about indexing. Third sentence about query plans."
    trimmed = _trim_text_at_sentence_boundary(text, max_chars=65)
    assert trimmed.endswith(".")
    assert "Second sentence about indexing." in trimmed
    assert "Third sentence" not in trimmed


def test_smart_truncate_tool_result_preserves_multiple_chunks_and_compacts_graph():
    """Verify smart truncate handles 6 chunks and compacts graph metadata under 8000 limit."""
    chunks = [
        {
            "chunk_id": i,
            "text": f"Chunk {i}: Important lecture content discussing data engineering topics and distributed pipelines with sufficient detail. " * 3,
            "page_number": i,
        }
        for i in range(1, 7)
    ]

    graph_payload = {
        "graph_expanded": True,
        "prereq_path": ["CS101", "CS102", "CS201", "CS301", "CS401"],
        "concept_relationships": [
            {
                "concept": f"Concept_{j}",
                "description": "Very long description that would bloat context " * 10,
                "related_to": [{"name": f"Rel_{k}", "weight": 0.9, "extra_bloat": "x" * 200} for k in range(5)],
            }
            for j in range(10)
        ],
    }

    raw_tool_result = json.dumps({
        "status": "success",
        "data": {
            "chunks": chunks,
            "graph": graph_payload,
        }
    })

    truncated_result = _smart_truncate_tool_result("search_course_materials", raw_tool_result, limit=8000)
    data = json.loads(truncated_result)["data"]

    # Compacted graph must have kept at most 3 prereqs and 3 concepts with 2 related nodes
    assert len(data["graph"]["prereq_path"]) <= 3
    assert len(data["graph"]["concept_relationships"]) <= 3
    for rel in data["graph"]["concept_relationships"]:
        assert len(rel["related"]) <= 2

    # All or most of the 6 chunks should be retained without dropping down to 2 or 3
    assert len(data["chunks"]) >= 5


@pytest.mark.asyncio
async def test_hydrate_parents_deduplication():
    """Verify hydrate_parents dedups parent passages across chunks from same parent."""
    chunk1 = RetrievedChunk(
        chunk_id=1,
        chunk_text="Child chunk 1 about indexing",
        similarity=0.9,
        source_type="document",
        page_number=1,
        start_time_sec=None,
        end_time_sec=None,
        content_id=10,
        node_id=1,
        language="vi",
    )
    chunk2 = RetrievedChunk(
        chunk_id=2,
        chunk_text="Child chunk 2 about B-trees",
        similarity=0.85,
        source_type="document",
        page_number=1,
        start_time_sec=None,
        end_time_sec=None,
        content_id=10,
        node_id=1,
        language="vi",
    )

    parent_text = (
        "Comprehensive database chapter. Indexing allows fast retrieval of data records. "
        "B-trees are balanced tree data structures commonly used in databases. "
        "Query execution uses indexes to avoid full table scans."
    )

    mock_rows = [
        {"child_id": 1, "parent_id": 999, "parent_text": parent_text},
        {"child_id": 2, "parent_id": 999, "parent_text": parent_text},
    ]

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_rows

    class MockConnContext:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    with patch("app.services.rag_service.get_ai_conn", return_value=MockConnContext()):
        hydrated = await rag_service.hydrate_parents([chunk1, chunk2])

        assert len(hydrated) == 2
        # Both chunks should have received parent-derived contextual text
        assert "Indexing" in hydrated[0].chunk_text or "database" in hydrated[0].chunk_text.lower()
        assert "B-trees" in hydrated[1].chunk_text or "database" in hydrated[1].chunk_text.lower()


def test_parse_tool_arguments_robust_recovery():
    """Verify _parse_tool_arguments parses diverse LLM formats without raising JSONDecodeError."""
    from app.agents.core.react_loop import _parse_tool_arguments

    # Empty / None
    assert _parse_tool_arguments("") == {}
    assert _parse_tool_arguments(None) == {}
    assert _parse_tool_arguments("{}") == {}
    assert _parse_tool_arguments("null") == {}

    # Valid JSON
    assert _parse_tool_arguments('{"query": "kafka", "top_k": 6}') == {"query": "kafka", "top_k": 6}

    # Single-quoted Python dict
    assert _parse_tool_arguments("{'query': 'kafka', 'top_k': 6}") == {"query": "kafka", "top_k": 6}

    # Markdown fenced code block
    fenced = '```json\n{"query": "kafka", "top_k": 6}\n```'
    assert _parse_tool_arguments(fenced) == {"query": "kafka", "top_k": 6}

    # Trailing commas
    assert _parse_tool_arguments('{"query": "kafka", "top_k": 6,}') == {"query": "kafka", "top_k": 6}

    # Unquoted keys (Llama 3 common glitch)
    assert _parse_tool_arguments('{query: "kafka", top_k: 6}') == {"query": "kafka", "top_k": 6}

    # Key-value syntax (query="kafka", top_k=6)
    assert _parse_tool_arguments('query="kafka", top_k=6') == {"query": "kafka", "top_k": 6}

