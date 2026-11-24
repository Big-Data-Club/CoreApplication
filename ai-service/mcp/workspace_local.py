"""Local-only Workspace MCP runner using the regular BDC router and database."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.cache import close_cache
from app.core.database import close_ai_pool, init_ai_pool
from mcp.router import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_ai_pool()
    try:
        yield
    finally:
        await close_cache()
        await close_ai_pool()


app = FastAPI(title="Local BDC Workspace MCP", lifespan=lifespan)
paths = {"/mcp/workspace", "/mcp/keys", "/mcp/keys/{key_id}"}
app.router.routes.extend(route for route in router.routes if route.path in paths)


@app.get("/health")
async def health():
    return {"status": "ok", "profile": "workspace-mcp-local"}
