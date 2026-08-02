"""
Regression tests for sentinel tick deduplication.
測試哨兵 tick 去重。

Context (2026-08-02): two Celery Beat entries terminated in the SAME call —
"sentinel-minutely-tick" (every minute) and "portfolio-rebalance-trigger"
(*/30 during 08:00-16:59 Mon-Fri) both ran
`SentinelService(user_id).process_tick()`. At :00 and :30 the tick therefore
ran twice, and both of those minutes satisfy the `minute % 10 == 0` gate that
guards the paid Tavily breaking-news search (:00 also hits FRED) — roughly 18
duplicated paid ticks per trading day. `_handle_rebalance_logic`'s 30-minute
debounce could not stop it: it keys off `self.last_fire_time` on an instance
each Celery task constructs fresh.

Fix: the redundant beat entry is gone, and `process_tick()` now takes a
per-user, per-minute Redis lock so no arrangement of callers can double-run it.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBeatScheduleHasNoDuplicateSentinelEntry:

    def test_portfolio_rebalance_trigger_is_gone(self):
        from src.infrastructure.celery_app import app

        assert "portfolio-rebalance-trigger" not in app.conf.beat_schedule

    def test_sentinel_minutely_tick_survives(self):
        from src.infrastructure.celery_app import app

        assert "sentinel-minutely-tick" in app.conf.beat_schedule

    def test_only_one_beat_entry_reaches_process_tick(self):
        """
        Structural guard against re-adding a twin under a different name.

        Scoped to process_tick specifically rather than "no two entries share a
        task" — several entries legitimately share dispatch_market_intelligence
        and dispatch_memory_distill at non-overlapping times (pre-market 08:30,
        mid-day 12:00, post-market 16:30, Sat 10:00, 1st-of-month 09:00), which
        is fine. What must never recur is two schedules driving the sentinel.
        限縮在 process_tick：其他任務在不重疊時間共用 dispatch 是正常的，
        不可再發生的是「兩個排程同時驅動哨兵」。
        """
        from src.infrastructure.celery_app import app
        import src.infrastructure.tasks as tasks_mod
        import inspect

        reaching = []
        for name, entry in app.conf.beat_schedule.items():
            fn_name = entry["task"].rsplit(".", 1)[-1]
            fn = getattr(tasks_mod, fn_name, None)
            if fn is None:
                continue
            src = inspect.getsource(fn)
            # dispatchers fan out to a per-user task; follow one hop
            for callee in ("sentinel_tick", "trigger_portfolio_rebalance"):
                if callee in src:
                    inner = getattr(tasks_mod, callee, None)
                    if inner and "process_tick" in inspect.getsource(inner):
                        reaching.append(name)
                        break
            else:
                if "process_tick" in src:
                    reaching.append(name)

        assert reaching == ["sentinel-minutely-tick"], (
            f"expected only the minutely tick to drive process_tick, got {reaching}"
        )

    def test_dispatch_portfolio_rebalance_removed(self):
        """Its only caller was the deleted beat entry."""
        import src.infrastructure.tasks as tasks

        assert not hasattr(tasks, "dispatch_portfolio_rebalance")

    def test_manual_rebalance_entrypoint_retained(self):
        """The dashboard 'Rebalance now' button still needs this task."""
        import src.infrastructure.tasks as tasks

        assert hasattr(tasks, "trigger_portfolio_rebalance")


@pytest.fixture
def sentinel():
    """A SentinelService with every collaborator stubbed except the lock."""
    from src.services.sentinel_service import SentinelService

    with patch('src.services.sentinel_service.AlchemySentinelRepository'), \
         patch('src.services.sentinel_service.SettingsService'), \
         patch('src.services.sentinel_service.CouncilService'), \
         patch('src.services.sentinel_service.TransactionService'), \
         patch('src.services.sentinel_service.MarketDataService'), \
         patch('src.services.sentinel_service.InternetSearchService'), \
         patch('src.services.sentinel_service.RiskKeywordService'), \
         patch('src.services.sentinel_service.AlchemySnapshotRepository'):
        svc = SentinelService(user_id="u1")

    svc.repo = MagicMock()
    svc.repo.get_all_thresholds.return_value = {}
    svc._check_buffer_flush = AsyncMock()
    svc._redis_buffer = MagicMock()
    return svc


class TestProcessTickLock:

    @pytest.mark.asyncio
    async def test_second_call_in_same_minute_is_skipped(self, sentinel):
        # First acquires, second loses the race.
        sentinel._redis_buffer.try_acquire = AsyncMock(side_effect=[True, False])

        await sentinel.process_tick()
        first_calls = sentinel.repo.get_all_thresholds.call_count

        await sentinel.process_tick()
        second_calls = sentinel.repo.get_all_thresholds.call_count

        assert first_calls == 1
        assert second_calls == 1, "duplicate tick was not skipped"

    @pytest.mark.asyncio
    async def test_lock_key_is_user_and_minute_scoped(self, sentinel):
        sentinel._redis_buffer.try_acquire = AsyncMock(return_value=True)

        await sentinel.process_tick()

        key = sentinel._redis_buffer.try_acquire.call_args[0][0]
        assert key.startswith("lock:sentinel:tick:u1:")
        assert len(key.rsplit(":", 1)[1]) == 12  # YYYYMMDDHHMM

    @pytest.mark.asyncio
    async def test_redis_failure_fails_open(self, sentinel):
        """A Redis outage must not silence the safety monitor."""
        from src.infrastructure.redis_sentinel_buffer import RedisSentinelBuffer

        buf = RedisSentinelBuffer()
        buf._get_client = AsyncMock(side_effect=ConnectionError("redis down"))

        assert await buf.try_acquire("k", 120) is True

    @pytest.mark.asyncio
    async def test_force_bypasses_the_lock(self, sentinel):
        """Manual 'rebalance now' must not be swallowed by the scheduled tick's lock."""
        sentinel._redis_buffer.try_acquire = AsyncMock(return_value=False)

        await sentinel.process_tick(force=True)

        sentinel._redis_buffer.try_acquire.assert_not_called()
        assert sentinel.repo.get_all_thresholds.call_count == 1

    @pytest.mark.asyncio
    async def test_anonymous_user_does_not_lock(self, sentinel):
        sentinel.user_id = None
        sentinel._redis_buffer.try_acquire = AsyncMock(return_value=True)

        await sentinel.process_tick()

        sentinel._redis_buffer.try_acquire.assert_not_called()


class TestTryAcquireSemantics:

    @pytest.mark.asyncio
    async def test_returns_true_when_key_is_won(self):
        from src.infrastructure.redis_sentinel_buffer import RedisSentinelBuffer

        buf = RedisSentinelBuffer()
        client = AsyncMock()
        client.set = AsyncMock(return_value=True)
        buf._get_client = AsyncMock(return_value=client)

        assert await buf.try_acquire("k", 120) is True
        client.set.assert_awaited_once_with("k", "1", nx=True, ex=120)

    @pytest.mark.asyncio
    async def test_returns_false_when_key_already_held(self):
        from src.infrastructure.redis_sentinel_buffer import RedisSentinelBuffer

        buf = RedisSentinelBuffer()
        client = AsyncMock()
        client.set = AsyncMock(return_value=None)   # redis SETNX miss
        buf._get_client = AsyncMock(return_value=client)

        assert await buf.try_acquire("k", 120) is False

    def test_no_release_method_exists(self):
        """
        Releasing early would re-open the duplicate window the lock exists to
        close — expiry is by TTL only. Guard against someone adding one.
        """
        from src.infrastructure.redis_sentinel_buffer import RedisSentinelBuffer

        assert not hasattr(RedisSentinelBuffer, "release_lock")
