"""
Tests for the sell-side confidence scorer.
賣出信心評分器的測試。

Context (2026-08-11): before this service existed, every sell in the system
carried a hardcoded number — 100 in the rebalance path, 10 in the manual path,
8 in the confidence-rebalance path. Those constants were compared against the
same auto-execute threshold as a genuinely scored buy, so a literal decided
whether real money moved.

These tests pin the shape of the replacement: each factor answers a specific
question about the position, and the composite is their weighted sum.

2026-08-11：在本服務之前，系統中每一筆賣出都帶著寫死的數字（再平衡 100、手動
10、確信度再平衡 8），而這些常數又和有實際評分的買單比對同一個自動執行門檻，
等於由字面常數決定真錢是否移動。
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.exit_compositor_service import (
    EXIT_FACTOR_WEIGHTS,
    ExitCompositorService,
)

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _svc(*, lots=None, closes=None, settings=None, risk=(5.0, {"key_factor": "無事件"})):
    settings_service = MagicMock()
    settings_service.get_setting.side_effect = (
        lambda key, default=None, *a, **k: (settings or {}).get(key, default)
    )

    market = MagicMock()
    market.get_ohlcv.return_value = {"close": closes or []}

    svc = ExitCompositorService(
        user_id="u1", settings_service=settings_service, market_service=market
    )
    svc._open_lots = MagicMock(return_value=lots or [])
    svc._llm._score_via_llm = AsyncMock(return_value=risk)
    return svc


def _factor(decision, key):
    return next(b for b in decision["breakdown"] if b["factor_key"] == key)


class TestWeights:

    def test_weights_sum_to_one(self):
        assert abs(sum(EXIT_FACTOR_WEIGHTS.values()) - 1.0) < 1e-9

    @pytest.mark.anyio
    async def test_composite_is_the_weighted_sum(self):
        svc = _svc(
            lots=[{"quantity": 1.0, "open_price": 100.0}],
            closes=[100.0] * 20,
            risk=(5.0, {"key_factor": "x"}),
        )
        d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=0.0)

        expected = sum(
            b["confidence"] * EXIT_FACTOR_WEIGHTS[b["factor_key"]] for b in d["breakdown"]
        )
        assert abs(d["composite_score"] - expected) < 0.02


class TestPnLFactor:

    @pytest.mark.anyio
    async def test_hitting_the_stop_scores_maximum(self):
        """When enable_fixed_stops is True, a position through its stop scores maximum."""
        svc = _svc(lots=[{"quantity": 1.0, "open_price": 100.0}],
                   settings={"stop_loss_pct": 8.0, "enable_fixed_stops": True})
        d = await svc.score_exit("AAPL", 1.0, current_price=90.0, current_weight_pct=5.0)
        assert _factor(d, "pnl")["confidence"] == 10.0
        assert d["unrealized_pnl_pct"] == -10.0

    @pytest.mark.anyio
    async def test_long_term_mode_treats_pullback_as_normal_noise(self):
        """In long-term mode (default), normal drawdowns (-10%) do not trigger panic exit."""
        svc = _svc(lots=[{"quantity": 1.0, "open_price": 100.0}],
                   settings={"stop_loss_pct": 8.0, "enable_fixed_stops": False})
        d = await svc.score_exit("AAPL", 1.0, current_price=90.0, current_weight_pct=5.0)
        # Score is 4.0 (normal pullback), not an urgent 10.0 exit!
        assert _factor(d, "pnl")["confidence"] == 4.0
        assert d["unrealized_pnl_pct"] == -10.0

    @pytest.mark.anyio
    async def test_a_modest_winner_is_not_a_reason_to_sell(self):
        """
        Being up must not by itself push toward the exit — that is how a
        system gives away its winners.
        獲利本身不該推向出場，否則就是在把賺錢的部位丟掉。
        """
        svc = _svc(lots=[{"quantity": 1.0, "open_price": 100.0}])
        d = await svc.score_exit("AAPL", 1.0, current_price=110.0, current_weight_pct=5.0)
        assert _factor(d, "pnl")["confidence"] < 5.0

    @pytest.mark.anyio
    async def test_loss_scales_toward_the_stop(self):
        svc = _svc(lots=[{"quantity": 1.0, "open_price": 100.0}],
                   settings={"stop_loss_pct": 10.0, "enable_fixed_stops": True})
        near = await svc.score_exit("AAPL", 1.0, current_price=92.0, current_weight_pct=5.0)
        far = await svc.score_exit("AAPL", 1.0, current_price=98.0, current_weight_pct=5.0)
        assert _factor(near, "pnl")["confidence"] > _factor(far, "pnl")["confidence"]

    @pytest.mark.anyio
    async def test_missing_cost_basis_is_neutral_not_alarming(self):
        """
        No lot history must not read as urgency. position_lots was empty in
        production for months; scoring that as 10 would have liquidated
        everything the moment this shipped.
        沒有開倉紀錄不得被解讀為急迫。position_lots 在 production 曾長期為空，
        若給 10 分，本功能上線瞬間就會把所有部位清掉。
        """
        svc = _svc(lots=[])
        d = await svc.score_exit("AAPL", 1.0, current_price=110.0, current_weight_pct=5.0)
        assert _factor(d, "pnl")["confidence"] == 5.0
        assert _factor(d, "pnl")["factors"]["_insufficient_data"] is True


class TestConcentrationFactor:

    @pytest.mark.anyio
    async def test_over_the_ceiling_scores_high(self):
        svc = _svc(settings={"max_single_position_weight": 25.0})
        d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=26.0)
        assert _factor(d, "concentration")["confidence"] >= 9.0

    @pytest.mark.anyio
    async def test_under_the_ceiling_is_not_an_exit_reason(self):
        svc = _svc(settings={"max_single_position_weight": 25.0})
        d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=10.0)
        assert _factor(d, "concentration")["confidence"] < 5.0

    @pytest.mark.anyio
    async def test_concentration_alone_does_not_clear_the_sell_bar(self):
        """
        The whole point of scoring exits: a position over the ceiling whose
        thesis is intact should ask, not auto-liquidate. Concentration carries
        0.25, so on its own it cannot reach the 6.0 SELL threshold.
        評分賣出的重點：權重超標但論點未破的部位應該詢問而非自動平倉。集中度權重
        0.25，單靠它無法達到 6.0 的賣出門檻。
        """
        svc = _svc(
            lots=[{"quantity": 1.0, "open_price": 100.0}],
            closes=[100.0] * 19 + [112.0],          # strong, above MA
            settings={"max_single_position_weight": 25.0},
            risk=(2.0, {"key_factor": "無事件"}),
        )
        d = await svc.score_exit("AAPL", 1.0, current_price=112.0, current_weight_pct=26.0)
        assert _factor(d, "concentration")["confidence"] >= 9.0
        assert d["composite_score"] < 6.0

    @pytest.mark.anyio
    async def test_winning_compounder_concentration_is_softened_when_protection_enabled(self):
        """
        When protect_winning_compounders is enabled, a profitable runner's concentration
        score is softened (kept low) rather than forcing an exit.
        """
        svc = _svc(
            lots=[{"quantity": 1.0, "open_price": 100.0}],
            closes=[100.0] * 19 + [120.0],
            settings={"max_single_position_weight": 25.0, "protect_winning_compounders": True},
            risk=(2.0, {"key_factor": "無事件"}),
        )
        d = await svc.score_exit("AAPL", 1.0, current_price=120.0, current_weight_pct=40.0)
        # Concentration confidence should be kept low (<= 4.0), not 10.0!
        assert _factor(d, "concentration")["confidence"] <= 4.0
        assert _factor(d, "concentration")["factors"]["winner_protected"] is True


class TestMomentumFactor:

    @pytest.mark.anyio
    async def test_breaking_below_the_average_scores_high(self):
        svc = _svc(closes=[100.0] * 19 + [90.0])
        d = await svc.score_exit("AAPL", 1.0, current_price=90.0, current_weight_pct=5.0)
        assert _factor(d, "momentum_reversal")["confidence"] >= 9.0

    @pytest.mark.anyio
    async def test_trading_strongly_above_scores_low(self):
        svc = _svc(closes=[100.0] * 19 + [115.0])
        d = await svc.score_exit("AAPL", 1.0, current_price=115.0, current_weight_pct=5.0)
        assert _factor(d, "momentum_reversal")["confidence"] <= 2.0

    @pytest.mark.anyio
    async def test_insufficient_history_is_neutral(self):
        svc = _svc(closes=[100.0] * 5)
        d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=5.0)
        assert _factor(d, "momentum_reversal")["confidence"] == 5.0


class TestRiskFactor:

    @pytest.mark.anyio
    async def test_llm_failure_is_neutral_not_a_liquidation_signal(self):
        """
        A broken LLM call is not evidence of risk. Scoring it 10 would turn
        every provider outage into a portfolio-wide sell.
        LLM 呼叫失敗不構成風險證據；給 10 分會讓每次供應商中斷變成全組合賣出。
        """
        svc = _svc()
        svc._llm._score_via_llm = AsyncMock(side_effect=RuntimeError("provider down"))
        d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=5.0)
        assert _factor(d, "risk")["confidence"] == 5.0

    @pytest.mark.anyio
    async def test_routine_holding_review_fast_path_exempts_llm(self):
        """
        Routine holding review with healthy position (max_possible_composite < 5.0)
        exempts from the expensive LLM call and returns risk=3.0.
        """
        svc = _svc(
            lots=[{"quantity": 1.0, "open_price": 90.0}],
            closes=[100.0] * 20,
        )
        svc._score_risk = AsyncMock()
        # current_price 100 vs open 90 -> +11.1% gain, weight 2.0% (tiny), above 20MA
        d = await svc.score_exit(
            "AAPL", 1.0, current_price=100.0, current_weight_pct=2.0,
            reason_hint="Periodic holding review for AAPL"
        )
        assert _factor(d, "risk")["confidence"] == 3.0
        assert _factor(d, "risk")["factors"].get("_fast_path_exempt") is True
        svc._score_risk.assert_not_called()

    @pytest.mark.anyio
    async def test_risk_scoring_timeout_returns_neutral(self):
        """
        If LLM risk scoring times out, it safely falls back to neutral 5.0.
        """
        svc = _svc()

        async def mock_wait_for(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError("timed out")

        with patch("src.services.exit_compositor_service.asyncio.wait_for", side_effect=mock_wait_for):
            d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=5.0)
            assert _factor(d, "risk")["confidence"] == 5.0
            assert "逾時" in _factor(d, "risk")["factors"].get("key_factor", "")


class TestOutputContract:

    @pytest.mark.anyio
    async def test_breakdown_shape_matches_the_card_contract(self):
        """decision_card reads agent / confidence / weight / contribution."""
        svc = _svc(lots=[{"quantity": 1.0, "open_price": 100.0}], closes=[100.0] * 20)
        d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=5.0)

        assert set(EXIT_FACTOR_WEIGHTS) == {b["factor_key"] for b in d["breakdown"]}
        for b in d["breakdown"]:
            assert {"agent", "confidence", "weight", "contribution", "key_factor"} <= set(b)
            assert abs(b["contribution"] - b["confidence"] * b["weight"]) < 0.02

    @pytest.mark.anyio
    async def test_renders_through_the_decision_card(self):
        from src.services.decision_card import render_card

        svc = _svc(lots=[{"quantity": 1.0, "open_price": 100.0}], closes=[100.0] * 20)
        d = await svc.score_exit("AAPL", 1.0, current_price=100.0, current_weight_pct=5.0)
        card = render_card(
            action="SELL", ticker="AAPL",
            score=d["composite_score"], threshold=6.0, breakdown=d["breakdown"],
        )
        assert "未實現損益" in card and "集中度" in card

    @pytest.mark.anyio
    async def test_scoring_never_raises(self):
        """
        A scoring failure must not stop a stop-loss from being considered.
        評分失敗不得讓停損失去被考慮的機會。
        """
        svc = _svc()
        svc._open_lots = MagicMock(side_effect=RuntimeError("db down"))
        svc._market = MagicMock(side_effect=RuntimeError("api down"))
        d = await svc.score_exit("AAPL", 1.0)
        assert 0.0 <= d["composite_score"] <= 10.0


class TestDynamicAtrExit:
    def test_initial_stop_regimes(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Bull regime: 2.5x ATR
        res_bull = compute_dynamic_atr_exit(entry_price=100.0, current_price=100.0, atr=2.0, regime="BULL_MOMENTUM")
        assert res_bull.stop_price == 95.0
        assert res_bull.ratchet_stage == "INITIAL"
        assert not res_bull.should_exit

        # Bear regime: 1.5x ATR
        res_bear = compute_dynamic_atr_exit(entry_price=100.0, current_price=100.0, atr=2.0, regime="BEAR_CRISIS")
        assert res_bear.stop_price == 97.0
        assert res_bear.ratchet_stage == "INITIAL"
        assert not res_bear.should_exit

        # Neutral regime: 2.0x ATR
        res_neutral = compute_dynamic_atr_exit(entry_price=100.0, current_price=100.0, atr=2.0, regime="NEUTRAL_RANGE")
        assert res_neutral.stop_price == 96.0

    def test_breakeven_ratchet_at_8_pct(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Up 8%: Breakeven stop triggered at entry * 1.005 = 100.5
        res = compute_dynamic_atr_exit(entry_price=100.0, current_price=108.0, highest_price=108.0, atr=2.0)
        assert res.ratchet_stage == "BREAKEVEN"
        assert res.stop_price == 100.5
        assert not res.should_exit

        # Pullback towards breakeven stop: falls to 100.4
        res_stopped = compute_dynamic_atr_exit(entry_price=100.0, current_price=100.4, highest_price=108.0, atr=2.0)
        assert res_stopped.should_exit
        assert res_stopped.exit_type == "BREAKEVEN_PROTECTION"

    def test_trailing_profit_ratchet_at_15_pct(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Reached 120 (gain 20% > 15%): trailing stop = 120 - 2.0 * 2.0 = 116.0
        res = compute_dynamic_atr_exit(entry_price=100.0, current_price=118.0, highest_price=120.0, atr=2.0)
        assert res.ratchet_stage == "TRAILING"
        assert res.stop_price == 116.0
        assert not res.should_exit

        # Drops to 115.5: triggers trailing profit exit
        res_exit = compute_dynamic_atr_exit(entry_price=100.0, current_price=115.5, highest_price=120.0, atr=2.0)
        assert res_exit.should_exit
        assert res_exit.exit_type == "TRAILING_PROFIT"

    def test_initial_stop_triggered_on_plunge(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Entry 100, ATR 2, Neutral stop is 96. Price drops to 95.5
        res = compute_dynamic_atr_exit(entry_price=100.0, current_price=95.5, highest_price=100.0, atr=2.0)
        assert res.should_exit
        assert res.exit_type == "STOP_LOSS"
        assert res.tier == 0

    def test_harvest_ratchet_at_25_pct(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Reached 130 (gain 30% >= 25%): harvest stop = max(130 - 1.2*2.0=127.6, 100 + 0.65*30=119.5) = 127.6
        res = compute_dynamic_atr_exit(entry_price=100.0, current_price=128.0, highest_price=130.0, atr=2.0)
        assert res.ratchet_stage == "HARVEST"
        assert res.tier == 3
        assert res.stop_price == 127.6
        assert res.locked_profit_pct == 27.6
        assert not res.should_exit

        # Drops to 127.0: triggers harvest exit
        res_exit = compute_dynamic_atr_exit(entry_price=100.0, current_price=127.0, highest_price=130.0, atr=2.0)
        assert res_exit.should_exit
        assert res_exit.exit_type == "TRAILING_PROFIT"
        assert "HARVEST" in res_exit.rationale

    def test_advancing_ratchet_at_12_pct(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Reached 112 (gain 12%): advancing stop = max(112 - 2.2*2.0=107.6, 100 + 0.35*12=104.2) = 107.6
        res = compute_dynamic_atr_exit(entry_price=100.0, current_price=110.0, highest_price=112.0, atr=2.0)
        assert res.ratchet_stage == "ADVANCING"
        assert res.tier == 1
        assert res.stop_price == 107.6
        assert not res.should_exit

        # Pullback drops to 107.0 <= 107.6: triggers exit
        res_exit = compute_dynamic_atr_exit(entry_price=100.0, current_price=107.0, highest_price=112.0, atr=2.0)
        assert res_exit.should_exit
        assert res_exit.exit_type == "TRAILING_PROFIT"
        assert "ADVANCING" in res_exit.rationale

    def test_runner_lock_ratchet_at_45_pct(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Reached 145 (gain 45% >= 40%): runner stop = max(145 - 1.0*2.0=143.0, 100 + 0.75*45=133.75) = 143.0
        res = compute_dynamic_atr_exit(entry_price=100.0, current_price=144.0, highest_price=145.0, atr=2.0)
        assert res.ratchet_stage == "RUNNER_LOCK"
        assert res.tier == 4
        assert res.stop_price == 143.0
        assert res.locked_profit_pct == 43.0
        assert not res.should_exit

        # Drops to 142.5 <= 143.0: triggers runner lock exit
        res_exit = compute_dynamic_atr_exit(entry_price=100.0, current_price=142.5, highest_price=145.0, atr=2.0)
        assert res_exit.should_exit
        assert res_exit.exit_type == "TRAILING_PROFIT"
        assert "RUNNER_LOCK" in res_exit.rationale

    def test_monotonic_stop_never_decreases(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Previously active stop was 116.0
        # If ATR suddenly spikes from 2.0 to 10.0, formula might suggest 120 - 2.0*10 = 100.0
        # But previous_stop_price ensures stop remains at least 116.0
        res = compute_dynamic_atr_exit(
            entry_price=100.0,
            current_price=118.0,
            highest_price=120.0,
            atr=10.0,
            previous_stop_price=116.0,
        )
        assert res.stop_price >= 116.0

    def test_tier0_initial_stop_preserves_volatility_noise_buffer_against_narrow_support(self):
        from src.services.exit_compositor_service import compute_dynamic_atr_exit

        # Entry at $160, ATR = $4.80. Normal initial stop = 160 - 2.0*4.80 = $150.40 (-6%)
        # Suppose institutional support is detected at $158.50 (just 0.9% below entry).
        # Without protection, support_stop = 158.50 * 0.992 = $157.23 (-1.7% from entry).
        # A -2.31% normal intraday noise pullback (to $156.30) would get stopped out!
        # With volatility noise buffer protection, Tier 0 requires at least 1.5x ATR (or 4.5%):
        # max_allowed_stop = 160 - max(1.5*4.8=7.2, 160*0.045=7.2) = $152.80.
        res = compute_dynamic_atr_exit(
            entry_price=160.0,
            current_price=156.30,  # -2.31% intraday pullback
            highest_price=160.5,   # Just entered, peak < 5%
            atr=4.80,
            institutional_support_price=158.50,
        )
        # Should NOT exit on normal -2.31% intraday pullback!
        assert res.should_exit is False
        assert res.exit_type == "HOLD"
        assert res.ratchet_stage == "INITIAL"
        assert res.stop_price <= 152.80



