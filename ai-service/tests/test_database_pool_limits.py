"""Exercise the production manifests' pool settings at the pool boundary."""

from pathlib import Path
import os
from urllib.parse import urlsplit
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from pydantic import ValidationError

from app.core import database
from app.core.config import Settings


def worker_pool_settings():
    root = Path(__file__).resolve().parents[2]
    for filename in ("ai-service-deployment.yaml", "ai-light-workers-deployment.yaml"):
        for doc in yaml.safe_load_all((root / "k3s/base" / filename).read_text()):
            if doc.get("kind") != "Deployment":
                continue
            for container in doc["spec"]["template"]["spec"]["containers"]:
                env = {
                    e["name"]: e["value"]
                    for e in container.get("env", [])
                    if "value" in e
                }
                if "AI_WORKER_MODE" in env:
                    yield doc["metadata"]["name"], env


@pytest.mark.asyncio
@pytest.mark.parametrize("name,env", list(worker_pool_settings()))
async def test_deployed_worker_pool_can_initialize(name, env):
    assert env.get("AI_DB_MIN_CONNECTIONS") == "1", name
    settings = Settings(
        _env_file=None,
        **{
            field: int(env[key])
            for key, field in (
                ("AI_DB_MIN_CONNECTIONS", "ai_db_min_connections"),
                ("AI_DB_MAX_CONNECTIONS", "ai_db_max_connections"),
            )
            if key in env
        }
    )

    async def create_pool(**kwargs):
        assert 0 <= kwargs["min_size"] <= kwargs["max_size"], name
        return SimpleNamespace(close=AsyncMock())

    with patch.object(database, "settings", settings), patch.object(
        database, "_ai_pool", None
    ), patch.object(database.asyncpg, "create_pool", side_effect=create_pool):
        await database.init_ai_pool()
        await database.close_ai_pool()


@pytest.mark.asyncio
async def test_lowered_maximum_also_caps_inherited_minimum():
    settings = Settings(
        _env_file=None, ai_db_min_connections=5, ai_db_max_connections=4
    )
    create = AsyncMock(return_value=SimpleNamespace(close=AsyncMock()))
    with patch.object(database, "settings", settings), patch.object(
        database, "_ai_pool", None
    ), patch.object(database.asyncpg, "create_pool", create):
        await database.init_ai_pool()
        assert create.await_args.kwargs["min_size"] == 4
        assert create.await_args.kwargs["max_size"] == 4
        await database.close_ai_pool()


@pytest.mark.parametrize(
    "values", [{"ai_db_min_connections": -1}, {"ai_db_max_connections": 0}]
)
def test_invalid_pool_bounds_are_rejected(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_worker_pools_connect_to_disposable_postgres():
    dsn = os.getenv("AI_POOL_TEST_DSN")
    if not dsn:
        pytest.skip("Disposable AI_POOL_TEST_DSN not supplied")
    url = urlsplit(dsn)
    cases = [
        (int(env["AI_DB_MIN_CONNECTIONS"]), int(env["AI_DB_MAX_CONNECTIONS"]))
        for _, env in worker_pool_settings()
    ] + [(5, 4)]
    for minimum, maximum in cases:
        settings = Settings(
            _env_file=None,
            ai_db_host=url.hostname,
            ai_db_port=url.port,
            ai_db_user=url.username,
            ai_db_password=url.password or "",
            ai_db_name=url.path.lstrip("/"),
            ai_db_min_connections=minimum,
            ai_db_max_connections=maximum,
        )
        with patch.object(database, "settings", settings), patch.object(
            database, "_ai_pool", None
        ):
            try:
                await database.init_ai_pool()
                assert database._ai_pool.get_min_size() <= maximum
                assert database._ai_pool.get_max_size() == maximum
                async with database.get_ai_conn() as conn:
                    assert await conn.fetchval("SELECT 1") == 1
            finally:
                await database.close_ai_pool()
