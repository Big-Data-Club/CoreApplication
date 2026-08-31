"""
ai-service/app/services/studio/plan_schema.py

Strict, model-independent contract for Content Studio plans.

Whatever LLM the gateway binds for TASK_CONTENT_STUDIO, its output is:
  1. parsed via chat_complete_json,
  2. coerced with ensure_dict,
  3. validated against these models - missing fields get deterministic
     defaults, malformed sections are repaired or dropped,
so a small model produces the same *structure* as a large one.
"""
from __future__ import annotations

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError


def _ensure_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, dict)), {})
    return {}


def _extract_plan_json(raw: str) -> object:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(?:\{[\s\S]*\}|\[[\s\S]*\])", text)
        if not match:
            raise ValueError("model response did not contain JSON")
        return json.loads(match.group())


class PlanSection(BaseModel):
    title: str = ""
    key_points: list[str] = Field(default_factory=list)
    slide_bullets: list[str] = Field(default_factory=list)
    narration: str = ""           # spoken script (video P1; also enriches docs)
    visual_suggestion: str = ""
    visual_type: Literal["auto", "flow", "cycle", "comparison", "hierarchy", "timeline"] = "auto"
    visual_labels: list[str] = Field(default_factory=list)
    illustration_prompt: str = ""
    alt_text: str = ""
    source_refs: list[str] = Field(default_factory=list)
    duration_est_sec: int = 0

    def cleaned(self) -> "PlanSection":
        strip = lambda s: re.sub(r"\s+", " ", s or "").strip()  # noqa: E731
        self.title = strip(self.title)[:200] or f"Mục {self.title or 'không tên'}"
        self.key_points = [strip(k)[:300] for k in (self.key_points or []) if strip(k)][:8]
        self.slide_bullets = [strip(b)[:200] for b in (self.slide_bullets or []) if strip(b)][:8]
        self.narration = (self.narration or "").strip()[:6000]
        self.visual_suggestion = strip(self.visual_suggestion)[:300]
        self.illustration_prompt = strip(self.illustration_prompt)[:1000]
        self.alt_text = strip(self.alt_text)[:500]
        self.source_refs = [
            ref for ref in (strip(str(value)).upper() for value in self.source_refs)
            if re.fullmatch(r"S\d{1,3}", ref)
        ][:8]
        from app.services.studio.visuals import clean_visual_labels
        self.visual_labels = clean_visual_labels(
            self.visual_labels,
            fallback=self.slide_bullets or self.key_points or [self.title],
        )
        return self


class StudioPlan(BaseModel):
    title: str = ""
    language: Literal["vi", "en"] = "vi"
    learning_objectives: list[str] = Field(default_factory=list)
    sections: list[PlanSection] = Field(default_factory=list)
    summary: str = ""

    @property
    def safe_title(self) -> str:
        t = re.sub(r"\s+", " ", self.title or "").strip()[:180]
        return t or "Bài giảng chưa đặt tên"


def coerce_plan(raw: object, *, kind: str, fallback_title: str,
                target_sections: int) -> tuple[Optional[StudioPlan], list[str]]:
    """
    Returns (plan|None, warnings).

    Deterministic repair rules:
      * dict wrapper vs bare array both accepted
      * strings where arrays expected -> split on newlines/bullets
      * sections beyond target kept (teacher trims later), empty ones dropped
      * unknown extra fields ignored by the model
    """
    warnings: list[str] = []
    if isinstance(raw, str):
        try:
            raw = _extract_plan_json(raw)
        except Exception as exc:
            return None, [f"Failed to parse LLM JSON: {exc}"]

    data = _ensure_dict(raw)

    # Some models wrap: {"plan": {...}} / {"sections": [...]} at top level only
    if not data.get("sections"):
        inner = _ensure_dict(data.get("plan"))
        if inner.get("sections"):
            data = {**data, **inner}

    raw_sections = data.get("sections")
    if isinstance(raw_sections, str):
        raw_sections = [
            {"title": line.lstrip("#-• ").strip()}
            for line in raw_sections.splitlines() if line.strip()
        ]
        warnings.append("sections was a string - split by lines")
    if not isinstance(raw_sections, list):
        return None, ["no sections produced"]

    fixed_sections: list[dict] = []
    for i, sec in enumerate(raw_sections):
        if not isinstance(sec, dict):
            # e.g. plain string item
            sec = {"title": str(sec)}
        for field in ("key_points", "slide_bullets"):
            v = sec.get(field)
            if isinstance(v, str):
                sec[field] = [
                    ln.lstrip("-•* ").strip()
                    for ln in v.splitlines() if ln.strip()
                ]
            elif isinstance(v, list):
                sec[field] = [str(x) for x in v]
            else:
                sec[field] = []
        if not isinstance(sec.get("visual_labels"), list):
            sec["visual_labels"] = []
        if not isinstance(sec.get("source_refs"), list):
            sec["source_refs"] = []
        from app.services.studio.visuals import VISUAL_TYPES
        if sec.get("visual_type") not in VISUAL_TYPES:
            sec["visual_type"] = "auto"
        if not str(sec.get("title") or "").strip():
            sec["title"] = f"Mục {i + 1}"
        fixed_sections.append(sec)

    try:
        plan = StudioPlan(
            title=str(data.get("title") or fallback_title),
            language=data.get("language") if data.get("language") in ("vi", "en") else "vi",
            learning_objectives=[str(x) for x in ensure_list(data.get("learning_objectives"))][:6],
            sections=[PlanSection(**s).cleaned() for s in fixed_sections],
            summary=str(data.get("summary") or "")[:1500],
        )
    except ValidationError as exc:
        return None, [f"validation failed: {exc}"]

    plan.sections = [s for s in plan.sections if s.title or s.key_points or s.slide_bullets]
    if not plan.sections:
        return None, ["all sections empty"]

    if len(plan.sections) < max(1, target_sections // 2):
        warnings.append(
            f"model returned {len(plan.sections)} sections (target {target_sections})"
        )
    return plan, warnings


def ensure_list(v: object) -> list:
    return v if isinstance(v, list) else ([] if v is None else [str(v)])
