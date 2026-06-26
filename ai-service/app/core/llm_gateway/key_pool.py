"""
KeyPool - picks an API key to use for a provider and maintains its health.
 
Strategy
--------
* `lease(provider_id)` returns the least-loaded *active* key whose cooldown has
  expired and whose daily quota hasn't been exceeded. If none are available it
  raises NoKeyAvailableError - the gateway then moves to the next model in the
  fallback chain.
 
* `record_success(key_id, tokens)` / `record_failure(key_id, kind, …)` update
  the key's counters atomically in the DB. Rate-limit errors trigger an
  exponential cooldown; auth errors mark the key `invalid` so the admin is
  alerted.
 
* All state is in Postgres - no Redis dependency is introduced in Phase 1 so
  the pool "just works" across worker processes. Counters are rolled over
  daily via `used_window_start`.
"""
from __future__ import annotations
 
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
 
from app.core.database import get_ai_conn
from app.core.llm_gateway.crypto import decrypt
from app.core.llm_gateway.errors import NoKeyAvailableError
from app.core.llm_gateway.types import ApiKey
 
logger = logging.getLogger(__name__)
 
 
# Exponential cooldown caps at 5 minutes - long enough to let a minute-level
# rate limit reset, short enough that admins don't notice a false positive.
_COOLDOWN_BASE_SECONDS = 15
_COOLDOWN_MAX_SECONDS = 300
_AUTH_FAILURES_BEFORE_INVALID = 2
 
 
class LeasedKey:
    """Wraps an ApiKey with its decrypted plaintext. Kept in-memory only."""
 
    __slots__ = ("record", "plaintext")
 
    def __init__(self, record: ApiKey, plaintext: str) -> None:
        self.record = record
        self.plaintext = plaintext
 
    @property
    def id(self) -> int:
        return self.record.id
 
 
class KeyPool:
    async def lease(self, provider_id: int) -> LeasedKey:
        """Pick a key for this provider.
 
        Selection order:
          1. status = 'active'
          2. no cooldown or cooldown expired
          3. daily_token_limit not exceeded
          4. least-used today (tokens ASC, then requests ASC)
        """
        now = datetime.now(timezone.utc)
        window_cutoff = now - timedelta(hours=24)
        async with get_ai_conn() as conn:
            # Roll over daily counters first.
            await conn.execute(
                """
                UPDATE llm_api_keys
                SET used_today_requests = 0,
                    used_today_tokens   = 0,
                    used_window_start   = $1
                WHERE provider_id = $2 AND used_window_start < $3
                """,
                now, provider_id, window_cutoff,
            )
            # Auto-clear expired cooldowns.
            await conn.execute(
                """
                UPDATE llm_api_keys
                SET status = 'active', cooldown_until = NULL
                WHERE provider_id = $1
                  AND status = 'cooldown'
                  AND cooldown_until IS NOT NULL
                  AND cooldown_until <= $2
                """,
                provider_id, now,
            )
 
            row = await conn.fetchrow(
                """
                SELECT *
                FROM llm_api_keys
                WHERE provider_id = $1
                  AND status = 'active'
                  AND (cooldown_until IS NULL OR cooldown_until <= $2)
                  AND (daily_token_limit IS NULL OR used_today_tokens < daily_token_limit)
                ORDER BY used_today_tokens ASC, used_today_requests ASC, id ASC
                LIMIT 1
                """,
                provider_id, now,
            )
 
        if not row:
            raise NoKeyAvailableError(f"No active API key for provider_id={provider_id}")
 
        record = ApiKey(
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
        return LeasedKey(record=record, plaintext=decrypt(record.encrypted_key))
 
    async def record_success(self, key_id: int, tokens_used: int) -> None:
        async with get_ai_conn() as conn:
            await conn.execute(
                """
                UPDATE llm_api_keys
                SET used_today_requests = used_today_requests + 1,
                    used_today_tokens   = used_today_tokens + $2,
                    last_used_at        = NOW(),
                    consecutive_failures = 0,
                    last_error          = NULL
                WHERE id = $1
                """,
                key_id, max(0, int(tokens_used)),
            )
 
    async def record_rate_limit(
        self,
        key_id: int,
        *,
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        """Apply exponential cooldown and keep key in 'cooldown' status."""
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT consecutive_failures FROM llm_api_keys WHERE id = $1",
                key_id,
            )
            fails = (row["consecutive_failures"] if row else 0) + 1
 
            backoff = _COOLDOWN_BASE_SECONDS * (2 ** min(fails, 5))
            if retry_after_seconds and retry_after_seconds > backoff:
                backoff = retry_after_seconds
            backoff = min(backoff, _COOLDOWN_MAX_SECONDS)
 
            cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=backoff)
            await conn.execute(
                """
                UPDATE llm_api_keys
                SET status               = 'cooldown',
                    cooldown_until       = $2,
                    consecutive_failures = $3,
                    last_used_at         = NOW(),
                    last_error           = $4
                WHERE id = $1
                """,
                key_id, cooldown_until, fails,
                f"rate_limited (retry in {int(backoff)}s)",
            )
        logger.warning(
            "API key %d rate-limited; cooling down for %ss (attempt %d)",
            key_id, int(backoff), fails,
        )
 
    async def record_auth_failure(self, key_id: int, message: str) -> None:
        """Escalate to 'invalid' after a couple of auth errors."""
        async with get_ai_conn() as conn:
            row = await conn.fetchrow(
                "SELECT consecutive_failures FROM llm_api_keys WHERE id = $1",
                key_id,
            )
            fails = (row["consecutive_failures"] if row else 0) + 1
            new_status = "invalid" if fails >= _AUTH_FAILURES_BEFORE_INVALID else "cooldown"
            cooldown = (
                None if new_status == "invalid"
                else datetime.now(timezone.utc) + timedelta(seconds=60)
            )
            await conn.execute(
                """
                UPDATE llm_api_keys
                SET status               = $2,
                    consecutive_failures = $3,
                    cooldown_until       = $4,
                    last_error           = $5,
                    last_used_at         = NOW()
                WHERE id = $1
                """,
                key_id, new_status, fails, cooldown, message[:500],
            )
        logger.error("API key %d auth failure (%d total) -> %s", key_id, fails, new_status)
 
    async def record_generic_failure(self, key_id: int, message: str) -> None:
        async with get_ai_conn() as conn:
            await conn.execute(
                """
                UPDATE llm_api_keys
                SET consecutive_failures = consecutive_failures + 1,
                    last_error           = $2,
                    last_used_at         = NOW()
                WHERE id = $1
                """,
                key_id, message[:500],
            )
 
 
_pool: Optional[KeyPool] = None
 
 
def get_key_pool() -> KeyPool:
    global _pool
    if _pool is None:
        _pool = KeyPool()
    return _pool