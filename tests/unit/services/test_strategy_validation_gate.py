"""
Regression tests for the strategy validation gate.
策略驗證關卡的回歸測試。

Context (2026-08-10): production was configured to trade a live eToro account
(`etoro_mode="real"`, `ai_trading_enabled=true`, no `TRADING_MODE` override)
and auto-execute anything scoring >= 7.5/10 — while `backtest_runs` held ZERO
rows and `transactions` held ZERO rows with `entry_category='trade'`. Nothing
had ever been measured, and nothing had ever filled.

The rule driving automated sells was `_check_allocation_drift`: trim any
position above 25% of the portfolio. That is concentration risk management,
not an edge, and its expected return had never been established.

These tests pin the resulting policy: live automated execution requires a
stored backtest that cleared explicit thresholds; paper/demo is deliberately
exempt so a strategy can earn its way to a live allocation.

2026-08-10：系統在 backtest_runs 為 0 筆、從未有任何成交的情況下，就設定為對
實盤帳戶以 ≥7.5 分自動成交。本測試固定的政策是：實盤自動執行必須有通過門檻的
回測紀錄；paper/demo 刻意豁免，讓策略得以透過紙上交易取得實盤資格。
"""
import pytest
from unittest.mock import MagicMock, patch

from src.services.strategy_validation_service import (
    STRATEGY_CONCENTRATION_REBALANCE,
    StrategyValidationService,
    ValidationThresholds,
    buy_and_hold_return_pct,
    evaluate_backtest,
)


def _passing_metrics(**overrides):
    metrics = {
        "sharpe": 1.4,
        "max_drawdown_pct": 12.0,
        "total_trades": 25,
    }
    metrics.update(overrides)
    return metrics


class TestEvaluateBacktest:

    def test_a_good_run_passes(self):
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(),
            initial_cash=100_000.0,
            final_cash=140_000.0,
            buy_and_hold_return_pct=15.0,
        )
        assert passed is True
        assert failures == []

    def test_weak_sharpe_fails(self):
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(sharpe=0.3),
            initial_cash=100_000.0,
            final_cash=140_000.0,
            buy_and_hold_return_pct=15.0,
        )
        assert passed is False
        assert any("Sharpe" in f for f in failures)

    def test_deep_drawdown_fails(self):
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(max_drawdown_pct=45.0),
            initial_cash=100_000.0,
            final_cash=140_000.0,
            buy_and_hold_return_pct=15.0,
        )
        assert passed is False
        assert any("drawdown" in f.lower() for f in failures)

    def test_negative_drawdown_sign_is_still_caught(self):
        """
        A sign-convention change must not silently pass a bad run.
        正負號慣例改變時，不得默默放行糟糕的結果。
        """
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(max_drawdown_pct=-45.0),
            initial_cash=100_000.0,
            final_cash=140_000.0,
            buy_and_hold_return_pct=15.0,
        )
        assert passed is False
        assert any("drawdown" in f.lower() for f in failures)

    def test_losing_money_fails(self):
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(),
            initial_cash=100_000.0,
            final_cash=92_000.0,
            buy_and_hold_return_pct=-20.0,
        )
        assert passed is False
        assert any("Net return" in f for f in failures)

    def test_underperforming_buy_and_hold_fails(self):
        """
        Trading all year to lag the asset is a cost generator, not an edge.
        整年交易卻輸給單純持有，那是成本來源而非優勢。
        """
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(),
            initial_cash=100_000.0,
            final_cash=110_000.0,
            buy_and_hold_return_pct=35.0,
        )
        assert passed is False
        assert any("buy-and-hold" in f for f in failures)

    def test_missing_benchmark_fails(self):
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(),
            initial_cash=100_000.0,
            final_cash=140_000.0,
            buy_and_hold_return_pct=None,
        )
        assert passed is False
        assert any("benchmark" in f for f in failures)

    def test_too_few_trades_fails(self):
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(total_trades=2),
            initial_cash=100_000.0,
            final_cash=140_000.0,
            buy_and_hold_return_pct=15.0,
        )
        assert passed is False
        assert any("statistically meaningful" in f for f in failures)

    def test_all_failures_are_reported_together(self):
        passed, failures = evaluate_backtest(
            metrics=_passing_metrics(sharpe=0.1, max_drawdown_pct=60.0, total_trades=1),
            initial_cash=100_000.0,
            final_cash=80_000.0,
            buy_and_hold_return_pct=None,
        )
        assert passed is False
        assert len(failures) >= 4, f"expected every failure listed, got {failures}"


class TestBuyAndHoldBenchmark:

    def test_computes_percentage_return(self):
        assert buy_and_hold_return_pct({"close": [100.0, 150.0]}) == pytest.approx(50.0)

    def test_needs_two_bars(self):
        assert buy_and_hold_return_pct({"close": [100.0]}) is None

    def test_guards_zero_start_price(self):
        assert buy_and_hold_return_pct({"close": [0.0, 100.0]}) is None


class TestIsValidated:

    def test_no_backtest_on_record_is_not_validated(self):
        """
        The production state on 2026-08-10: backtest_runs held zero rows.
        2026-08-10 的 production 狀態：backtest_runs 為 0 筆。
        """
        repo = MagicMock()
        repo.list_runs.return_value = []

        validated, detail = StrategyValidationService(repository=repo).is_validated(
            "u1", STRATEGY_CONCENTRATION_REBALANCE
        )

        assert validated is False
        assert "no backtest on record" in detail

    def test_a_passing_run_validates(self):
        repo = MagicMock()
        repo.list_runs.return_value = [{
            "id": "run-1",
            "strategy_name": STRATEGY_CONCENTRATION_REBALANCE,
            "initial_cash": 100_000.0,
            "final_cash": 140_000.0,
            "metrics": _passing_metrics(),
            "params": {"buy_and_hold_return_pct": 15.0},
        }]

        validated, detail = StrategyValidationService(repository=repo).is_validated(
            "u1", STRATEGY_CONCENTRATION_REBALANCE
        )

        assert validated is True
        assert "run-1" in detail

    def test_only_failing_runs_does_not_validate(self):
        repo = MagicMock()
        repo.list_runs.return_value = [{
            "id": "run-1",
            "strategy_name": STRATEGY_CONCENTRATION_REBALANCE,
            "initial_cash": 100_000.0,
            "final_cash": 90_000.0,
            "metrics": _passing_metrics(sharpe=0.1),
            "params": {"buy_and_hold_return_pct": 15.0},
        }]

        validated, detail = StrategyValidationService(repository=repo).is_validated(
            "u1", STRATEGY_CONCENTRATION_REBALANCE
        )

        assert validated is False
        assert "none cleared the thresholds" in detail

    def test_another_strategys_pass_does_not_count(self):
        repo = MagicMock()
        repo.list_runs.return_value = [{
            "id": "run-1",
            "strategy_name": "some_other_strategy",
            "initial_cash": 100_000.0,
            "final_cash": 140_000.0,
            "metrics": _passing_metrics(),
            "params": {"buy_and_hold_return_pct": 15.0},
        }]

        validated, _ = StrategyValidationService(repository=repo).is_validated(
            "u1", STRATEGY_CONCENTRATION_REBALANCE
        )

        assert validated is False

    def test_unreadable_history_fails_closed(self):
        repo = MagicMock()
        repo.list_runs.side_effect = RuntimeError("db down")

        validated, detail = StrategyValidationService(repository=repo).is_validated(
            "u1", STRATEGY_CONCENTRATION_REBALANCE
        )

        assert validated is False
        assert "unavailable" in detail

    def test_json_string_columns_are_parsed(self):
        """SQLite stores metrics/params as TEXT; postgres as JSONB."""
        import json

        repo = MagicMock()
        repo.list_runs.return_value = [{
            "id": "run-1",
            "strategy_name": STRATEGY_CONCENTRATION_REBALANCE,
            "initial_cash": 100_000.0,
            "final_cash": 140_000.0,
            "metrics": json.dumps(_passing_metrics()),
            "params": json.dumps({"buy_and_hold_return_pct": 15.0}),
        }]

        validated, _ = StrategyValidationService(repository=repo).is_validated(
            "u1", STRATEGY_CONCENTRATION_REBALANCE
        )

        assert validated is True


@pytest.mark.asyncio
class TestGateInExecutionPath:
    """
    The gate as it actually behaves inside evaluate_and_execute_trade.
    關卡在 evaluate_and_execute_trade 中的實際行為。
    """

    @staticmethod
    def _service():
        from src.services.automated_trading_service import AutomatedTradingService

        svc = AutomatedTradingService.__new__(AutomatedTradingService)
        svc.notification_service = MagicMock()
        svc.settings_repo = MagicMock()
        # 2026-08-11: `tradable_capital_usd: 0` disables the capital cap, which
        # in turn disables the small-test waiver added the same day. These
        # tests are about the gate itself, so they must run with it armed —
        # under the $100 default the waiver fires first and nothing is gated.
        # Waiver behaviour is covered separately in TestSmallTestWaiver.
        # 2026-08-11：tradable_capital_usd 設為 0 即解除資本上限，連帶關閉同日新增
        # 的小額實測豁免。本組測試針對關卡本身，必須在「關卡啟用」狀態下執行；
        # 若沿用 $100 預設，豁免會先生效而使關卡完全不作用。
        svc.settings_repo.get.side_effect = lambda uid, key: {
            "ai_trading_enabled": "true",
            "auto_trade_threshold": 75,
            "auto_trade_threshold_sell": 60,
            "auto_trade_min_threshold": 30,
            "tradable_capital_usd": 0,
        }.get(key)
        return svc

    @staticmethod
    def _broker():
        """
        A broker that satisfies the position-sizing and SELL-clamp blocks.
        滿足部位大小與賣出鉗制檢查的 broker 替身。

        Both blocks fail CLOSED, so without a working broker every trade is
        blocked for reasons unrelated to the gate under test.
        兩處檢查皆為 fail-closed，沒有可用 broker 時所有交易都會因與本測試無關的
        理由被擋下。
        """
        from unittest.mock import AsyncMock

        account = MagicMock(total_equity=100_000.0, available_cash=50_000.0)
        position = MagicMock(symbol="AAPL", quantity=100.0)

        broker = MagicMock()
        broker.get_account = AsyncMock(return_value=account)
        broker.get_positions = AsyncMock(return_value=[position])
        return broker

    async def test_live_buy_is_blocked_without_a_passing_backtest(self):
        svc = self._service()

        with patch("src.services.broker_factory.effective_trading_mode", return_value="real"), \
             patch("src.services.strategy_validation_service.StrategyValidationService.is_validated",
                   return_value=(False, "no backtest on record")):
            result = await svc.evaluate_and_execute_trade(
                user_id="u1", ticker="AAPL", action="BUY", quantity=1000.0,
                confidence_score=95, rationale="test",
                strategy_name=STRATEGY_CONCENTRATION_REBALANCE,
            )

        assert result["status"] == "blocked"
        assert "not validated" in result["reason"]

    async def test_demo_mode_is_exempt(self):
        """
        Paper trading must stay open — it is how a strategy earns validation.
        紙上交易必須保持開放：策略正是透過它取得驗證資格。
        """
        svc = self._service()

        async def _exec(*a, **k):
            return {"status": "executed"}

        svc._execute_trade = _exec

        with patch("src.services.automated_trading_service.BrokerFactory.get_broker",
                   return_value=self._broker()), \
             patch("src.services.broker_factory.effective_trading_mode", return_value="demo"), \
             patch("src.services.strategy_validation_service.StrategyValidationService.is_validated",
                   return_value=(False, "no backtest on record")) as mock_validate:
            result = await svc.evaluate_and_execute_trade(
                user_id="u1", ticker="AAPL", action="BUY", quantity=1000.0,
                confidence_score=95, rationale="test",
                strategy_name=STRATEGY_CONCENTRATION_REBALANCE,
            )

        mock_validate.assert_not_called()
        assert result["status"] == "executed"

    async def test_live_sell_is_downgraded_to_approval_not_blocked(self):
        """
        Refusing to sell can trap a user in a position, so an unvalidated SELL
        loses auto-execution but still reaches the human approval path.
        拒絕賣出會把使用者困在部位裡，故未驗證的 SELL 只失去自動執行資格，
        仍會走人工核准流程。
        """
        svc = self._service()
        approvals = []

        # 2026-08-11: the withheld-auto-execution reason moved out of
        # `rationale` and into its own `extra_reason` kwarg, so the decision
        # card can place it under "為何沒自動執行" instead of burying it in
        # the free-text rationale.
        # 2026-08-11：撤銷自動執行的理由已從 rationale 移到獨立的 extra_reason，
        # 讓決策卡能把它放在「為何沒自動執行」而非埋進自由文字裡。
        async def _approve(user_id, order, score, rationale, **kwargs):
            approvals.append(kwargs.get("extra_reason") or "")
            return {"status": "pending_approval"}

        svc._request_approval_and_execute = _approve

        with patch("src.services.automated_trading_service.BrokerFactory.get_broker",
                   return_value=self._broker()), \
             patch("src.services.broker_factory.effective_trading_mode", return_value="real"), \
             patch("src.services.strategy_validation_service.StrategyValidationService.is_validated",
                   return_value=(False, "no backtest on record")):
            result = await svc.evaluate_and_execute_trade(
                user_id="u1", ticker="AAPL", action="SELL", quantity=1.0,
                confidence_score=100, rationale="concentration trim",
                strategy_name=STRATEGY_CONCENTRATION_REBALANCE,
            )

        assert result["status"] == "pending_approval"
        assert approvals and "not validated" in approvals[0]

    async def test_no_strategy_name_leaves_behaviour_unchanged(self):
        """
        Callers that do not name a strategy are not gated — the gate is opt-in
        per call site so this change cannot silently block unrelated flows.
        未指定策略名稱的呼叫端不受關卡影響：關卡逐呼叫點採 opt-in，避免默默
        擋掉無關流程。
        """
        svc = self._service()

        async def _exec(*a, **k):
            return {"status": "executed"}

        svc._execute_trade = _exec

        with patch("src.services.automated_trading_service.BrokerFactory.get_broker",
                   return_value=self._broker()), \
             patch("src.services.broker_factory.effective_trading_mode") as mock_mode:
            result = await svc.evaluate_and_execute_trade(
                user_id="u1", ticker="AAPL", action="BUY", quantity=1000.0,
                confidence_score=95, rationale="test",
            )

        mock_mode.assert_not_called()
        assert result["status"] == "executed"
