"""Opt-in real browser/FFmpeg regression check; no neural provider calls."""
from __future__ import annotations

import asyncio
import os
import shutil

import pytest

from app.services.studio.browser_renderer import audio_duration, command, render_pdf, render_video
from app.services.studio.html_renderer import render_html
from app.services.studio.plan_schema import PlanSection, VisualSpec
from app.services.studio.storyboard import compile_storyboard
from app.services.studio.visuals import VISUAL_TYPES
from tests.test_studio_media import lesson

pytestmark = pytest.mark.skipif(os.environ.get("STUDIO_RENDER_SMOKE") != "1", reason="Set STUDIO_RENDER_SMOKE=1 with Chromium/FFmpeg installed")


def all_visuals():
    plan = lesson()
    for kind in sorted(VISUAL_TYPES - {"auto", "matrix_dot_product"}):
        nodes = [{"id": f"n{i}", "label": ["Input", "Compute", "Reduce", "Output"][i],
                  "role": ["input", "input", "intermediate", "output"][i]} for i in range(4)]
        if kind in {"reduction_tree", "broadcast_tree", "hierarchy", "algorithm_tree"}:
            edges = [{"source": a, "target": b, "label": "data"} for a,b in [("n0","n1"),("n0","n2"),("n1","n3")]]
        elif kind in {"comparison", "resource_timeline", "timeline", "matrix_tiling", "code_execution"}:
            edges = []
        else:
            edges = [{"source": f"n{i}", "target": f"n{i+1}", "label": "data"} for i in range(3)]
        spec = VisualSpec(nodes=nodes, edges=edges, code="for (int k = 0; k < n; ++k) {\n  c += a[k] * b[k];\n}" if kind == "code_execution" else "")
        plan.sections.append(PlanSection(title=kind, learning_goal="Explain " + kind,
            slide_bullets=["Dữ liệu đầu vào", "Phép tính", "Kết quả"], narration="Theo dõi dữ liệu qua từng bước.",
            visual_type=kind, visual_spec=spec, animation_steps=["input", "compute", "reduce", "output"], source_refs=["S1"]))
    return plan


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
def test_real_pdf_and_mp4_qa(aspect, tmp_path):
    assert shutil.which("ffmpeg") and shutil.which("ffprobe")
    async def run():
        board = compile_storyboard(all_visuals(), {"aspect_ratio": aspect})
        pdf, qa = await render_pdf(board, render_html(board), tmp_path)
        assert pdf.startswith(b"%PDF") and len(qa["samples"]) == len(board.scenes)*4
        plan = lesson(); plan.sections.append(plan.sections[0].model_copy(update={"title": "Work and span"}))
        video = compile_storyboard(plan, {"aspect_ratio": aspect}, video=True)
        (tmp_path / "narration").mkdir()
        for i, scene in enumerate(video.scenes):
            path = tmp_path / "narration" / f"{scene.id}.mp3"
            await command("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={1.19+i*.18}", "-c:a", "libmp3lame", path)
            scene.duration = await audio_duration(path)
        report = await render_video(video, tmp_path, "google")
        assert report["media"]["passed"] and (tmp_path / "video.mp4").stat().st_size > 1000
    asyncio.run(run())
