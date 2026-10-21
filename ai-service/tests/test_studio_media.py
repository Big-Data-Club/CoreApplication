from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.studio.browser_renderer import validate_video
from app.services.studio.html_renderer import render_html
from app.services.studio.plan_schema import Narrative, PlanSection, StudioPlan, VisualSpec
from app.services.studio.storyboard import compile_storyboard
from app.services.studio.studio_service import StudioService


def lesson():
    return StudioPlan(title="Matrix lesson", narrative=Narrative(
        learner_goal="Understand dot products", misconception="Parallel time alone determines speed",
        concept_dependencies=["Dot product", "Work", "Parallel decomposition"],
    ), sections=[PlanSection(
        title="Một ô của tích ma trận", learning_goal="Explain the reduction",
        slide_bullets=["Một hàng của A", "Một cột của B", "Cộng các tích"],
        narration="Một hàng của A kết hợp với một cột của B. Cộng các tích để tính một ô của C.",
        visual_type="matrix_dot_product", animation_steps=["highlight_row", "highlight_column", "multiply", "reduce"],
        source_refs=["S1"],
    )])


def test_storyboard_duration_is_unknown_until_audio_measured():
    plan = lesson(); plan.sections[0].duration_est_sec = 999
    board = compile_storyboard(plan, {}, video=True)
    assert board.scenes[0].duration is None
    assert board.scenes[0].learning_goal == "Explain the reduction"


def test_portrait_is_native_canvas_with_its_own_layout():
    board = compile_storyboard(lesson(), {"aspect_ratio": "9:16"}, video=True)
    html = render_html(board)
    assert (board.video.width, board.video.height) == (1080, 1920)
    assert "flex-direction:column" in html
    assert "padding-right:150px" in html
    assert "17% 61% 22%" in html
    assert 'viewBox="0 0 800 900"' in html


def test_source_text_cannot_escape_html_or_script():
    plan = lesson(); plan.sections[0].narration = '</script><script>alert("source")</script>'
    plan.sections[0].title = '<img src=x onerror=alert(1)>'
    html = render_html(compile_storyboard(plan, {}))
    assert '<img src=x' not in html
    assert '</script><script>alert' not in html
    assert '&lt;img src=x' in html


@pytest.mark.parametrize("change", ["many_points", "long_title", "long_narration", "invalid_edge", "matrix"])
def test_dense_or_invalid_semantic_scenes_fail_before_rendering(change):
    plan = lesson(); scene = plan.sections[0]
    if change == "many_points": scene.slide_bullets = ["point"] * 4
    if change == "long_title": scene.title = "Title " * 30
    if change == "long_narration": scene.narration = "x" * 2401
    if change == "invalid_edge": scene.visual_spec = VisualSpec(edges=[{"source": "missing", "target": "other"}])
    if change == "matrix": scene.visual_spec = VisualSpec(matrix_a=[["1"], ["1", "2"]])
    with pytest.raises(ValueError): compile_storyboard(plan, {}, video=True)


def test_video_requires_narrative_before_visual_design():
    plan = lesson(); plan.narrative = Narrative()
    with pytest.raises(ValueError, match="narrative"): compile_storyboard(plan, {}, video=True)


def test_final_media_rejects_wrong_codec_and_drift():
    board = compile_storyboard(lesson(), {})
    board.scenes[0].duration = 3.19
    info = {"streams": [
        {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "width": 1920, "height": 1080, "r_frame_rate": "30/1", "duration": "3.2"},
        {"codec_type": "audio", "codec_name": "aac", "duration": "3.19"},
    ], "format": {"duration": "3.2"}}
    assert validate_video(info, board)["passed"]
    info["format"]["duration"] = "3.8"
    with pytest.raises(ValueError, match="timing"): validate_video(info, board)
    info["format"]["duration"] = "3.2"; info["streams"][1]["codec_name"] = "mp3"
    with pytest.raises(ValueError, match="AAC"): validate_video(info, board)


def test_stale_worker_cannot_overwrite_a_new_job():
    from uuid import uuid4
    from app.services.studio.jobs import active_lease
    async def run():
        conn = AsyncMock(); conn.execute.return_value = "UPDATE 0"
        with patch("app.services.studio.studio_service.get_ai_conn") as pool:
            pool.return_value.__aenter__.return_value = conn
            token = active_lease.set((uuid4(), uuid4()))
            try:
                with pytest.raises(ValueError, match="lease expired"):
                    await StudioService()._update(str(uuid4()), 10, status="ready")
            finally:
                active_lease.reset(token)
        query, *params = conn.execute.call_args.args
        assert "j.lease_until>now()" in query and "current_job_id=$4" in query
        assert len(params) == 5
    asyncio.run(run())


def test_slides_generate_pdf_html_and_never_pptx(tmp_path):
    async def run():
        service = StudioService()
        service.get_project = AsyncMock(return_value={"kind": "slides", "plan": lesson().model_dump(), "settings": {}, "context_pack": []})
        service._update = AsyncMock()
        async def pdf(board, html, directory):
            return b"%PDF fixture", {"passed": True}
        with patch("app.services.studio.browser_renderer.render_pdf", side_effect=pdf), patch(
            "app.services.studio.temporary_media.store", new=AsyncMock(return_value={"asset_id": "private-fixture", "url": "/api/ai/studio/media/private-fixture"})
        ):
            await service._generate_and_store("fixture-project", 1)
        final = service._update.call_args.kwargs
        import json
        artifacts = json.loads(final["artifacts"])
        assert final["status"] == "ready"
        assert {a["type"] for a in artifacts} == {"pdf", "html", "storyboard", "qa", "bundle"}
    asyncio.run(run())


def test_diagrams_keep_independent_arrow_markers_when_other_scenes_are_hidden():
    plan = lesson()
    graph = PlanSection(title="Data path", visual_type="flow", source_refs=["S1"],
        visual_spec=VisualSpec(nodes=[{"id":"a","label":"CPU"},{"id":"b","label":"Memory"}],
                               edges=[{"source":"a","target":"b"}]))
    plan.sections.extend([graph,graph.model_copy()])
    html = render_html(compile_storyboard(plan, {}), video=True)
    assert 'marker-end="url(#arrow_scene_02)"' in html
    assert 'marker-end="url(#arrow_scene_03)"' in html
    assert html.count('id="arrow_scene_02"') == 1


def test_duplicate_enqueue_returns_existing_job_without_starting_another():
    from app.services.studio.jobs import enqueue
    from unittest.mock import MagicMock
    from uuid import uuid4
    job_id = uuid4()
    async def run():
        conn = AsyncMock(); conn.transaction = MagicMock(return_value=AsyncMock())
        conn.fetchrow.side_effect = [{"id": "project"}, {"id": job_id}]
        with patch("app.services.studio.jobs.get_ai_conn") as pool:
            pool.return_value.__aenter__.return_value = conn
            result = await enqueue(str(uuid4()), 7, "render")
        assert result == {"already_running": True, "job_id": str(job_id)}
        conn.execute.assert_awaited_once()
        assert "pg_advisory_xact_lock" in conn.execute.call_args.args[0]
    asyncio.run(run())


def test_section_edit_api_returns_the_project_wrapper_expected_by_frontend():
    from fastapi import FastAPI
    import httpx
    from app.api.endpoints import studio
    from app.core.config import get_settings
    app = FastAPI(); app.include_router(studio.router)
    async def run():
        with patch.object(studio, "_project", new=AsyncMock()), patch.object(get_settings(), "ai_service_secret", "fixture-secret"), patch.object(
            studio.studio_service, "update_section", new=AsyncMock(return_value={"id":"project", "status":"planned"})
        ):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
                result = await client.patch("/studio/projects/project/sections", headers={"X-AI-Secret":"fixture-secret"},
                                            json={"user_id":7,"index":0,"patch":{"title":"Edited"}})
        assert result.status_code == 200 and result.json()["project"]["status"] == "planned"
    asyncio.run(run())


def test_markdown_preserves_topology_equations_and_code():
    from app.services.studio.doc_renderer import render_plan_to_markdown
    plan = lesson()
    plan.sections[0].visual_spec = VisualSpec(nodes=[{"id":"a","label":"CPU"},{"id":"b","label":"Cache"},{"id":"c","label":"RAM"}],
        edges=[{"source":"a","target":"b"},{"source":"a","target":"c"}], equation="Tₚ ≥ max(T₁/p, T∞)", code="c += a[k] * b[k];")
    text = render_plan_to_markdown(plan)
    assert "N0 --> N1" in text and "N0 --> N2" in text and "N1 --> N2" not in text
    assert "Tₚ ≥ max(T₁/p, T∞)" in text and "c += a[k] * b[k];" in text
