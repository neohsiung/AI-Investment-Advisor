"""
Unit tests for ShadowPromotionOrchestrator (P5).
================================================
Tests the closed-loop automation of shadow candidate graduation,
opportunity cost hurdles, holding alpha decay, and live portfolio rotation.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
import pytest

from src.services.shadow_promotion_orchestrator import (
    ShadowPromotionOrchestrator,
    PromotionProposal,
    PromotionExecutionResult,
    RotationActionType,
)
from src.services.shadow_ledger_service import GraduationResult
from src.services.opportunity_cost_service import SwapDecision
from src.services.alpha_decay_service import AlphaDecayAssessment


@pytest.fixture
def mock_shadow_repo():
    repo = MagicMock()
    return repo


@pytest.fixture
def mock_ticker_repo():
    repo = MagicMock()
    repo.get_all.return_value = []
    repo.upsert.return_value = True
    repo.add_log.return_value = True
    return repo


@pytest.fixture
def mock_shadow_ledger():
    ledger = MagicMock()
    return ledger


@pytest.fixture
def mock_opportunity_cost():
    svc = MagicMock()
    svc.calculate_roundtrip_friction.return_value = 0.003
    svc.calculate_opportunity_cost_hurdle.return_value = 0.0175
    return svc


@pytest.fixture
def mock_alpha_decay():
    svc = MagicMock()
    svc.calculate_holding_days.return_value = 25
    return svc


@pytest.fixture
def mock_sor_service():
    svc = MagicMock()
    mock_plan = MagicMock()
    mock_plan.symbol = "TEST"
    mock_plan.action.value = "BUY"
    mock_plan.strategy.value = "TWAP"
    mock_plan.total_requested_quantity = 10.0
    mock_plan.approved_quantity = 10.0
    mock_plan.unfilled_rollover_quantity = 0.0
    mock_plan.child_orders = [MagicMock(to_dict=lambda: {"slice_index": 1, "target_quantity": 10.0})]
    svc.generate_plan.return_value = mock_plan
    return svc


@pytest.fixture
def mock_portfolio_aggregator():
    agg = MagicMock()
    return agg


@pytest.fixture
def mock_alert_hub():
    hub = MagicMock()
    hub.dispatch_shadow_promotion_rotation_alert = AsyncMock(return_value={"status": "sent"})
    return hub


@pytest.fixture
def mock_settings():
    st = MagicMock()
    st.get_setting.side_effect = lambda key, default=None: {
        "shadow_auto_rotation_enabled": False,
        "shadow_rotation_min_edge": 0.015,
        "shadow_max_active_positions": 5,
        "rotation_friction_multiplier": 2.5,
        "rotation_hurdle_rate": 0.010,
    }.get(key, default)
    return st


@pytest.fixture
def orchestrator(
    mock_shadow_repo,
    mock_ticker_repo,
    mock_shadow_ledger,
    mock_opportunity_cost,
    mock_alpha_decay,
    mock_sor_service,
    mock_portfolio_aggregator,
    mock_alert_hub,
    mock_settings,
):
    orch = ShadowPromotionOrchestrator(
        user_id="test-user",
        shadow_repo=mock_shadow_repo,
        ticker_repo=mock_ticker_repo,
        shadow_ledger_service=mock_shadow_ledger,
        opportunity_cost_service=mock_opportunity_cost,
        alpha_decay_service=mock_alpha_decay,
        sor_service=mock_sor_service,
        portfolio_aggregator=mock_portfolio_aggregator,
        alert_hub=mock_alert_hub,
        settings_service=mock_settings,
    )
    return orch


@pytest.mark.asyncio
async def test_evaluate_promotions_direct_promotion_when_cash_ample(
    orchestrator,
    mock_shadow_repo,
    mock_shadow_ledger,
    mock_portfolio_aggregator,
):
    """When portfolio has free capacity and ample cash, candidate graduates via DIRECT_PROMOTION."""
    # 1. Shadow position in OPEN state
    mock_shadow_repo.list_positions.return_value = [{
        "id": "shadow-1",
        "ticker": "NVDA",
        "status": "OPEN",
        "allocated_capital": 2000.0,
        "entry_price": 120.0,
        "current_price": 135.0,
    }]

    # 2. Graduation evaluation passes
    mock_shadow_ledger.evaluate_graduation.return_value = GraduationResult(
        ticker="NVDA",
        qualified=True,
        status="QUALIFIED",
        evaluation_days=10,
        unrealized_pnl_pct=12.5,
        max_drawdown_pct=2.1,
        support_breached=False,
        reasons=["All shadow graduation criteria satisfied"],
        metrics={"evaluation_days": 10, "unrealized_pnl_pct": 12.5},
    )

    # 3. Portfolio has 2 holdings (max is 5) and ample cash ($25,000)
    mock_pos1 = MagicMock(symbol="AAPL", market_value=15000.0, quantity=70.0, current_price=210.0, open_date=datetime.now(timezone.utc), unrealized_pnl=500.0)
    mock_pos2 = MagicMock(symbol="MSFT", market_value=15000.0, quantity=35.0, current_price=420.0, open_date=datetime.now(timezone.utc), unrealized_pnl=600.0)
    mock_portfolio_aggregator.get_aggregated_portfolio = AsyncMock(return_value={
        "positions": [mock_pos1, mock_pos2],
        "total_equity": 30000.0,
        "total_cash": 25000.0,
    })

    proposals = await orchestrator.evaluate_promotions()

    assert len(proposals) == 1
    prop = proposals[0]
    assert prop.candidate_ticker == "NVDA"
    assert prop.action_type == RotationActionType.DIRECT_PROMOTION.value
    assert prop.qualified is True
    assert prop.displaced_ticker is None
    assert len(prop.sor_plans) == 1
    assert "直接提拔為實盤開倉" in prop.rationale


@pytest.mark.asyncio
async def test_evaluate_promotions_capital_rotation_displaces_decaying_holding(
    orchestrator,
    mock_shadow_repo,
    mock_shadow_ledger,
    mock_portfolio_aggregator,
    mock_alpha_decay,
    mock_opportunity_cost,
):
    """When portfolio is at capacity, candidate replaces decaying holding that clears hurdle."""
    mock_shadow_repo.list_positions.return_value = [{
        "id": "shadow-2",
        "ticker": "TSLA",
        "status": "OPEN",
        "allocated_capital": 2500.0,
        "entry_price": 200.0,
        "current_price": 230.0,
    }]

    mock_shadow_ledger.evaluate_graduation.return_value = GraduationResult(
        ticker="TSLA",
        qualified=True,
        status="QUALIFIED",
        evaluation_days=14,
        unrealized_pnl_pct=15.0,
        max_drawdown_pct=3.0,
        support_breached=False,
        reasons=["Qualified"],
        metrics={"evaluation_days": 14, "unrealized_pnl_pct": 15.0},
    )

    # 5 active holdings (at capacity = 5), very low cash ($50.0)
    active_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "INTC"]
    positions = [
        MagicMock(symbol=sym, market_value=10000.0, quantity=50.0, current_price=200.0, open_date=datetime.now(timezone.utc) - timedelta(days=35), unrealized_pnl=-200.0)
        for sym in active_symbols
    ]
    mock_portfolio_aggregator.get_aggregated_portfolio = AsyncMock(return_value={
        "positions": positions,
        "total_equity": 50000.0,
        "total_cash": 50.0,
    })

    # INTC is stagnant and suffers alpha decay
    def mock_holding_decay(ticker, **kwargs):
        if ticker == "INTC":
            return AlphaDecayAssessment(
                ticker="INTC",
                holding_days=35,
                has_decay=True,
                decay_factor=0.50,
                is_stagnant=True,
                reason="持倉超過 20 日且下破均線，Alpha 鈍化",
            )
        return AlphaDecayAssessment(
            ticker=ticker,
            holding_days=20,
            has_decay=False,
            decay_factor=1.0,
            is_stagnant=False,
            reason="動能健康",
        )

    mock_alpha_decay.evaluate_holding_decay.side_effect = mock_holding_decay

    def mock_eval_swap(holding_ticker, candidate_ticker, **kwargs):
        if holding_ticker == "INTC":
            return SwapDecision(
                should_swap=True,
                holding_ticker="INTC",
                candidate_ticker="TSLA",
                holding_score=3.0,
                candidate_score=9.0,
                raw_delta=6.0,
                net_opportunity_delta=0.045,  # 4.5% net advantage > 1.75% hurdle
                friction_hurdle=0.0175,
                reason="利差顯著跨越機會成本門檻",
                roundtrip_friction=0.003,
            )
        return SwapDecision(
            should_swap=False,
            holding_ticker=holding_ticker,
            candidate_ticker="TSLA",
            holding_score=8.0,
            candidate_score=9.0,
            raw_delta=1.0,
            net_opportunity_delta=0.005,  # 0.5% < 1.75% hurdle
            friction_hurdle=0.0175,
            reason="未達非線性機會成本門檻",
            roundtrip_friction=0.003,
        )

    mock_opportunity_cost.evaluate_swap.side_effect = mock_eval_swap

    proposals = await orchestrator.evaluate_promotions()

    assert len(proposals) == 1
    prop = proposals[0]
    assert prop.candidate_ticker == "TSLA"
    assert prop.action_type == RotationActionType.CAPITAL_ROTATION.value
    assert prop.qualified is True
    assert prop.displaced_ticker == "INTC"
    assert prop.displaced_metrics["has_decay"] is True
    assert prop.net_opportunity_delta == 0.045
    assert len(prop.sor_plans) == 2  # SELL INTC, BUY TSLA


@pytest.mark.asyncio
async def test_evaluate_promotions_blocked_by_hurdle_when_no_weak_holding(
    orchestrator,
    mock_shadow_repo,
    mock_shadow_ledger,
    mock_portfolio_aggregator,
    mock_alpha_decay,
    mock_opportunity_cost,
):
    """When portfolio is full but all holdings are strong leaders, swap is BLOCKED_BY_HURDLE."""
    mock_shadow_repo.list_positions.return_value = [{
        "id": "shadow-3",
        "ticker": "AMD",
        "status": "OPEN",
        "allocated_capital": 1000.0,
        "entry_price": 150.0,
        "current_price": 158.0,
    }]

    mock_shadow_ledger.evaluate_graduation.return_value = GraduationResult(
        ticker="AMD",
        qualified=True,
        status="QUALIFIED",
        evaluation_days=8,
        unrealized_pnl_pct=5.3,
        max_drawdown_pct=1.8,
        support_breached=False,
        reasons=["Qualified"],
        metrics={"evaluation_days": 8, "unrealized_pnl_pct": 5.3},
    )

    # 5 positions, zero cash
    positions = [
        MagicMock(symbol=sym, market_value=10000.0, quantity=50.0, current_price=200.0, open_date=datetime.now(timezone.utc), unrealized_pnl=1200.0)
        for sym in ["NVDA", "AAPL", "MSFT", "META", "AMZN"]
    ]
    mock_portfolio_aggregator.get_aggregated_portfolio = AsyncMock(return_value={
        "positions": positions,
        "total_equity": 50000.0,
        "total_cash": 0.0,
    })

    # None have decay
    mock_alpha_decay.evaluate_holding_decay.return_value = AlphaDecayAssessment(
        ticker="LEADER",
        holding_days=15,
        has_decay=False,
        decay_factor=1.0,
        is_stagnant=False,
        reason="強勁動能",
    )

    # All swaps fail the hurdle
    mock_opportunity_cost.evaluate_swap.return_value = SwapDecision(
        should_swap=False,
        holding_ticker="LEADER",
        candidate_ticker="AMD",
        holding_score=8.5,
        candidate_score=8.0,
        raw_delta=-0.5,
        net_opportunity_delta=-0.015,
        friction_hurdle=0.0175,
        reason="換手利差不足",
    )

    proposals = await orchestrator.evaluate_promotions()

    assert len(proposals) == 1
    prop = proposals[0]
    assert prop.candidate_ticker == "AMD"
    assert prop.action_type == RotationActionType.BLOCKED_BY_HURDLE.value
    assert prop.qualified is True
    assert prop.displaced_ticker is None
    assert prop.can_auto_execute is False
    assert "未達非線性機會成本門檻" in prop.rationale


@pytest.mark.asyncio
async def test_evaluate_promotions_skips_pinned_holdings(
    orchestrator,
    mock_shadow_repo,
    mock_shadow_ledger,
    mock_ticker_repo,
    mock_portfolio_aggregator,
    mock_alpha_decay,
    mock_opportunity_cost,
):
    """User-pinned holdings are 100% immune from displacement."""
    mock_shadow_repo.list_positions.return_value = [{
        "id": "shadow-4",
        "ticker": "PLTR",
        "status": "OPEN",
        "allocated_capital": 1000.0,
    }]

    mock_shadow_ledger.evaluate_graduation.return_value = GraduationResult(
        ticker="PLTR",
        qualified=True,
        status="QUALIFIED",
        evaluation_days=10,
        unrealized_pnl_pct=8.0,
        max_drawdown_pct=2.0,
        support_breached=False,
        reasons=["Qualified"],
    )

    # INTC is pinned
    mock_ticker_repo.get_all.return_value = [{"ticker": "INTC", "is_pinned": True}]

    positions = [MagicMock(symbol="INTC", market_value=10000.0, quantity=500.0, current_price=20.0, open_date=datetime.now(timezone.utc), unrealized_pnl=-500.0)]
    mock_portfolio_aggregator.get_aggregated_portfolio = AsyncMock(return_value={
        "positions": positions,
        "total_equity": 10000.0,
        "total_cash": 0.0,
    })

    proposals = await orchestrator.evaluate_promotions()
    assert len(proposals) == 1
    prop = proposals[0]
    # Since INTC was pinned, no holding was eligible to displace
    assert prop.action_type == RotationActionType.BLOCKED_BY_HURDLE.value


@pytest.mark.asyncio
async def test_execute_promotion_end_to_end(
    orchestrator,
    mock_shadow_repo,
    mock_shadow_ledger,
    mock_ticker_repo,
    mock_alert_hub,
):
    """Verify execution of promotion: graduates shadow position, updates universe, dispatches alert."""
    mock_shadow_repo.get_open_position.return_value = {
        "id": "shadow-exec-1",
        "ticker": "NVDA",
        "status": "OPEN",
        "allocated_capital": 1500.0,
        "current_price": 130.0,
    }
    mock_shadow_ledger.graduate_position = AsyncMock(return_value={"status": "GRADUATED"})

    res = await orchestrator.execute_promotion(
        candidate_ticker="NVDA",
        displaced_ticker="INTC",
        auto_rebalance=True,
    )

    assert res.success is True
    assert res.action_type == "CAPITAL_ROTATION"
    assert res.candidate_ticker == "NVDA"
    assert res.displaced_ticker == "INTC"
    assert res.alert_dispatched is True
    assert len(res.sor_execution_plans) == 2

    mock_shadow_ledger.graduate_position.assert_called_once_with(
        "NVDA",
        reason="Graduated to live universe (Displaced: INTC)",
    )
    mock_ticker_repo.upsert.assert_called_with("test-user", "INTC", status="candidate")
    mock_alert_hub.dispatch_shadow_promotion_rotation_alert.assert_called_once()
