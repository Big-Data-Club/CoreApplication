"""Versioned semantic storyboard contract shared by HTML, QA and MP4 rendering."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.services.studio.plan_schema import StudioPlan, VisualSpec
from app.services.studio.visuals import VisualType


class VideoConfig(BaseModel):
    title: str
    language: Literal["vi", "en"] = "vi"
    aspectRatio: Literal["16:9", "9:16"] = "16:9"
    width: int = 1920
    height: int = 1080
    fps: Literal[30] = 30


class Scene(BaseModel):
    id: str
    topic: str
    learning_goal: str
    narration: str
    duration: float | None = None
    visual_type: VisualType
    key_message: str
    points: list[str]
    labels: list[str]
    animation_steps: list[str]
    visual_spec: VisualSpec
    source_refs: list[str]
    grounding: Literal["source", "extension"] = "source"


class Storyboard(BaseModel):
    schema_version: Literal[1] = 1
    video: VideoConfig
    narrative: dict
    scenes: list[Scene] = Field(min_length=1, max_length=30)


def compile_storyboard(plan: StudioPlan, settings: dict, *, video: bool = False) -> Storyboard:
    aspect = settings.get("aspect_ratio", "16:9")
    if aspect not in {"16:9", "9:16"}:
        raise ValueError("aspect_ratio must be 16:9 or 9:16")
    width, height = (1080, 1920) if aspect == "9:16" else (1920, 1080)
    if aspect == "16:9" and settings.get("resolution") == "720p":
        width, height = 1280, 720
    if video and (not plan.narrative.learner_goal or not plan.narrative.concept_dependencies):
        raise ValueError("Video requires a teaching narrative before visual compilation")
    scenes = []
    for index, section in enumerate(plan.sections):
        if video and (not section.narration.strip() or not section.learning_goal or not section.animation_steps):
            raise ValueError(f"Scene {index + 1} needs narration, learning goal and animation steps")
        # Never silently clip or shrink teacher-authored visual content.
        points = section.slide_bullets or section.key_points
        if len(points) > 3 or any(len(p) > 120 for p in points) or len(section.title) > 110:
            raise ValueError(f"Scene {index + 1}: shorten title/points; maximum 3 short points")
        if len(section.narration) > 2400:
            raise ValueError(f"Scene {index + 1}: split narration into shorter scenes (2400 characters maximum)")
        spec = section.visual_spec
        ids = {node.id for node in spec.nodes}
        if len(ids) != len(spec.nodes) or any(e.source not in ids or e.target not in ids for e in spec.edges):
            raise ValueError(f"Scene {index + 1}: invalid diagram node references")
        for matrix in (spec.matrix_a, spec.matrix_b):
            if matrix and (any(not row or len(row) > 4 for row in matrix) or len({len(row) for row in matrix}) != 1
                           or any(len(str(value)) > 8 for row in matrix for value in row)):
                raise ValueError("Matrices must be rectangular, at most 4×4, with short cells")
        if video and section.visual_type == "code_execution" and not spec.code.strip():
            raise ValueError("code_execution requires a grounded code snippet")
        if video and re.search(r"(?:ở slide này|tiếp theo là slide|video số|AI đã tạo)", section.narration, re.I):
            raise ValueError("Narration must explain the concept directly")
        scenes.append(Scene(
            id=f"scene_{index + 1:02d}", topic=section.title,
            learning_goal=section.learning_goal, narration=section.narration,
            visual_type=section.visual_type, visual_spec=spec,
            key_message=section.key_message or section.title, points=points,
            labels=section.visual_labels, animation_steps=section.animation_steps or ["reveal"],
            source_refs=section.source_refs, grounding=section.grounding,
        ))
    return Storyboard(video=VideoConfig(title=plan.safe_title, language=plan.language, aspectRatio=aspect, width=width, height=height),
                      narrative=plan.narrative.model_dump(), scenes=scenes)
