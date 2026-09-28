"""
Behavior-Driven Development (BDD) Scenarios: Event Impact Bias Loop.
行為驅動開發 (BDD) 測試規格：事件量化抽取與交易評分偏置閉環（嚴格區分個經與總經）。
====================================================================================
Aligned with User Directives:
1. 「我信件收到要販售 nike 通報，所以這回如何影響系統的行動... 任何被判斷的事件都要有下一步行動或是對下一件事有加權效果」
2. 「注意要分為個經和總經的差異」
3. Rule #0: 靜默失敗防治 (Fail-Silent Prevention)
"""

from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine

from src.domain.event_impact import EventImpact, EventScope, EventSentiment
from src.repositories.event_impact_repository import AlchemyEventImpactRepository
from src.services.event_impact_service import EventImpactService
from src.services.exit_compositor_service import ExitCompositorService
from src.services.confidence_compositor_service import CompositorService, AgentSubScore
from src.services.opportunity_cost_service import OpportunityCostService


class TestBddEventImpactBiasLoop:
    """
    Feature: 事件量化抽取與交易評分偏置閉環 (Event Impact Bias Loop)
    """

    @pytest.fixture
    def test_env(self):
        """Set up in-memory database and shared services."""
        engine = create_engine("sqlite:///:memory:")
        repo = AlchemyEventImpactRepository(engine=engine)
        user_id = "bdd_test_user"
        svc = EventImpactService(user_id=user_id, repository=repo)
        return {"repo": repo, "service": svc, "user_id": user_id, "engine": engine}

    @pytest.mark.asyncio
    async def test_bdd_scenario_nike_downgrade_biases_exit_and_buy_decisions(self, test_env):
        """
        Scenario 1: Nike (NKE) 收到美國銀行降評事件通知後，實質在後續出場評估中注入利空並設立風險地板
        """
        svc = test_env["service"]
        user_id = test_env["user_id"]

        # ── Given ──
        # Ingest Nike downgrade event via EventImpactService
        svc.record_event_impact(
            scope=EventScope.MICRO,
            ticker="NKE",
            headline="Bank of America Downgrades Nike to Underperform",
            summary="Lower margins and competition from On and Hoka",
            category="analyst_rating",
            sentiment=EventSentiment.BEARISH,
            initial_impact=-1.5,
        )

        # Verify micro bias is immediately queryable
        bias, active_evts = svc.get_ticker_micro_bias("NKE")
        assert bias == -1.50
        assert len(active_evts) == 1

        # ── When: ExitCompositor evaluates existing NKE holding ──
        exit_svc = ExitCompositorService(user_id=user_id)
        # Mock repository/market calls to return stable mock data
        with patch.object(exit_svc, "_score_risk", new_callable=AsyncMock) as mock_risk:
            mock_risk.return_value = (5.0, {"key_factor": "Neutral risk", "rationale": "Base line"})

            with patch("src.services.event_impact_service.EventImpactService", return_value=svc):
                exit_decision = await exit_svc.score_exit(
                    ticker="NKE",
                    quantity=50.0,
                    current_price=75.0,
                    current_weight_pct=15.0,
                    open_price=90.0,  # -16.6% loss
                    reason_hint="Periodic holding review for NKE",
                )

        # ── Then ──
        # 1. Risk factor must enforce the event risk floor: 5.0 + abs(-1.5) * 2.0 = 8.0
        risk_breakdown = next(b for b in exit_decision["breakdown"] if b["factor_key"] == "risk")
        assert risk_breakdown["confidence"] >= 8.0
        assert risk_breakdown["factors"]["event_bias_floor_applied"] is True
        assert risk_breakdown["factors"]["active_event_bias"] == -1.5

        # 2. OpportunityCostService recognizes the holding's negative bias
        opp_svc = OpportunityCostService()
        swap_res = opp_svc.evaluate_swap(
            holding_ticker="NKE",
            candidate_ticker="ONON",
            holding_score=6.0,
            candidate_score=7.5,
            holding_state={"event_bias": bias},
        )
        # Effective holding score becomes 6.0 + (-1.5) = 4.5. Raw delta is 7.5 - 4.5 = 3.0
        assert swap_res.raw_delta == 3.0
        assert swap_res.should_swap is True
        assert "遭遇重大負面事件衝擊" in swap_res.reason

    def test_bdd_scenario_exponential_time_decay_recovers_impact(self, test_env):
        """
        Scenario 2: 事件影響力依半衰期 (36小時) 指數衰減，自然恢復至中性，杜絕永久偏見
        """
        svc = test_env["service"]
        now = datetime.now(timezone.utc)

        # Record event
        imp = svc.record_event_impact(
            scope=EventScope.MICRO,
            ticker="NKE",
            headline="Negative news shock",
            initial_impact=-1.5,
            half_life_hours=36.0,
        )

        # At t=0
        delta_0, _ = svc.get_ticker_micro_bias("NKE", at_time=now)
        assert delta_0 == -1.50

        # At t=36h (1 half-life): 50% remaining
        t_36h = now + timedelta(hours=36)
        delta_36, _ = svc.get_ticker_micro_bias("NKE", at_time=t_36h)
        assert delta_36 == -0.75

        # At t=72h (2 half-lives): 25% remaining
        t_72h = now + timedelta(hours=72)
        delta_72, _ = svc.get_ticker_micro_bias("NKE", at_time=t_72h)
        assert delta_72 == -0.38

        # At t=144h (4 half-lives): decays below threshold, returns 0.0
        t_144h = now + timedelta(hours=144)
        delta_144, active_144 = svc.get_ticker_micro_bias("NKE", at_time=t_144h)
        assert delta_144 == 0.0
        assert len(active_144) == 0

    @pytest.mark.asyncio
    async def test_bdd_scenario_macro_systemic_event_protects_cash_without_penalizing_stock_alpha(self, test_env):
        """
        Scenario 3: 總經重大事件（如 FOMC 升息或通膨暴衝）提高整體現金儲備，絕不重覆懲罰單一個股 Alpha
        """
        svc = test_env["service"]
        user_id = test_env["user_id"]

        # ── Given ──
        # Record a Macro Systemic Shock (stress = -0.80)
        svc.record_event_impact(
            scope=EventScope.MACRO,
            headline="FOMC Raises Rates by 50bps Unexpectedly",
            category="monetary_policy",
            sentiment=EventSentiment.BEARISH,
            initial_impact=-0.8,
            half_life_hours=96.0,
        )

        # ── When: Checking individual stock micro alpha ──
        nvda_bias, nvda_events = svc.get_ticker_micro_bias("NVDA")
        aapl_bias, aapl_events = svc.get_ticker_micro_bias("AAPL")

        # ── Then: Stock alphas are NOT tainted by macro shock ──
        assert nvda_bias == 0.0
        assert aapl_bias == 0.0
        assert len(nvda_events) == 0
        assert len(aapl_events) == 0

        # ── When: Compositor calculates cash reserve factor ──
        compositor = CompositorService(user_id=user_id)
        with patch("src.services.event_impact_service.EventImpactService", return_value=svc):
            # Base high-confidence reserve is 0.20 (20%)
            # Macro stress is -0.80 -> extra cash reserve = 0.80 * 0.15 = 0.12 (+12%)
            # Total cash reserve should become 0.20 + 0.12 = 0.32 (32%)
            reserve_factor = compositor._compute_cash_reserve_factor(composite_score=8.5, cash_ratio=0.15)
            assert reserve_factor == 0.32
