"""Offline unit tests for StudioService logic & JSON/UUID handling."""
from __future__ import annotations

import json
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from app.services.studio.studio_service import StudioService


class StudioServiceSerializationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = StudioService()

    @patch("app.services.studio.studio_service.get_ai_conn")
    def test_get_project_deserializes_json_and_uuid(self, mock_get_conn: AsyncMock) -> None:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        fake_uuid = uuid.uuid4()
        mock_conn.fetchrow.return_value = {
            "id": fake_uuid,
            "course_id": 65,
            "created_by": 10,
            "kind": "slides",
            "title": "Test Title",
            "status": "collecting",
            "context_pack": json.dumps([{"type": "text", "text": "hello", "hash": "abc"}]),
            "settings": json.dumps({"theme": "academic"}),
            "plan": None,
            "artifacts": json.dumps([]),
            "section_hashes": json.dumps({}),
        }

        import asyncio
        project = asyncio.run(self.service.get_project(str(fake_uuid), 10))

        self.assertIsNotNone(project)
        self.assertEqual(project["id"], str(fake_uuid))
        self.assertIsInstance(project["context_pack"], list)
        self.assertEqual(len(project["context_pack"]), 1)
        self.assertEqual(project["context_pack"][0]["text"], "hello")
        self.assertIsInstance(project["settings"], dict)
        self.assertEqual(project["settings"]["theme"], "academic")

    @patch("app.services.studio.studio_service.get_ai_conn")
    def test_add_context_source_text(self, mock_get_conn: AsyncMock) -> None:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        fake_uuid = str(uuid.uuid4())
        mock_conn.fetchrow.return_value = {
            "id": fake_uuid,
            "course_id": 65,
            "created_by": 10,
            "kind": "slides",
            "title": "Test Title",
            "status": "collecting",
            "context_pack": json.dumps([]),
            "settings": json.dumps({"theme": "academic"}),
            "plan": None,
            "artifacts": json.dumps([]),
            "section_hashes": json.dumps({}),
        }

        import asyncio
        res = asyncio.run(self.service.add_context_source(
            fake_uuid, 10, {"type": "text", "title": "Văn bản dán", "text": "Nội dung bài giảng..."}
        ))

        self.assertFalse(res["duplicate"])
        self.assertEqual(res["sources"], 1)
        self.assertGreater(res["chars"], 0)

    def test_llm_gateway_exports_task_content_studio(self) -> None:
        from app.core.llm_gateway import TASK_CONTENT_STUDIO, ALL_TASK_CODES
        self.assertEqual(TASK_CONTENT_STUDIO, "content_studio")
        self.assertIn("content_studio", ALL_TASK_CODES)


if __name__ == "__main__":
    unittest.main()
