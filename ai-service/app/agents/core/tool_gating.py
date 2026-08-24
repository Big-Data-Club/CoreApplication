"""
ai-service/app/agents/core/tool_gating.py

Planner-driven tool disclosure. Instead of dumping every tool schema into
the prompt (which drowns small models in 20+ choices per turn), the first
gateway call only sees the tools the Unified Planner selected for this
turn. Later iterations re-disclose the full set so the model can recover
if the plan missed something.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Tools that are cheap, safe and broadly useful - always worth keeping in
# the focused view when the planner asked for retrieval of any kind.
_RETRIEVAL_CORE = {"search_course_materials", "search_web", "fetch_page"}


def select_tool_schemas(
    all_schemas: list[dict],
    selected_names: list[str] | None,
) -> tuple[list[dict], bool]:
    """
    Return (schemas_to_disclose, gated).

    Gating rules (conservative by design):
      * No plan output / empty selection -> full set (gated=False).
      * Selection larger than half the catalogue -> gating adds no noise
        reduction; disclose everything (gated=False).
      * Otherwise disclose selected + retrieval core intersection, keeping
        registry order for stable prompts (gated=True).
    Unknown names are silently dropped (planner hallucination guard).
    """
    if not all_schemas:
        return [], False

    valid = {
        s.get("function", {}).get("name") or s.get("name")
        for s in all_schemas
        if isinstance(s, dict)
    }
    picked = [n for n in (selected_names or []) if n in valid]

    if not picked or len(picked) >= max(1, len(all_schemas) // 2):
        return all_schemas, False

    # Retrieval core joins only when the turn already involves retrieval;
    # otherwise keep strictly to what the planner chose.
    keep: set[str] = set(picked)
    if any(n in _RETRIEVAL_CORE for n in picked):
        keep |= _RETRIEVAL_CORE & valid

    focused = [
        s for s in all_schemas
        if (s.get("function", {}).get("name") or s.get("name")) in keep
    ]
    logger.info(
        "Tool gating: %d/%d schemas disclosed (%s)",
        len(focused), len(all_schemas), ",".join(sorted(keep)),
    )
    return focused, True
