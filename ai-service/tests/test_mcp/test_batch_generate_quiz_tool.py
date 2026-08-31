from __future__ import annotations

import pytest

from app.agents.tools.teacher.mcp_batch_generate_quiz import _save_to_question_bank


@pytest.mark.asyncio
async def test_mcp_questions_are_saved_as_question_bank_drafts(monkeypatch):
    captured = {}

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"data": [{"id": 91}, {"id": 92}]}

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
            }],
        }],
    )

    assert [item["id"] for item in items] == [91, 92]
    assert captured["url"].endswith("/courses/69/question-bank")
    item = captured["payload"]["items"][0]
    assert item["status"] == "DRAFT"
    assert item["source"] == "AI_GENERATED"
    assert item["answer_options"][1]["is_correct"] is True
