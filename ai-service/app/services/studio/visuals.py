"""Shared, deterministic visual language for Studio PPTX and MCP Markdown."""
from __future__ import annotations

import re

VISUAL_TYPES = {"auto", "flow", "cycle", "comparison", "hierarchy", "timeline"}


def clean_visual_labels(values: object, fallback: list[str] | None = None) -> list[str]:
    raw = values if isinstance(values, list) else []
    labels = [re.sub(r"\s+", " ", str(value)).strip()[:80] for value in raw]
    labels = [value for value in labels if value][:6]
    if not labels and fallback:
        labels = [re.sub(r"\s+", " ", str(value)).strip()[:80] for value in fallback if str(value).strip()][:4]
    return labels


def resolve_visual_type(visual_type: str, labels: list[str]) -> str:
    if visual_type in VISUAL_TYPES - {"auto"}:
        return visual_type
    if len(labels) == 2:
        return "comparison"
    if len(labels) >= 5:
        return "timeline"
    return "flow"


def mermaid_for_visual(visual_type: str, labels: list[str]) -> str:
    """Return bounded Mermaid syntax generated only from sanitized labels."""
    safe = [
        re.sub(r"\s+", " ", re.sub(r'["\[\]{}()<>`]', "", str(label))).strip()[:80]
        for label in labels
    ]
    safe = [label for label in safe if label][:6]
    if not safe:
        return ""
    kind = resolve_visual_type(visual_type, safe)
    nodes = [f'N{i}["{label}"]' for i, label in enumerate(safe)]
    if kind == "comparison":
        return "flowchart LR\n  " + "\n  ".join(nodes)
    if kind == "hierarchy":
        edges = [nodes[0]] + [f"N0 --> {node}" for node in nodes[1:]]
        return "flowchart TD\n  " + "\n  ".join(edges)
    if kind == "cycle" and len(nodes) > 1:
        edges = [nodes[0]] + [f"N{i} --> N{i + 1}" for i in range(len(nodes) - 1)] + [f"N{len(nodes) - 1} --> N0"]
        return "flowchart LR\n  " + "\n  ".join(edges)
    if kind == "timeline":
        return "timeline\n" + "\n".join(f"  {i + 1} : {label}" for i, label in enumerate(safe))
    edges = [nodes[0]] + [f"N{i} --> N{i + 1}" for i in range(len(nodes) - 1)]
    return "flowchart LR\n  " + "\n  ".join(edges)
