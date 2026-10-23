from __future__ import annotations

from itertools import combinations
from xml.etree import ElementTree as ET

import pytest

from app.services.studio.html_renderer import diagram
from app.services.studio.plan_schema import VisualSpec
from app.services.studio.storyboard import compile_storyboard
from tests.test_studio_media import lesson


def timeline_lesson(count=9, *, kind="resource_timeline", equation=True, edges="chain"):
    plan = lesson()
    section = plan.sections[0]
    section.title = "Lịch trình trên 2 bộ xử lý và giới hạn tốc độ"
    section.slide_bullets = ["Tôn trọng phụ thuộc", "Work và span giới hạn tốc độ"]
    section.narration = "Hai bộ xử lý thực hiện các tác vụ theo quan hệ phụ thuộc. Work và span cùng giới hạn tốc độ."
    section.visual_type = kind
    names = ["Bộ xử lý 1 thực hiện các tác vụ", "Bộ xử lý 2 thực hiện các tác vụ", "Chờ dữ liệu", "Tác vụ C", "Tác vụ D", "Đồng bộ", "Kết quả", "Giới hạn T₁/2", "Giới hạn T∞"]
    pairs = [(i,i+1) for i in range(count-1)]
    if edges == "dense":
        pairs += [pair for pair in combinations(range(count),2) if pair not in pairs]
    if edges == "none":
        pairs = []
    section.visual_spec = VisualSpec(
        nodes=[{"id":f"n{i}","label":names[i]} for i in range(count)],
        edges=[{"source":f"n{i}","target":f"n{j}","label":"phụ thuộc"} for i,j in pairs[:12]],
        equation="T₂ ≥ max(T₁/2, T∞)" if equation else "",
    )
    return plan


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
@pytest.mark.parametrize("kind", ["timeline", "resource_timeline"])
@pytest.mark.parametrize("count", range(1,10))
@pytest.mark.parametrize("equation", [False, True])
def test_timelines_fit_all_schema_nodes_without_removing_labels(aspect,kind,count,equation):
    board = compile_storyboard(timeline_lesson(count,kind=kind,equation=equation),{"aspect_ratio":aspect},video=True)
    scene = board.scenes[0]
    original = scene.model_dump()
    svg = ET.fromstring(diagram(scene, aspect == "9:16"))
    nodes = [el for el in svg.iter() if "data-node-boundary" in el.attrib]
    assert len(nodes) == count
    width,height = (800,900) if aspect == "9:16" else (1180,650)
    rectangles = []
    for node in nodes:
        x,y,w,h = (float(node.attrib[key]) for key in ("x","y","width","height"))
        assert 0 <= x < x+w <= width and 0 <= y < y+h <= height-(100 if equation else 20)+1
        assert h >= 100
        rectangles.append((x,y,w,h))
    for a,b in combinations(rectangles,2):
        assert not (a[0]<b[0]+b[2] and a[0]+a[2]>b[0] and a[1]<b[1]+b[3] and a[1]+a[3]>b[1])
    text = " ".join(svg.itertext())
    assert all(node.label in text for node in scene.visual_spec.nodes)
    assert text.count("phụ thuộc") == len(scene.visual_spec.edges)
    assert scene.model_dump() == original


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
def test_timeline_keeps_twelve_labeled_dependencies_and_equation(aspect):
    scene = compile_storyboard(timeline_lesson(edges="dense"),{"aspect_ratio":aspect}).scenes[0]
    svg = ET.fromstring(diagram(scene,aspect=="9:16"))
    assert " ".join(svg.itertext()).count("phụ thuộc") == 12
    assert scene.visual_spec.equation in " ".join(svg.itertext())
