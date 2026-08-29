"""
tests/test_mcp/test_auth.py

Unit tests for MCP API key authentication and rate limiting.

Tests:
  - Valid API key resolves to correct user_id
  - Missing Authorization header → 401
  - Invalid key → 401
  - Wrong scheme (Basic instead of Bearer) → 401
  - MCP disabled → 403
  - No keys configured → 403
  - Rate limiting: exceeding RPM limit → 429
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


# ── Fixtures ────────────────────────────────────────────────────────────────

VALID_KEY = "bdc_mcp_testkey123"
VALID_USER_ID = 42
ANOTHER_KEY = "bdc_mcp_anotherkey"
ANOTHER_USER_ID = 7

TEST_KEY_MAP = {
    VALID_KEY: VALID_USER_ID,
    ANOTHER_KEY: ANOTHER_USER_ID,
}


def _make_settings(
    mcp_enabled: bool = True,
    mcp_api_keys: str = f"{VALID_KEY}:{VALID_USER_ID},{ANOTHER_KEY}:{ANOTHER_USER_ID}",
    mcp_rate_limit_rpm: int = 100,
):
    """Return a mock settings object."""
    s = MagicMock()
    s.mcp_enabled = mcp_enabled
    s.mcp_api_keys = mcp_api_keys
    s.mcp_rate_limit_rpm = mcp_rate_limit_rpm
    return s


# ── _parse_api_keys ──────────────────────────────────────────────────────────

def test_parse_api_keys_valid():
    """Parse a valid MCP_API_KEYS string."""
    from mcp.auth import _parse_api_keys
    with patch("mcp.auth.settings", _make_settings()):
        result = _parse_api_keys()
    assert result == TEST_KEY_MAP


def test_parse_api_keys_empty():
    """Empty string returns empty dict."""
    from mcp.auth import _parse_api_keys
    with patch("mcp.auth.settings", _make_settings(mcp_api_keys="")):
        result = _parse_api_keys()
    assert result == {}


def test_parse_api_keys_skips_malformed():
    """Malformed pairs are skipped, valid ones are kept."""
    from mcp.auth import _parse_api_keys
    with patch("mcp.auth.settings", _make_settings(mcp_api_keys=f"no_colon,{VALID_KEY}:{VALID_USER_ID}")):
        result = _parse_api_keys()
    assert result == {VALID_KEY: VALID_USER_ID}


def test_parse_api_keys_skips_non_integer_uid():
    """Non-integer user_id is skipped."""
    from mcp.auth import _parse_api_keys
    with patch("mcp.auth.settings", _make_settings(mcp_api_keys="bdc_mcp_bad:not_a_number")):
        result = _parse_api_keys()
    assert result == {}


# ── _extract_bearer ──────────────────────────────────────────────────────────

def test_extract_bearer_valid():
    from mcp.auth import _extract_bearer
    assert _extract_bearer(f"Bearer {VALID_KEY}") == VALID_KEY


def test_extract_bearer_none():
    from mcp.auth import _extract_bearer
    assert _extract_bearer(None) is None


def test_extract_bearer_empty():
    from mcp.auth import _extract_bearer
    assert _extract_bearer("") is None


def test_extract_bearer_wrong_scheme():
    from mcp.auth import _extract_bearer
    assert _extract_bearer(f"Basic {VALID_KEY}") is None


def test_extract_bearer_no_token():
    from mcp.auth import _extract_bearer
    assert _extract_bearer("Bearer ") is None


def test_token_hash_does_not_contain_secret():
    from mcp.auth import _token_hash
    digest = _token_hash(VALID_KEY)
    assert len(digest) == 64
    assert VALID_KEY not in digest


# ── get_mcp_user_id ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_mcp_user_id_success():
    """Valid key returns the mapped user_id."""
    from mcp import auth as auth_module
    with (
        patch.object(auth_module, "settings", _make_settings()),
        patch.object(auth_module, "_get_key_map", return_value=TEST_KEY_MAP),
        patch.object(auth_module, "_check_rate_limit", new=AsyncMock()),
    ):
        result = await auth_module.get_mcp_user_id(
            authorization=f"Bearer {VALID_KEY}"
        )
    assert result == VALID_USER_ID


@pytest.mark.asyncio
async def test_get_mcp_user_id_missing_header():
    """No Authorization header → HTTP 401."""
    from mcp import auth as auth_module
    with (
        patch.object(auth_module, "settings", _make_settings()),
        patch.object(auth_module, "_get_key_map", return_value=TEST_KEY_MAP),
    ):
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_mcp_user_id(authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_mcp_user_id_invalid_key():
    """Unknown key → HTTP 401."""
    from mcp import auth as auth_module
    with (
        patch.object(auth_module, "settings", _make_settings()),
        patch.object(auth_module, "_get_key_map", return_value=TEST_KEY_MAP),
    ):
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_mcp_user_id(
                authorization="Bearer bdc_mcp_WRONG"
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_mcp_user_id_mcp_disabled():
    """MCP_ENABLED=false → HTTP 403."""
    from mcp import auth as auth_module
    with patch.object(auth_module, "settings", _make_settings(mcp_enabled=False)):
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_mcp_user_id(
                authorization=f"Bearer {VALID_KEY}"
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_mcp_user_id_no_keys_configured():
    """An unresolved key always returns HTTP 401 without revealing server config."""
    from mcp import auth as auth_module
    with (
        patch.object(auth_module, "settings", _make_settings()),
        patch.object(auth_module, "_get_key_map", return_value={}),
    ):
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_mcp_user_id(
                authorization=f"Bearer {VALID_KEY}"
            )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_mcp_user_id_rate_limited():
    """Rate limit exceeded → HTTP 429."""
    from mcp import auth as auth_module

    async def _raise_429(api_key: str):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    with (
        patch.object(auth_module, "settings", _make_settings()),
        patch.object(auth_module, "_get_key_map", return_value=TEST_KEY_MAP),
        patch.object(auth_module, "_check_rate_limit", side_effect=_raise_429),
    ):
        with pytest.raises(HTTPException) as exc:
            await auth_module.get_mcp_user_id(
                authorization=f"Bearer {VALID_KEY}"
            )
    assert exc.value.status_code == 429
