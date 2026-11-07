"""Notebook proxy contract in isolation from model/agent startup dependencies."""
import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
import httpx
import pytest
from fastapi import Header, HTTPException
from pydantic import BaseModel


def load_proxy():
    tree = ast.parse((Path(__file__).parents[1] / "app/api/agent_router.py").read_text())
    names = {"NotebookEntryRequest", "_verify_secret", "create_notebook_entry", "update_notebook_entry"}
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    scope = {"BaseModel": BaseModel, "Optional": Optional, "Header": Header, "HTTPException": HTTPException, "settings": SimpleNamespace(ai_service_secret="test-secret", personalize_service_url="http://test"), "logger": logging.getLogger(__name__)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "notebook-proxy", "exec"), scope)
    return scope


def test_optional_annotation_forwarding_and_secret(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs): calls.append(kwargs["json"]); return httpx.Response(200, json={"id": "note", **kwargs["json"]})
        async def put(self, url, **kwargs): return await self.post(url, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    proxy = load_proxy()
    Model = proxy["NotebookEntryRequest"]
    annotation = {"version": 1, "content_id": 21, "quote": "Text", "start": 0, "end": 4, "color": "yellow"}
    asyncio.run(proxy["create_notebook_entry"](Model(title="Title", content="Text", course_id=11, annotation=annotation), 7, "test-secret"))
    assert calls[-1]["annotation"] == annotation and calls[-1]["user_id"] == 7
    asyncio.run(proxy["update_notebook_entry"]("note", Model(title="Title", content="Text"), 7, "test-secret"))
    assert "annotation" not in calls[-1]
    asyncio.run(proxy["update_notebook_entry"]("note", Model(title="Title", content="Text", annotation=None), 7, "test-secret"))
    assert calls[-1]["annotation"] is None
    with pytest.raises(HTTPException) as error:
        asyncio.run(proxy["create_notebook_entry"](Model(title="Title", content="Text"), 7, "wrong"))
    assert error.value.status_code == 401
