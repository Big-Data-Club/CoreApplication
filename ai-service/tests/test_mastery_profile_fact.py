"""Learner profiles carry null metrics until the first activity."""
from app.services.mastery_service import build_progress_fact


def test_null_accuracy_and_counts_do_not_crash():
    fact = build_progress_fact({
        "completed_lessons": None,
        "attempted_lessons": None,
        "check_accuracy": None,
    })
    assert "0/0" in fact
    assert "0%" in fact


def test_numeric_profile_is_formatted():
    fact = build_progress_fact({
        "completed_lessons": 3,
        "attempted_lessons": 5,
        "check_accuracy": 0.75,
    })
    assert "3/5" in fact
    assert "75%" in fact


def test_invalid_accuracy_falls_back_to_zero():
    fact = build_progress_fact({"check_accuracy": "not-a-number"})
    assert "0%" in fact
