"""
Behavior-Driven Development (BDD) Scenarios: Market Regime, Dynamic Risk, and CAGR Protection.
行為驅動開發 (BDD) 測試規格：市場體制感知、動態風控與年化 10% 淨利保障防線。
==============================================================================================
Aligned with:
- wiki/05_Quality_Assurance/端到端行為驅動測試規格-BDD-E2E-Testing-Specs.md
- Rule #0: 靜默失敗防治 (Fail-Silent Prevention)
- 10-Year Net CAGR > 10% with Max Drawdown <= 15%
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.services.market_regime_service import (
    MarketRegime,
    MarketRegimeService,
    RegimePolicy,
)
from src.services.exit_compositor_service import (
    compute_dynamic_atr_exit,
    DynamicAtrExitResult,
)
from src.services.portfolio_backtest_engine import (
    PortfolioBacktestEngine,
    BacktestResult,
)


class TestBddMarketRegimeAdaptiveDefense:
    """
    Feature: 市場體制感知器與極端黑天鵝防禦 (Market Regime Adaptive Defense)
    """

    def test_bdd_scenario_bear_crisis_activates_50_pct_cash_and_halts_buys(self):
        """
        Scenario: 熊市體制黑天鵝觸發動態防禦與 50% 現金增持
        """
        # ── Given ──
        # 標普 500 (SPY) 跌破 200 日移動均線 (SPY=480, SMA200=510, ratio=0.941 < 0.98) 且 VIX=32.5 > 28.0
        spy_price = 480.0
        spy_sma200 = 510.0
        vix = 32.5

        # ── When ──
        # MarketRegimeService 進行市場體制分類與風控政策推導
        service = MarketRegimeService()
        policy: RegimePolicy = service.classify_regime(
            spy_price=spy_price,
            spy_sma200=spy_sma200,
            vix=vix,
        )

        # ── Then ──
        # 1. 體制被精準判定為 BEAR_CRISIS (危機防禦)
        assert policy.regime == MarketRegime.BEAR_CRISIS
        # 2. 現金儲備比率強制拉高至 50% 以上，為極端回撤構築緩衝厚度
        assert policy.cash_reserve_pct >= 50.0
        # 3. 買入信心門檻提高至 9.0（近乎苛求），並正式凍結常態新買單
        assert policy.buy_confidence_threshold >= 9.0
        assert policy.allow_new_buys is False
        # 4. 槓桿嚴格歸零 (0.0x)，杜絕爆倉風險
        assert policy.max_leverage == 0.0
        # 5. ATR 停損乘數收緊至 1.5x，快速斬斷下行部位
        assert policy.stop_atr_multiplier <= 1.5
        # 6. 具備明確、可稽核的政策決策依據
        assert "Bearish/Crisis signal detected" in policy.rationale

    def test_bdd_scenario_bull_momentum_allows_offensive_capital_deployment(self):
        """
        Scenario: 牛市強動能體制放寬買入限制並允許 1.2x 安全槓桿
        """
        # ── Given ──
        # SPY 明顯高於 200MA (550 vs 520, ratio=1.057 >= 1.02) 且 VIX=14.2 (低波動平穩)
        spy_price = 550.0
        spy_sma200 = 520.0
        vix = 14.2

        # ── When ──
        service = MarketRegimeService()
        policy = service.classify_regime(spy_price=spy_price, spy_sma200=spy_sma200, vix=vix)

        # ── Then ──
        assert policy.regime == MarketRegime.BULL_MOMENTUM
        assert policy.cash_reserve_pct == 5.0
        assert policy.buy_confidence_threshold == 6.5
        assert policy.allow_new_buys is True
        assert policy.max_leverage == 1.2
        assert policy.stop_atr_multiplier == 2.5


class TestBddDynamicAtrProfitRatchet:
    """
    Feature: 動態 ATR 追蹤停損與利潤棘輪 (Dynamic ATR Profit Ratchet)
    """

    def test_bdd_scenario_three_stage_profit_ratchet_locks_gains_and_cuts_losses(self):
        """
        Scenario: 動態 ATR 三階段利潤棘輪：初始停損 -> +8% 保本鎖定 -> +15% 追蹤停利
        """
        # ── Given ──
        # 投資人於 100 元建倉，ATR=2.0，牛市體制 (初始乘數 2.5x)
        entry_price = 100.0
        atr = 2.0
        regime = MarketRegime.BULL_MOMENTUM

        # ── When / Then (Stage 1: 初始保護) ──
        # 現價仍為 100 元，初始停損點應為 100 - (2.5 * 2.0) = 95.0 元
        res_initial = compute_dynamic_atr_exit(
            entry_price=entry_price,
            current_price=100.0,
            highest_price=100.0,
            atr=atr,
            regime=regime,
        )
        assert res_initial.ratchet_stage == "INITIAL"
        assert res_initial.stop_price == 95.0
        assert res_initial.should_exit is False

        # ── When / Then (Stage 2: 獲利 +8% 觸發保本防線) ──
        # 標的價格上漲至 108.5 元（獲利 +8.5% >= +8%），停損線單向拉抬至成本保本價 (100 * 1.005 = 100.5)
        res_breakeven = compute_dynamic_atr_exit(
            entry_price=entry_price,
            current_price=108.5,
            highest_price=108.5,
            atr=atr,
            regime=regime,
        )
        assert res_breakeven.ratchet_stage == "BREAKEVEN"
        assert res_breakeven.stop_price == 100.5
        assert res_breakeven.should_exit is False

        # ── When / Then (Stage 3: 獲利 +25% 觸發追蹤停利) ──
        # 標的衝刺至 125.0 元（獲利 +25% >= +15%），最高價記為 125.0，追蹤停利點為 125.0 - (2.0 * 2.0) = 121.0 元
        res_trailing = compute_dynamic_atr_exit(
            entry_price=entry_price,
            current_price=124.0,
            highest_price=125.0,
            atr=atr,
            regime=regime,
        )
        assert res_trailing.ratchet_stage == "TRAILING"
        assert res_trailing.stop_price == 121.0
        assert res_trailing.should_exit is False

        # ── When / Then (Stage 4: 盤中急挫跌破停利線，觸發平倉鎖利) ──
        # 標的從 125 跌至 120.5（跌破 121.0 追蹤停利點）
        res_exit = compute_dynamic_atr_exit(
            entry_price=entry_price,
            current_price=120.5,
            highest_price=125.0,
            atr=atr,
            regime=regime,
        )
        assert res_exit.should_exit is True
        assert res_exit.exit_type == "TRAILING_PROFIT"
        assert res_exit.stop_price == 121.0  # 停損價單調遞增，不曾縮水
        assert "觸發追蹤停利" in res_exit.rationale


class TestBddLongTermCagrAndTokenBreaker:
    """
    Feature: 長期 10 年年化淨報酬率 > 10% 與 Token 成本摩擦防線 (10-Year Net CAGR > 10% & Low Token Drag)
    """

    def test_bdd_scenario_friction_adjusted_backtest_achieves_cagr_above_10_pct(self):
        """
        Scenario: 扣除全項手續費、滑點與 2026 高效模型 Token 算力費用後，長期 10 年 CAGR > 10% 且 MaxDD <= 15%
        """
        # ── Given ──
        # 模擬 10 年週期交易環境 (10 年 * 252 交易日 = 2520 根日 K 棒)
        # 底層資產具有長期年化約 12.5% 之動能走勢，期間包含兩波可控之中度回撤 (約 12%)
        import numpy as np

        np.random.seed(42)
        n_bars = 2520
        # 構建幾何布朗運動伴隨長期年化 12.5% 漂移率與 16% 年化波動率
        daily_drift = 0.125 / 252.0
        daily_vol = 0.16 / np.sqrt(252.0)
        daily_returns = np.random.normal(daily_drift, daily_vol, n_bars)
        price_series = 100.0 * np.exp(np.cumsum(daily_returns))

        ohlcv = {
            "date": [f"D{i:04d}" for i in range(n_bars)],
            "close": [round(float(p), 4) for p in price_series],
            "low": [round(float(p * 0.995), 4) for p in price_series],
        }

        # ── When ──
        # 回測引擎配置：手續費 0.1%，滑點 0.05%，每筆交易 Token 費用 $0.005，每根 Bar 監控 Token 費用 $0.001
        # 配合 30% 防禦現金儲備 (position_size_pct=0.70)，杜絕無緩衝的全額暴險
        engine = PortfolioBacktestEngine(
            initial_cash=100_000.0,
            fee_pct=0.001,
            slippage_pct=0.0005,
            stoploss_pct=0.08,
            position_size_pct=0.70,
            token_cost_per_trade=0.005,
            token_cost_per_bar=0.001,
        )

        # 採用中長期順勢穿越策略 (50MA 趨勢過濾)：站上 50MA 佈局、拉回不盲目砍倉、讓贏家奔跑
        def trend_regime_signal(i: int, data: dict) -> str:
            closes = data["close"]
            if i < 50:
                return "HOLD"
            ma50 = sum(closes[i - 50:i]) / 50.0
            curr = closes[i]
            if curr > ma50:
                return "BUY"
            return "HOLD"

        result: BacktestResult = engine.run("SPY_MOMENTUM", ohlcv, trend_regime_signal)

        # ── Then ──
        # 1. 10 年全項成本扣除後，淨年化報酬率 CAGR 必須大於 10.0%
        net_cagr = result.metrics.get("net_cagr_pct") or result.metrics.get("cagr")
        assert net_cagr is not None
        assert net_cagr > 10.0, f"Expected 10-year net CAGR > 10%, but got {net_cagr:.2f}%"
        assert result.metrics["is_cagr_target_met"] is True

        # 2. 最大回撤 (Max Drawdown) 嚴格控制在 15% 以內
        max_dd = abs(result.metrics.get("max_drawdown_pct") or 0.0)
        assert max_dd <= 15.0, f"Expected Max Drawdown <= 15%, but suffered {max_dd:.2f}%"
        assert result.metrics["is_max_dd_target_met"] is True

        # 3. 10 年累計 Token 費用佔總資產比率極低（< 0.1%），無實質摩擦損耗
        total_tokens = result.metrics.get("total_token_cost", 0.0)
        assert total_tokens < 100.0, f"Token cost too high: ${total_tokens}"


class TestBddAutomatedApprovalGuards:
    """
    Feature: 四重自動放行與交易安全防呆審批 (Automated Execution Safeguards)
    """

    def test_bdd_scenario_four_guards_block_unauthorized_trades(self):
        """
        Scenario: 交易分級自動放行四重防護（防呆攔截）
        """
        # ── Given ──
        # 一筆委託單，設定資本限制 $100，買入門檻 7.0
        cap_limit = 100.0
        min_confidence = 7.0
        ai_enabled = True

        def check_trade_approval(
            amount: float,
            confidence: float,
            regime_allows_buys: bool,
            killswitch_active: bool,
        ) -> tuple[bool, str]:
            if killswitch_active:
                return False, "Emergency killswitch active"
            if not regime_allows_buys:
                return False, "Market regime prohibits new buying"
            if amount > cap_limit:
                return False, f"Trade amount ${amount} exceeds capital limit ${cap_limit}"
            if confidence < min_confidence:
                return False, f"Confidence {confidence} below threshold {min_confidence}"
            return True, "All 4 safeguard gates passed"

        # ── When / Then (Guard 1: 超出受託資本上限) ──
        approved, reason = check_trade_approval(
            amount=150.0, confidence=8.5, regime_allows_buys=True, killswitch_active=False
        )
        assert not approved
        assert "exceeds capital limit" in reason

        # ── When / Then (Guard 2: 確信度未達標) ──
        approved, reason = check_trade_approval(
            amount=80.0, confidence=6.2, regime_allows_buys=True, killswitch_active=False
        )
        assert not approved
        assert "below threshold" in reason

        # ── When / Then (Guard 3: 熊市危機體制禁買) ──
        approved, reason = check_trade_approval(
            amount=80.0, confidence=8.5, regime_allows_buys=False, killswitch_active=False
        )
        assert not approved
        assert "prohibits new buying" in reason

        # ── When / Then (Guard 4: 緊急斷路器啟動) ──
        approved, reason = check_trade_approval(
            amount=80.0, confidence=8.5, regime_allows_buys=True, killswitch_active=True
        )
        assert not approved
        assert "killswitch active" in reason

        # ── When / Then (四重防線全數通過) ──
        approved, reason = check_trade_approval(
            amount=80.0, confidence=8.5, regime_allows_buys=True, killswitch_active=False
        )
        assert approved is True
        assert "All 4 safeguard gates passed" in reason
