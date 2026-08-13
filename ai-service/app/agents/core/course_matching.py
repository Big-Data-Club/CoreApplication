"""Pure, deterministic matching of user references to verified courses."""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Optional


def _normalise_course_reference(value: Any) -> str:
    """Fold Unicode variants and punctuation while preserving word content."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(
        "".join(char if char.isalnum() else " " for char in text).split()
    )


def _explicit_course_id(message: str, valid_ids: set[int]) -> Optional[int]:
    """Return an ID only when the user expresses it as a course reference."""
    normalised = _normalise_course_reference(message)
    if normalised.isdecimal():
        candidate = int(normalised)
        return candidate if candidate in valid_ids else None

    patterns = (
        r"(?:course|course id|kh[oó]a h[oọ]c|kho[aá] h[oọ]c)\s*(?:id\s*)?(\d+)",
        r"#\s*(\d+)",
    )
    source = unicodedata.normalize("NFKC", message)
    for pattern in patterns:
        match = re.search(pattern, source, re.IGNORECASE)
        if match:
            candidate = int(match.group(1))
            if candidate in valid_ids:
                return candidate
    return None


def _title_tokens(title: str, min_len: int) -> set[str]:
    """Keep normal words plus short all-uppercase acronyms such as AI."""
    normalised = _normalise_course_reference(title)
    tokens = {token for token in normalised.split() if len(token) >= min_len}
    raw_words = "".join(
        char if char.isalnum() else " "
        for char in unicodedata.normalize("NFKC", title)
    ).split()
    tokens.update(word.casefold() for word in raw_words if len(word) >= 2 and word.isupper())
    return tokens


def find_course_by_title(
    anchor: dict,
    message: str,
    *,
    min_len: int = 3,
) -> Optional[dict]:
    """Resolve a course by verified ID or a catalogue-scored title match.

    Full-title matching is Unicode/punctuation insensitive. Partial titles are
    scored using inverse document frequency learned from the current catalogue,
    so distinctive terms matter more without any course-specific vocabulary.
    Ambiguous references deliberately return ``None``.
    """
    if not message:
        return None
    courses = [
        course for course in (anchor.get("courses") or [])
        if course.get("id") is not None and (course.get("title") or "").strip()
    ]
    if not courses:
        return None

    valid_ids = {int(course["id"]) for course in courses}
    referenced_id = _explicit_course_id(message, valid_ids)
    if referenced_id is not None:
        return next(course for course in courses if int(course["id"]) == referenced_id)
    if len(message.strip()) < min_len:
        return None

    msg_normalised = _normalise_course_reference(message)
    msg_tokens = set(msg_normalised.split())
    strong: list[dict] = []
    title_tokens: list[tuple[dict, set[str]]] = []
    for course in courses:
        title_normalised = _normalise_course_reference(course["title"])
        if title_normalised and title_normalised in msg_normalised:
            strong.append(course)
        tokens = _title_tokens(str(course["title"]), min_len)
        title_tokens.append((course, tokens))

    if len(strong) == 1:
        return strong[0]
    if strong:
        return None

    vocabulary = set().union(*(tokens for _, tokens in title_tokens))
    document_frequency = {
        token: sum(token in tokens for _, tokens in title_tokens)
        for token in vocabulary
    }
    course_count = len(title_tokens)
    ranked: list[tuple[float, int, int, dict]] = []
    for course, tokens in title_tokens:
        overlap = tokens & msg_tokens
        if not overlap:
            continue
        weights = {
            token: 1.0 + math.log((course_count + 1) / document_frequency[token])
            for token in tokens
        }
        matched_weight = sum(weights[token] for token in overlap)
        coverage = matched_weight / sum(weights.values())
        unique_hits = sum(document_frequency[token] == 1 for token in overlap)
        precision = len(overlap) / max(1, len(msg_tokens))
        discriminative_evidence = unique_hits / len(overlap)
        score = coverage + 0.15 * precision + 0.15 * discriminative_evidence
        ranked.append((score, len(overlap), unique_hits, course))

    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    best = ranked[0]
    runner_up_score = ranked[1][0] if len(ranked) > 1 else 0.0
    enough_evidence = (
        (best[1] >= 2 and best[0] >= 0.30)
        or (best[2] >= 1 and best[0] >= 0.25)
    )
    runner_up_unique_hits = ranked[1][2] if len(ranked) > 1 else 0
    clearly_ahead = (
        best[0] - runner_up_score >= 0.12
        or (best[1] >= 2 and best[2] > runner_up_unique_hits)
    )
    return best[3] if enough_evidence and clearly_ahead else None
