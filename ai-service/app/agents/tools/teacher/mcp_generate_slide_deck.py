"""Deterministically format slides authored by the caller's external model."""
from __future__ import annotations

from app.agents.tools.base_tool import BaseTool, ToolResult


class McpGenerateSlideDeckTool(BaseTool):
    name = "mcp_generate_slide_deck"
    description = (
        "Validate and format a slide deck already authored by your external AI model. "
        "This tool does not call BDC's LLM gateway. Generate the slide content first, "
        "then pass it here to receive safe Reveal/Marp Markdown."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 200},
            "theme": {"type": "string", "enum": ["default", "dark", "academic", "minimal"], "default": "academic"},
            "slides": {
                "type": "array", "minItems": 1, "maxItems": 30,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "maxLength": 200},
                        "bullets": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 500}},
                        "speaker_notes": {"type": "string", "maxLength": 3000},
                        "code_snippet": {"type": "string", "maxLength": 5000},
                        "mermaid_diagram": {"type": "string", "maxLength": 5000},
                    },
                    "required": ["title", "bullets"],
                },
            },
        },
        "required": ["title", "slides"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        title = str(kwargs.get("title") or "").strip()[:200]
        slides = kwargs.get("slides") or []
        theme = str(kwargs.get("theme") or "academic")
        if not title or not isinstance(slides, list) or not 1 <= len(slides) <= 30:
            return ToolResult(status="error", data={"error": "invalid_slide_deck"}, message="Provide a title and 1–30 slides.")

        rendered: list[str] = [f"# {title}"]
        normalized: list[dict] = []
        for index, raw in enumerate(slides, 1):
            if not isinstance(raw, dict):
                return ToolResult(status="error", data={"error": "invalid_slide"}, message=f"Slide {index} must be an object.")
            slide_title = str(raw.get("title") or "").strip()[:200]
            bullets = [str(v).strip()[:500] for v in (raw.get("bullets") or []) if str(v).strip()][:10]
            if not slide_title:
                return ToolResult(status="error", data={"error": "missing_slide_title"}, message=f"Slide {index} needs a title.")
            notes = str(raw.get("speaker_notes") or "")[:3000]
            code = str(raw.get("code_snippet") or "")[:5000]
            mermaid = str(raw.get("mermaid_diagram") or "")[:5000]
            normalized.append({"slide_number": index, "title": slide_title, "bullets": bullets, "speaker_notes": notes, "code_snippet": code, "mermaid_diagram": mermaid})
            block = [f"## {slide_title}"]
            if mermaid:
                block.append(f"```mermaid\n{mermaid}\n```")
            block.extend(f"- {bullet}" for bullet in bullets)
            if code:
                block.append(f"```\n{code}\n```")
            if notes:
                block.append(f"<!-- speaker-notes: {notes.replace('-->', '—>')} -->")
            rendered.append("\n\n".join(block))

        return ToolResult(
            status="success",
            data={"title": title, "theme": theme, "slides": normalized, "reveal_markdown": "\n\n---\n\n".join(rendered)},
            message=f"Validated and formatted {len(normalized)} externally authored slides without using the BDC LLM gateway.",
        )
