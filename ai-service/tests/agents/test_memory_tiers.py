"""Memory boundaries, provenance, lifecycle and retry regressions (no live LLM)."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.memory.memory_policy import (
    bind_memory_sources, merge_memory_items, select_memory_for_prompt,
)
from app.agents.memory.mtm import MTMemory
from app.agents.memory.ltm import LTMemory
from app.agents.memory.consolidation_pipeline import consolidate_session_job
from app.agents.tools.registry import execute_tool
from app.agents.tools.shared.recall_conversation import RecallConversationTool


def preference(message_id=10, **changes):
    return {"kind": "preference", "key": "response_style", "scope": "user",
            "value": "concise", "source": "user_statement", "confidence": 0.9,
            "source_message_id": message_id, "source_quote": "Keep it concise", **changes}


def connection_for(conn):
    @asynccontextmanager
    async def connection():
        yield conn
    return connection


def test_course_memory_requires_exact_known_scope_and_finite_confidence():
    items = [{"kind": "anchor", "value": "MPI", "scope": "course", "course_id": 27},
             {"value": "unknown course", "scope": "course"},
             {"value": "poison", "confidence": float("nan")},
             {"value": "weak guess", "confidence": 0.1},
             {"value": "completed", "status": "completed"}]
    assert select_memory_for_prompt(items, course_id=None) == []
    assert select_memory_for_prompt(items, course_id=28) == []
    assert [x["value"] for x in select_memory_for_prompt(items, course_id=27)] == ["MPI"]


def test_only_original_user_quote_promotes_preferences_and_course_is_server_bound():
    messages = [{"id": 10, "role": "user", "content": "Keep it concise please"},
                {"id": 11, "role": "assistant", "content": "You prefer English"}]
    items = bind_memory_sources([
        preference(), preference(11, source_quote="You prefer English"),
        preference(10, source_quote="not in original"),
        preference(10, kind="pending_action"),
        preference(10, key="role_admin"),
        {"value": "MPI", "scope": "course", "course_id": 99},
    ], messages, 27)
    assert [x["scope"] for x in items] == ["user", "session", "session", "session", "session", "course"]
    assert items[-1]["course_id"] == 27
    assert items[1]["source_message_id"] is None
    assert bind_memory_sources([items[-1]], messages, None)[0]["scope"] == "session"


def test_correction_and_tombstone_win_by_source_order_not_session_activity():
    newer = preference(20, value="detailed", status="superseded")
    merged = merge_memory_items([newer], [preference(10)])
    assert len(merged) == 1 and merged[0]["status"] == "superseded"
    assert select_memory_for_prompt(merged, course_id=None) == []
    updated = merge_memory_items(merged, [preference(30, value="detailed")])
    assert updated[0]["source_message_id"] == 30
    for index in range(40):
        merged = merge_memory_items(merged, [{"value": f"local fact {index}"}])
    assert len(merged) == 20
    assert merged[-1]["status"] == "superseded"


@pytest.mark.asyncio
async def test_cross_session_preferences_keep_newest_source_including_tombstones():
    conn = AsyncMock()
    conn.fetch.return_value = [
        {"items": [preference(10), preference(50, scope="session"), preference(60, source="conversation_summary")]},
        {"items": [preference(20, status="superseded")]},
    ]
    with patch("app.agents.memory.mtm.get_ai_conn", connection_for(conn)):
        items = await MTMemory().get_user_preferences(42, "mentor", "current")
    assert len(items) == 1 and items[0]["source_message_id"] == 20
    assert items[0]["status"] == "superseded"
    assert conn.fetch.await_args.args[1:] == (42, "mentor", "current")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["create_new_session", "get_or_create_session"])
async def test_new_session_starts_without_previous_task(method):
    conn = AsyncMock()
    conn.fetchrow.side_effect = [None, {"id": uuid4()}]
    with patch("app.agents.memory.mtm.get_ai_conn", connection_for(conn)):
        result = await getattr(MTMemory(), method)(42, "mentor")
    assert result["context"] == {}
    assert conn.fetchrow.await_count == 2
    assert "IS NOT DISTINCT FROM" in conn.fetchrow.await_args_list[0].args[0]


@pytest.mark.asyncio
async def test_archive_tool_cannot_forge_session_or_owner_and_bounds_results():
    with patch("app.agents.tools.shared.recall_conversation.message_store.search_history", new=AsyncMock(return_value=[])) as read:
        denied = await execute_tool("recall_conversation", {"_user_id": 7, "_session_id": "foreign"}, user_id=42)
        assert denied.status == "error"
        read.assert_not_awaited()
        denied = await execute_tool("recall_conversation", {"_user_id": 7, "_session_id": "foreign"}, user_id=42, session_id="own")
        assert denied.data["error"] == "reserved_argument"
        read.assert_not_awaited()
        result = await execute_tool("recall_conversation", {}, user_id=42, session_id="own")
        assert result.status == "success"
        read.assert_awaited_once_with("own", 42, "", 10, "user")
    with patch("app.agents.tools.shared.recall_conversation.message_store.search_history", new=AsyncMock(return_value=[{"id": 1, "role": "user", "content": "x" * 5000}])):
        result = await RecallConversationTool().execute(_user_id=42, _session_id="own")
        assert len(result.data["results"][0]["snippet"]) <= 1600
        assert result.data["results"][0]["excerpted"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["episode", "cas"])
async def test_worker_does_not_discard_hot_history_when_durable_write_loses(failure):
    session = {"user_id": 42, "agent_type": "mentor", "course_id": None, "context": {}}
    with (
        patch("app.agents.memory.consolidation_pipeline.mtm.get_session", new=AsyncMock(return_value=session)),
        patch("app.agents.memory.consolidation_pipeline.message_store.get_unconsolidated", new=AsyncMock(return_value=[{"id": 10}])),
        patch("app.agents.memory.consolidation_pipeline.compress_conversation", new=AsyncMock(return_value={"key_facts": {"current_topic": "MPI"}})) as compress,
        patch("app.agents.memory.consolidation_pipeline.ltm.store_episode", new=AsyncMock(return_value=None if failure == "episode" else "episode")) as episode,
        patch("app.agents.memory.consolidation_pipeline.mtm.save_compressed", new=AsyncMock(return_value=False)) as save,
        patch("app.agents.memory.consolidation_pipeline.stm.trim_to_recent", new=AsyncMock()) as trim,
    ):
        with pytest.raises(RuntimeError):
            await consolidate_session_job({"session_id": "own", "user_id": 42, "context": {"course_id": 99}})
    assert compress.await_args.kwargs["course_id"] is None
    assert episode.await_args.kwargs["course_id"] is None
    trim.assert_not_awaited()
    if failure == "episode":
        save.assert_not_awaited()
    else:
        assert save.await_args.kwargs["expected_cursor"] == 0


@pytest.mark.asyncio
async def test_worker_rejects_foreign_session_before_reading_transcript():
    with (
        patch("app.agents.memory.consolidation_pipeline.mtm.get_session", new=AsyncMock(return_value={"user_id": 7, "agent_type": "mentor"})),
        patch("app.agents.memory.consolidation_pipeline.message_store.get_unconsolidated", new=AsyncMock()) as read,
    ):
        with pytest.raises(ValueError):
            await consolidate_session_job({"session_id": "foreign", "user_id": 42})
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_episode_storage_is_durable_without_embedding_and_pg_errors_propagate():
    conn = AsyncMock()
    conn.fetchrow.return_value = {"id": uuid4(), "summary": "MPI", "qdrant_point_id": None}
    with (
        patch("app.agents.memory.ltm.get_ai_conn", connection_for(conn)),
        patch("app.agents.memory.ltm.settings.use_qdrant", False),
        patch("app.core.embeddings.create_passage_embedding", new=AsyncMock()) as embed,
    ):
        assert await LTMemory().store_episode("own", 42, "mentor", "MPI")
        embed.assert_not_awaited()
        conn.fetchrow.side_effect = RuntimeError("database unavailable")
        with pytest.raises(RuntimeError):
            await LTMemory().store_episode("own", 42, "mentor", "MPI")


@pytest.mark.asyncio
async def test_recent_episode_is_not_a_semantic_confidence_score():
    conn = AsyncMock()
    conn.fetch.return_value = [{"summary": "MPI", "session_id": "own", "course_id": None, "created_at": datetime.now(timezone.utc)}]
    with patch("app.agents.memory.ltm.get_ai_conn", connection_for(conn)):
        episodes = await LTMemory()._recall_from_pg(42, "mentor")
    assert episodes[0]["score"] is None
    assert episodes[0]["retrieval"] == "recent"
    assert conn.fetch.await_args.args[1:] == (42, "mentor", [], 3)


@pytest.mark.asyncio
async def test_index_failure_keeps_durable_episode_and_does_not_mark_it_indexed():
    conn = AsyncMock()
    episode_id = uuid4()
    conn.fetchrow.return_value = {"id": episode_id, "summary": "Canonical", "qdrant_point_id": None}
    with (
        patch("app.agents.memory.ltm.get_ai_conn", connection_for(conn)),
        patch("app.agents.memory.ltm.settings.use_qdrant", True),
        patch("app.core.embeddings.create_passage_embedding", new=AsyncMock(side_effect=RuntimeError("embedding down"))),
    ):
        assert await LTMemory().store_episode("own", 42, "mentor", "MPI") == str(episode_id)
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
async def test_vector_payload_is_never_used_without_owned_pg_hydration(stale):
    client, conn = AsyncMock(), AsyncMock()
    client.search.return_value = [SimpleNamespace(id=123, score=0.8, payload={"summary": "Forged vector payload"})]
    conn.fetch.return_value = [] if stale else [{"summary": "Canonical PG", "session_id": "own",
        "course_id": 27, "created_at": datetime.now(timezone.utc), "qdrant_point_id": 123}]
    fallback = AsyncMock(return_value=[])
    memory = LTMemory()
    with (
        patch("app.agents.memory.ltm.get_ai_conn", connection_for(conn)),
        patch("app.agents.memory.ltm.settings.use_qdrant", True),
        patch("app.core.embeddings.create_embedding", new=AsyncMock(return_value=[0.1])),
        patch("app.services.qdrant_service.qdrant_service._get_client", return_value=client),
        patch.object(memory, "_recall_from_pg", fallback),
    ):
        episodes = await memory.recall(42, "mentor", "MPI", course_ids=[27])
    assert conn.fetch.await_args.args[1:] == (42, "mentor", [27], [123])
    if stale:
        assert episodes == []
        fallback.assert_awaited_once()
    else:
        assert episodes[0]["summary"] == "Canonical PG"
        assert episodes[0]["score"] == 0.8
        fallback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs", [{"limit": 100000}, {"limit": True}, {"role": []}, {"query": "x" * 161}])
async def test_archive_rejects_invalid_parameters_without_reading(kwargs):
    with patch("app.agents.tools.shared.recall_conversation.message_store.search_history", new=AsyncMock()) as read:
        result = await RecallConversationTool().execute(_user_id=42, _session_id="own", **kwargs)
    assert result.status == "error"
    read.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [0, 64, 512, 2000])
async def test_cross_session_preferences_share_actual_budget_without_course_enrichment(budget):
    from app.agents.memory.context_builder import ContextBuilder
    config = SimpleNamespace(max_context_tokens=4000, stm_budget=1000,
                             ltm_facts_budget=500, ltm_episodic_budget=500)
    with (
        patch("app.agents.memory.context_builder.get_settings", return_value=config),
        patch("app.agents.memory.context_builder.mtm.get_user_preferences", new=AsyncMock(return_value=[preference()])) as prefs,
        patch("app.agents.memory.context_builder.ltm.recall", new=AsyncMock()) as recall,
        patch("httpx.AsyncClient") as http,
    ):
        result = await ContextBuilder().build(42, "own", "mentor", "hello", course_id=27,
            memory_budget_tokens=budget, session_context={},
            history_window={"messages": [], "status": "available", "source": "postgres"})
    assert result["token_estimate"] <= budget
    recall.assert_not_awaited()
    http.assert_not_called()
    if budget >= 512:
        assert "Keep it concise" in result["prompt_section"]
        prefs.assert_awaited_once_with(42, "mentor", "own")
    else:
        prefs.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", [False, True])
async def test_worker_boundary_does_not_acknowledge_transient_memory_failure(terminal):
    from app.agents.memory.consolidation_pipeline import ConsolidationRejected
    with patch("app.core.logging_config.configure_logging"):
        from app.worker.kafka_worker import process_ai_command
    error = ConsolidationRejected("wrong owner") if terminal else RuntimeError("storage unavailable")
    with (
        patch("app.agents.memory.consolidation_pipeline.consolidate_session_job", new=AsyncMock(side_effect=error)),
        patch("app.worker.kafka_worker.publish_ai_job_status", new=AsyncMock()) as status,
    ):
        job = {"job_id": "test-memory-job", "command_type": "CONSOLIDATE_SESSION", "payload": {}}
        if terminal:
            await process_ai_command(job)
        else:
            with pytest.raises(RuntimeError, match="storage unavailable"):
                await process_ai_command(job)
    assert status.await_args.kwargs["status"] == "failed"
