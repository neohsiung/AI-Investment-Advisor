"""
Unit tests for the WebhookService inbound handlers.
WebhookService 入站處理器單元測試。

Covers the dedup/lock gate that every inbound event passes through, plus the
three source handlers. What makes these worth asserting rather than assuming:

- `_is_duplicate` and `_acquire_concurrency_lock` both fail OPEN — an infra
  hiccup lets an event through rather than dropping it. That is the right
  trade-off for a webhook, but it means a silent regression to fail-closed
  would quietly stop ingesting, so both directions are pinned here.
- Finnhub must answer 200 even on a bad secret; a 4xx makes Finnhub disable
  the endpoint outright. Stripe is the opposite — a bad signature must be 400.
  Getting these backwards breaks the integration in a way no test of the happy
  path would catch.

`_is_duplicate` 與 `_acquire_concurrency_lock` 都是 fail-open：基礎設施出問題時
放行而非丟棄事件。對 webhook 而言這是對的取捨，但若無聲退化成 fail-closed 就會
默默停止收件，所以兩個方向都釘住。Finnhub 密鑰錯誤必須回 200（回 4xx 會讓
Finnhub 直接停用端點），Stripe 簽章錯誤則必須回 400 —— 兩者相反，寫反了只測
happy path 抓不到。
"""
import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services.webhook_service import WebhookService

USER_ID = "11111111-2222-4333-8444-555555555555"


@pytest.fixture
def svc():
    """A WebhookService with Redis stubbed out (constructor would dial a real one)."""
    with patch("redis.from_url", return_value=MagicMock()):
        service = WebhookService(settings_service=MagicMock())
    service._redis = MagicMock()
    return service


def _request(payload=None, headers=None, body=b"", raises=False):
    req = MagicMock()
    req.headers = headers or {}
    req.body = AsyncMock(return_value=body)
    if raises:
        req.json = AsyncMock(side_effect=ValueError("bad json"))
    else:
        req.json = AsyncMock(return_value=payload)
    return req


def _engine(first_result):
    """Stub engine whose single query returns `first_result` from .first()."""
    conn = MagicMock()
    conn.execute.return_value.first.return_value = first_result
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine, conn


class TestIsDuplicate:
    def test_no_url_and_no_signal_id_short_circuits(self, svc):
        """Nothing to match on — must not touch the database at all."""
        with patch("src.data.database.get_db_engine") as mock_engine:
            assert svc._is_duplicate(USER_ID) is False
        mock_engine.assert_not_called()

    def test_existing_row_is_a_duplicate(self, svc):
        engine, _ = _engine((1,))
        with patch("src.data.database.get_db_engine", return_value=engine):
            assert svc._is_duplicate(USER_ID, url="http://x/1") is True

    def test_no_row_is_not_a_duplicate(self, svc):
        engine, _ = _engine(None)
        with patch("src.data.database.get_db_engine", return_value=engine):
            assert svc._is_duplicate(USER_ID, url="http://x/1") is False

    def test_url_query_binds_url_and_like_pattern(self, svc):
        engine, conn = _engine(None)
        with patch("src.data.database.get_db_engine", return_value=engine):
            svc._is_duplicate(USER_ID, url="http://x/1")
        sql, params = conn.execute.call_args.args
        assert params == {"uid": USER_ID, "url": "http://x/1",
                          "url_pattern": "%http://x/1%"}
        # Every value is bound, never interpolated.
        assert "http://x/1" not in str(sql)

    def test_signal_id_only_binds_signal_id(self, svc):
        engine, conn = _engine(None)
        with patch("src.data.database.get_db_engine", return_value=engine):
            svc._is_duplicate(USER_ID, signal_id="sig-1")
        _, params = conn.execute.call_args.args
        assert params == {"uid": USER_ID, "signal_id": "sig-1"}

    def test_both_criteria_are_combined(self, svc):
        engine, conn = _engine(None)
        with patch("src.data.database.get_db_engine", return_value=engine):
            svc._is_duplicate(USER_ID, url="http://x/1", signal_id="sig-1")
        _, params = conn.execute.call_args.args
        assert set(params) == {"uid", "url", "url_pattern", "signal_id"}

    def test_database_failure_fails_open(self, svc):
        """A DB outage must not silently drop every inbound event."""
        with patch("src.data.database.get_db_engine", side_effect=RuntimeError("db down")):
            assert svc._is_duplicate(USER_ID, url="http://x/1") is False


class TestAcquireConcurrencyLock:
    def test_no_redis_permits(self, svc):
        svc._redis = None
        assert svc._acquire_concurrency_lock(USER_ID, url="http://x/1") is True

    def test_no_key_material_permits(self, svc):
        assert svc._acquire_concurrency_lock(USER_ID) is True

    def test_setnx_success_permits(self, svc):
        svc._redis.set.return_value = True
        assert svc._acquire_concurrency_lock(USER_ID, url="http://x/1") is True

    def test_setnx_contention_blocks(self, svc):
        svc._redis.set.return_value = None
        assert svc._acquire_concurrency_lock(USER_ID, url="http://x/1") is False

    def test_lock_key_is_hashed_and_expires(self, svc):
        svc._redis.set.return_value = True
        url = "http://x/1"
        svc._acquire_concurrency_lock(USER_ID, url=url)
        key = svc._redis.set.call_args.args[0]
        digest = hashlib.sha256(url.encode()).hexdigest()
        assert key == f"lock:webhook:{USER_ID}:{digest}"
        # The URL itself never becomes part of the key.
        assert url not in key
        assert svc._redis.set.call_args.kwargs == {"ex": 15, "nx": True}

    def test_url_takes_precedence_over_signal_id(self, svc):
        svc._redis.set.return_value = True
        svc._acquire_concurrency_lock(USER_ID, url="http://x/1", signal_id="sig")
        expected = hashlib.sha256(b"http://x/1").hexdigest()
        assert svc._redis.set.call_args.args[0].endswith(expected)

    def test_redis_failure_fails_open(self, svc):
        svc._redis.set.side_effect = RuntimeError("redis down")
        assert svc._acquire_concurrency_lock(USER_ID, url="http://x/1") is True


class TestHandleGenericWebhook:
    async def test_accepted_event_starts_the_analysis_workflow(self, svc):
        svc._resolve_user = AsyncMock(return_value=USER_ID)
        svc._is_duplicate = MagicMock(return_value=False)
        svc._acquire_concurrency_lock = MagicMock(return_value=True)
        wf = MagicMock()
        wf.run = AsyncMock()

        with patch("src.services.workflow_service.EventAnalysisWorkflow", return_value=wf) as MockWf:
            result = await svc.handle_generic_webhook(
                "tradingview", _request({"ticker": "AAPL", "signal": "BUY"}))
            await asyncio.sleep(0)

        assert result == {"status": "accepted", "user_id": USER_ID, "source": "tradingview"}
        assert MockWf.call_args.kwargs["event_data"]["type"] == "TECHNICAL_SIGNAL"

    async def test_duplicate_is_skipped_before_the_lock(self, svc):
        svc._resolve_user = AsyncMock(return_value=USER_ID)
        svc._is_duplicate = MagicMock(return_value=True)
        svc._acquire_concurrency_lock = MagicMock(return_value=True)

        result = await svc.handle_generic_webhook("n8n", _request({"link": "http://x/1"}))

        assert result["status"] == "skipped"
        assert result["reason"] == "duplicate"
        svc._acquire_concurrency_lock.assert_not_called()

    async def test_lock_contention_is_skipped(self, svc):
        svc._resolve_user = AsyncMock(return_value=USER_ID)
        svc._is_duplicate = MagicMock(return_value=False)
        svc._acquire_concurrency_lock = MagicMock(return_value=False)

        result = await svc.handle_generic_webhook("n8n", _request({"link": "http://x/1"}))

        assert result["reason"] == "concurrent_lock"

    @pytest.mark.parametrize("source", ["skill-learning", "skill_learning"])
    async def test_skill_learning_routes_to_its_own_service(self, svc, source):
        svc._resolve_user = AsyncMock(return_value=USER_ID)
        svc._is_duplicate = MagicMock(return_value=False)
        svc._acquire_concurrency_lock = MagicMock(return_value=True)
        learner = MagicMock()
        learner.run_daily_learning = AsyncMock()

        with patch("src.services.investment_skill_learning_service.InvestmentSkillLearningService",
                   return_value=learner), \
             patch("src.services.workflow_service.EventAnalysisWorkflow") as MockWf:
            result = await svc.handle_generic_webhook(
                source, _request({"content": "text", "source_url": "http://a"}))
            await asyncio.sleep(0)

        assert result["workflow"] == "skill_learning"
        MockWf.assert_not_called()
        learner.run_daily_learning.assert_awaited_once()

    async def test_unknown_source_uses_the_base_parser(self, svc):
        svc._resolve_user = AsyncMock(return_value=USER_ID)
        svc._is_duplicate = MagicMock(return_value=False)
        svc._acquire_concurrency_lock = MagicMock(return_value=True)
        wf = MagicMock()
        wf.run = AsyncMock()

        with patch("src.services.workflow_service.EventAnalysisWorkflow", return_value=wf) as MockWf:
            await svc.handle_generic_webhook("unheard-of", _request({"raw": 1}))
            await asyncio.sleep(0)

        assert MockWf.call_args.kwargs["event_data"] == {"raw": 1}

    async def test_bad_payload_is_a_400(self, svc):
        svc._resolve_user = AsyncMock(return_value=USER_ID)
        with pytest.raises(HTTPException) as exc:
            await svc.handle_generic_webhook("n8n", _request(raises=True))
        assert exc.value.status_code == 400


class TestHandleFinnhubWebhook:
    @staticmethod
    def _patch_secret(secret):
        svc_mock = MagicMock()
        svc_mock.get_setting.return_value = secret
        return patch("src.services.settings_service.SettingsService", return_value=svc_mock)

    @pytest.mark.parametrize("received,expected", [
        (None, "right"),        # header absent
        ("wrong", "right"),     # mismatch
        ("right", ""),          # nothing configured
    ])
    async def test_bad_secret_acknowledges_with_200(self, svc, received, expected, monkeypatch):
        """
        Never 4xx here: Finnhub disables an endpoint that rejects, so a
        misconfiguration would silently and permanently kill the integration.
        絕不能回 4xx —— Finnhub 會直接停用會拒絕的端點。
        """
        monkeypatch.setenv("DEFAULT_FINNHUB_USER_ID", USER_ID)
        monkeypatch.delenv("FINNHUB_WEBHOOK_SECRET", raising=False)
        headers = {"X-Finnhub-Secret": received} if received else {}
        with self._patch_secret(expected):
            result = await svc.handle_finnhub_webhook(_request({}, headers=headers))
        assert result == {"status": "acknowledged", "detail": "invalid_secret"}

    async def test_secret_falls_back_to_env_var(self, svc, monkeypatch):
        monkeypatch.setenv("DEFAULT_FINNHUB_USER_ID", USER_ID)
        monkeypatch.setenv("FINNHUB_WEBHOOK_SECRET", "from-env")
        svc._is_duplicate = MagicMock(return_value=False)
        svc._acquire_concurrency_lock = MagicMock(return_value=True)
        wf = MagicMock()
        wf.run = AsyncMock()

        with self._patch_secret(""), \
             patch("src.services.workflow_service.EventAnalysisWorkflow", return_value=wf):
            result = await svc.handle_finnhub_webhook(_request(
                {"event": "news", "data": {"headline": "H"}},
                headers={"X-Finnhub-Secret": "from-env"}))
            await asyncio.sleep(0)

        assert result == {"status": "accepted", "user_id": USER_ID}

    async def test_settings_lookup_failure_still_falls_back_to_env(self, svc, monkeypatch):
        monkeypatch.setenv("DEFAULT_FINNHUB_USER_ID", USER_ID)
        monkeypatch.setenv("FINNHUB_WEBHOOK_SECRET", "from-env")
        svc._is_duplicate = MagicMock(return_value=False)
        svc._acquire_concurrency_lock = MagicMock(return_value=True)
        wf = MagicMock()
        wf.run = AsyncMock()

        with patch("src.services.settings_service.SettingsService",
                   side_effect=RuntimeError("settings down")), \
             patch("src.services.workflow_service.EventAnalysisWorkflow", return_value=wf):
            result = await svc.handle_finnhub_webhook(_request(
                {"event": "news", "data": {}},
                headers={"X-Finnhub-Secret": "from-env"}))
            await asyncio.sleep(0)

        assert result["status"] == "accepted"

    async def test_duplicate_is_skipped(self, svc, monkeypatch):
        monkeypatch.setenv("DEFAULT_FINNHUB_USER_ID", USER_ID)
        svc._is_duplicate = MagicMock(return_value=True)
        with self._patch_secret("s"):
            result = await svc.handle_finnhub_webhook(_request(
                {"event": "news", "data": {"url": "http://n/1"}},
                headers={"X-Finnhub-Secret": "s"}))
        assert result["reason"] == "duplicate"

    async def test_lock_contention_is_skipped(self, svc, monkeypatch):
        monkeypatch.setenv("DEFAULT_FINNHUB_USER_ID", USER_ID)
        svc._is_duplicate = MagicMock(return_value=False)
        svc._acquire_concurrency_lock = MagicMock(return_value=False)
        with self._patch_secret("s"):
            result = await svc.handle_finnhub_webhook(_request(
                {"event": "news", "data": {}}, headers={"X-Finnhub-Secret": "s"}))
        assert result["reason"] == "concurrent_lock"

    async def test_processing_error_still_acknowledges(self, svc, monkeypatch):
        monkeypatch.setenv("DEFAULT_FINNHUB_USER_ID", USER_ID)
        with self._patch_secret("s"):
            result = await svc.handle_finnhub_webhook(
                _request(raises=True, headers={"X-Finnhub-Secret": "s"}))
        assert result == {"status": "acknowledged", "detail": "processing_error"}


class TestHandleStripeWebhook:
    @staticmethod
    def _patch_secret(secret):
        svc_mock = MagicMock()
        svc_mock.get_setting.return_value = secret
        return patch("src.services.webhook_service.SettingsService", return_value=svc_mock)

    async def test_unconfigured_secret_is_503(self, svc, monkeypatch):
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        with self._patch_secret(""):
            with pytest.raises(HTTPException) as exc:
                await svc.handle_stripe_webhook(_request())
        assert exc.value.status_code == 503

    async def test_bad_signature_is_400(self, svc, monkeypatch):
        """
        Unlike Finnhub, Stripe's own guidance is to reject — and Stripe retries
        rather than disabling, so 400 is safe here.
        與 Finnhub 相反：Stripe 官方建議直接拒絕，且它會重試而非停用端點。
        """
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        with self._patch_secret("whsec"), \
             patch.object(stripe.Webhook, "construct_event",
                          side_effect=stripe.error.SignatureVerificationError("bad", "sig")):
            with pytest.raises(HTTPException) as exc:
                await svc.handle_stripe_webhook(_request(headers={"Stripe-Signature": "x"}))
        assert exc.value.status_code == 400

    async def test_other_event_types_are_ignored(self, svc, monkeypatch):
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        with self._patch_secret("whsec"), \
             patch.object(stripe.Webhook, "construct_event",
                          return_value={"type": "invoice.paid"}):
            result = await svc.handle_stripe_webhook(_request())
        assert result == {"status": "ignored", "event_type": "invoice.paid"}

    @staticmethod
    def _completed(email=None, customer_email=None, name=None):
        details = {}
        if email:
            details["email"] = email
        if name:
            details["name"] = name
        session = {"customer_details": details}
        if customer_email:
            session["customer_email"] = customer_email
        return {"type": "checkout.session.completed", "data": {"object": session}}

    async def test_missing_email_is_acknowledged(self, svc, monkeypatch):
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        with self._patch_secret("whsec"), \
             patch.object(stripe.Webhook, "construct_event", return_value=self._completed()):
            result = await svc.handle_stripe_webhook(_request())
        assert result == {"status": "acknowledged", "detail": "no_email"}

    async def test_existing_user_is_reused_not_recreated(self, svc, monkeypatch):
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        repo = MagicMock()
        repo.get_by_identity.return_value = {"id": USER_ID}

        with self._patch_secret("whsec"), \
             patch.object(stripe.Webhook, "construct_event",
                          return_value=self._completed(email="a@b.c")), \
             patch("src.repositories.user_repository.AlchemyUserRepository", return_value=repo), \
             patch("src.services.notification_service.NotificationService"):
            result = await svc.handle_stripe_webhook(_request())
            await asyncio.sleep(0)

        assert result == {"status": "accepted", "user_id": USER_ID}
        repo.create_user.assert_not_called()

    async def test_new_user_is_created_and_settings_seeded(self, svc, monkeypatch):
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        repo = MagicMock()
        repo.get_by_identity.return_value = None
        repo.create_user.return_value = "new-user-id-0123456789"

        with self._patch_secret("whsec") as settings_cls, \
             patch.object(stripe.Webhook, "construct_event",
                          return_value=self._completed(email="a@b.c", name="Ada")), \
             patch("src.repositories.user_repository.AlchemyUserRepository", return_value=repo), \
             patch("src.services.notification_service.NotificationService"):
            result = await svc.handle_stripe_webhook(_request())
            await asyncio.sleep(0)

        repo.create_user.assert_called_once_with(email="a@b.c", name="Ada")
        assert result["user_id"] == "new-user-id-0123456789"
        # Default settings must be seeded for the new account, not the admin's.
        settings_cls.return_value.initialize_user_settings.assert_called_once_with(
            "new-user-id-0123456789")

    async def test_customer_email_is_used_when_details_email_absent(self, svc, monkeypatch):
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        repo = MagicMock()
        repo.get_by_identity.return_value = {"id": USER_ID}

        with self._patch_secret("whsec"), \
             patch.object(stripe.Webhook, "construct_event",
                          return_value=self._completed(customer_email="fallback@b.c")), \
             patch("src.repositories.user_repository.AlchemyUserRepository", return_value=repo), \
             patch("src.services.notification_service.NotificationService"):
            await svc.handle_stripe_webhook(_request())
            await asyncio.sleep(0)

        repo.get_by_identity.assert_called_once_with("email", "fallback@b.c")

    async def test_notification_failure_does_not_block_activation(self, svc, monkeypatch):
        """The subscription is already paid for — a failed welcome email must not undo it."""
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        repo = MagicMock()
        repo.get_by_identity.return_value = {"id": USER_ID}

        with self._patch_secret("whsec"), \
             patch.object(stripe.Webhook, "construct_event",
                          return_value=self._completed(email="a@b.c")), \
             patch("src.repositories.user_repository.AlchemyUserRepository", return_value=repo), \
             patch("src.services.notification_service.NotificationService.create_with_settings",
                   side_effect=RuntimeError("smtp down")):
            result = await svc.handle_stripe_webhook(_request())

        assert result == {"status": "accepted", "user_id": USER_ID}

    async def test_processing_error_acknowledges_to_stop_retry_storms(self, svc, monkeypatch):
        import stripe
        monkeypatch.setenv("DEFAULT_STRIPE_ADMIN_USER_ID", USER_ID)
        with self._patch_secret("whsec"), \
             patch.object(stripe.Webhook, "construct_event",
                          return_value=self._completed(email="a@b.c")), \
             patch("src.repositories.user_repository.AlchemyUserRepository",
                   side_effect=RuntimeError("db down")):
            result = await svc.handle_stripe_webhook(_request())
        assert result == {"status": "acknowledged", "detail": "processing_error"}
