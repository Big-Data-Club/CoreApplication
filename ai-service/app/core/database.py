from __future__ import annotations

import asyncpg
import psycopg2
import psycopg2.extras
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from app.core.config import get_settings

settings = get_settings()


# ── Async pools (FastAPI + Kafka worker) ──────────────────────────────────────

_ai_pool: asyncpg.Pool | None = None


async def init_ai_pool() -> None:
    global _ai_pool
    _ai_pool = await asyncpg.create_pool(
        host=settings.ai_db_host,
        port=settings.ai_db_port,
        user=settings.ai_db_user,
        password=settings.ai_db_password,
        database=settings.ai_db_name,
        min_size=settings.ai_db_min_connections,
        max_size=settings.ai_db_max_connections,
        statement_cache_size=100,
        max_inactive_connection_lifetime=300,
    )


async def close_ai_pool() -> None:
    global _ai_pool
    if _ai_pool:
        await _ai_pool.close()
        _ai_pool = None


@asynccontextmanager
async def get_ai_conn() -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection from the AI pool. Releases on context exit."""
    assert _ai_pool is not None, "AI pool not initialised - call init_ai_pool()"
    async with _ai_pool.acquire() as conn:
        yield conn


# ── Sync connections (used by migration scripts only) ─────────────────────────

def _make_sync_conn(
    host: str, port: int, user: str, password: str, dbname: str,
) -> psycopg2.extensions.connection:
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=dbname,
    )
    conn.autocommit = False
    return conn


@contextmanager
def get_sync_ai_conn() -> Iterator[psycopg2.extensions.connection]:
    """Sync context manager for AI tables - use in migration scripts only."""
    conn = _make_sync_conn(
        settings.ai_db_host, settings.ai_db_port,
        settings.ai_db_user, settings.ai_db_password, settings.ai_db_name,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_sync_cursor(conn: psycopg2.extensions.connection):
    """Returns a DictCursor for convenient column-name access."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
