"""Optional Jev decision entry point; keys are managed by the LLM gateway."""

from __future__ import annotations

from typing import Any

from app.core.llm_gateway.gateway import get_gateway


async def decide_decomposition(state: str) -> dict[str, Any] | None:
    """Use the gateway's managed key; None falls back to local routing."""
    return await get_gateway().decide_jev(state)
