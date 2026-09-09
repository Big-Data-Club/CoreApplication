import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.graph_linker import (
    NodeInfo,
    link_all_nodes_for_course,
    INTRA_COURSE_LINK_PROMPT_TEMPLATE,
)


def test_intra_course_link_prompt_template():
    prompt = INTRA_COURSE_LINK_PROMPT_TEMPLATE.format(
        course_id=42,
        name_a="Linear Regression",
        desc_a="Basic regression model",
        name_b="Gradient Descent",
        desc_b="Optimization algorithm",
    )
    assert "Khóa học ID: 42" in prompt
    assert "Linear Regression" in prompt
    assert "Gradient Descent" in prompt
    assert "prerequisite" in prompt
    assert "extends" in prompt


@pytest.mark.asyncio
async def test_link_all_nodes_less_than_two_nodes():
    with patch("app.services.graph_linker._fetch_nodes_for_course", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            NodeInfo(id=1, course_id=10, name="Node 1", description="", embedding=[0.1] * 384)
        ]
        result = await link_all_nodes_for_course(10)
        assert result == 0


@pytest.mark.asyncio
async def test_link_all_nodes_bridges_components():
    # 4 nodes in 2 disconnected components: (1, 2) and (3, 4)
    nodes = [
        NodeInfo(id=1, course_id=10, name="A1", description="", embedding=[1.0, 0.0, 0.0]),
        NodeInfo(id=2, course_id=10, name="A2", description="", embedding=[0.9, 0.1, 0.0]),
        NodeInfo(id=3, course_id=10, name="B1", description="", embedding=[0.8, 0.2, 0.0]),
        NodeInfo(id=4, course_id=10, name="B2", description="", embedding=[0.7, 0.3, 0.0]),
    ]

    mock_existing_edges = [
        {"source_node_id": 1, "target_node_id": 2},
        {"source_node_id": 3, "target_node_id": 4},
    ]

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = mock_existing_edges
    mock_tx = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_conn.execute = AsyncMock()

    class MockConnContext:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, *args):
            pass

    mock_llm_response = {
        "connected": True,
        "relation_type": "prerequisite",
        "direction": "a_to_b",
        "strength": 0.88,
        "reason": "A2 is prerequisite to B1",
    }

    with patch("app.services.graph_linker._fetch_nodes_for_course", new_callable=AsyncMock, return_value=nodes), \
         patch("app.services.graph_linker.get_ai_conn", return_value=MockConnContext()), \
         patch("app.services.graph_linker._llm_enrich_pair", new_callable=AsyncMock, return_value=mock_llm_response) as mock_llm, \
         patch("app.services.graph_linker.neo4j_service.upsert_relationships_batch", new_callable=AsyncMock) as mock_neo4j:

        created = await link_all_nodes_for_course(10)

        assert created > 0
        assert mock_llm.called
        assert mock_neo4j.called
        assert mock_conn.execute.called

@pytest.mark.asyncio
async def test_link_all_nodes_llm_rejects():
    nodes = [
        NodeInfo(id=1, course_id=10, name="A1", description="", embedding=[1.0, 0.0, 0.0]),
        NodeInfo(id=2, course_id=10, name="B1", description="", embedding=[0.9, 0.1, 0.0]),
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []
    mock_tx = AsyncMock()
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_conn.execute = AsyncMock()

    class MockConnContext:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, *args):
            pass

    # LLM confirms NO semantic connection
    mock_llm_response = {
        "connected": False,
    }

    with patch("app.services.graph_linker._fetch_nodes_for_course", new_callable=AsyncMock, return_value=nodes), \
         patch("app.services.graph_linker.get_ai_conn", return_value=MockConnContext()), \
         patch("app.services.graph_linker._llm_enrich_pair", new_callable=AsyncMock, return_value=mock_llm_response):

        created = await link_all_nodes_for_course(10)
        assert created == 0
        assert not mock_conn.execute.called
