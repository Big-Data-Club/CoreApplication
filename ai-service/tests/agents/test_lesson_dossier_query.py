from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.memory import lesson_dossier


@pytest.mark.asyncio
async def test_ancestor_query_uses_recursive_alias_and_course_scope():
    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        {"title": "Lesson", "status": "ready"},
        {"chunks": 0, "min_page": None, "max_page": None,
         "start_sec": None, "end_sec": None},
    ]
    conn.fetch.side_effect = [
        [{"id": 4, "parent_id": 2, "name": "Child", "name_vi": None, "level": 2}],
        [{"node_id": 4, "root_path": ["Root", "Child"]}],
        [],
    ]

    @asynccontextmanager
    async def fake_conn():
        yield conn

    with patch("app.core.database.get_ai_conn", fake_conn):
        lesson_dossier._CACHE.clear()
        result = await lesson_dossier.load_lesson_dossier(74, 2862)

    assert result["nodes"][0]["path"] == ["Root", "Child"]
    query = conn.fetch.call_args_list[1].args[0]
    assert "JOIN chain c" in query
    assert "chain.root_path" not in query
    assert "k.course_id = $2" in query
    assert conn.fetch.call_args_list[1].args[2] == 74
