from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.studio.authoring_context import prepare_authoring_context, select_evidence


def test_small_context_is_kept_verbatim():
    with patch(
        "app.services.studio.authoring_context._request_budget",
        new=AsyncMock(return_value=2000),
    ):
        result = asyncio.run(prepare_authoring_context(
            [{"title": "A", "text": "Exact source text"}],
            requested_output_tokens=500,
            fixed_prompt_tokens=100,
        ))
    assert result.reduced is False
    assert "Exact source text" in result.text
    assert "SOURCE S1" in result.text


def test_large_context_reduces_every_source_with_stable_refs():
    async def fake_summary(**kwargs):
        content = kwargs["messages"][1]["content"]
        label = "S1" if "S1" in content else "S2"
        return {"summary": f"Summary for {label}", "key_facts": [f"Fact {label}"]}

    with (
        patch("app.services.studio.authoring_context._request_budget", new=AsyncMock(return_value=900)),
        patch("app.services.studio.authoring_context.chat_complete_json", new=AsyncMock(side_effect=fake_summary)),
    ):
        result = asyncio.run(prepare_authoring_context(
            [
                {"title": "First", "text": "A" * 3000},
                {"title": "Second", "text": "B" * 3000},
            ],
            requested_output_tokens=500,
            fixed_prompt_tokens=100,
        ))
    assert result.reduced is True
    assert "S1" in result.text
    assert "S2" in result.text
    assert result.estimated_tokens <= result.token_budget


def test_select_evidence_keeps_only_referenced_sources():
    text = "[EVIDENCE S1: A]\nFact A\n\n[EVIDENCE S2: B]\nFact B"
    selected = select_evidence(text, ["S2"])
    assert "Fact B" in selected
    assert "Fact A" not in selected
