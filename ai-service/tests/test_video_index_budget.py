"""Index long transcripts without dropping evidence or hiding extraction errors."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.llm_gateway.errors import ContextLengthError, ProviderError
from app.core.llm_gateway.token_budget import estimate_request_tokens
from app.services.auto_index_service import AutoIndexService, _node_extraction_messages
from app.services.chunker import DocumentChunk


@pytest.fixture
def extraction(monkeypatch):
    preview = AsyncMock(return_value=6000)
    monkeypatch.setattr("app.services.auto_index_service.get_gateway",
                        lambda: SimpleNamespace(preview_request_budget=preview))
    return AutoIndexService(), preview


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [3000, 6000, 20000])
async def test_batches_fit_full_prompt_and_preserve_every_evidence_fragment(extraction, monkeypatch, budget):
    service, preview = extraction
    preview.return_value = budget
    chunks = [DocumentChunk(text=f"Bài giảng {i}: " + "Giải thích khái niệm và ví dụ. " * 200,
                            index=i, source_type="video", start_time_sec=i * 90) for i in range(3)]
    received = {c.index: [] for c in chunks}
    async def extract(text, file_type, language, *args, **kwargs):
        assert estimate_request_tokens(_node_extraction_messages(text, file_type, language, None)) + kwargs["max_tokens"] + min(256, budget // 20) <= budget
        for index, chunk in kwargs["evidence_chunks"].items():
            assert chunk.start_time_sec == index * 90
            assert f"[EVIDENCE CHUNK {index}]\n{chunk.text}" in text
            received[index].append(chunk.text)
        return [], []
    monkeypatch.setattr(service, "_extract_nodes_and_relations", extract)
    assert await service._batch_extract_nodes(chunks, "", "video", "vi") == ([], [])
    assert {index: "".join(parts) for index, parts in received.items()} == {c.index: c.text for c in chunks}


@pytest.mark.asyncio
async def test_smaller_actual_key_retries_by_splitting_evidence(extraction, monkeypatch):
    service, _ = extraction
    chunks = [DocumentChunk(text=f"Concept {i}. " * 40, index=i, source_type="video") for i in range(2)]
    calls = []
    async def extract(text, *args, **kwargs):
        calls.append(text)
        if len(kwargs["evidence_chunks"]) > 1:
            raise ContextLengthError("Actual key is smaller than preview")
        return [], []
    monkeypatch.setattr(service, "_extract_nodes_and_relations", extract)
    assert await service._batch_extract_nodes(chunks, "", "video", "en") == ([], [])
    assert len(calls) == 3
    assert chunks[0].text in calls[1] and chunks[1].text in calls[2]


@pytest.mark.asyncio
async def test_too_small_budget_fails_before_calling_model(extraction, monkeypatch):
    service, preview = extraction
    preview.return_value = 100
    extract = AsyncMock(return_value=([], []))
    monkeypatch.setattr(service, "_extract_nodes_and_relations", extract)
    with pytest.raises(ContextLengthError):
        await service._batch_extract_nodes([DocumentChunk(text="Concept explanation. " * 20,
            index=1, source_type="video")], "", "video", "en")
    extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_is_not_an_empty_success(monkeypatch):
    monkeypatch.setattr("app.services.auto_index_service.chat_complete_json",
                        AsyncMock(side_effect=ProviderError("transient provider failure")))
    with pytest.raises(ProviderError):
        await AutoIndexService()._extract_nodes_and_relations("Evidence", "video", "en")


@pytest.mark.asyncio
async def test_index_marks_failed_when_node_extraction_fails(extraction, monkeypatch):
    service, _ = extraction
    monkeypatch.setattr(service, "_extract_text_and_chunks", AsyncMock(return_value=("Transcript", [])))
    monkeypatch.setattr(service, "_batch_extract_nodes", AsyncMock(side_effect=ContextLengthError("too small")))
    status, store = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service, "_update_content_status", status)
    monkeypatch.setattr(service, "_chunk_and_store", store)
    with pytest.raises(ContextLengthError):
        await service.auto_index(7, 27, "lecture.mp4", "video/mp4", b"video")
    assert status.call_args.args[1] == "failed"
    store.assert_not_awaited()
