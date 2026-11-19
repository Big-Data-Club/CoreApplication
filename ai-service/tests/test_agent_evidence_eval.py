import importlib.util
import json
from pathlib import Path

import httpx
import pytest

module_path = Path(__file__).resolve().parents[1] / "scripts" / "eval_golden_qa.py"
spec = importlib.util.spec_from_file_location("agent_evidence_eval", module_path)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,expected_ok", [
    ("MDP and policy are core concepts [ref 1].", True),
    ("MDP and policy are core concepts.", False),  # Collected sources alone do not pass.
    ("A policy is useful [1].", False),  # Required aspect omitted.
    ("MDP and policy are core concepts [ref 99].", False),
])
async def test_golden_eval_checks_actual_answer_not_retrieval_volume(answer, expected_ok):
    def respond(request):
        payload = json.loads(request.content)
        assert payload["course_id"] == payload["page_context"]["courseId"] == 47
        assert request.headers["x-ai-secret"] == "fixture"
        events = [{"type": "thinking", "data": {"delta": "MDP, policy, Bellman"}},
                  {"type": "text_delta", "data": {"delta": answer}},
                  {"type": "done", "data": {"model": "fixture-model", "references": [{"title": "Source"}],
                      "retrieval_evidence": {"received_entries": 36, "prepared_sources": 1}}}]
        return httpx.Response(200, text="".join("data: " + json.dumps(event) + "\n\n" for event in events))

    case = {"id": "fixture", "message": "What should I master for RL?", "expected_sources": True,
            "must_cover": {"mdp": ["mdp"], "policy": ["policy"]}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await evaluation.run_case(client, "https://fixture.example", "fixture", 42, case, 47)
    assert result["ok"] is expected_ok
    assert result["text"] == answer
    assert result["retrieval_evidence"]["received_entries"] == 36
    assert "elapsed_seconds" in result
