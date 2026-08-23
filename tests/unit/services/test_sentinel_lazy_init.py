"""
SentinelService construction cost — `__init__` must stay cheap.

Why (2026-08-13): `__init__` eagerly built eight services (MarketDataService
alone constructs Polygon, Tiingo, FMP, FRED, AlphaVantage, Finnhub,
FinancialData and a Tavily client), read five settings, seeded and read the
threshold table, and ran a 252-day ^VIX calibration fetch. tasks.py rebuilds
SentinelService for every Celery task and webhook_service.py for every request,
so that whole graph was rebuilt once a minute — 461 "Tavily initialized" and
461 "FRED initialized" lines per 6h of production logs, and 453 ^VIX history
fetches — while a typical tick touches two or three of those services.

These tests pin construction cost. Without them the eager constructor grows
back one collaborator at a time and nothing fails.
建構成本測試：沒有這些測試，急切建構會一個一個長回來，而測試不會有任何反應。
"""
from unittest.mock import MagicMock, patch

import pytest

from src.services.sentinel_service import SentinelService

LAZY_COLLABORATORS = [
    "market_service",
    "search_service",
    "transaction_service",
    "council_service",
    "keyword_service",
    "snapshot_repo",
    "model_router",
    "gateway",
]


@pytest.fixture
def sentinel():
    with patch("src.services.sentinel_service.AlchemySentinelRepository"), \
         patch("src.services.sentinel_service.SettingsService"):
        yield SentinelService(user_id="test_user")


def test_constructor_builds_no_collaborators(sentinel):
    for name in LAZY_COLLABORATORS:
        assert getattr(sentinel, f"_{name}") is None, (
            f"{name} was built in __init__; SentinelService is constructed once per "
            "Celery task and per webhook request"
        )


def test_constructor_touches_neither_market_data_nor_settings():
    """The 252-day ^VIX fetch and the five settings reads both used to happen
    before the caller had asked for anything."""
    with patch("src.services.sentinel_service.AlchemySentinelRepository"), \
         patch("src.services.sentinel_service.SettingsService") as settings_cls, \
         patch("src.services.sentinel_service.MarketDataService") as market_cls:
        SentinelService(user_id="test_user")

    market_cls.assert_not_called()
    settings_cls.assert_not_called()


def test_constructor_does_not_read_or_seed_thresholds():
    with patch("src.services.sentinel_service.AlchemySentinelRepository") as repo_cls, \
         patch("src.services.sentinel_service.SettingsService"):
        SentinelService(user_id="test_user")

    repo = repo_cls.return_value
    repo.seed_defaults.assert_not_called()
    repo.get_all_thresholds.assert_not_called()


@pytest.mark.parametrize("name", LAZY_COLLABORATORS)
def test_collaborator_is_built_once_on_first_access(sentinel, name):
    with patch("src.services.sentinel_service.MarketDataService"), \
         patch("src.services.sentinel_service.InternetSearchService"), \
         patch("src.services.sentinel_service.TransactionService"), \
         patch("src.services.sentinel_service.CouncilService"), \
         patch("src.services.sentinel_service.RiskKeywordService"), \
         patch("src.services.sentinel_service.AlchemySnapshotRepository"), \
         patch("src.services.sentinel_service.OpenRouterGateway"), \
         patch("src.infrastructure.llm.budget_aware_model_router.BudgetAwareModelRouter"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        first = getattr(sentinel, name)
        second = getattr(sentinel, name)

    assert first is second, f"{name} was rebuilt on second access"


@pytest.mark.parametrize("name", LAZY_COLLABORATORS + ["settings_service"])
def test_injected_collaborator_is_used_as_is(name):
    injected = MagicMock()
    kwargs = {name: injected}
    if name in ("model_router", "gateway"):
        pytest.skip("not constructor-injectable; covered by the setter test")

    with patch("src.services.sentinel_service.AlchemySentinelRepository"), \
         patch("src.services.sentinel_service.SettingsService"):
        svc = SentinelService(user_id="test_user", **kwargs)

    assert getattr(svc, name) is injected


@pytest.mark.parametrize("name", LAZY_COLLABORATORS + ["settings_service", "thresholds",
                                                      "priority_minutes"])
def test_attribute_can_be_assigned_and_deleted(sentinel, name):
    """Several tests and callers assign these after construction, and
    `unittest.mock.patch.object` deletes them on exit — a lazy property must
    survive both."""
    sentinel_attr = MagicMock()
    setattr(sentinel, name, sentinel_attr)
    assert getattr(sentinel, name) is sentinel_attr

    delattr(sentinel, name)
    assert getattr(sentinel, f"_{name}") is None


def test_thresholds_seed_and_read_on_first_access_only(sentinel):
    sentinel.repo.get_all_thresholds.return_value = {"vix_high": 25.0}

    assert sentinel.thresholds == {"vix_high": 25.0}
    assert sentinel.thresholds == {"vix_high": 25.0}

    sentinel.repo.seed_defaults.assert_called_once_with(sentinel.default_thresholds)
    sentinel.repo.get_all_thresholds.assert_called_once()


class TestCalibrationCooldown:
    """Calibration reads 252 days of ^VIX and writes three threshold rows. It
    ran on every construction; its inputs are year-long percentiles."""

    @pytest.mark.asyncio
    async def test_calibrates_when_the_daily_window_is_free(self, sentinel):
        with patch.object(sentinel, "_acquire_cooldown", return_value=True) as cooldown, \
             patch.object(sentinel, "_calibrate_thresholds") as calibrate:
            await sentinel._maybe_calibrate_thresholds()

        calibrate.assert_called_once()
        name, seconds = cooldown.call_args.args[0], cooldown.call_args.args[1]
        assert name == "threshold_calibration"
        assert seconds == 86400

    @pytest.mark.asyncio
    async def test_skips_when_another_worker_holds_the_window(self, sentinel):
        with patch.object(sentinel, "_acquire_cooldown", return_value=False), \
             patch.object(sentinel, "_calibrate_thresholds") as calibrate:
            await sentinel._maybe_calibrate_thresholds()

        calibrate.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_closed_so_redis_loss_does_not_restore_per_tick_work(self, sentinel):
        """fail_open=False: stored thresholds are stale at worst, whereas
        failing open puts the 252-day fetch back on every tick of every
        worker — the exact cost being removed."""
        with patch.object(sentinel, "_acquire_cooldown", return_value=True) as cooldown, \
             patch.object(sentinel, "_calibrate_thresholds"):
            await sentinel._maybe_calibrate_thresholds()

        assert cooldown.call_args.kwargs.get("fail_open") is False


class TestCloseReleasesEverySession:
    """
    `close()` used to be one try block wrapping three closes, and the middle
    one was a guaranteed `AttributeError`: it called
    `settings_service.repo.close_session()` while `SettingsService` exposes
    `settings_repo` (settings_service.py:25). The except swallowed it into a
    single log line, so the settings session AND the keyword session below it
    leaked on every close — silently, for as long as the code existed.

    close() 原本三個關閉共用一個 try，中間那個必然 AttributeError，
    導致 settings 與 keyword 的 session 每次都沒被關閉，且只留一行 log。
    """

    def test_closes_repo_settings_and_keyword_sessions(self, sentinel):
        settings_service = MagicMock()
        keyword_service = MagicMock()
        sentinel.settings_service = settings_service
        sentinel.keyword_service = keyword_service
        sentinel.repo = MagicMock()

        sentinel.close()

        sentinel.repo.close_session.assert_called_once()
        settings_service.settings_repo.close_session.assert_called_once()
        keyword_service._repo.close_session.assert_called_once()

    def test_one_failing_close_does_not_skip_the_others(self, sentinel):
        settings_service = MagicMock()
        settings_service.settings_repo.close_session.side_effect = RuntimeError("boom")
        keyword_service = MagicMock()
        sentinel.settings_service = settings_service
        sentinel.keyword_service = keyword_service
        sentinel.repo = MagicMock()

        sentinel.close()

        sentinel.repo.close_session.assert_called_once()
        keyword_service._repo.close_session.assert_called_once()

    def test_close_does_not_build_collaborators_it_never_used(self, sentinel):
        """`self.settings_service` is a lazy property that CONSTRUCTS on read."""
        sentinel._settings_service = None
        sentinel._keyword_service = None
        sentinel.repo = MagicMock()

        sentinel.close()

        assert sentinel._settings_service is None
        assert sentinel._keyword_service is None
        sentinel.repo.close_session.assert_called_once()
