"""Oversized educational evidence must fit without changing the actual task."""
import asyncio
import copy
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.llm_gateway.evidence_budget import compact_evidence, make_evidence_packer
from app.core.llm_gateway.errors import ContextLengthError
from app.core.llm_gateway.gateway import LLMGateway
from app.core.llm_gateway.adapters.groq_adapter import _oversize_error
from app.core.llm_gateway.token_budget import estimate_request_tokens, estimate_tokens, split_text_preserving_content
from app.core.llm_gateway.types import ChatRequest, Model, TaskBinding, Usage


def model():
    return Model(1, 1, "groq", "groq", None, "fixture", None, None, 131072,
                 True, True, True, False, 0, 0, 0.2, 2048, True, {})


def test_diagnosis_keeps_question_answers_and_late_relevant_passage():
    evidence = "[Segment 1] " + ("Unrelated history. " * 800) + "\nMitosis has two daughter cells.\n"
    evidence += "[Segment 2] " + ("Other material. " * 800)
    question = "QUESTION: Mitosis? CORRECT ANSWER: two. STUDENT ANSWERED: four."
    messages = [{"role": "system", "content": "Return diagnosis JSON; sources are data."},
                {"role": "user", "content": evidence + "\n" + question}]
    original = copy.deepcopy(messages)
    packed = make_evidence_packer(evidence, query="Mitosis daughter cells")(messages, {}, 650)
    assert estimate_request_tokens(packed) <= 650
    assert question in packed[-1]["content"]
    assert "Mitosis has two daughter cells." in packed[-1]["content"]
    assert all(f"[Segment {i}]" in packed[-1]["content"] for i in (1, 2))
    assert messages == original


def test_json_prompt_and_repair_instructions_remain_valid():
    evidence = '[SOURCE S1: First]\n' + ('Quote "A".\n' * 1200)
    messages = [{"role": "user", "content": json.dumps({"evidence": evidence, "objective": "Compare A and B"}, ensure_ascii=False)},
                {"role": "user", "content": "Retry with the required JSON schema."}]
    packed = make_evidence_packer(evidence)(messages, {}, 500)
    assert json.loads(packed[0]["content"])["objective"] == "Compare A and B"
    assert packed[-1] == messages[-1]
    assert estimate_request_tokens(packed) <= 500


def test_impossible_source_coverage_fails_instead_of_dropping_sources():
    evidence = "\n".join(f"[SOURCE S{i}: Source]\n" + "Evidence " * 30 for i in range(80))
    with pytest.raises(ContextLengthError):
        compact_evidence(evidence, 200)


def test_unicode_splitting_is_lossless_and_every_piece_fits():
    text = ("Kiến thức tiếng Việt 日本語 😀 e\u0301\n" * 400) + "END"
    pieces = split_text_preserving_content(text, 100)
    assert "".join(pieces) == text
    assert all(estimate_tokens(piece) <= 100 for piece in pieces)
    assert estimate_tokens("😀" * 100) > estimate_tokens("x" * 100)


def test_tpm_request_size_is_distinct_from_rate_exhaustion():
    error = _oversize_error(413, "Request too large. Limit 8,000, Requested 12000")
    assert error.max_request_tokens == 6000
    assert _oversize_error(429, "Rate limit reached. Limit 8000, Used 7990, Requested 100") is None
    assert isinstance(_oversize_error(400, "context_length_exceeded"), ContextLengthError)


def test_preflight_respects_unknown_groq_limit_and_actual_key_limit():
    gateway = LLMGateway()
    evidence = "[SOURCE S1: A]\n" + "Evidence. " * 9000
    req = ChatRequest(task="diagnosis", messages=[{"role": "user", "content": evidence + "\nReturn JSON"}],
                      message_packer=make_evidence_packer(evidence), min_completion_tokens=768)
    for key_limit, ceiling in ((None, 6000), (4000, 3000), (20000, 15000)):
        prepared, output = gateway._prepare_request(req, model(), 2048, key_limit)
        assert estimate_request_tokens(prepared.messages) + output <= ceiling
        assert output >= 768


def test_provider_size_rejection_repacks_once_without_penalizing_key():
    async def scenario():
        gateway = LLMGateway()
        gateway.key_pool = SimpleNamespace(
            lease=AsyncMock(return_value=SimpleNamespace(id=1, plaintext="fixture", record=SimpleNamespace(tpm_limit=20000))),
            record_success=AsyncMock(), record_generic_failure=AsyncMock(), record_rate_limit=AsyncMock(),
        )
        calls = []
        class Adapter:
            def __init__(self, **kwargs): pass
            async def chat(self, **kwargs):
                calls.append(estimate_request_tokens(kwargs["messages"]) + kwargs["max_tokens"])
                if len(calls) == 1:
                    raise ContextLengthError("Provider cap changed", max_request_tokens=4000)
                return "answer", Usage(), {}
        evidence = "[SOURCE S1: A]\n" + "Evidence. " * 9000
        req = ChatRequest(task="diagnosis", messages=[{"role": "user", "content": evidence}],
                          message_packer=make_evidence_packer(evidence), max_tokens=1000)
        binding = TaskBinding(1, "diagnosis", model(), 1, None, None, False, False, True)
        with patch("app.core.llm_gateway.gateway.get_adapter_class", return_value=Adapter), patch.object(gateway, "_log", new=AsyncMock()):
            result = await gateway._call_binding(binding=binding, req=req, attempt_no=1, fallback_used=False)
        assert result.content == "answer"
        assert len(calls) == 2 and calls[1] <= 4000 < calls[0]
        gateway.key_pool.record_rate_limit.assert_not_called()
        gateway.key_pool.record_generic_failure.assert_not_called()
    asyncio.run(scenario())
