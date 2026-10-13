import asyncio
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
import httpx

from app.api.endpoints import quiz_gen, studio


def client():
    app = FastAPI()
    app.include_router(quiz_gen.router)
    app.include_router(studio.router)
    return app


def post(app, path, body):
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            return await api.post(path, json=body)
    return asyncio.run(request())


def test_source_generation_requires_internal_auth_and_nonempty_sources():
    api = client()
    body = {"course_id": 2, "sources": [{"content_id": 9, "title": "Lesson", "type": "TEXT", "text": "Material"}]}
    with patch.object(quiz_gen.quiz_gen_service, "generate_for_bank", new=AsyncMock()) as generate:
        assert post(api, "/quiz/generate-from-sources", body).status_code == 403
        assert post(api, "/quiz/generate-from-sources", {"course_id": 2, "sources": []}).status_code == 422
    generate.assert_not_awaited()


def test_studio_cannot_create_project_without_course_edit_permission():
    api = client()
    with patch.object(studio, "_verify"), patch.object(studio, "lms_sources", new=AsyncMock(side_effect=PermissionError("Forbidden"))), patch.object(studio.studio_service, "create_project", new=AsyncMock()) as create:
        response = post(api, "/studio/projects", {"course_id": 2, "user_id": 7})
    assert response.status_code == 403
    create.assert_not_awaited()


def test_curriculum_context_rejects_invalid_ids_before_retrieval():
    with patch.object(studio, "_verify"), patch.object(studio.studio_service, "add_context_source", new=AsyncMock()) as add:
        response = post(client(), "/studio/projects/example/context", {"user_id": 7, "type": "curriculum", "content_ids": [-1]})
    assert response.status_code == 422
    add.assert_not_awaited()
