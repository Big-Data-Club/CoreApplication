"""Exercise real multipart parsing; mock document conversion and model calls."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api.endpoints import quiz_gen


class QuizFileUploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = FastAPI()
        app.include_router(quiz_gen.router, prefix="/ai")
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.settings = patch.object(quiz_gen, "settings", SimpleNamespace(ai_service_secret="upload-test"))
        self.settings.start()
        self.headers = {"X-AI-Secret": "upload-test"}

    async def asyncTearDown(self):
        await self.client.aclose()
        self.settings.stop()

    async def test_uploaded_file_reaches_conversion_and_question_parser(self):
        content = b"Question: Which command updates uv? A. uv self update B. uv sync"
        questions = [{"question_type": "SINGLE_CHOICE", "question_text": "Which command updates uv?"}]
        with patch("app.services.file_to_markdown.convert_to_markdown", new=AsyncMock(return_value=SimpleNamespace(markdown=content.decode(), images=[], page_count=1, ocr_pages=0))) as convert, patch("app.services.quiz_parse_service.quiz_parse_service.parse", new=AsyncMock(return_value=questions)) as parse:
            response = await self.client.post("/ai/quiz/parse-file", headers=self.headers, files={"file": ("exam.md", content, "text/markdown")}, data={"points_per_question": "5", "language": "vi"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["source"]["file_name"], "exam.md")
        self.assertEqual(convert.await_args.kwargs["file_bytes"], content)
        self.assertEqual(parse.await_args.kwargs["points_per_question"], 5)

    async def test_missing_file_is_bad_request(self):
        response = await self.client.post("/ai/quiz/parse-file", headers=self.headers, files={"other": ("exam.txt", b"text")})
        self.assertEqual(response.status_code, 400, response.text)

    async def test_empty_file_is_bad_request(self):
        response = await self.client.post("/ai/quiz/parse-file", headers=self.headers, files={"file": ("exam.txt", b"")})
        self.assertEqual(response.status_code, 400, response.text)

    async def test_upload_requires_internal_auth(self):
        response = await self.client.post("/ai/quiz/parse-file", files={"file": ("exam.txt", b"text")})
        self.assertEqual(response.status_code, 403, response.text)
