"""Regression tests for the active-course authorization anchor."""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from app.agents.memory import active_courses
except ModuleNotFoundError as exc:
    # Local source-only environments may not install AI-service dependencies.
    active_courses = None
    _IMPORT_ERROR = str(exc)
else:
    _IMPORT_ERROR = ""


class _Response:
    status_code = 200

    def json(self):
        return {"data": {"items": [{"id": 42, "title": "Big Data"}]}}


class _Client:
    request: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **kwargs):
        self.request = {"url": url, **kwargs}
        return _Response()


@unittest.skipIf(active_courses is None, f"AI-service dependencies unavailable: {_IMPORT_ERROR}")
class ActiveCoursesTests(unittest.TestCase):
    def test_teacher_fetch_requests_full_authoritative_page(self):
        client = _Client()
        with patch.object(active_courses.httpx, "AsyncClient", return_value=client):
            courses = asyncio.run(active_courses._fetch_teacher_courses(7))

        self.assertEqual(courses, [{
            "id": 42, "title": "Big Data", "status": None, "role": "owner",
        }])
        self.assertEqual(
            client.request["params"],
            {"page": 1, "page_size": active_courses._MAX_COURSES},
        )
        self.assertEqual(client.request["headers"]["X-User-Id"], "7")

    def test_authorization_anchor_keeps_courses_beyond_node_hydration_limit(self):
        courses = [{"id": number, "title": f"Course {number}"} for number in range(1, 21)]
        async def fetch(_user_id):
            return [dict(course) for course in courses]

        async def nodes(course_id):
            return [{"id": course_id, "name": "node", "level": 1}]

        active_courses._CACHE.clear()
        with (
            patch.object(active_courses, "_fetch_teacher_courses", fetch),
            patch.object(active_courses, "_fetch_course_nodes", nodes),
        ):
            anchor = asyncio.run(active_courses.load_active_courses(
                user_id=7, agent_type="teacher", include_nodes=True, refresh=True,
            ))

        self.assertEqual(len(anchor["courses"]), 20)
        self.assertEqual(anchor["courses"][-1]["id"], 20)
        self.assertEqual(anchor["courses"][0]["nodes"][0]["id"], 1)
        self.assertIsNone(anchor["courses"][-1]["nodes"])
