"""
Unit tests for dashboard_router's auth gate, DI providers and health check.
dashboard_router 的認證閘門、DI 提供者與健康檢查單元測試。

`get_current_user` is the only thing standing between an unauthenticated
request and every dashboard endpoint — it is mounted at /api/dashboard by
services/mcp_server/src/app/__init__.py:639. The two token sources (header and
cookie) and the `type == "access"` check are each a way in if they regress, so
they are asserted individually rather than through one happy-path request.

`get_dashboard_service` re-derives the user id from the token on every call;
that is the multi-tenant isolation boundary, so the missing-`sub` branch
matters as much as the happy one.

get_current_user 是未認證請求與所有 dashboard 端點之間唯一的關卡；兩種 token
來源與 type=="access" 檢查各自都是破口，所以逐項斷言而非只測 happy path。
get_dashboard_service 每次都從 token 重新取 user id，那是多租戶隔離邊界。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services import dashboard_router as dr


def _request(auth_header=None, cookies=None):
    req = MagicMock()
    req.headers = {"Authorization": auth_header} if auth_header else {}
    req.cookies = cookies or {}
    return req


class TestGetCurrentUser:
    def test_bearer_header_is_accepted(self):
        payload = {"sub": "u1", "type": "access"}
        with patch.object(dr, "decode_token", return_value=payload) as decode:
            assert dr.get_current_user(_request(auth_header="Bearer tok-123")) == payload
        decode.assert_called_once_with("tok-123")

    def test_cookie_is_the_fallback(self):
        payload = {"sub": "u1", "type": "access"}
        with patch.object(dr, "decode_token", return_value=payload) as decode:
            assert dr.get_current_user(_request(cookies={"access_token": "cookie-tok"})) == payload
        decode.assert_called_once_with("cookie-tok")

    def test_header_takes_precedence_over_cookie(self):
        with patch.object(dr, "decode_token", return_value={"sub": "u1", "type": "access"}) as decode:
            dr.get_current_user(_request(auth_header="Bearer from-header",
                                         cookies={"access_token": "from-cookie"}))
        decode.assert_called_once_with("from-header")

    def test_no_token_is_401(self):
        with pytest.raises(HTTPException) as exc:
            dr.get_current_user(_request())
        assert exc.value.status_code == 401
        assert exc.value.detail == "Not authenticated"

    def test_non_bearer_header_is_ignored(self):
        """A Basic/other scheme must not be treated as a token."""
        with pytest.raises(HTTPException) as exc:
            dr.get_current_user(_request(auth_header="Basic abc123"))
        assert exc.value.status_code == 401

    def test_undecodable_token_is_401(self):
        with patch.object(dr, "decode_token", return_value=None):
            with pytest.raises(HTTPException) as exc:
                dr.get_current_user(_request(auth_header="Bearer bad"))
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid token"

    def test_refresh_token_is_rejected(self):
        """
        A refresh token decodes cleanly but must not authorize API calls —
        only type == "access" may pass.
        refresh token 解得開但不得放行，只有 type == "access" 可通過。
        """
        with patch.object(dr, "decode_token", return_value={"sub": "u1", "type": "refresh"}):
            with pytest.raises(HTTPException) as exc:
                dr.get_current_user(_request(auth_header="Bearer refresh-tok"))
        assert exc.value.status_code == 401

    def test_token_without_type_is_rejected(self):
        with patch.object(dr, "decode_token", return_value={"sub": "u1"}):
            with pytest.raises(HTTPException):
                dr.get_current_user(_request(auth_header="Bearer no-type"))


class TestDependencyProviders:
    def test_dashboard_service_is_bound_to_the_token_subject(self):
        with patch.object(dr, "DashboardService") as Svc:
            dr.get_dashboard_service({"sub": "user-42", "type": "access"})
        Svc.assert_called_once_with(user_id="user-42")

    def test_dashboard_service_without_sub_is_401(self):
        """No subject means no tenant to scope to — refuse rather than guess."""
        with pytest.raises(HTTPException) as exc:
            dr.get_dashboard_service({"type": "access"})
        assert exc.value.status_code == 401

    def test_performance_service_is_bound_to_the_token_subject(self):
        with patch.object(dr, "PerformanceService") as Svc:
            dr.get_performance_service({"sub": "user-42"})
        Svc.assert_called_once_with(user_id="user-42")

    def test_reports_repository_is_constructed(self):
        with patch.object(dr, "AsyncAlchemyReportRepository") as Repo:
            assert dr.get_reports_repository({"sub": "user-42"}) is Repo.return_value


class TestHealthCheck:
    @staticmethod
    def _engine(raises=False):
        engine = MagicMock()
        if raises:
            engine.connect.side_effect = RuntimeError("db unreachable")
            return engine
        conn = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        return engine

    @staticmethod
    def _celery(ping):
        app = MagicMock()
        if isinstance(ping, Exception):
            app.control.ping.side_effect = ping
        else:
            app.control.ping.return_value = ping
        return app

    async def test_all_components_up(self):
        with patch("src.data.database.get_db_engine", return_value=self._engine()), \
             patch("src.infrastructure.celery_app.app", self._celery([{"w1": {}}, {"w2": {}}])):
            health = await dr.health_check()
        assert health["status"] == "healthy"
        assert health["components"]["database"] == "ok"
        assert health["components"]["celery_workers"] == "active (2)"

    async def test_database_down_is_503(self):
        with patch("src.data.database.get_db_engine", return_value=self._engine(raises=True)), \
             patch("src.infrastructure.celery_app.app", self._celery([{"w1": {}}])):
            with pytest.raises(HTTPException) as exc:
                await dr.health_check()
        assert exc.value.status_code == 503
        assert exc.value.detail["status"] == "degraded"
        assert "db unreachable" in exc.value.detail["components"]["database"]

    async def test_no_workers_is_degraded(self):
        """An empty ping list means nothing is consuming the queue."""
        with patch("src.data.database.get_db_engine", return_value=self._engine()), \
             patch("src.infrastructure.celery_app.app", self._celery([])):
            with pytest.raises(HTTPException) as exc:
                await dr.health_check()
        assert exc.value.detail["components"]["celery_workers"] == "no active workers"

    async def test_broker_error_is_degraded(self):
        with patch("src.data.database.get_db_engine", return_value=self._engine()), \
             patch("src.infrastructure.celery_app.app",
                   self._celery(RuntimeError("broker unreachable"))):
            with pytest.raises(HTTPException) as exc:
                await dr.health_check()
        assert "broker unreachable" in exc.value.detail["components"]["celery_workers"]


class TestModelRouterAndGateway:
    """
    The lazy singletons in get_model_router_and_gateway are process-global, and
    the settings repo is cached PER USER — a bug that shared one repo across
    users would leak settings between tenants, so the per-user keying is
    asserted explicitly.
    這裡的 lazy singleton 是 process 全域的，而 settings repo 是「每個使用者一份」；
    若退化成共用一份就會造成跨租戶設定外洩，所以明確斷言 per-user 快取。
    """

    def setup_method(self):
        dr._model_router = None
        dr._gateway = None
        dr._settings_repo_cache = {}

    teardown_method = setup_method

    def test_router_and_gateway_are_created_once(self):
        with patch.object(dr, "SettingsAwareModelRouter") as Router, \
             patch.object(dr, "OpenRouterGateway") as Gateway, \
             patch.object(dr, "AlchemySettingsRepository"), \
             patch("src.data.database.get_db_engine"):
            first = dr.get_model_router_and_gateway("u1")
            second = dr.get_model_router_and_gateway("u1")

        assert first[0] is second[0] and first[1] is second[1]
        Router.assert_called_once()
        Gateway.assert_called_once()

    def test_settings_repo_is_cached_per_user(self):
        with patch.object(dr, "SettingsAwareModelRouter"), \
             patch.object(dr, "OpenRouterGateway"), \
             patch.object(dr, "AlchemySettingsRepository",
                          side_effect=lambda **kw: MagicMock()) as Repo, \
             patch("src.data.database.get_db_engine"):
            repo_a = dr.get_model_router_and_gateway("u1")[2]
            repo_b = dr.get_model_router_and_gateway("u2")[2]
            repo_a_again = dr.get_model_router_and_gateway("u1")[2]

        assert repo_a is not repo_b
        assert repo_a is repo_a_again
        assert Repo.call_count == 2


class TestCallAgentLlm:
    def setup_method(self):
        dr._model_router = None
        dr._gateway = None
        dr._settings_repo_cache = {}

    teardown_method = setup_method

    @staticmethod
    def _wire(model, chat_result):
        router = MagicMock()
        router.get_model.return_value = model
        gateway = MagicMock()
        if isinstance(chat_result, Exception):
            gateway.chat = AsyncMock(side_effect=chat_result)
        else:
            gateway.chat = AsyncMock(return_value=chat_result)
        return patch.object(dr, "get_model_router_and_gateway",
                            return_value=(router, gateway, MagicMock())), router, gateway

    async def test_routes_by_tier_and_returns_the_reply(self):
        patcher, router, gateway = self._wire("gpt-x", "分析結果")
        with patcher:
            out = await dr._call_agent_llm("u1", {"q": 1}, tier="advanced")
        assert out == "分析結果"
        router.get_model.assert_called_once_with("u1", "advanced")

    async def test_unroutable_tier_falls_back_to_a_default_model(self):
        patcher, router, gateway = self._wire(None, "ok")
        with patcher:
            await dr._call_agent_llm("u1", {})
        assert gateway.chat.call_args.args[1].model == "claude-3.5-sonnet"

    async def test_context_is_serialized_into_the_user_message(self):
        patcher, _, gateway = self._wire("m", "ok")
        with patcher:
            await dr._call_agent_llm("u1", {"ticker": "AAPL"})
        messages = gateway.chat.call_args.args[0]
        assert messages[0].role == "system"
        assert '"ticker": "AAPL"' in messages[1].content

    async def test_non_string_response_raises(self):
        """A dict slipping through here would be rendered to the user verbatim."""
        patcher, _, _ = self._wire("m", {"unexpected": "shape"})
        with patcher:
            with pytest.raises(ValueError):
                await dr._call_agent_llm("u1", {})

    async def test_gateway_failure_propagates(self):
        patcher, _, _ = self._wire("m", RuntimeError("upstream 500"))
        with patcher:
            with pytest.raises(RuntimeError):
                await dr._call_agent_llm("u1", {})
