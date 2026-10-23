"""Opt-in real browser/FFmpeg regression check; no neural provider calls."""
from __future__ import annotations

import asyncio
import os
import re
import shutil

import pytest

from app.services.studio.browser_renderer import audio_duration, command, render_pdf, render_video
from app.services.studio.html_renderer import render_html
from app.services.studio.plan_schema import PlanSection, VisualSpec
from app.services.studio.storyboard import compile_storyboard
from app.services.studio.visuals import VISUAL_TYPES
from tests.test_studio_media import lesson, work_span_lesson
from tests.test_studio_code_layout import code_lesson
from tests.test_studio_timeline_layout import timeline_lesson

pytestmark = pytest.mark.skipif(os.environ.get("STUDIO_RENDER_SMOKE") != "1", reason="Set STUDIO_RENDER_SMOKE=1 with Chromium/FFmpeg installed")


@pytest.mark.parametrize("aspect,resolution", [("16:9", "1080p"), ("16:9", "720p"), ("9:16", "1080p")])
def test_real_dense_timeline_layout(aspect,resolution,tmp_path):
    async def run():
        plan = timeline_lesson(5)
        for count in (6,7,8,9):
            plan.sections.extend(timeline_lesson(count).sections)
        plan.sections.extend(timeline_lesson(9,edges="dense").sections)
        plan.sections.extend(timeline_lesson(9,equation=False,edges="dense").sections)
        board = compile_storyboard(plan,{"aspect_ratio":aspect,"resolution":resolution},video=True)
        pdf,qa = await render_pdf(board,render_html(board),tmp_path)
        assert pdf.startswith(b"%PDF") and qa["passed"]
        assert len(qa["samples"]) == 4*len(board.scenes)
        from app.services.studio.browser_renderer import browser_page,screenshot_qa
        async with browser_page(board,render_html(board,video=True)) as page:
            assert (await screenshot_qa(page,board,tmp_path/"video-qa"))["passed"]
            await page.evaluate("window.seekScene(4,1)")
            assert await page.locator('[data-scene="4"] [data-node-boundary]').count() == 9
            assert await page.locator('[data-scene="4"] [data-progress-bar]').evaluate_all(
                "bars=>bars.every(bar=>Number(bar.getAttribute('width'))===Math.round(Number(bar.dataset.maxWidth)))")
    asyncio.run(run())


@pytest.mark.parametrize("aspect,resolution", [("16:9", "1080p"), ("16:9", "720p"), ("9:16", "1080p")])
def test_real_dense_code_pdf_and_video_layout(aspect, resolution, tmp_path):
    from app.services.studio.browser_renderer import browser_page, screenshot_qa
    from app.services.studio.code_layout import code_pages
    async def run():
        plan = code_lesson()
        for code in ['pthread_create(' + 'argument, '*30 + 'NULL);', 'x();\n'*61]:
            plan.sections.extend(code_lesson(code).sections)
        board = compile_storyboard(plan, {"aspect_ratio": aspect, "resolution": resolution}, video=True)
        pdf_pages = sum(len(code_pages(s.visual_spec.code, aspect == "9:16")) for s in board.scenes)
        pdf, report = await render_pdf(board, render_html(board), tmp_path)
        assert pdf.startswith(b"%PDF") and len(report["samples"]) == pdf_pages * 4
        assert len({sample["scene"] for sample in report["samples"]}) == pdf_pages
        pdf_path = tmp_path / "dense-code.pdf"
        pdf_path.write_bytes(pdf)
        if shutil.which("pdfinfo"):
            info = await command("pdfinfo", pdf_path)
            assert int(re.search(rb"Pages:\s+(\d+)", info).group(1)) == pdf_pages
        async with browser_page(board, render_html(board, video=True)) as page:
            qa = await screenshot_qa(page, board, tmp_path / "video-qa")
            assert qa["passed"]
            # More than four pages requires QA outside the usual 20/40/60/80%.
            assert any(sample["scene"] == "scene_03" and sample["progress"] > .8 for sample in qa["samples"])
            await page.evaluate("window.seekScene(0, .2)")
            title_before = await page.locator('.scene:visible h1').bounding_box()
            await page.evaluate("window.seekScene(0, 1)")
            assert await page.locator('.scene:visible h1').bounding_box() == title_before
            assert await page.locator('[data-scene="0"] [data-safe="code"]:visible').all_text_contents()
            assert not await page.evaluate("window.inspectLayout()")
    asyncio.run(run())


@pytest.mark.parametrize("aspect",["16:9","9:16"])
def test_real_work_span_connector_and_equation_qa(aspect,tmp_path):
    async def run():
        plan = work_span_lesson()
        for kind,count in [("architecture",5),("algorithm_tree",5),("resource_timeline",3),("flow",5)]:
            plan.sections.extend(work_span_lesson(kind,count).sections)
        board = compile_storyboard(plan,{"aspect_ratio":aspect})
        pdf,qa = await render_pdf(board,render_html(board),tmp_path)
        assert pdf.startswith(b"%PDF") and qa["passed"]
        assert len(qa["samples"]) == 20
    asyncio.run(run())


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
