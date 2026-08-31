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
                        "visual_type": {"type": "string", "enum": ["auto", "flow", "cycle", "comparison", "hierarchy", "timeline"], "default": "auto"},
                        "visual_labels": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string", "maxLength": 80}},
                        "illustration_prompt": {"type": "string", "maxLength": 1000, "description": "Optional prompt the external client may use with its own image generator."},
                        "alt_text": {"type": "string", "maxLength": 500},
                        "source_refs": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 200}},
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
        from app.services.studio.visuals import clean_visual_labels, mermaid_for_visual
        for index, raw in enumerate(slides, 1):
            if not isinstance(raw, dict):
                return ToolResult(status="error", data={"error": "invalid_slide"}, message=f"Slide {index} must be an object.")
            slide_title = str(raw.get("title") or "").strip()[:200]
            bullets = [str(v).strip()[:500] for v in (raw.get("bullets") or []) if str(v).strip()][:10]
            if not slide_title:
                return ToolResult(status="error", data={"error": "missing_slide_title"}, message=f"Slide {index} needs a title.")
            notes = str(raw.get("speaker_notes") or "")[:3000]
            code = str(raw.get("code_snippet") or "")[:5000]
            visual_type = str(raw.get("visual_type") or "auto")
            labels = clean_visual_labels(raw.get("visual_labels"), fallback=bullets or [slide_title])
            from app.services.studio.visuals import resolve_visual_type
            visual_type = resolve_visual_type(visual_type, labels)
            mermaid = mermaid_for_visual(visual_type, labels)
            illustration_prompt = str(raw.get("illustration_prompt") or "")[:1000]
            alt_text = str(raw.get("alt_text") or "").strip()[:500]
            source_refs = [str(value).strip()[:200] for value in (raw.get("source_refs") or []) if str(value).strip()][:12]
            normalized.append({"slide_number": index, "title": slide_title, "bullets": bullets, "speaker_notes": notes, "code_snippet": code, "visual_type": visual_type, "visual_labels": labels, "mermaid_diagram": mermaid, "illustration_prompt": illustration_prompt, "alt_text": alt_text, "source_refs": source_refs})
            block = [f"## {slide_title}"]
            if mermaid:
                block.append(f"```mermaid\n{mermaid}\n```")
            block.extend(f"- {bullet}" for bullet in bullets)
            if code:
                block.append(f"```\n{code}\n```")
            if notes:
                block.append(f"<!-- speaker-notes: {notes.replace('-->', '->')} -->")
            if illustration_prompt:
                block.append(f"<!-- optional-external-image-prompt: {illustration_prompt.replace('-->', '->')} -->")
            if alt_text:
                block.append(f"*Visual description: {alt_text}*")
            if source_refs:
                block.append("Sources: " + "; ".join(source_refs))
            rendered.append("\n\n".join(block))

        return ToolResult(
            status="success",
            data={"title": title, "theme": theme, "slides": normalized, "visual_coverage": f"{len(normalized)}/{len(normalized)}", "reveal_markdown": "\n\n---\n\n".join(rendered)},
            message=f"Validated and formatted {len(normalized)} externally authored slides with a safe Mermaid visual on every slide, without using the BDC LLM gateway.",
        )
