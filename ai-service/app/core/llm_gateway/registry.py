"""
Registry - DB repository + in-process cache for providers, models, API keys
and task bindings.
 
The gateway consults the registry on every call; to avoid a round trip we
cache the resolved fallback chains for each task in memory with a short TTL.
Admin mutations publish a version bump via `invalidate()` which blows the
cache so changes are visible within ~1 second without a restart.
"""
from __future__ import annotations
 
import logging
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Optional
 
from app.core.database import get_ai_conn
from app.core.llm_gateway.crypto import encrypt, fingerprint
from app.core.llm_gateway.types import (
    ALL_TASK_CODES,
    ApiKey,
    Model,
    Provider,
    TaskBinding,
)
 
logger = logging.getLogger(__name__)
 
 
CACHE_TTL_SECONDS = 30  # bindings cache lifetime
 
 
class ModelRegistry:
    """Async repository for the llm_* and task_model_bindings tables."""
 
    def __init__(self) -> None:
        self._bindings_cache: dict[str, tuple[float, list[TaskBinding]]] = {}
        self._cache_version: int = 0
 
    # ── Cache management ─────────────────────────────────────────────────────
    def invalidate(self) -> None:
        """Drop cached binding chains. Called after any admin mutation."""
        self._bindings_cache.clear()
        self._cache_version += 1
 
    # ── Providers ────────────────────────────────────────────────────────────
    async def list_providers(self, *, only_enabled: bool = False) -> list[Provider]:
        q = "SELECT * FROM llm_providers"
        if only_enabled:
            q += " WHERE enabled = TRUE"
        q += " ORDER BY id"
        async with get_ai_conn() as conn:
            rows = await conn.fetch(q)
        return [_row_to_provider(r) for r in rows]
 
    async def get_provider(self, provider_id: int) -> Optional[Provider]:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow("SELECT * FROM llm_providers WHERE id = $1", provider_id)
        return _row_to_provider(row) if row else None
 
    async def get_provider_by_code(self, code: str) -> Optional[Provider]:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow("SELECT * FROM llm_providers WHERE code = $1", code)
        return _row_to_provider(row) if row else None
 
    async def upsert_provider(
        self,
        *,
        code: str,
        display_name: str,
        adapter_type: str,
        base_url: Optional[str] = None,
        enabled: bool = True,
        config: Optional[dict[str, Any]] = None,
    ) -> Provider:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO llm_providers (code, display_name, adapter_type, base_url, enabled, config)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (code) DO UPDATE SET
                  display_name = EXCLUDED.display_name,
                  adapter_type = EXCLUDED.adapter_type,
                  base_url     = EXCLUDED.base_url,
                  enabled      = EXCLUDED.enabled,
                  config       = EXCLUDED.config
                RETURNING *
                """,
                code, display_name, adapter_type, base_url, enabled,
                _json(config or {}),
            )
        self.invalidate()
        return _row_to_provider(row)
 
    async def update_provider(self, provider_id: int, **fields: Any) -> Provider:
        allowed = {"display_name", "adapter_type", "base_url", "enabled", "config"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            p = await self.get_provider(provider_id)
            if not p:
                raise KeyError(f"Provider {provider_id} not found")
            return p
        set_clause, values = _build_update(updates, start=2)
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                f"UPDATE llm_providers SET {set_clause} WHERE id = $1 RETURNING *",
                provider_id, *values,
            )
        if not row:
            raise KeyError(f"Provider {provider_id} not found")
        self.invalidate()
        return _row_to_provider(row)
 
    async def delete_provider(self, provider_id: int) -> None:
        async with get_ai_conn() as conn:
            await conn.execute("DELETE FROM llm_providers WHERE id = $1", provider_id)
        self.invalidate()
 
    # ── Models ───────────────────────────────────────────────────────────────
    async def list_models(
        self, *, provider_id: Optional[int] = None, only_enabled: bool = False
    ) -> list[Model]:
        q = (
            "SELECT m.*, p.code AS provider_code, p.adapter_type, p.base_url AS provider_base_url "
            "FROM llm_models m JOIN llm_providers p ON p.id = m.provider_id"
        )
        conds, args = [], []
        if provider_id is not None:
            args.append(provider_id)
            conds.append(f"m.provider_id = ${len(args)}")
        if only_enabled:
            conds.append("m.enabled = TRUE AND p.enabled = TRUE")
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY m.provider_id, m.model_name"
        async with get_ai_conn() as conn:
            rows = await conn.fetch(q, *args)
        return [_row_to_model(r) for r in rows]
 
    async def get_model(self, model_id: int) -> Optional[Model]:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                SELECT m.*, p.code AS provider_code, p.adapter_type,
                       p.base_url AS provider_base_url
                FROM llm_models m JOIN llm_providers p ON p.id = m.provider_id
                WHERE m.id = $1
                """,
                model_id,
            )
        return _row_to_model(row) if row else None
 
    async def upsert_model(
        self,
        *,
        provider_id: int,
        model_name: str,
        display_name: Optional[str] = None,
        family: Optional[str] = None,
        context_window: int = 8192,
        supports_json: bool = True,
        supports_tools: bool = False,
        supports_streaming: bool = True,
        supports_vision: bool = False,
        input_cost_per_1k: float = 0.0,
        output_cost_per_1k: float = 0.0,
        default_temperature: float = 0.3,
        default_max_tokens: int = 1024,
        enabled: bool = True,
        config: Optional[dict[str, Any]] = None,
    ) -> Model:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO llm_models (
                    provider_id, model_name, display_name, family, context_window,
                    supports_json, supports_tools, supports_streaming, supports_vision,
                    input_cost_per_1k, output_cost_per_1k, default_temperature,
                    default_max_tokens, enabled, config
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb
                )
                ON CONFLICT (provider_id, model_name) DO UPDATE SET
                  display_name        = EXCLUDED.display_name,
                  family              = EXCLUDED.family,
                  context_window      = EXCLUDED.context_window,
                  supports_json       = EXCLUDED.supports_json,
                  supports_tools      = EXCLUDED.supports_tools,
                  supports_streaming  = EXCLUDED.supports_streaming,
                  supports_vision     = EXCLUDED.supports_vision,
                  input_cost_per_1k   = EXCLUDED.input_cost_per_1k,
                  output_cost_per_1k  = EXCLUDED.output_cost_per_1k,
                  default_temperature = EXCLUDED.default_temperature,
                  default_max_tokens  = EXCLUDED.default_max_tokens,
                  enabled             = EXCLUDED.enabled,
                  config              = EXCLUDED.config
                RETURNING *
                """,
                provider_id, model_name, display_name, family, context_window,
                supports_json, supports_tools, supports_streaming, supports_vision,
                input_cost_per_1k, output_cost_per_1k, default_temperature,
                default_max_tokens, enabled, _json(config or {}),
            )
            prov = await conn.fetchrow(
                "SELECT code, adapter_type, base_url FROM llm_providers WHERE id = $1",
                provider_id,
            )
        self.invalidate()
        merged = dict(row)
        merged["provider_code"] = prov["code"]
        merged["adapter_type"] = prov["adapter_type"]
        merged["provider_base_url"] = prov["base_url"]
        return _row_to_model(merged)
 
    async def update_model(self, model_id: int, **fields: Any) -> Model:
        allowed = {
            "model_name", "display_name", "family", "context_window",
            "supports_json", "supports_tools", "supports_streaming",
            "supports_vision", "input_cost_per_1k", "output_cost_per_1k",
            "default_temperature", "default_max_tokens", "enabled", "config",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            m = await self.get_model(model_id)
            if not m:
                raise KeyError(f"Model {model_id} not found")
            return m
        set_clause, values = _build_update(updates, start=2)
        async with get_ai_conn() as conn:
            await conn.execute(
                f"UPDATE llm_models SET {set_clause} WHERE id = $1",
                model_id, *values,
            )
        self.invalidate()
        model = await self.get_model(model_id)
        if not model:
            raise KeyError(f"Model {model_id} not found after update")
        return model
 
    async def delete_model(self, model_id: int) -> None:
        async with get_ai_conn() as conn:
            await conn.execute("DELETE FROM llm_models WHERE id = $1", model_id)
        self.invalidate()
 
    # ── API keys ─────────────────────────────────────────────────────────────
    async def list_api_keys(self, *, provider_id: Optional[int] = None) -> list[ApiKey]:
        q = "SELECT * FROM llm_api_keys"
        args: list[Any] = []
        if provider_id is not None:
            q += " WHERE provider_id = $1"
            args.append(provider_id)
        q += " ORDER BY provider_id, alias"
        async with get_ai_conn() as conn:
            rows = await conn.fetch(q, *args)
        return [_row_to_key(r) for r in rows]
 
    async def get_api_key(self, key_id: int) -> Optional[ApiKey]:
        async with get_ai_conn() as conn:
            row = await conn.fetchrow("SELECT * FROM llm_api_keys WHERE id = $1", key_id)
        return _row_to_key(row) if row else None
 
    async def create_api_key(
        self,
        *,
        provider_id: int,
        alias: str,
        plaintext_key: str,
        rpm_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        daily_token_limit: Optional[int] = None,
        status: str = "active",
    ) -> ApiKey:
        encrypted = encrypt(plaintext_key)
        fp = fingerprint(plaintext_key)
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO llm_api_keys (
                    provider_id, alias, encrypted_key, key_fingerprint,
                    rpm_limit, tpm_limit, daily_token_limit, status
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                RETURNING *
                """,
                provider_id, alias, encrypted, fp,
                rpm_limit, tpm_limit, daily_token_limit, status,
            )
        self.invalidate()
        return _row_to_key(row)
 
    async def update_api_key(
        self,
        key_id: int,
        *,
        alias: Optional[str] = None,
        plaintext_key: Optional[str] = None,
        rpm_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        daily_token_limit: Optional[int] = None,
        status: Optional[str] = None,
    ) -> ApiKey:
        updates: dict[str, Any] = {}
        if alias is not None:
            updates["alias"] = alias
        if plaintext_key is not None:
            updates["encrypted_key"] = encrypt(plaintext_key)
            updates["key_fingerprint"] = fingerprint(plaintext_key)
        if rpm_limit is not None:
            updates["rpm_limit"] = rpm_limit
        if tpm_limit is not None:
            updates["tpm_limit"] = tpm_limit
        if daily_token_limit is not None:
            updates["daily_token_limit"] = daily_token_limit
        if status is not None:
            updates["status"] = status
        if not updates:
            key = await self.get_api_key(key_id)
            if not key:
                raise KeyError(f"API key {key_id} not found")
            return key
        set_clause, values = _build_update(updates, start=2)
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                f"UPDATE llm_api_keys SET {set_clause} WHERE id = $1 RETURNING *",
                key_id, *values,
            )
        if not row:
            raise KeyError(f"API key {key_id} not found")
        self.invalidate()
        return _row_to_key(row)
 
    async def delete_api_key(self, key_id: int) -> None:
        async with get_ai_conn() as conn:
            await conn.execute("DELETE FROM llm_api_keys WHERE id = $1", key_id)
        self.invalidate()
 
    # ── Task bindings (with cache) ───────────────────────────────────────────
    async def list_bindings(self, task_code: Optional[str] = None) -> list[TaskBinding]:
        q = """
        SELECT b.*,
               m.provider_id, m.model_name, m.display_name AS m_display, m.family,
               m.context_window, m.supports_json, m.supports_tools,
               m.supports_streaming, m.supports_vision,
               m.input_cost_per_1k, m.output_cost_per_1k,
               m.default_temperature, m.default_max_tokens,
               m.enabled AS m_enabled, m.config AS m_config,
               p.code AS provider_code, p.adapter_type, p.base_url AS provider_base_url,
               p.enabled AS p_enabled
        FROM task_model_bindings b
        JOIN llm_models m ON m.id = b.model_id
        JOIN llm_providers p ON p.id = m.provider_id
        """
        args: list[Any] = []
        if task_code:
            q += " WHERE b.task_code = $1"
            args.append(task_code)
        q += " ORDER BY b.task_code, b.priority, b.id"
        async with get_ai_conn() as conn:
            rows = await conn.fetch(q, *args)
        return [_row_to_binding(r) for r in rows]
 
    async def get_binding_chain(self, task_code: str) -> list[TaskBinding]:
        """Return the ordered, currently-usable fallback chain for a task.
 
        Cached in-process for CACHE_TTL_SECONDS. Rows where the model, provider
        or binding itself is disabled are filtered out. If any binding is
        `pinned`, the chain is collapsed to just the pinned rows.
        """
        now = time.monotonic()
        cached = self._bindings_cache.get(task_code)
        if cached and cached[0] > now:
            return cached[1]
 
        rows = await self.list_bindings(task_code)
        usable = [
            b for b in rows
            if b.enabled and b.model.enabled
        ]
        pinned = [b for b in usable if b.pinned]
        chain = pinned if pinned else usable
        self._bindings_cache[task_code] = (now + CACHE_TTL_SECONDS, chain)
        return chain
 
    async def upsert_binding(
        self,
        *,
        task_code: str,
        model_id: int,
        priority: int = 100,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        pinned: bool = False,
        enabled: bool = True,
        notes: Optional[str] = None,
    ) -> TaskBinding:
        async with get_ai_conn() as conn:
            await conn.execute(
                """
                INSERT INTO task_model_bindings
                  (task_code, model_id, priority, temperature, max_tokens,
                   json_mode, pinned, enabled, notes)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (task_code, model_id) DO UPDATE SET
                  priority    = EXCLUDED.priority,
                  temperature = EXCLUDED.temperature,
                  max_tokens  = EXCLUDED.max_tokens,
                  json_mode   = EXCLUDED.json_mode,
                  pinned      = EXCLUDED.pinned,
                  enabled     = EXCLUDED.enabled,
                  notes       = EXCLUDED.notes
                """,
                task_code, model_id, priority, temperature, max_tokens,
                json_mode, pinned, enabled, notes,
            )
        self.invalidate()
        rows = await self.list_bindings(task_code)
        for b in rows:
            if b.model.id == model_id:
                return b
        raise RuntimeError("upsert_binding: row missing after write")
 
    async def update_binding(self, binding_id: int, **fields: Any) -> TaskBinding:
        allowed = {"priority", "temperature", "max_tokens", "json_mode", "pinned", "enabled", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            # No-op; caller will fetch fresh state.
            rows = await self.list_bindings()
            for b in rows:
                if b.id == binding_id:
                    return b
            raise KeyError(f"Binding {binding_id} not found")
        set_clause, values = _build_update(updates, start=2)
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                f"UPDATE task_model_bindings SET {set_clause} WHERE id = $1 RETURNING task_code",
                binding_id, *values,
            )
        if not row:
            raise KeyError(f"Binding {binding_id} not found")
        self.invalidate()
        for b in await self.list_bindings(row["task_code"]):
            if b.id == binding_id:
                return b
        raise RuntimeError("update_binding: row missing after write")
 
    async def delete_binding(self, binding_id: int) -> None:
        async with get_ai_conn() as conn:
            await conn.execute("DELETE FROM task_model_bindings WHERE id = $1", binding_id)
        self.invalidate()
 
    # ── Misc ─────────────────────────────────────────────────────────────────
    @staticmethod
    def known_task_codes() -> tuple[str, ...]:
        return ALL_TASK_CODES
 
 
# ── Row mappers ─────────────────────────────────────────────────────────────
def _row_to_provider(row: Any) -> Provider:
    return Provider(
        id=row["id"],
        code=row["code"],
        display_name=row["display_name"],
        adapter_type=row["adapter_type"],
        base_url=row.get("base_url") if isinstance(row, dict) else row["base_url"],
        enabled=row["enabled"],
        config=_load_json(row["config"]),
    )
 
 
def _row_to_model(row: Any) -> Model:
    def g(k: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(k, default)
        try:
            return row[k]
        except (KeyError, IndexError):
            return default
 
    # The `m_display` / `m_config` aliases appear only in the bindings join.
    display = g("display_name") if "display_name" in _keys(row) else g("m_display")
    config = g("config") if "config" in _keys(row) else g("m_config")
    enabled = g("enabled") if "enabled" in _keys(row) else g("m_enabled")
 
    return Model(
        id=g("id") if "id" in _keys(row) else g("model_id"),
        provider_id=g("provider_id"),
        provider_code=g("provider_code"),
        adapter_type=g("adapter_type"),
        base_url=g("provider_base_url") or g("base_url"),
        model_name=g("model_name"),
        display_name=display,
        family=g("family"),
        context_window=g("context_window", 8192),
        supports_json=bool(g("supports_json", True)),
        supports_tools=bool(g("supports_tools", False)),
        supports_streaming=bool(g("supports_streaming", True)),
        supports_vision=bool(g("supports_vision", False)),
        input_cost_per_1k=float(g("input_cost_per_1k", 0) or 0),
        output_cost_per_1k=float(g("output_cost_per_1k", 0) or 0),
        default_temperature=float(g("default_temperature", 0.3) or 0.3),
        default_max_tokens=int(g("default_max_tokens", 1024) or 1024),
        enabled=bool(enabled),
        config=_load_json(config),
    )
 
 
def _row_to_key(row: Any) -> ApiKey:
    return ApiKey(
        id=row["id"],
        provider_id=row["provider_id"],
        alias=row["alias"],
        encrypted_key=row["encrypted_key"],
        fingerprint=row["key_fingerprint"],
        status=row["status"],
        rpm_limit=row["rpm_limit"],
        tpm_limit=row["tpm_limit"],
        daily_token_limit=row["daily_token_limit"],
        used_today_requests=row["used_today_requests"],
        used_today_tokens=row["used_today_tokens"],
        cooldown_until=row["cooldown_until"],
        consecutive_failures=row["consecutive_failures"],
    )
 
 
def _row_to_binding(row: Any) -> TaskBinding:
    model = _row_to_model({
        "id": row["model_id"],
        "provider_id": row["provider_id"],
        "provider_code": row["provider_code"],
        "adapter_type": row["adapter_type"],
        "provider_base_url": row["provider_base_url"],
        "model_name": row["model_name"],
        "m_display": row["m_display"],
        "family": row["family"],
        "context_window": row["context_window"],
        "supports_json": row["supports_json"],
        "supports_tools": row["supports_tools"],
        "supports_streaming": row["supports_streaming"],
        "supports_vision": row["supports_vision"],
        "input_cost_per_1k": row["input_cost_per_1k"],
        "output_cost_per_1k": row["output_cost_per_1k"],
        "default_temperature": row["default_temperature"],
        "default_max_tokens": row["default_max_tokens"],
        "m_enabled": row["m_enabled"],
        "m_config": row["m_config"],
    })
    return TaskBinding(
        id=row["id"],
        task_code=row["task_code"],
        model=model,
        priority=row["priority"],
        temperature=float(row["temperature"]) if row["temperature"] is not None else None,
        max_tokens=int(row["max_tokens"]) if row["max_tokens"] is not None else None,
        json_mode=bool(row["json_mode"]),
        pinned=bool(row["pinned"]),
        enabled=bool(row["enabled"]) and bool(row["p_enabled"]),
    )
 
 
# ── helpers ─────────────────────────────────────────────────────────────────
def _keys(row: Any) -> list[str]:
    if isinstance(row, dict):
        return list(row.keys())
    try:
        return list(row.keys())
    except Exception:
        return []
 
 
def _build_update(updates: dict[str, Any], *, start: int) -> tuple[str, list[Any]]:
    pieces, values = [], []
    for i, (col, val) in enumerate(updates.items(), start=start):
        # JSONB columns need an explicit ::jsonb cast.
        if col == "config":
            pieces.append(f"{col} = ${i}::jsonb")
            values.append(_json(val))
        else:
            pieces.append(f"{col} = ${i}")
            values.append(val)
    return ", ".join(pieces), values
 
 
def _json(obj: Any) -> str:
    import json as _jsonlib
    return _jsonlib.dumps(obj or {})
 
 
def _load_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value if isinstance(value, dict) else {"value": value}
    import json as _jsonlib
    try:
        return _jsonlib.loads(value)
    except Exception:
        return {}
 
 
# ── Singleton ───────────────────────────────────────────────────────────────
_registry: Optional[ModelRegistry] = None
 
 
def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry