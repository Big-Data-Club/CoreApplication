import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.core.source_reader import SourceReader, apply_source_notes
from app.core.llm_gateway.token_budget import estimate_request_tokens
from app.agents.core.sub_agents import DraftingSpecialist, CritiqueSpecialist, CritiqueReport


@pytest.mark.asyncio
async def test_readers_reject_invented_quotes_and_preserve_original_refs():
    sources = [{"ref": 5, "text": "A policy maps each state to a distribution over available actions."},
               {"ref": 12, "text": "The value function describes the expected discounted return."}]

    async def respond(**kwargs):
        assert estimate_request_tokens(kwargs["messages"]) + kwargs["max_tokens"] < 3000
        payload = json.loads(kwargs["messages"][1]["content"])
        rows = payload["source_segments"]
        return {"notes": [{"ref": row["ref"], "quote": row["text"], "aspect": "definition"} for row in rows]
            + [{"ref": 999, "quote": sources[0]["text"]},
               {"ref": 5, "quote": "The discount factor must always equal 0.999."}],
            "missing_aspects": ["Which prerequisites are assumed?"]}

    reader = SourceReader()
    with patch("app.agents.core.source_reader.get_gateway", return_value=SimpleNamespace(preview_request_budget=AsyncMock(return_value=3000))), \
         patch("app.agents.core.source_reader.chat_complete_json", side_effect=respond) as llm:
        await reader.read(sources, "Which RL concepts should I master?")
        calls = llm.call_count
        await reader.read(sources, "Which RL concepts should I master?")
    assert llm.call_count == calls
    assert set(reader.notes) == {5, 12}
    assert reader.snapshot()["reader_rejected_notes"] == 2
    assert reader.snapshot()["reader_complete_sources"] == 2
    assert reader.snapshot()["reader_pending_segments"] == 0
    assert reader.missing_aspects == ["Which prerequisites are assumed?"]


@pytest.mark.asyncio
async def test_parallelism_and_total_reader_calls_are_bounded():
    active, peak = 0, 0
    async def respond(**kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.001)
        active -= 1
        rows = json.loads(kwargs["messages"][1]["content"])["source_segments"]
        return {"notes": [{"ref": row["ref"], "quote": row["text"][:100]} for row in rows]}

    reader = SourceReader()
    sources = [{"ref": n, "text": f"Distinct source {n}. " * 130} for n in range(1, 14)]
    with patch("app.agents.core.source_reader.get_gateway", return_value=SimpleNamespace(preview_request_budget=AsyncMock(return_value=3000))), \
         patch("app.agents.core.source_reader.chat_complete_json", side_effect=respond) as llm:
        await reader.read(sources, "Compare these sources")
        await reader.read(sources, "Compare these sources")
    assert llm.call_count == reader.MAX_BATCHES
    assert peak <= reader.CONCURRENCY
    assert reader.snapshot()["reader_pending_segments"] > 0


def test_source_notes_modify_only_private_read_copies():
    text = "The Bellman equation relates the value of a state to subsequent rewards."
    original = [{"role": "tool", "tool_call_id": "read", "content": json.dumps({"status": "success",
        "data": {"chunks": [{"ref": 5, "text": text, "child_text": "Old child"}]},
        "evidence": {"source": "search_course_materials"}})},
        {"role": "tool", "tool_call_id": "write", "content": json.dumps({
            "data": {"chunks": [{"ref": 5, "text": "Pending approval"}]},
            "evidence": {"source": "generate_content_draft"}})}]
    prepared = apply_source_notes(original, {5: [{"quote": text[:41], "aspect": "Bellman"}]})
    row = json.loads(prepared[0]["content"])["data"]["chunks"][0]
    assert row["text"] == text[:41] and "child_text" not in row and row["_excerpted"]
    assert prepared[1] == original[1]
    assert json.loads(original[0]["content"])["data"]["chunks"][0]["text"] == text


@pytest.mark.asyncio
async def test_deep_writer_packs_sources_without_erasing_question_or_citation_labels():
    context = "\n\n".join(f"[Source {i}]\n" + "Reference detail. " * 300 for i in range(1, 7))
    question = "What are the RL prerequisites?"

    async def stream(req):
        original = json.dumps(req.messages)
        for budget in (1800, 4250):
            packed = req.message_packer(req.messages, {}, budget)
            assert estimate_request_tokens(packed) <= budget
            assert question in packed[-1]["content"]
            assert all(f"[Source {i}]" in packed[-1]["content"] for i in range(1, 7))
        assert json.dumps(req.messages) == original
        yield "An answer [1].", None, {"model": "fixture", "choices": [{"finish_reason": "stop"}]}

    with patch("app.agents.core.sub_agents.get_gateway", return_value=SimpleNamespace(stream=stream)):
        events = [ev async for ev in DraftingSpecialist("owned", "turn").execute(question, context)]
    assert events[-1] == "An answer [1]."


@pytest.mark.asyncio
async def test_deep_review_packs_evidence_while_preserving_the_draft():
    context = "\n\n".join(f"[Source {i}]\n" + "Reference detail. " * 300 for i in range(1, 7))
    draft = "The draft must cover MDP, policy, value and learning order."
    report = CritiqueReport(factuality_score=.9, pedagogy_score=.9, format_score=.9,
                            verdict="approve", critique_report="No decisive omission found in this fixture.")

    async def review(**kwargs):
        packed = kwargs["message_packer"](kwargs["messages"], {}, 3000)
        assert estimate_request_tokens(packed) <= 3000
        assert draft in packed[-1]["content"]
        assert all(f"[Source {i}]" in packed[-1]["content"] for i in range(1, 7))
        return report

    with patch("app.agents.core.sub_agents.chat_complete_structured", side_effect=review):
        events = [ev async for ev in CritiqueSpecialist("owned", "turn").execute("What should I master?", draft, context)]
    assert report in events
