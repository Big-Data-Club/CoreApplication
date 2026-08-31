"""Validate and format a report authored by an external MCP client model."""
from __future__ import annotations

import re
from typing import Any

from app.agents.tools.base_tool import BaseTool, ToolResult
from app.services.studio.visuals import clean_visual_labels, mermaid_for_visual, resolve_visual_type


def _safe_markdown(value: Any, limit: int) -> str:
    text = str(value or "").strip()[:limit]
    # Reports are returned as source Markdown, but active/raw HTML is not part
    # of the authoring contract and should not survive into downstream renderers.
    text = re.sub(r"<\/?(?:script|iframe|object|embed|style|link|meta)\b[^>]*>", "", text, flags=re.I)
    return text.replace("javascript:", "")


class McpGenerateReportTool(BaseTool):
    name = "mcp_generate_report"
    description = (
        "Validate and format a structured academic/technical report already authored by the external client model. "
        "Produces safe Markdown, source references, Mermaid diagrams, accessibility text, and optional image prompts. "
        "It does not call BDC's LLM or image gateway."
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 240},
            "executive_summary": {"type": "string", "maxLength": 5000},
            "audience": {"type": "string", "maxLength": 300},
            "sections": {
                "type": "array", "minItems": 1, "maxItems": 30,
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string", "maxLength": 240},
                        "body_markdown": {"type": "string", "maxLength": 15000},
                        "key_findings": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 600}},
                        "visual_type": {"type": "string", "enum": ["auto", "flow", "cycle", "comparison", "hierarchy", "timeline"]},
                        "visual_labels": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 80}},
                        "alt_text": {"type": "string", "maxLength": 500},
                        "illustration_prompt": {"type": "string", "maxLength": 1000},
                        "source_refs": {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 300}},
                    },
                    "required": ["heading", "body_markdown"],
                },
            },
            "conclusion": {"type": "string", "maxLength": 5000},
        },
        "required": ["title", "sections"],
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        title = _safe_markdown(kwargs.get("title"), 240).lstrip("# ")
        sections = kwargs.get("sections")
        if not title or not isinstance(sections, list) or not 1 <= len(sections) <= 30:
            return ToolResult(status="error", data={"error": "invalid_report"}, message="Provide a title and 1–30 report sections.")

        summary = _safe_markdown(kwargs.get("executive_summary"), 5000)
        audience = _safe_markdown(kwargs.get("audience"), 300)
        lines = [f"# {title}", ""]
        if audience:
            lines.extend([f"**Đối tượng:** {audience}", ""])
        if summary:
            lines.extend(["## Tóm tắt điều hành", "", summary, ""])
        lines.extend(["## Mục lục", ""])
        normalised: list[dict[str, Any]] = []
        for index, raw in enumerate(sections, 1):
            if not isinstance(raw, dict):
                return ToolResult(status="error", data={"error": "invalid_section"}, message=f"Report section {index} must be an object.")
            heading = _safe_markdown(raw.get("heading"), 240).lstrip("# ")
            body = _safe_markdown(raw.get("body_markdown"), 15000)
            if not heading or not body:
                return ToolResult(status="error", data={"error": "incomplete_section"}, message=f"Report section {index} needs a heading and body.")
            lines.append(f"- [{index}. {heading}](#{index}-{re.sub(r'[^a-z0-9-]+', '-', heading.lower()).strip('-')})")
            findings = [_safe_markdown(item, 600) for item in (raw.get("key_findings") or [])]
            findings = [item for item in findings if item][:10]
            labels = clean_visual_labels(raw.get("visual_labels"), fallback=findings or [heading])
            visual_type = resolve_visual_type(str(raw.get("visual_type") or "auto"), labels)
            diagram = mermaid_for_visual(visual_type, labels)
            refs = [_safe_markdown(item, 300) for item in (raw.get("source_refs") or [])]
            refs = [item for item in refs if item][:20]
            normalised.append({
                "section_number": index, "heading": heading, "visual_type": visual_type,
                "visual_labels": labels, "mermaid_diagram": diagram,
                "alt_text": _safe_markdown(raw.get("alt_text"), 500),
                "illustration_prompt": _safe_markdown(raw.get("illustration_prompt"), 1000),
                "source_refs": refs,
            })

        for item, raw in zip(normalised, sections):
            lines.extend(["", f"## {item['section_number']}. {item['heading']}", "", _safe_markdown(raw.get("body_markdown"), 15000), ""])
            findings = [_safe_markdown(value, 600) for value in (raw.get("key_findings") or []) if _safe_markdown(value, 600)][:10]
            if findings:
                lines.extend(["### Phát hiện chính", "", *(f"- {value}" for value in findings), ""])
            if item["mermaid_diagram"]:
                lines.extend(["```mermaid", item["mermaid_diagram"], "```", ""])
            if item["alt_text"]:
                lines.extend([f"*Mô tả hình: {item['alt_text']}*", ""])
            if item["illustration_prompt"]:
                lines.extend([f"> Gợi ý ảnh (chưa tạo): {item['illustration_prompt']}", ""])
            if item["source_refs"]:
                lines.extend(["**Nguồn:** " + "; ".join(item["source_refs"]), ""])

        conclusion = _safe_markdown(kwargs.get("conclusion"), 5000)
        if conclusion:
            lines.extend(["## Kết luận", "", conclusion, ""])

        return ToolResult(
            status="success",
            data={
                "title": title, "sections": normalised,
                "visual_coverage": f"{sum(bool(item['mermaid_diagram']) for item in normalised)}/{len(normalised)}",
                "report_markdown": "\n".join(lines).strip() + "\n",
            },
            message=f"Validated and formatted a {len(normalised)}-section report with grounded references and non-blocking visual suggestions.",
        )
