"""
Behavior-Driven Development (BDD) Scenarios: State-Driven Decisions & Opportunity Cost.
行為驅動開發 (BDD) 測試規格：狀態驅動買賣決策與機會成本換庫防線。
====================================================================================
Aligned with:
- User Directive: 集中權重損害高但相對報酬也較高，應由標的當下狀態決定買賣，
  且買賣跟機會成本有關，而不是和持倉比例有關。
- Rule #0: 靜默失敗防治 (Fail-Silent Prevention)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.opportunity_cost_service import (
    OpportunityCostService,
    SwapDecision,
)
from src.services.confidence_rebalance_service import ConfidenceRebalanceService
from src.services.exit_compositor_service import ExitCompositorService


class TestBddStateDrivenWinnerPreservation:
    """
    Feature: 狀態驅動之贏家保護機制 (State-Driven Winner Protection)
    """

    @pytest.mark.asyncio
    async def test_bdd_scenario_high_weight_healthy_winner_is_preserved_from_mechanical_selling(self):
        """
        Scenario: 高權重持倉 (如 46% TSM) 狀態良好時，系統拒絕機械式強平，保護贏家持續複利
        """
        # ── Given ──
        from src.services.long_term_winner_service import WinnerAssessment, ProtectionStatus
        rbs = ConfidenceRebalanceService(user_id="test_owner")
        rbs.ticker_service = MagicMock()
        rbs.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [
                {"ticker": "TSM", "target_weight": 0.1192, "confidence_score": 0.669},
                {"ticker": "AAPL", "target_weight": 0.1210, "confidence_score": 0.686},
            ],
        }

        mock_assessment = WinnerAssessment(
            ticker="TSM",
            is_long_term_winner=True,
            has_short_term_opportunity_cost=False,
            status=ProtectionStatus.FULL_PROTECT_COMPOUNDING,
            long_term_score=8.5,
            short_term_momentum_score=8.5,
            long_term_reasons=["股價高於 200MA 多頭結構", "品質評分優良"],
            short_term_reasons=["動能強勁無死錢疑慮"],
            action_summary="全額保護複利",
        )
        rbs.winner_service.evaluate_winner = AsyncMock(return_value=mock_assessment)

        mock_weights = {
            "weights": {
                "TSM": 46.47,     # 佔比高達 46% 的超額贏家
                "AAPL": 10.00,    # 輕微未滿額
                "DEAD_STOCK": 5.0 # 死資本
            },
            "cash_weight": 5.0,
            "total_value": 1000.0,
        }

        # ── When ──
        # 系統執行再平衡規劃
        with patch.object(rbs, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rbs.get_rebalance_plan()

        # ── Then ──
        # 1. 成功生成規劃
        assert plan["success"] is True
        sells = plan["trades"]["sells"]
        holding_runners = plan["trades"]["holding_runners"]

        # 2. TSM 絕不出現在賣出清單中！(保護鮮花不被砍)
        sell_tickers = [s["ticker"] for s in sells]
        assert "TSM" not in sell_tickers, "TSM should NOT be sold just because its weight is 46%!"

        # 3. TSM 被精準歸類在 holding_runners，行動標記為 HOLD_COMPOUNDING
        runner_tickers = [h["ticker"] for h in holding_runners]
        assert "TSM" in runner_tickers
        tsm_item = next(h for h in holding_runners if h["ticker"] == "TSM")
        assert tsm_item["action"] == "HOLD_COMPOUNDING"
        assert "不砍贏家" in tsm_item["reason"]

        # 4. 非核心死資本 DEAD_STOCK 被正確識別為賣出
        assert "DEAD_STOCK" in sell_tickers

    @pytest.mark.asyncio
    async def test_bdd_scenario_low_weight_broken_holding_is_promptly_liquidated(self):
        """
        Scenario: 低權重持倉 (如 2% 垃圾股) 論點破壞時立即清退，不因佔比微小而縱容
        """
        # ── Given ──
        # 一檔佔比僅 2% 的微型持倉 BAD_MICRO，已自目標池剔除 (確信度為 0)
        rbs = ConfidenceRebalanceService(user_id="test_owner")
        rbs.ticker_service = MagicMock()
        rbs.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [{"ticker": "NVDA", "target_weight": 0.20, "confidence_score": 0.85}],
        }

        mock_weights = {
            "weights": {"BAD_MICRO": 2.00, "NVDA": 18.00},
            "cash_weight": 80.0,
            "total_value": 1000.0,
        }

        # ── When ──
        with patch.object(rbs, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rbs.get_rebalance_plan()

        # ── Then ──
        sells = plan["trades"]["sells"]
        sell_tickers = [s["ticker"] for s in sells]
        # 即使只有 2%，也必須堅決賣出釋放資本
        assert "BAD_MICRO" in sell_tickers
        item = next(s for s in sells if s["ticker"] == "BAD_MICRO")
        assert item["is_pruning"] is True
        assert item["target_weight"] == 0.0


class TestBddOpportunityCostEngine:
    """
    Feature: 機會成本評估與資本置換門檻 (Opportunity Cost & Swap Hurdle)
    """

    def test_bdd_scenario_swap_rejected_when_score_delta_below_hurdle(self):
        """
        Scenario: 候選標的評分優勢未達機會成本門檻時拒絕換庫，避免白付摩擦手續費
        """
        # ── Given ──
        # 現有持倉 TSM 評分 7.2，候選標的 INTC 評分 8.0 (差距 +0.8 < 門檻 2.0)
        svc = OpportunityCostService(min_score_delta=2.0)

        # ── When ──
        decision: SwapDecision = svc.evaluate_swap(
            holding_ticker="TSM",
            candidate_ticker="INTC",
            holding_score=7.2,
            candidate_score=8.0,
        )

        # ── Then ──
        # 換庫被否決，維持持有現有標的
        assert decision.should_swap is False
        assert "未達換庫門檻" in decision.reason

    def test_bdd_scenario_swap_approved_when_candidate_has_significant_opportunity_advantage(self):
        """
        Scenario: 候選標的評分顯著超越現有標的 (Delta >= 2.0)，依機會成本原則放行置換
        """
        # ── Given ──
        # 現有持倉 STALE 評分 5.5，候選標的 SUPER_AI 評分 8.8 (差距 +3.3 >= 門檻 2.0)
        svc = OpportunityCostService(min_score_delta=2.0)

        # ── When ──
        decision = svc.evaluate_swap(
            holding_ticker="STALE",
            candidate_ticker="SUPER_AI",
            holding_score=5.5,
            candidate_score=8.8,
        )

        # ── Then ──
        # 換庫獲准，將資本導向更高邊際效用標的
        assert decision.should_swap is True
        assert decision.net_opportunity_delta >= 2.0
        assert "依機會成本原則放行置換" in decision.reason


class TestBddExitCompositorWinningRunnerSoftening:
    """
    Feature: 出場評分器對獲利奔跑者之集中度脫敏
    """

    @pytest.mark.anyio
    async def test_bdd_scenario_winning_runner_concentration_does_not_trigger_exit(self):
        """
        Scenario: 獲利中且趨勢走強之部位即使超過 25% 上限，集中度因子保持低值，不觸發賣出
        """
        # ── Given ──
        # 持有標的獲利 +15% 且權重達 45% (上限 25%)，開啟贏家保護設定
        settings_mock = MagicMock()
        settings_mock.get_setting.side_effect = lambda k, d=None, *a, **kws: {
            "max_single_position_weight": 25.0,
            "protect_winning_compounders": True,
        }.get(k, d)

        market_mock = MagicMock()
        market_mock.get_ohlcv.return_value = {"close": [100.0] * 19 + [115.0]}

        svc = ExitCompositorService(user_id="test_user", settings_service=settings_mock, market_service=market_mock)
        svc._open_lots = MagicMock(return_value=[{"quantity": 1.0, "open_price": 100.0}])
        svc._llm._score_via_llm = AsyncMock(return_value=(2.0, {"key_factor": "無風險"}))

        # ── When ──
        # 現價 115 元 (獲利 +15%)，權重 45%
        decision = await svc.score_exit(
            ticker="TSM",
            quantity=1.0,
            current_price=115.0,
            current_weight_pct=45.0,
        )

        # ── Then ──
        # 集中度評分被軟化至 4.0 以下（非 10.0 極限值）
        conc_factor = next(b for b in decision["breakdown"] if b["factor_key"] == "concentration")
        assert conc_factor["confidence"] <= 4.0
        assert conc_factor["factors"]["winner_protected"] is True

        # 總出場急迫度評分維持低位 (< 4.0)，遠低於 6.0 賣出門檻
        assert decision["composite_score"] < 4.0


class TestBddSmartCashDeployment:
    """
    Feature: 先賣後買之智慧資金再部署閉環 (Smart Cash Deployment)
    """

    @pytest.mark.asyncio
    async def test_bdd_scenario_pruned_dead_capital_seamlessly_funds_underallocated_targets(self):
        """
        Scenario: 清退死資本釋放之現金全數無縫部署至高確信度增持目標，徹底消滅現金拖累
        """
        # ── Given ──
        # 帳戶持有 3 檔死資本 (合計 30% = $300)，現有現金 2% ($20)，
        # 目標池有 2 檔高確信目標 (NVDA, AAPL 各需加碼 15% = $150，合計 $300)
        rbs = ConfidenceRebalanceService(user_id="test_owner")
        rbs.ticker_service = MagicMock()
        rbs.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [
                {"ticker": "NVDA", "target_weight": 0.25, "confidence_score": 0.88},
                {"ticker": "AAPL", "target_weight": 0.25, "confidence_score": 0.82},
            ],
        }

        mock_weights = {
            "weights": {
                "DEAD_A": 10.0,
                "DEAD_B": 10.0,
                "DEAD_C": 10.0,
                "NVDA": 10.0,
                "AAPL": 10.0,
            },
            "cash_weight": 50.0,
            "total_value": 1000.0,
        }

        # ── When ──
        with patch.object(rbs, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rbs.get_rebalance_plan()

        # ── Then ──
        assert plan["success"] is True
        sells = plan["trades"]["sells"]
        buys = plan["trades"]["buys"]

        # 1. 3 檔死資本全數列入賣單
        assert len(sells) == 3
        assert plan["summary"]["total_sell_amount"] == 300.0

        # 2. 2 檔目標股全數列入買單，且每筆買單金額明確大於 broker 門檻 ($10)
        assert len(buys) == 2
        for b in buys:
            assert b["delta_amount"] >= 10.0
            assert b["action"] == "BUY"

        # 3. 資金完全自給自足，現金缺口為 0
        assert plan["summary"]["cash_shortfall"] == 0.0
        assert plan["summary"]["total_buy_amount"] == 300.0


class TestBddLongTermWinnerAndOpportunityCostWorkflow:
    """
    Feature: 中長期贏家深研資格審查與短期機會成本動態防線
    """

    @pytest.mark.asyncio
    async def test_bdd_scenario_certified_long_term_winner_with_healthy_momentum_gets_full_compounding_protection(self):
        """
        Scenario: 經深研認證為中長期結構性贏家且短線動能強勁 (如 TSM)，享有 100% 全額複利保護
        """
        # ── Given ──
        # TSM 當前佔比 20%，目標 10%，經深研確認：股價高於 200MA、高於 20MA、RSI 61、品質分 7.0
        from src.services.long_term_winner_service import LongTermWinnerService, WinnerAssessment, ProtectionStatus
        rbs = ConfidenceRebalanceService(user_id="test_owner")
        rbs.ticker_service = MagicMock()
        rbs.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [{"ticker": "TSM", "target_weight": 0.10, "confidence_score": 0.85}],
        }

        mock_assessment = WinnerAssessment(
            ticker="TSM",
            is_long_term_winner=True,
            has_short_term_opportunity_cost=False,
            status=ProtectionStatus.FULL_PROTECT_COMPOUNDING,
            long_term_score=8.5,
            short_term_momentum_score=9.0,
            long_term_reasons=["股價高於 200MA 多頭結構", "品質把關評分優秀"],
            short_term_reasons=["股價穩居 20MA 之上，動能強勁"],
            action_summary="全額保護複利",
        )
        rbs.winner_service.evaluate_winner = AsyncMock(return_value=mock_assessment)

        mock_weights = {
            "weights": {"TSM": 20.0},
            "cash_weight": 80.0,
            "total_value": 1000.0,
        }

        # ── When ──
        with patch.object(rbs, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rbs.get_rebalance_plan()

        # ── Then ──
        assert plan["success"] is True
        holding_runners = plan["trades"]["holding_runners"]
        sells = plan["trades"]["sells"]

        # TSM 完全不出現在賣單中
        assert not any(s["ticker"] == "TSM" for s in sells)
        # TSM 被歸入 holding_runners，保護等級為 FULL_PROTECT_COMPOUNDING
        assert any(h["ticker"] == "TSM" for h in holding_runners)
        tsm_runner = next(h for h in holding_runners if h["ticker"] == "TSM")
        assert tsm_runner["protection_status"] == "FULL_PROTECT_COMPOUNDING"
        assert tsm_runner["action"] == "HOLD_COMPOUNDING"

    @pytest.mark.asyncio
    async def test_bdd_scenario_long_term_winner_with_stalled_momentum_gets_tactical_excess_trimmed_to_avoid_dead_money(self):
        """
        Scenario: 長線贏家但短線嚴重破線且外部有高確信機會，戰術調節超額部位，杜絕短期死錢拖累
        """
        # ── Given ──
        # STALLED_WINNER 當前佔比 25%，目標 10% (超額 15% = $150)。
        # 長線雖好，但短線跌破 20MA、RSI 陷入弱勢，外部有 8.8 分高動能標的
        from src.services.long_term_winner_service import WinnerAssessment, ProtectionStatus
        rbs = ConfidenceRebalanceService(user_id="test_owner")
        rbs.ticker_service = MagicMock()
        rbs.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [
                {"ticker": "STALLED_WINNER", "target_weight": 0.10, "confidence_score": 0.70},
                {"ticker": "FAST_RUNNER", "target_weight": 0.20, "confidence_score": 0.90},
            ],
        }

        mock_assessment = WinnerAssessment(
            ticker="STALLED_WINNER",
            is_long_term_winner=True,
            has_short_term_opportunity_cost=True,
            status=ProtectionStatus.TRIM_EXCESS_FOR_OPPORTUNITY,
            long_term_score=7.2,
            short_term_momentum_score=4.0,
            long_term_reasons=["股價仍高於 200MA"],
            short_term_reasons=["跌破 20MA，動能停滯", "外部存在更高機會成本標的 FAST_RUNNER"],
            action_summary="戰術調節超額部位，避免死錢拖累",
        )
        rbs.winner_service.evaluate_winner = AsyncMock(return_value=mock_assessment)

        mock_weights = {
            "weights": {"STALLED_WINNER": 25.0, "FAST_RUNNER": 5.0},
            "cash_weight": 70.0,
            "total_value": 1000.0,
        }

        # ── When ──
        with patch.object(rbs, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rbs.get_rebalance_plan()

        # ── Then ──
        sells = plan["trades"]["sells"]
        # 超額部分被戰術調節賣出，避免死錢
        stalled_sell = next((s for s in sells if s["ticker"] == "STALLED_WINNER"), None)
        assert stalled_sell is not None
        assert stalled_sell["is_tactical_trim"] is True
        assert stalled_sell["protection_status"] == "TRIM_EXCESS_FOR_OPPORTUNITY"
        assert stalled_sell["delta_amount"] == -150.0  # (10% - 25%) * 1000 = -$150
        assert "長線核心底倉" in stalled_sell["reason"]

    @pytest.mark.asyncio
    async def test_bdd_scenario_broken_long_term_trend_loses_winner_protection_and_rebalances_normally(self):
        """
        Scenario: 過去上漲但長線技術結構跌破 200MA 之標的，失去贏家資格，回歸普通再平衡
        """
        # ── Given ──
        # BROKEN_STOCK 當前佔比 20%，目標 10%，跌破 200MA 生命線，長線多頭破壞
        from src.services.long_term_winner_service import WinnerAssessment, ProtectionStatus
        rbs = ConfidenceRebalanceService(user_id="test_owner")
        rbs.ticker_service = MagicMock()
        rbs.ticker_service.optimize_allocations.return_value = {
            "success": True,
            "targets": [{"ticker": "BROKEN_STOCK", "target_weight": 0.10, "confidence_score": 0.50}],
        }

        mock_assessment = WinnerAssessment(
            ticker="BROKEN_STOCK",
            is_long_term_winner=False,
            has_short_term_opportunity_cost=True,
            status=ProtectionStatus.NO_PROTECTION_REBALANCE,
            long_term_score=4.5,
            short_term_momentum_score=3.5,
            long_term_reasons=["股價跌破 200 日生命線，長線結構破壞"],
            short_term_reasons=["全面轉弱"],
            action_summary="不具備贏家保護資格",
        )
        rbs.winner_service.evaluate_winner = AsyncMock(return_value=mock_assessment)

        mock_weights = {
            "weights": {"BROKEN_STOCK": 20.0},
            "cash_weight": 80.0,
            "total_value": 1000.0,
        }

        # ── When ──
        with patch.object(rbs, "_get_current_weights", AsyncMock(return_value=mock_weights)):
            plan = await rbs.get_rebalance_plan()

        # ── Then ──
        sells = plan["trades"]["sells"]
        broken_sell = next((s for s in sells if s["ticker"] == "BROKEN_STOCK"), None)
        assert broken_sell is not None
        assert broken_sell["protection_status"] == "NO_PROTECTION_REBALANCE"
        assert broken_sell["action"] == "SELL"
        assert "不具備贏家保護資格" in broken_sell["reason"]


