from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def test_key_management_rejects_forged_user_header():
    from mcp import router
    fake_settings = MagicMock(ai_service_secret="real-service-secret")
    with patch.object(router, "settings", fake_settings):
        with pytest.raises(HTTPException) as exc:
            router._require_internal_identity(42, "attacker-controlled")
    assert exc.value.status_code == 401


def test_key_management_accepts_authenticated_bff():
    from mcp import router
    fake_settings = MagicMock(ai_service_secret="real-service-secret")
    with patch.object(router, "settings", fake_settings):
        assert router._require_internal_identity(42, "real-service-secret") == 42
