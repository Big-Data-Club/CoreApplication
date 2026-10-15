"""Pack explicitly designated evidence while preserving the task and citations."""
from __future__ import annotations

import json
import logging
import re

from app.core.llm_gateway.errors import ContextLengthError
from app.core.llm_gateway.token_budget import estimate_request_tokens, estimate_tokens

logger = logging.getLogger(__name__)
NOTICE = "[Evidence excerpts; omitted passages were not reviewed. Do not infer missing facts.]"


def _excerpt(text: str, tokens: int, query: str = "") -> str:
    if estimate_tokens(text) <= tokens:
        return text
    words = set(re.findall(r"\w{3,}", query.casefold()))
    # Include relevant passages even when the answer occurs late in a parent.
    passages = re.split(r"(?<=[.!?])\s+|\n+", text)
    ranked = sorted(range(len(passages)), key=lambda i: (
        -len(words & set(re.findall(r"\w{3,}", passages[i].casefold()))), i,
    ))
    selected = []
    for i in ranked:
        candidate = "\n[…]\n".join(passages[j] for j in sorted(selected + [i]))
        if estimate_tokens(candidate) <= tokens:
            selected.append(i)
    if selected:
        return "\n[…]\n".join(passages[i] for i in sorted(selected))
    # A single huge paragraph: keep a bounded window around a matching term.
    passage = passages[ranked[0]] if ranked else text
    match = next((m for m in re.finditer(r"\w{3,}", passage) if m.group().casefold() in words), None)
    start = max(0, match.start() - 100) if match else 0
    passage = passage[start:]
    low, high = 0, len(passage)
    while low < high:
        mid = (low + high + 1) // 2
        if estimate_tokens(passage[:mid]) <= tokens:
            low = mid
        else:
            high = mid - 1
    return passage[:low]


def compact_evidence(text: str, max_tokens: int, query: str = "") -> str:
    """Keep every source label, allocating bounded excerpts across sources."""
    if estimate_tokens(text) <= max_tokens:
        return text
    blocks = re.split(r"(?m)(?=^\[(?:SOURCE S\d+:|EVIDENCE S\d+:|(?:Segment|Source) \d+\]))", text)
    sources = []
    for block in blocks:
        if not block.strip():
            continue
        match = re.match(r"(\[(?:SOURCE S\d+:|EVIDENCE S\d+:|(?:Segment|Source) \d+\])[^\n]*)(?:\n| )?", block)
        # Segment headers end at ], not the end of their first paragraph.
        segment = re.match(r"(\[(?:Segment|Source) \d+\])\s*", block)
        match = segment or match
        sources.append((match.group(1) if match else "", block[match.end():] if match else block))
    headers = NOTICE + "\n" + "\n\n".join(header for header, _ in sources)
    allowance = (max_tokens - estimate_tokens(headers) - 32) // max(1, len(sources))
    if allowance < 32:
        raise ContextLengthError("Too many source labels for this model/key; split the authoring scope into batches")
    while allowance >= 16:
        result = NOTICE + "\n" + "\n\n".join(
            header + "\n" + _excerpt(body, allowance, query) for header, body in sources
        )
        if estimate_tokens(result) <= max_tokens:
            return result
        allowance -= max(1, (estimate_tokens(result) - max_tokens) // len(sources) + 1)
    raise ContextLengthError("Source evidence cannot fit without losing useful grounding")


def make_evidence_packer(reference_text: str, *, query: str = ""):
    """Adapt only the supplied evidence span, including inside JSON prompts.

    Current question/answers, system instructions, schemas and repair messages
    are immutable. Repacking always starts from the original evidence.
    """
    def pack(messages, extra, max_input_tokens):
        if estimate_request_tokens(messages, extra) <= max_input_tokens:
            return messages
        packed = [dict(message) for message in messages]
        for message in packed:
            content = message.get("content")
            if not isinstance(content, str) or not reference_text:
                continue
            encoded = False
            needle = reference_text
            if needle not in content:
                needle = json.dumps(reference_text, ensure_ascii=False)[1:-1]
                encoded = True
            if needle not in content:
                continue
            # Only one explicitly supplied span is eligible for compaction.
            def render(evidence):
                value = json.dumps(evidence, ensure_ascii=False)[1:-1] if encoded else evidence
                message["content"] = content.replace(needle, value, 1)
                return estimate_request_tokens(packed, extra)
            fixed = render("")
            allowance = max_input_tokens - fixed - 64
            for _ in range(8):
                reduced = compact_evidence(reference_text, allowance, query)
                actual = render(reduced)
                if actual <= max_input_tokens:
                    logger.info("Evidence packed: estimated_input=%d budget=%d", actual, max_input_tokens)
                    return packed
                allowance -= actual - max_input_tokens + 32
            break
        raise ContextLengthError("Mandatory instructions/question/schema exceed the selected model/key budget")
    return pack
