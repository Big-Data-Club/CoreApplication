"""Separate provider-exposed reasoning from learner-facing answer text."""
from __future__ import annotations

from typing import Any


def split_content(content: Any) -> tuple[str, str]:
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return "", ""
    text, thinking = [], []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in ("text", "output_text") and isinstance(block.get("text"), str):
            text.append(block["text"])
        elif block.get("type") == "thinking":
            value = block.get("thinking")
            if isinstance(value, str):
                thinking.append(value)
            elif isinstance(value, list):
                thinking.append(split_content(value)[0])
    return "".join(text), "".join(thinking)


def provider_thinking(raw: Any) -> str:
    """Supports dict responses and SDK objects without serializing other fields."""
    def field(obj, name):
        return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)

    choices = field(raw, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        return ""
    message = field(choices[0], "delta") or field(choices[0], "message")
    if message is None:
        return ""
    for name in ("reasoning_content", "reasoning"):
        value = field(message, name)
        if isinstance(value, str) and value:
            return value
    return split_content(field(message, "content"))[1]
