"""Validation shared by course-bound retrieval entry points."""


def require_course_id(course_id: int | None) -> None:
    if type(course_id) is not int or course_id <= 0:
        raise ValueError("A positive course_id is required for retrieval")
