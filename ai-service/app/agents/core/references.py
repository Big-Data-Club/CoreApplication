"""
ai-service/app/agents/core/references.py

Per-turn reference ledger shared by the ReAct loop and multi-agent pipeline.

Assigns stable 1-based citation indices ([1], [2], ...) to retrieved
sources so that:
  * tool results carry a ``ref`` field the LLM can cite verbatim,
  * DONE.references preserves display order,
  * duplicate retrievals collapse onto the same index.
"""
from __future__ import annotations


def _reference_key(ref: dict) -> str:
    """Identity of a source within one turn, used for de-duplication."""
    if ref.get("source_type") == "web":
        return f"web::{ref.get('url') or ref.get('title')}"
    return (
        f"mat::{ref.get('content_id')}::{ref.get('page_number')}"
        f"::{(ref.get('content') or '')[:120]}"
    )


class ReferenceLedger:
    """Accumulates turn references and hands out stable 1-based indices.

    The same index is embedded into the tool result JSON the model sees
    (as the ``ref`` field), so inline citations like ``[2]`` in the final
    answer map deterministically onto ``references[1]``.
    """

    def __init__(self) -> None:
        self.references: list[dict] = []
        self._keys: dict[str, int] = {}

    def add(self, ref: dict) -> int:
        key = _reference_key(ref)
        existing = self._keys.get(key)
        if existing is not None:
            return existing
        self.references.append(dict(ref))
        idx = len(self.references)
        self._keys[key] = idx
        return idx

    def __len__(self) -> int:
        return len(self.references)

    def __bool__(self) -> bool:
        return bool(self.references)


def validate_inline_citations(text: str, n_references: int) -> list[int]:
    """
    Return invalid citation numbers found in ``text``.

    A marker is valid when it is an integer in [1, n_references]. Used by
    the offline eval harness to detect fabricated or dangling citations.
    """
    import re

    if n_references <= 0:
        return []
    invalid: set[int] = set()
    for match in re.finditer(r"\[(\d{1,2})\]", text or ""):
        num = int(match.group(1))
        if not (1 <= num <= n_references):
            invalid.add(num)
    return sorted(invalid)
