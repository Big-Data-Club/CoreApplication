"""No live model, Kafka, database or vector store is used by these regressions."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services import quiz_index_service as service
from app.api.endpoints.quiz_index import IndexRequest, handle


def test_chunks_do_not_include_answer_keys_or_explanation():
    question = {
        "question_text": "**MPI**?",
        "options": ["A", "B"],
        "explanation": "secret",
        "correct_answers": ["A"],
    }
    assert service.question_content(question) == "**MPI**?\n\nA\n\nB"
    assert service.point_id(1, "a", 2) == service.point_id(1, "a", 2)
    assert service.point_id(1, "a", 2) != service.point_id(1, "b", 2)


def test_private_endpoint_rejects_missing_service_authentication():
    body = IndexRequest(quiz_id=1, course_id=2, requester_id=3, revision="a" * 32)
    with patch(
        "app.api.endpoints.quiz_index.get_settings",
        return_value=SimpleNamespace(ai_service_secret="real-secret"),
    ):
        with pytest.raises(Exception) as exc:
            asyncio.run(handle("queue", body, SimpleNamespace(headers={})))
    assert exc.value.status_code == 403


def run_worker(*, changed=False, duplicate=False):
    job_id = uuid4()
    job = {
        "quiz_id": 42,
        "course_id": 7,
        "requester_id": 3,
        "revision": "a" * 32,
        "generation": None,
        "job_id": job_id,
    }
    conn = SimpleNamespace(
        fetchrow=AsyncMock(return_value=None if duplicate else job),
        fetchval=AsyncMock(
            side_effect=lambda query, *args: [99] if "array_agg" in query else 42
        ),
        execute=AsyncMock(),
        executemany=AsyncMock(),
    )

    @asynccontextmanager
    async def transaction():
        yield

    conn.transaction = transaction

    @asynccontextmanager
    async def database():
        yield conn

    responses = [
        {"course_id": 7, "data": {"revision": "a" * 32, "total": 1}},
        {
            "course_id": 7,
            "data": [
                {
                    "id": 12,
                    "node_id": 99,
                    "question_text": "Question",
                    "points": 10,
                    "options": ["A"],
                    "source_hash": "b" * 32,
                }
            ],
        },
        {"course_id": 7, "data": []},
        {
            "course_id": 7,
            "data": {"revision": ("c" if changed else "a") * 32, "total": 1},
        },
    ]
    vector = SimpleNamespace(
        upsert=AsyncMock(), search_batch=AsyncMock(return_value=[[]])
    )
    with patch.object(service, "get_ai_conn", database), patch.object(
        service, "ensure_collection", AsyncMock()
    ), patch.object(service, "source", AsyncMock(side_effect=responses)), patch.object(
        service,
        "create_passage_embeddings_batch",
        AsyncMock(return_value=[[0.0] * 1024]),
    ) as embed, patch.object(
        service.qdrant_service, "_get_client", return_value=vector
    ):
        if changed:
            with pytest.raises(ValueError, match="changed during"):
                asyncio.run(service.process(str(job_id), 42))
        else:
            result = asyncio.run(service.process(str(job_id), 42))
            assert result["status"] == ("already_claimed" if duplicate else "ready")
        if duplicate:
            embed.assert_not_awaited()
        else:
            vector.upsert.assert_awaited_once()
            vector.search_batch.assert_not_awaited()
            assert vector.upsert.call_args.args[0] == "quiz_questions_private"
            record = conn.executemany.call_args.args[1][0]
            assert record[6] == 99  # Explicit existing node is retained.
            assert record[7] is None
        publishes = [
            call
            for call in conn.fetchval.call_args_list
            if "status='ready'" in call.args[0]
        ]
        assert len(publishes) == (0 if changed or duplicate else 1)


def test_worker_publishes_one_chunk_and_keeps_explicit_node():
    run_worker()


def test_changed_quiz_is_not_published():
    run_worker(changed=True)


def test_duplicate_worker_does_not_reembed():
    run_worker(duplicate=True)


def test_search_requires_current_revision_and_all_scope_filters():
    job_id = uuid4()
    body = IndexRequest(
        quiz_id=1, course_id=2, requester_id=3, revision="a" * 32, query="MPI"
    )
    conn = SimpleNamespace(
        fetchrow=AsyncMock(return_value={"generation": job_id}),
        fetch=AsyncMock(return_value=[]),
    )

    @asynccontextmanager
    async def database():
        yield conn

    client = SimpleNamespace(search=AsyncMock(return_value=[]))
    with patch.object(service, "get_ai_conn", database), patch.object(
        service, "create_embedding", AsyncMock(return_value=[0.0] * 1024)
    ), patch.object(service.qdrant_service, "_get_client", return_value=client):
        assert asyncio.run(service.search(body)) == {"items": []}
    conditions = client.search.call_args.kwargs["query_filter"].must
    assert {c.key: c.match.value for c in conditions} == {
        "quiz_id": 1,
        "course_id": 2,
        "generation": str(job_id),
    }
    assert "revision=$3" in conn.fetchrow.call_args.args[0]


def test_long_question_embeddings_cover_the_tail_in_bounded_windows():
    calls = []

    async def embed(texts):
        calls.extend(texts)
        assert len(texts) <= 16
        return [[1.0] + [0.0] * 1023 for _ in texts]

    with patch.object(service, "create_passage_embeddings_batch", embed):
        result = asyncio.run(service.embed_questions(["a" * 9000 + "TAIL_EVIDENCE"]))
    assert len(result) == 1 and len(result[0]) == 1024
    assert any("TAIL_EVIDENCE" in value for value in calls)
    assert all(len(value) <= 3000 for value in calls)


def test_teacher_tool_checks_course_before_search_and_is_absent_for_students():
    from app.agents.tools.teacher.search_quiz_questions import SearchQuizQuestionsTool
    from app.agents.tools.registry import get_tools

    assert "search_quiz_questions" not in {tool.name for tool in get_tools("mentor")}
    assert "search_quiz_questions" in {tool.name for tool in get_tools("teacher")}
    with patch.object(
        service,
        "source",
        AsyncMock(return_value={"course_id": 99, "data": {"revision": "a" * 32}}),
    ), patch.object(service, "search", AsyncMock()) as search:
        result = asyncio.run(
            SearchQuizQuestionsTool().execute(
                _user_id=3, _course_id=7, quiz_id=42, query="MPI"
            )
        )
    assert result.status == "error"
    search.assert_not_awaited()
