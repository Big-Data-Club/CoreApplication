"""Readable code pages. Wrap the display only; never rewrite the source code."""
from __future__ import annotations

from dataclasses import dataclass
import unicodedata

ROWS_PER_PAGE = 12


@dataclass(frozen=True)
class CodeRow:
    text: str
    source_line: int
    continuation: bool = False


def code_pages(code: str, portrait: bool) -> list[list[CodeRow]]:
    # Leave room for line numbers at the existing, readable 26px monospace size.
    columns = 42 if portrait else 68
    groups = []
    for number, line in enumerate(code.splitlines(), start=1):
        remaining = line.expandtabs(4)
        group = []
        continuation = False
        while remaining:
            width, cut = 0, len(remaining)
            for index, char in enumerate(remaining):
                size = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1)
                if width + size > columns:
                    cut = index
                    # Prefer an argument/whitespace boundary to splitting an
                    # identifier or string. Preserve every character either way.
                    boundaries = [i+1 for i, value in enumerate(remaining[:cut]) if value.isspace() or value in ",;("]
                    if boundaries and boundaries[-1] >= cut // 2:
                        cut = boundaries[-1]
                    break
                width += size
            group.append(CodeRow(remaining[:cut], number, continuation))
            remaining, continuation = remaining[cut:], True
        groups.append(group or [CodeRow("", number)])
    pages = [[]]
    for group in groups:
        # A wrapped call stays together when it fits on one page. Only an
        # individual source line longer than a whole page must span pages.
        if pages[-1] and len(pages[-1]) + len(group) > ROWS_PER_PAGE:
            pages.append([])
        for row in group:
            if len(pages[-1]) == ROWS_PER_PAGE:
                pages.append([])
            pages[-1].append(row)
    return pages
