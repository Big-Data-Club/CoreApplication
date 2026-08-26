"""
ai-service/app/services/studio/doc_renderer.py

Markdown lecture-document renderer. The output is the platform's native
content format - publishable directly as a TEXT lesson (metadata.content)
and downloadable as .md.
"""
from __future__ import annotations

from app.services.studio.plan_schema import StudioPlan


def render_plan_to_markdown(plan: StudioPlan) -> str:
    lines: list[str] = []
    lines.append(f"# {plan.safe_title}")
    lines.append("")
    if plan.learning_objectives:
        lines.append("## 🎯 Mục tiêu học tập")
        for obj in plan.learning_objectives:
            lines.append(f"- {obj}")
        lines.append("")
    if plan.summary:
        lines.append(f"> {plan.summary}")
        lines.append("")

    for idx, sec in enumerate(plan.sections, start=1):
        lines.append(f"## {idx}. {sec.title}")
        lines.append("")
        body_points = sec.key_points or sec.slide_bullets
        if body_points:
            for p in body_points:
                lines.append(f"- {p}")
            lines.append("")
        if sec.narration and sec.narration not in "\n".join(body_points or []):
            lines.append(sec.narration)
            lines.append("")

    return "\n".join(lines).strip() + "\n"
