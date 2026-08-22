"""
Regression tests for the Sentinel rebalance guardrails.
哨兵再平衡護欄的回歸測試。

Context (2026-08-10): a three-day production outage — the API leaked Redis
connections until `maxclients` was exhausted and every Celery worker died —
forced a review of what would happen the moment the trading loop resumed.
Three defects in `_handle_rebalance_logic` would each have fired against a
live eToro account (`etoro_mode="real"`, `ai_trading_enabled=true`):

  1. The debounce stamped `last_fire_time` BEFORE the empty-triggers check,
     so an idle tick armed the 30-minute cooldown and suppressed the next
     real trigger.
  2. The debounce lived in `self.last_fire_time`, an instance dict on an
     object that tasks.py rebuilds per Celery task and webhook_service.py
     per request — so it never spanned processes and never debounced
     anything in production.
  3. The sell was submitted with `confidence_score=100`, which normalizes to
     10.0 and always clears `auto_trade_threshold` (7.5) — every
     concentration rebalance liquidated part of a real position with no
     human in the loop, on a heuristic that has never been backtested.

2026-08-10：Redis 連線洩漏導致交易迴圈停擺三天。恢復前檢視發現
_handle_rebalance_logic 有三個會直接對實盤帳戶生效的缺陷（見上）。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _sentinel(**settings):
    """
    Build a SentinelService with its constructor side effects stubbed out.
    建立 SentinelService，並停用建構子的外部副作用。
    """
    from src.services.sentinel_service import SentinelService

    settings_service = MagicMock()
    settings_service.get_setting.side_effect = (
        lambda key, default=None, *a, **k: settings.get(key, default)
    )

    with patch.object(SentinelService, "_calibrate_thresholds", return_value=None), \
         patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer"):
        svc = SentinelService(user_id="u1", settings_service=settings_service)
    return svc


class _FakeRedis:
    """Minimal SET NX EX / TTL stand-in. 最小化的 SET NX EX / TTL 替身。"""

    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def ttl(self, key):
        return 1800 if key in self.store else -2


@pytest.mark.asyncio
class TestRebalanceCooldown:

    async def test_idle_tick_does_not_suppress_the_next_real_trigger(self):
        """
        An idle tick must leave the window untouched.
        無事可做的 tick 不得佔用冷卻窗口。

        This is defect (1). Asserted behaviourally — that the following real
        trigger still executes — rather than by inspecting the cooldown store,
        because the old code armed an in-process dict and never touched Redis
        at all, so a store-level assertion would have passed against it.
        以行為斷言（後續真實觸發仍會執行）而非檢查冷卻狀態：舊版是寫入行程內
        dict、完全不碰 Redis，檢查 store 的斷言對舊版也會通過，抓不到缺陷。
        """
        svc = _sentinel()
        auto_svc = MagicMock()
        auto_svc.evaluate_and_execute_trade = AsyncMock(return_value={"status": "ok"})

        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(return_value=_FakeRedis())), \
             patch("src.services.automated_trading_service.AutomatedTradingService",
                   return_value=auto_svc):
            await svc._handle_rebalance_logic([])
            await svc._handle_rebalance_logic(
                [{"action": "trigger_rebalance", "ticker": "AAPL", "sell_quantity": 5.0}]
            )

        auto_svc.evaluate_and_execute_trade.assert_awaited_once()

    async def test_cooldown_is_shared_across_instances(self):
        """
        A second SentinelService must observe the first one's cooldown.
        第二個 SentinelService 必須看得到第一個設下的冷卻窗口。

        This is defect (2). Two separate instances stand in for the two Celery
        workers, which each construct their own SentinelService per task.
        """
        fake = _FakeRedis()
        trigger = {"action": "trigger_rebalance", "ticker": "AAPL", "sell_quantity": 5.0}

        executed = []

        async def _record(**kwargs):
            executed.append(kwargs)
            return {"status": "ok"}

        auto_svc = MagicMock()
        auto_svc.evaluate_and_execute_trade = AsyncMock(side_effect=_record)

        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(return_value=fake)), \
             patch("src.services.automated_trading_service.AutomatedTradingService",
                   return_value=auto_svc):
            await _sentinel()._handle_rebalance_logic([dict(trigger)])
            await _sentinel()._handle_rebalance_logic([dict(trigger)])

        assert len(executed) == 1, (
            "the second worker must be debounced by the first worker's window"
        )

    async def test_fails_closed_when_cooldown_backend_is_down(self):
        """
        No Redis means no rebalance — a duplicate sell is irreversible.
        Redis 不可用時不得再平衡：重複賣單不可逆。
        """
        svc = _sentinel()
        auto_svc = MagicMock()
        auto_svc.evaluate_and_execute_trade = AsyncMock()

        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(side_effect=ConnectionError("max number of clients reached"))), \
             patch("src.services.automated_trading_service.AutomatedTradingService",
                   return_value=auto_svc):
            await svc._handle_rebalance_logic(
                [{"action": "trigger_rebalance", "ticker": "AAPL", "sell_quantity": 5.0}]
            )

        auto_svc.evaluate_and_execute_trade.assert_not_called()


@pytest.mark.asyncio
class TestRebalanceRequiresApproval:

    @staticmethod
    async def _run_rebalance(exit_decision):
        """
        Drive one rebalance with a fixed exit score, capture what was submitted.
        以固定的出場分數跑一次再平衡，攔截送出的參數。
        """
        svc = _sentinel()
        auto_svc = MagicMock()
        auto_svc.evaluate_and_execute_trade = AsyncMock(return_value={"status": "ok"})

        compositor = MagicMock()
        compositor.score_exit = AsyncMock(return_value=exit_decision)

        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(return_value=_FakeRedis())), \
             patch("src.services.exit_compositor_service.ExitCompositorService",
                   return_value=compositor), \
             patch("src.services.automated_trading_service.AutomatedTradingService",
                   return_value=auto_svc):
            await svc._handle_rebalance_logic([{
                "action": "trigger_rebalance",
                "ticker": "AAPL",
                "sell_quantity": 5.0,
                "current_weight_pct": 26.0,
                "current_price": 190.0,
            }])

        auto_svc.evaluate_and_execute_trade.assert_awaited_once()
        return auto_svc.evaluate_and_execute_trade.await_args.kwargs

    @staticmethod
    def _decision(score):
        return {
            "ticker": "AAPL",
            "action": "SELL",
            "quantity": 5.0,
            "composite_score": score,
            "breakdown": [
                {"agent": "未實現損益", "confidence": 4.0, "weight": 0.30,
                 "contribution": 1.20, "key_factor": "+12.4%"},
                {"agent": "集中度", "confidence": 9.0, "weight": 0.25,
                 "contribution": 2.25, "key_factor": "26% > 25%"},
            ],
            "rationale": "test",
        }

    async def test_submitted_score_comes_from_the_exit_compositor(self):
        """
        The sell score must be the computed composite, not a constant.
        賣出分數必須來自實際計算的綜合分數，而非常數。

        Until 2026-08-11 this path passed a bare 100 (and briefly a settings
        constant), so a fixed number decided whether real money moved.
        2026-08-11 之前此路徑傳的是寫死的 100（後來短暫改為設定常數），等於由固定
        數字決定真錢是否移動。
        """
        kwargs = await self._run_rebalance(self._decision(5.4))
        assert kwargs["confidence_score"] == 5.4

    async def test_breakdown_is_forwarded_for_the_approval_card(self):
        """
        Without the breakdown the card cannot explain the score.
        沒有分項，卡片就無法解釋分數從何而來。
        """
        kwargs = await self._run_rebalance(self._decision(5.4))
        breakdown = kwargs["confidence_breakdown"]
        assert [b["agent"] for b in breakdown] == ["未實現損益", "集中度"]

    async def test_a_weak_exit_score_does_not_auto_execute(self):
        """
        A score below the SELL bar (6.0) must route to approval, not execution.
        低於賣出門檻(6.0)的分數必須走核准流程而非直接執行。
        """
        kwargs = await self._run_rebalance(self._decision(5.4))
        assert kwargs["confidence_score"] < 6.0

    async def test_a_strong_exit_score_can_auto_execute(self):
        """
        A genuinely urgent exit (stop-loss hit, thesis broken) clears the bar.
        真正急迫的出場（觸及停損、論點破裂）可以越過門檻。
        """
        kwargs = await self._run_rebalance(self._decision(8.6))
        assert kwargs["confidence_score"] >= 6.0


@pytest.mark.asyncio
class TestEscalationCooldown:

    async def test_idle_tick_does_not_suppress_the_next_real_alert(self):
        """
        Same inverted-order defect as the rebalance path.
        與再平衡路徑相同的順序顛倒缺陷。

        Asserted through _acquire_cooldown, which is the shared seam both
        paths now use, so an idle escalation cannot consume the window.
        """
        svc = _sentinel()
        fake = _FakeRedis()

        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(return_value=fake)):
            await svc._escalate([])
            # The window must still be claimable after an idle escalation.
            still_available = await svc._acquire_cooldown(
                f"escalate:Sentinel:{svc.user_id}", 1800, fail_open=True
            )

        assert still_available is True

    async def test_fails_open_when_cooldown_backend_is_down(self):
        """
        Alerts fail OPEN — a missed P0 is worse than a duplicate notification.
        告警採 fail-open：漏掉 P0 比重複通知更糟。

        Deliberately the opposite of the rebalance path, which fails closed.
        """
        svc = _sentinel()

        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(side_effect=ConnectionError("redis down"))):
            allowed = await svc._acquire_cooldown("escalate:test:u1", 1800, fail_open=True)
            blocked = await svc._acquire_cooldown("rebalance:u1", 1800, fail_open=False)

        assert allowed is True, "alerting must proceed without a cooldown backend"
        assert blocked is False, "trading must not proceed without a cooldown backend"

    async def test_in_process_fallback_still_debounces_repeats(self):
        """
        With Redis down, fail-open still suppresses repeats on the same instance.
        Redis 不可用時，fail-open 仍會壓掉同一 instance 的重複呼叫。
        """
        svc = _sentinel()

        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(side_effect=ConnectionError("redis down"))):
            first = await svc._acquire_cooldown("escalate:test:u1", 1800, fail_open=True)
            second = await svc._acquire_cooldown("escalate:test:u1", 1800, fail_open=True)

        assert first is True
        assert second is False
