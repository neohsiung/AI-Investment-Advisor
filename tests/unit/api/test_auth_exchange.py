"""
Unit tests for the OAuth exchange-code flow (src/api/v1/endpoints/auth.py).

2026-07-12: OAuth callback tokens no longer travel in the redirect URL
query string (browser history / access logs / Referer leakage). A
short-lived single-use opaque code does instead; the frontend POSTs it to
/auth/exchange to redeem the real tokens in a JSON response body.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _import_auth_module():
    """
    auth.py <-> router.py have a pre-existing circular import (auth.py
    imports oauth2_scheme/get_current_user_id from router.py; router.py
    imports auth.router back). Importing auth.py directly as the FIRST
    touch of that chain in a process breaks with a partial-init
    AttributeError. Importing router.py first resolves it the same way
    the full app's natural boot order does (also reads a Google
    client_secret.json at import time — falls back to client_id=None if
    absent, importable in a bare test env).
    """
    import src.api.v1.router  # noqa: F401 - establishes safe import order
    import src.api.v1.endpoints.auth as auth
    return auth


class TestStoreExchangeCode:
    def test_stores_tokens_and_returns_opaque_code(self):
        auth = _import_auth_module()
        mock_redis = MagicMock()
        with patch.object(auth, "_get_redis", return_value=mock_redis):
            code = auth._store_exchange_code("access-tok", "refresh-tok")

        assert isinstance(code, str)
        assert len(code) > 20  # secrets.token_urlsafe(32) is not short
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert args[0] == f"{auth._EXCHANGE_PREFIX}{code}"
        stored = json.loads(args[1])
        assert stored == {"access_token": "access-tok", "refresh_token": "refresh-tok"}
        assert kwargs["ex"] == auth._EXCHANGE_TTL_SECONDS


class TestExchangeEndpoint:
    def _request_with_body(self, body: dict):
        from fastapi import Request
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/exchange",
            "headers": [
                (b"host", b"localhost"),
                (b"content-type", b"application/json")
            ],
            "client": ("127.0.0.1", 12345),
        }
        req = Request(scope)

        async def _json():
            return body
        req.json = _json
        return req

    @pytest.mark.asyncio
    async def test_valid_code_returns_tokens_and_deletes_key(self):
        auth = _import_auth_module()
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({
            "access_token": "a", "refresh_token": "r",
        })
        with patch.object(auth, "_get_redis", return_value=mock_redis):
            result = await auth.exchange_code(self._request_with_body({"code": "abc123"}))

        assert result == {"access_token": "a", "refresh_token": "r"}
        mock_redis.delete.assert_called_once_with(f"{auth._EXCHANGE_PREFIX}abc123")

    @pytest.mark.asyncio
    async def test_missing_code_400(self):
        auth = _import_auth_module()
        with pytest.raises(HTTPException) as exc_info:
            await auth.exchange_code(self._request_with_body({}))
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_expired_or_replayed_code_400(self):
        auth = _import_auth_module()
        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # expired / already consumed
        with patch.object(auth, "_get_redis", return_value=mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                await auth.exchange_code(self._request_with_body({"code": "stale"}))
        assert exc_info.value.status_code == 400
        mock_redis.delete.assert_not_called()
