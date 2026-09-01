from app.api.endpoints.course_blueprints import _validate_external_mcp_plan


def test_legacy_mcp_blueprint_accepts_lesson_rich_curriculum():
    report = _validate_external_mcp_plan({
        "title": "Foundation in AI",
        "chapters": [
            {
                "title": "Introduction to AI",
                "description": "Foundations",
                "lessons": [
                    {"title": "What is intelligence?", "description": "Definitions"},
                    {"title": "History of AI", "markdown": "# History"},
                ],
            }
        ],
    })
    assert report["valid"] is True
    assert report["lesson_count"] == 2


def test_legacy_mcp_blueprint_rejects_invalid_lessons():
    report = _validate_external_mcp_plan({
        "title": "Foundation in AI",
        "chapters": [{"title": "Introduction", "lessons": [{"title": ""}]}],
    })
    assert report["valid"] is False
    assert any(item["code"] == "invalid_lesson" for item in report["errors"])
