from app.next_action import next_actions


def test_progress_prerequisites_deduplication_and_budget():
    profile = {"available_content": [
        {"content_id": 1, "content_title": "Done", "completed": True},
        {"content_id": 2, "content_title": "Locked", "prerequisites_met": False},
        {"content_id": 3, "content_title": "Next", "completed": False},
        {"content_id": 4, "content_title": "Resume", "started": True},
        {"content_id": 4, "content_title": "Resume", "started": True, "skill_id": 9},
    ]}
    result = next_actions(profile, 15)
    assert [item["content_id"] for item in result] == [4, 3]
    assert sum(item["estimated_minutes"] for item in result) <= 15


def test_unknown_mastery_is_not_evidence_of_weakness():
    result = next_actions({
        "skill_states": [{"skill_id": 1, "mastery_score": 0, "attempt_count": 0}],
        "available_content": [{"content_id": 1, "content_title": "Start", "skill_id": 1}],
    })
    assert result[0]["action"] == "learn_new"


def test_explicit_format_preference_filters_content():
    profile = {"available_content": [
        {"content_id": 1, "content_title": "Reading", "content_type": "TEXT"},
        {"content_id": 2, "content_title": "Practice", "content_type": "QUIZ"},
    ]}
    assert next_actions(profile, prefer_format="practice")[0]["content_id"] == 2
    assert next_actions(profile, prefer_format="theory")[0]["content_id"] == 1


def test_completed_content_is_reviewed_only_with_observed_skill_gap():
    profile = {
        "skill_states": [{"skill_id": 1, "skill_name": "Python", "mastery_score": 0.3, "attempt_count": 3}],
        "available_content": [{"content_id": 1, "content_title": "Review", "skill_id": 1, "completed": True}],
    }
    assert next_actions(profile)[0]["action"] == "review"
    profile["skill_states"][0]["mastery_score"] = 0.9
    assert next_actions(profile) == []
