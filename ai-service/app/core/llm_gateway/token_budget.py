"""Conservative preflight token budgeting for the LLM gateway.

The gateway cannot safely truncate arbitrary prompts: doing so may silently
drop course material.  Instead it estimates the *requested* token cost before
the provider sees a call.  Workflows with large source material can then use
the helpers in this module to create lossless batches and reduce them
hierarchically.
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable


# Vietnamese and structured JSON tend to tokenize more densely than English.
# This deliberately conservative ratio keeps us below a provider TPM cap even
# when an exact tokenizer is not installed in the API process.
_CHARS_PER_TOKEN = 2.4
_MESSAGE_OVERHEAD = 12


def estimate_tokens(value: Any) -> int:
    """Return a safe, provider-agnostic estimate for text/JSON payloads."""
    if value is None:
        return 0
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return max(1, math.ceil(len(text) / _CHARS_PER_TOKEN))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_tokens(message.get("content")) + _MESSAGE_OVERHEAD for message in messages)


def split_text_preserving_content(text: str, max_tokens: int) -> list[str]:
    """Split at paragraph/word boundaries without discarding a character."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if estimate_tokens(text) <= max_tokens:
        return [text]

    max_chars = max(1, int(max_tokens * _CHARS_PER_TOKEN))
    paragraphs = text.splitlines(keepends=True)
    pieces: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            pieces.append(current)
            current = ""

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            if current and len(current) + len(paragraph) > max_chars:
                flush()
            current += paragraph
            continue
        flush()
        # An unbroken paragraph is split on whitespace where possible, then
        # only as a last resort on a character boundary. Nothing is removed.
        remaining = paragraph
        while len(remaining) > max_chars:
            cut = remaining.rfind(" ", 0, max_chars + 1)
            if cut <= 0:
                cut = max_chars
            pieces.append(remaining[:cut])
            remaining = remaining[cut:]
        current = remaining
    flush()
    return pieces


def pack_by_token_budget(items: Iterable[Any], max_tokens: int) -> list[list[Any]]:
    """Pack ordered items into bounded batches; oversized strings are split."""
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    batches: list[list[Any]] = []
    current: list[Any] = []
    current_tokens = 0
    for item in items:
        expanded: list[Any]
        if isinstance(item, str) and estimate_tokens(item) > max_tokens:
            expanded = split_text_preserving_content(item, max_tokens)
        else:
            expanded = [item]
        for part in expanded:
            cost = estimate_tokens(part)
            if current and current_tokens + cost > max_tokens:
                batches.append(current)
                current, current_tokens = [], 0
            current.append(part)
            current_tokens += cost
    if current:
        batches.append(current)
    return batches
