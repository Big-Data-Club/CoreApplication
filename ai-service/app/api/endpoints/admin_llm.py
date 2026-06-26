"""
Admin endpoints for the multi-model LLM registry.
Authentication: the existing X-AI-Secret internal header (same as
app/api/endpoints/admin.py). The auth-and-management service will expose a
role-gated proxy (`/api/admin/llm/*`) that injects this header - end users
never call this FastAPI service directly.
Conventions:
  * POST returns the full new/updated row.
  * DELETE returns 204 No Content.
  * Mutations call `registry.invalidate()` automatically (inside the
    registry methods) so fallback chains pick up the change within ~30s
    even without a restart.
"""
from __future__ import annotations
import logging
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.llm_gateway import (
    ALL_TASK_CODES,
    ChatRequest,
    get_gateway,
    get_registry,
)
from app.core.llm_gateway.adapters import supported_adapter_types
from app.core.llm_gateway.usage import aggregate_usage
logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/admin/llm", tags=["Admin - LLM Registry"])
def _verify(request: Request) -> None:
    if request.headers.get("X-AI-Secret", "") != settings.ai_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")
# ── Schemas ────────────────────────────────────────────────────────────────
class ProviderIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    display_name: str
    adapter_type: str
    base_url: Optional[str] = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
class ProviderUpdate(BaseModel):
    display_name: Optional[str] = None
    adapter_type: Optional[str] = None
    base_url: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict[str, Any]] = None
class ApiKeyIn(BaseModel):
    provider_id: int
    alias: str
    plaintext_key: str
    rpm_limit: Optional[int] = None
    tpm_limit: Optional[int] = None
    daily_token_limit: Optional[int] = None
    status: str = "active"
class ApiKeyUpdate(BaseModel):
    alias: Optional[str] = None
    plaintext_key: Optional[str] = None
    rpm_limit: Optional[int] = None
    tpm_limit: Optional[int] = None
    daily_token_limit: Optional[int] = None
    status: Optional[str] = None
class ModelIn(BaseModel):
    provider_id: int
    model_name: str
    display_name: Optional[str] = None
    family: Optional[str] = None
    context_window: int = 8192
    supports_json: bool = True
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_vision: bool = False
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    default_temperature: float = 0.3
    default_max_tokens: int = 1024
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
class ModelUpdate(BaseModel):
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    family: Optional[str] = None
    context_window: Optional[int] = None
    supports_json: Optional[bool] = None
    supports_tools: Optional[bool] = None
    supports_streaming: Optional[bool] = None
    supports_vision: Optional[bool] = None
    input_cost_per_1k: Optional[float] = None
    output_cost_per_1k: Optional[float] = None
    default_temperature: Optional[float] = None
    default_max_tokens: Optional[int] = None
    enabled: Optional[bool] = None
    config: Optional[dict[str, Any]] = None
class BindingIn(BaseModel):
    task_code: str
    model_id: int
    priority: int = 100
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    json_mode: bool = False
    pinned: bool = False
    enabled: bool = True
    notes: Optional[str] = None
class BindingUpdate(BaseModel):
    priority: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    json_mode: Optional[bool] = None
    pinned: Optional[bool] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = None
class TestCallIn(BaseModel):
    task: Optional[str] = None
    model_hint: Optional[str] = None
    prompt: str = "Say 'ok'."
# ── DTO mappers ─────────────────────────────────────────────────────────────
def _provider_dto(p) -> dict:
    return {
        "id": p.id, "code": p.code, "display_name": p.display_name,
        "adapter_type": p.adapter_type, "base_url": p.base_url,
        "enabled": p.enabled, "config": p.config,
    }
def _model_dto(m) -> dict:
    return {
        "id": m.id, "provider_id": m.provider_id, "provider_code": m.provider_code,
        "adapter_type": m.adapter_type,
        "model_name": m.model_name, "display_name": m.display_name,
        "family": m.family,
        "context_window": m.context_window,
        "supports_json": m.supports_json, "supports_tools": m.supports_tools,
        "supports_streaming": m.supports_streaming, "supports_vision": m.supports_vision,
        "input_cost_per_1k": m.input_cost_per_1k, "output_cost_per_1k": m.output_cost_per_1k,
        "default_temperature": m.default_temperature, "default_max_tokens": m.default_max_tokens,
        "enabled": m.enabled, "config": m.config,
    }
def _key_dto(k) -> dict:
    return {
        "id": k.id, "provider_id": k.provider_id, "alias": k.alias,
        "fingerprint": k.fingerprint, "status": k.status,
        "rpm_limit": k.rpm_limit, "tpm_limit": k.tpm_limit,
        "daily_token_limit": k.daily_token_limit,
        "used_today_requests": k.used_today_requests,
        "used_today_tokens": k.used_today_tokens,
        "cooldown_until": k.cooldown_until.isoformat() if k.cooldown_until else None,
        "consecutive_failures": k.consecutive_failures,
    }
def _binding_dto(b) -> dict:
    return {
        "id": b.id, "task_code": b.task_code,
        "model": _model_dto(b.model),
        "priority": b.priority,
        "temperature": b.temperature, "max_tokens": b.max_tokens,
        "json_mode": b.json_mode, "pinned": b.pinned, "enabled": b.enabled,
    }
# ── Catalogue ───────────────────────────────────────────────────────────────
@router.get("/catalogue")
async def get_catalogue(request: Request):
    _verify(request)
    return {
        "adapter_types": supported_adapter_types(),
        "task_codes": list(ALL_TASK_CODES),
    }
# ── Providers ───────────────────────────────────────────────────────────────
@router.get("/providers")
async def list_providers(request: Request):
    _verify(request)
    reg = get_registry()
    return [_provider_dto(p) for p in await reg.list_providers()]
@router.post("/providers", status_code=201)
async def upsert_provider(body: ProviderIn, request: Request):
    _verify(request)
    if body.adapter_type not in supported_adapter_types():
        raise HTTPException(400, f"Unsupported adapter_type: {body.adapter_type}")
    reg = get_registry()
    p = await reg.upsert_provider(**body.model_dump())
    return _provider_dto(p)
@router.patch("/providers/{provider_id}")
async def update_provider(provider_id: int, body: ProviderUpdate, request: Request):
    _verify(request)
    reg = get_registry()
    try:
        p = await reg.update_provider(provider_id, **body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "Provider not found")
    return _provider_dto(p)
@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: int, request: Request):
    _verify(request)
    await get_registry().delete_provider(provider_id)
    return None
# ── Models ──────────────────────────────────────────────────────────────────
@router.get("/models")
async def list_models(
    request: Request,
    provider_id: Optional[int] = Query(None),
    only_enabled: bool = Query(False),
):
    _verify(request)
    rows = await get_registry().list_models(provider_id=provider_id, only_enabled=only_enabled)
    return [_model_dto(m) for m in rows]
@router.post("/models", status_code=201)
async def upsert_model(body: ModelIn, request: Request):
    _verify(request)
    m = await get_registry().upsert_model(**body.model_dump())
    return _model_dto(m)
@router.patch("/models/{model_id}")
async def update_model(model_id: int, body: ModelUpdate, request: Request):
    _verify(request)
    try:
        m = await get_registry().update_model(model_id, **body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "Model not found")
    return _model_dto(m)
@router.delete("/models/{model_id}", status_code=204)
async def delete_model(model_id: int, request: Request):
    _verify(request)
    await get_registry().delete_model(model_id)
    return None
# ── API Keys ────────────────────────────────────────────────────────────────
@router.get("/keys")
async def list_api_keys(
    request: Request,
    provider_id: Optional[int] = Query(None),
):
    _verify(request)
    rows = await get_registry().list_api_keys(provider_id=provider_id)
    return [_key_dto(k) for k in rows]
@router.post("/keys", status_code=201)
async def create_api_key(body: ApiKeyIn, request: Request):
    _verify(request)
    k = await get_registry().create_api_key(**body.model_dump())
    return _key_dto(k)
@router.patch("/keys/{key_id}")
async def update_api_key(key_id: int, body: ApiKeyUpdate, request: Request):
    _verify(request)
    try:
        k = await get_registry().update_api_key(key_id, **body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "API key not found")
    return _key_dto(k)
@router.delete("/keys/{key_id}", status_code=204)
async def delete_api_key(key_id: int, request: Request):
    _verify(request)
    await get_registry().delete_api_key(key_id)
    return None
# ── Task Bindings ───────────────────────────────────────────────────────────
@router.get("/bindings")
async def list_bindings(
    request: Request,
    task_code: Optional[str] = Query(None),
):
    _verify(request)
    rows = await get_registry().list_bindings(task_code)
    return [_binding_dto(b) for b in rows]
@router.post("/bindings", status_code=201)
async def upsert_binding(body: BindingIn, request: Request):
    _verify(request)
    if body.task_code not in ALL_TASK_CODES:
        # We still allow it - admins may add custom codes - but warn.
        logger.warning("Binding for unknown task_code=%s", body.task_code)
    b = await get_registry().upsert_binding(**body.model_dump())
    return _binding_dto(b)
@router.patch("/bindings/{binding_id}")
async def update_binding(binding_id: int, body: BindingUpdate, request: Request):
    _verify(request)
    try:
        b = await get_registry().update_binding(binding_id, **body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "Binding not found")
    return _binding_dto(b)
@router.delete("/bindings/{binding_id}", status_code=204)
async def delete_binding(binding_id: int, request: Request):
    _verify(request)
    await get_registry().delete_binding(binding_id)
    return None
# ── Usage analytics ─────────────────────────────────────────────────────────
@router.get("/usage")
async def usage_stats(
    request: Request,
    since_hours: int = Query(24, ge=1, le=24 * 30),
    task_code: Optional[str] = Query(None),
):
    _verify(request)
    return {
        "since_hours": since_hours,
        "task_code": task_code,
        "rows": await aggregate_usage(since_hours=since_hours, task_code=task_code),
    }
# ── Test call (admin sanity check) ──────────────────────────────────────────
@router.post("/test-call")
async def test_call(body: TestCallIn, request: Request):
    _verify(request)
    task = body.task or "chat"
    try:
        response = await get_gateway().chat(ChatRequest(
            task=task,
            messages=[{"role": "user", "content": body.prompt}],
            temperature=0.2,
            max_tokens=128,
            model_hint=body.model_hint,
        ))
    except Exception as exc:
        logger.exception("Admin test-call failed")
        raise HTTPException(502, f"{type(exc).__name__}: {exc}")
    return {
        "content": response.content,
        "model": response.model.model_name,
        "provider": response.model.provider_code,
        "fallback_used": response.fallback_used,
        "attempt_no": response.attempt_no,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        },
        "latency_ms": response.latency_ms,
    }