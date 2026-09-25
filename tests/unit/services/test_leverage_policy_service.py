import pytest
from src.services.leverage_policy_service import LeveragePolicyService


@pytest.fixture
def service():
    return LeveragePolicyService(user_id="test_user")


def test_spot_equity_when_confidence_below_threshold(service):
    # Confidence 7.8 < 8.5 -> Must be X1 spot equity
    decision = service.evaluate_leverage(
        ticker="AAPL",
        action="BUY",
        confidence_score=7.8,
        current_price=150.0,
        amount_usd=50.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=200.0,
        vix=15.0,
        sentinel_macro_risk="low_risk",
        confirming_agents_count=3,
    )
    assert decision.eligible_leverage == 1
    assert decision.is_leveraged is False
    assert decision.overnight_fee_annual_pct == 0.0
    assert "Confidence 7.8 < 8.5" in decision.reason
    assert decision.stop_loss_rate == round(150.0 * 0.92, 4)  # 8% stop loss


def test_spot_equity_when_vix_too_high(service):
    # High confidence 9.0 but VIX 24.5 > 20.0 -> Suppress to X1 spot
    decision = service.evaluate_leverage(
        ticker="NVDA",
        action="BUY",
        confidence_score=9.0,
        current_price=100.0,
        amount_usd=50.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=200.0,
        vix=24.5,
        sentinel_macro_risk="low_risk",
        confirming_agents_count=3,
    )
    assert decision.eligible_leverage == 1
    assert decision.is_leveraged is False
    assert "Macro VIX" in decision.reason


def test_spot_equity_when_portfolio_gross_leverage_exceeded(service):
    # Confidence 9.0, VIX 14.0, but current gross TNV 1250 on NLV 1000.
    # Adding $100 * 2 = $200 would push TNV to 1450 (1.45x > 1.30x cap)
    decision = service.evaluate_leverage(
        ticker="MSFT",
        action="BUY",
        confidence_score=9.0,
        current_price=400.0,
        amount_usd=100.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=1250.0,
        vix=14.0,
        sentinel_macro_risk="low_risk",
        confirming_agents_count=3,
    )
    assert decision.eligible_leverage == 1
    assert decision.is_leveraged is False
    assert "exceeds 1.30x cap" in decision.reason


def test_leverage_granted_when_all_conditions_met(service):
    # Confidence 9.0, VIX 14.0, Low Risk, 3 agents, Total leverage within 1.3x cap
    decision = service.evaluate_leverage(
        ticker="TSM",
        action="BUY",
        confidence_score=9.0,
        current_price=180.0,
        amount_usd=50.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=300.0,
        vix=14.0,
        sentinel_macro_risk="low_risk",
        confirming_agents_count=3,
    )
    assert decision.eligible_leverage == 2
    assert decision.is_leveraged is True
    assert decision.is_trailing_stop_loss is True
    assert decision.stop_loss_pct == 5.5
    assert decision.stop_loss_rate == round(180.0 * (1.0 - 0.055), 4)
    assert decision.overnight_fee_annual_pct == 8.5
    assert decision.max_holding_days == 10
    assert "Deploying controlled X2 leverage" in decision.reason


def test_sell_order_does_not_use_leverage(service):
    decision = service.evaluate_leverage(
        ticker="TSLA",
        action="SELL",
        confidence_score=9.0,
    )
    assert decision.eligible_leverage == 1
    assert decision.is_leveraged is False


def test_vix_panic_rebound_stage1_spot(service):
    # VIX 37 in [35, 40) under vix_panic_rebound strategy -> Deploys X1 spot equity
    decision = service.evaluate_leverage(
        ticker="QQQ",
        action="BUY",
        confidence_score=7.0,  # Confidence check bypassed by panic rebound mandate
        current_price=450.0,
        amount_usd=50.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=100.0,
        vix=37.0,
        strategy_name="vix_panic_rebound",
    )
    assert decision.eligible_leverage == 1
    assert decision.is_leveraged is False
    assert "Stage 1" in decision.reason
    assert "Deploying unleveraged X1 spot" in decision.reason


def test_vix_panic_rebound_stage2_leverage_granted(service):
    # VIX 42 >= 40 under vix_panic_rebound strategy -> Grants X2 leverage with trailing stop
    decision = service.evaluate_leverage(
        ticker="QQQ",
        action="BUY",
        confidence_score=7.0,
        current_price=420.0,
        amount_usd=50.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=200.0,
        vix=42.0,
        strategy_name="vix_panic_rebound",
    )
    assert decision.eligible_leverage == 2
    assert decision.is_leveraged is True
    assert decision.is_trailing_stop_loss is True
    assert decision.stop_loss_pct == 5.0
    assert decision.stop_loss_rate == round(420.0 * 0.95, 4)
    assert "VixPanicRebound Stage 2 authorized" in decision.reason


def test_vix_panic_rebound_stage3_leverage_granted(service):
    # VIX 48 >= 45 under vix_panic_rebound strategy -> Grants X2 leverage with 5.5% trailing stop
    decision = service.evaluate_leverage(
        ticker="TQQQ",
        action="BUY",
        confidence_score=7.0,
        current_price=50.0,
        amount_usd=50.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=200.0,
        vix=48.0,
        strategy_name="vix_panic_rebound",
    )
    assert decision.eligible_leverage == 2
    assert decision.is_leveraged is True
    assert decision.is_trailing_stop_loss is True
    assert decision.stop_loss_pct == 5.5
    assert decision.stop_loss_rate == round(50.0 * (1.0 - 0.055), 4)
    assert "VixPanicRebound Stage 3 authorized" in decision.reason


def test_vix_panic_rebound_suppressed_when_gross_leverage_exceeded(service):
    # VIX 42, but adding $100 * 2 would push TNV 1250 -> 1450 (1.45x > 1.30x cap)
    decision = service.evaluate_leverage(
        ticker="QQQ",
        action="BUY",
        confidence_score=7.0,
        current_price=420.0,
        amount_usd=100.0,
        portfolio_nlv=1000.0,
        current_gross_tnv=1250.0,
        vix=42.0,
        strategy_name="vix_panic_rebound",
    )
    assert decision.eligible_leverage == 1
    assert decision.is_leveraged is False
    assert "exceeds 1.30x cap" in decision.reason

