"""Invariant tests for curriculum ordering; no provider/database required."""
from app.services.course_blueprint_service import BlueprintChapter, CoursePlan, validate_plan


def _plan(chapters):
    return CoursePlan(title="Lập trình Python", description="Từ cơ bản đến nâng cao", chapters=chapters)


def test_topological_order_ignores_model_list_order():
    plan = _plan([
        BlueprintChapter(id="functions", title="Hàm", description="Hàm Python", material_ids=["b"], prerequisites=["variables"]),
        BlueprintChapter(id="variables", title="Biến", description="Biến Python", material_ids=["a"]),
    ])
    result = validate_plan(plan, {"a", "b"})
    assert result["valid"]
    assert result["topological_order"] == ["variables", "functions"]


def test_cycle_and_ungrounded_material_are_rejected():
    plan = _plan([
        BlueprintChapter(id="a", title="Chương A", description="A", material_ids=["missing"], prerequisites=["b"]),
        BlueprintChapter(id="b", title="Chương B", description="B", material_ids=["known"], prerequisites=["a"]),
    ])
    result = validate_plan(plan, {"known"})
    assert not result["valid"]
    assert {error["code"] for error in result["errors"]} == {"unknown_source", "prerequisite_cycle"}
