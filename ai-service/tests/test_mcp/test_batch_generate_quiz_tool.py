from __future__ import annotations

import pytest

from app.agents.tools.teacher.mcp_batch_generate_quiz import (
    _balance_correct_position,
    _classification,
    _quiz_settings_payload,
    _save_to_question_bank,
)


@pytest.mark.asyncio
async def test_mcp_questions_are_saved_as_question_bank_drafts(monkeypatch):
    captured = {}

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"data": {"items": [{"id": 91}], "count": 1}}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, json, headers):
            captured.update(url=url, payload=json, headers=headers)
            return Response()

    monkeypatch.setattr(
        "app.agents.tools.teacher.mcp_batch_generate_quiz.httpx.AsyncClient",
        lambda **kwargs: Client(),
    )

    items = await _save_to_question_bank(
        course_id=69,
        user_id=2,
        quizzes=[{
            "node_id": 6647,
            "title": "Attention",
            "questions": [{
                "question": "Which option is correct?",
                "options": ["A", "B"],
                "correct_index": 1,
                "explanation": "Because B.",
                "points": 10.0,
                "difficulty": "EASY",
                "bloom_level": "remember",
                "source_refs": ["content:2559#attention"],
            }],
        }],
    )

    assert [item["id"] for item in items] == [91]
    assert captured["url"].endswith("/courses/69/question-bank")
    item = captured["payload"]["items"][0]
    assert item["status"] == "DRAFT"
    assert item["source"] == "AI_GENERATED"
    assert item["answer_options"][1]["is_correct"] is True
    assert item["settings"]["source_refs"] == ["content:2559#attention"]


def test_bloom_ladder_and_difficulty_are_deterministic():
    expected = [
        ("remember", "EASY"),
        ("remember", "EASY"),
        ("remember", "EASY"),
        ("remember", "EASY"),
        ("understand", "MEDIUM"),
        ("understand", "MEDIUM"),
        ("apply", "MEDIUM"),
        ("analyze", "HARD"),
        ("analyze", "HARD"),
        ("analyze", "HARD"),
    ]
    assert [_classification({}, index, enforce_ladder=True) for index in range(1, 11)] == expected


def test_correct_answers_are_balanced_without_changing_answer_text():
    options = ["wrong 1", "correct", "wrong 2", "wrong 3"]
    positions = []
    for sequence in range(4):
        rotated, correct = _balance_correct_position(options, 1, sequence)
        positions.append(correct)
        assert rotated[correct] == "correct"
    assert positions == [0, 1, 2, 3]


def test_complete_quiz_settings_include_schedule_and_attempt_limit():
    payload = _quiz_settings_payload(
        {
            "section_id": 378,
            "time_limit_minutes": 30,
            "max_attempts": 10,
            "passing_score": 80,
            "available_from": "2026-09-02T08:00:00+07:00",
            "available_until": "2026-09-30T23:59:00+07:00",
            "shuffle_answers": True,
            "publish": True,
        },
        [91, 92],
        fallback_title="Attention performance",
    )

    assert payload["item_ids"] == [91, 92]
    assert payload["max_attempts"] == 10
    assert payload["time_limit_minutes"] == 30
    assert payload["available_from"].endswith("+07:00")
    assert payload["available_until"].endswith("+07:00")
    assert payload["shuffle_answers"] is True
    assert payload["is_published"] is True
