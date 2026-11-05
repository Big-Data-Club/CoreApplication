import threading
import duckdb
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.lakehouse import LakehouseService
from app.api.notebook_models import NotebookAnnotation
from app.api.router import router

ANNOTATION = {"version": 1, "content_id": 21, "quote": "Dữ liệu học tập", "prefix": "", "suffix": "", "start": 0, "end": 15, "color": "yellow"}


@pytest.fixture
def service(tmp_path):
    result = LakehouseService.__new__(LakehouseService)
    result.conn = duckdb.connect(str(tmp_path / "notes.duckdb"))
    result.lock = threading.RLock()
    # Simulate the old schema, including an existing note, before the migration.
    result.conn.execute("CREATE TABLE notebook_entries (id VARCHAR PRIMARY KEY, user_id BIGINT, course_id BIGINT, node_id BIGINT, title VARCHAR, content TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)")
    result.conn.execute("INSERT INTO notebook_entries VALUES ('legacy', 7, 11, NULL, 'Old', 'Existing note', now(), now())")
    result._init_tables()
    yield result
    result.conn.close()


def test_additive_migration_annotations_and_legacy_clients(service):
    assert service.list_notebook_entries(7)[0]["annotation"] is None
    note = service.save_notebook_entry(7, "Highlight", "Comment", 11, annotation=ANNOTATION)
    assert service.list_notebook_entries(7, 11)[0]["annotation"] == ANNOTATION
    updated = service.update_notebook_entry(note["id"], 7, "Edited", "New comment")
    assert updated["annotation"] == ANNOTATION  # old clients omit the new field
    changed = service.update_notebook_entry(note["id"], 7, "Edited", "New comment", {**ANNOTATION, "color": "blue"}, True)
    assert changed["annotation"]["color"] == "blue"
    service._init_tables()  # repeated initialization is safe
    assert service.list_notebook_entries(7, 11)[0]["annotation"]["color"] == "blue"
    cleared = service.update_notebook_entry(note["id"], 7, "Edited", "New comment", None, True)
    assert cleared["annotation"] is None


def test_owner_and_course_isolation(service):
    note = service.save_notebook_entry(7, "Highlight", "Private", 11, annotation=ANNOTATION)
    assert service.list_notebook_entries(8, 11) == []
    assert service.list_notebook_entries(7, 12) == []
    assert service.update_notebook_entry(note["id"], 8, "Wrong", "Wrong", None, True) is None
    service.delete_notebook_entry(note["id"], 8)
    assert any(entry["id"] == note["id"] for entry in service.list_notebook_entries(7))
    service.delete_notebook_entry(note["id"], 7)
    assert all(entry["id"] != note["id"] for entry in service.list_notebook_entries(7))


def test_validated_private_api():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    headers = {"X-AI-Secret": "notebook-test-only-secret"}
    assert client.get("/personalize/notebook", params={"user_id": 7}).status_code == 401
    payload = {"user_id": 7, "title": "Note", "content": "Comment", "course_id": 11, "annotation": ANNOTATION}
    created = client.post("/personalize/notebook", json=payload, headers=headers)
    assert created.status_code == 200
    entry_id = created.json()["id"]
    assert client.put(f"/personalize/notebook/{entry_id}", json={**payload, "user_id": 8}, headers=headers).status_code == 404
    assert client.post("/personalize/notebook", json={**payload, "course_id": None}, headers=headers).status_code == 400
    for change in ({"color": "red"}, {"quote": ""}, {"start": 20, "end": 10}, {"content_id": -1}):
        assert client.post("/personalize/notebook", json={**payload, "annotation": {**ANNOTATION, **change}}, headers=headers).status_code == 422
    assert NotebookAnnotation(**ANNOTATION).color == "yellow"
