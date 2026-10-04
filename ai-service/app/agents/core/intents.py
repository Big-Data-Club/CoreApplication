"""Canonical router categories; planner operations are a separate vocabulary."""
from typing import Literal

RouterIntent = Literal[
    "knowledge_question", "progress_advice", "content_creation",
    "interactive_exercise", "general_chat",
]


def normalize_router_intent(value):
    if not isinstance(value, str):
        return value
    value = value.strip().lower()
    return {
        "content_qa": "knowledge_question",
        "navigation_helper": "knowledge_question",
        "recommendation_engine": "progress_advice",
        "quiz_assist": "interactive_exercise",
    }.get(value, value)
