"""
Unit tests for CrossCurrencyFXHedgingService (Phase 65).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.cross_currency_fx_hedging_service import (
    CrossCurrencyFXHedgingService,
    FXBufferStatus,
    FXExposureReport,
    FXHedgingDecision,
    FXRateQuote,
    FXRegime,
)
from src.services.unified_risk_gateway_service import (
    RiskGatewayResult,
    RiskSeverity,
    UnifiedRiskGatewayService,
)


@pytest.fixture
def fx_service():
    return CrossCurrencyFXHedgingService(user_id="test_user")


@pytest.mark.asyncio
async def test_get_fx_quote_benchmark_priors(fx_service):
    """Test retrieving benchmark priors for liquid currency pairs."""
    quote_twd = await fx_service.get_fx_quote("TWD")
    assert quote_twd.base_currency == "TWD"
    assert quote_twd.rate_usd_to_base == 32.20
    assert quote_twd.sma20 == 32.10
    assert quote_twd.sma50 == 31.80
    assert quote_twd.price_deviation_pct > 0.01

    quote_eur = await fx_service.get_fx_quote("EUR")
    assert quote_eur.base_currency == "EUR"
    assert quote_eur.rate_usd_to_base == 0.925

    quote_jpy = await fx_service.get_fx_quote("JPY")
    assert quote_jpy.base_currency == "JPY"
    assert quote_jpy.rate_usd_to_base == 152.00

    quote_usd = await fx_service.get_fx_quote("USD")
    assert quote_usd.base_currency == "USD"
    assert quote_usd.rate_usd_to_base == 1.0


@pytest.mark.asyncio
async def test_get_fx_quote_unknown_currency(fx_service):
    """Test fallback quote for unknown foreign currency."""
    quote = await fx_service.get_fx_quote("XYZ")
    assert quote.base_currency == "XYZ"
    assert quote.rate_usd_to_base == 1.0
    assert quote.sma50 == 1.0


def test_determine_fx_regime(fx_service):
    """Test three-state regime classification under varying market deviations."""
    # 1. Strong Bullish USD (P > SMA50, SMA20 > SMA50, dev > +1.5%)
    bull_quote = FXRateQuote(
        base_currency="TWD",
        rate_usd_to_base=32.50,
        sma20=32.20,
        sma50=31.80,
        price_deviation_pct=0.022,
        annualized_vol=0.05,
        symbol="USDTWD=X",
        source="TEST",
    )
    regime, hedge_ratio, rationale = fx_service.determine_fx_regime(bull_quote)
    assert regime == FXRegime.UNHEDGED_FAVORABLE
    assert hedge_ratio == 0.0
    assert "多頭通道" in rationale

    # 2. Bearish USD Breakdown (dev < -1.5%)
    bear_quote = FXRateQuote(
        base_currency="TWD",
        rate_usd_to_base=31.20,
        sma20=31.50,
        sma50=31.80,
        price_deviation_pct=-0.0189,
        annualized_vol=0.05,
        symbol="USDTWD=X",
        source="TEST",
    )
    regime_b, hedge_ratio_b, rationale_b = fx_service.determine_fx_regime(bear_quote)
    assert regime_b == FXRegime.ACTIVE_HEDGING_DEFICIT
    assert hedge_ratio_b >= 0.75
    assert "空頭破位" in rationale_b

    # 3. Choppy Buffer Deadband (-1.5% <= dev <= +1.5%)
    choppy_quote = FXRateQuote(
        base_currency="TWD",
        rate_usd_to_base=31.85,
        sma20=31.82,
        sma50=31.80,
        price_deviation_pct=0.0016,
        annualized_vol=0.05,
        symbol="USDTWD=X",
        source="TEST",
    )
    regime_c, hedge_ratio_c, rationale_c = fx_service.determine_fx_regime(choppy_quote)
    assert regime_c == FXRegime.PARTIAL_HEDGE_BUFFER
    assert 0.25 <= hedge_ratio_c <= 0.50
    assert "震盪緩衝帶" in rationale_c

    # 4. Base is USD
    usd_quote = FXRateQuote(
        base_currency="USD",
        rate_usd_to_base=1.0,
        sma20=1.0,
        sma50=1.0,
        price_deviation_pct=0.0,
        annualized_vol=0.0,
        symbol="USD",
        source="TEST",
    )
    regime_u, hedge_ratio_u, rationale_u = fx_service.determine_fx_regime(usd_quote)
    assert regime_u == FXRegime.UNHEDGED_FAVORABLE
    assert hedge_ratio_u == 0.0


@pytest.mark.asyncio
async def test_calculate_portfolio_fx_exposure(fx_service):
    """Test full portfolio FX exposure, VaR, and margin buffer calculations."""
    mock_summary = {
        "total_equity": 20000.0,
        "total_cash": 4000.0,
    }

    report = await fx_service.calculate_portfolio_fx_exposure(
        base_currency="TWD",
        portfolio_summary=mock_summary,
    )

    assert report.base_currency == "TWD"
    assert report.total_equity_usd == 20000.0
    assert report.total_cash_usd == 4000.0
    assert report.total_equity_base == pytest.approx(20000.0 * report.rate_usd_to_base)
    assert report.total_cash_base == pytest.approx(4000.0 * report.rate_usd_to_base)
    assert report.usd_exposure_pct == 0.80  # (20000 - 4000) / 20000
    assert report.fx_var_99_10d_usd > 0
    assert report.required_buffer_base > 0
    assert report.buffer_headroom_base > 0
    assert report.buffer_status == FXBufferStatus.SUFFICIENT
    assert len(report.hedge_suggestions) > 0


@pytest.mark.asyncio
async def test_evaluate_order_fx_liquidity_fail_open_on_sell(fx_service):
    """Ensure SELL / EXIT orders always fail open to restore portfolio liquidity."""
    decision = await fx_service.evaluate_order_fx_liquidity(
        ticker="NVDA",
        action="SELL",
        order_amount_usd=5000.0,
        base_currency="TWD",
    )
    assert decision.allowed is True
    assert "SELL/EXIT 訂單放行" in decision.reason
    assert decision.projected_headroom_base > decision.current_headroom_base


@pytest.mark.asyncio
async def test_evaluate_order_fx_liquidity_buy_sizing(fx_service):
    """Test BUY order liquidity headroom checks and deficit breaker."""
    # Custom rate setting with minimal cash
    mock_summary = {
        "total_equity": 10000.0,
        "total_cash": 1000.0,  # Cash = 1000 USD (32,200 TWD)
    }

    with patch.object(
        fx_service,
        "calculate_portfolio_fx_exposure",
        AsyncMock(
            return_value=FXExposureReport(
                base_currency="TWD",
                rate_usd_to_base=32.20,
                total_equity_usd=10000.0,
                total_cash_usd=1000.0,
                usd_exposure_pct=0.90,
                total_equity_base=322000.0,
                total_cash_base=32200.0,
                regime=FXRegime.PARTIAL_HEDGE_BUFFER,
                recommended_hedge_ratio=0.35,
                hedged_amount_usd=3150.0,
                unhedged_exposure_usd=5850.0,
                fx_var_99_10d_usd=300.0,
                fx_var_99_10d_base=9660.0,
                required_buffer_base=25760.0,  # 8% = 25,760 TWD (25% threshold = 6,440 TWD)
                available_buffer_base=32200.0,
                buffer_headroom_base=6440.0,
                buffer_status=FXBufferStatus.SUFFICIENT,
                regime_rationale="Test",
            )
        ),
    ):
        # 1. Small BUY of $100 USD (3,220 TWD) -> Headroom remaining: 3,220 TWD -> ALLOWED & SUFFICIENT
        dec_safe = await fx_service.evaluate_order_fx_liquidity(
            ticker="AAPL",
            action="BUY",
            order_amount_usd=100.0,
            base_currency="TWD",
        )
        assert dec_safe.allowed is True
        assert dec_safe.buffer_status == FXBufferStatus.SUFFICIENT

        # 2. Moderate BUY of $250 USD (8,050 TWD) -> Headroom becomes -1,610 TWD (warning, but within 25% threshold)
        dec_warn = await fx_service.evaluate_order_fx_liquidity(
            ticker="AAPL",
            action="BUY",
            order_amount_usd=250.0,
            base_currency="TWD",
        )
        assert dec_warn.allowed is True
        assert dec_warn.buffer_status == FXBufferStatus.WARNING

        # 3. Excessive BUY of $1500 USD (exceeds total cash of 1000 USD) -> BLOCKED
        dec_block = await fx_service.evaluate_order_fx_liquidity(
            ticker="TSLA",
            action="BUY",
            order_amount_usd=1500.0,
            base_currency="TWD",
        )
        assert dec_block.allowed is False
        assert dec_block.buffer_status == FXBufferStatus.DEFICIT
        assert "嚴重穿透最低保證金流動性緩衝" in dec_block.reason


@pytest.mark.asyncio
async def test_unified_risk_gateway_integration():
    """Verify UnifiedRiskGatewayService incorporates Guard 12."""
    gateway = UnifiedRiskGatewayService(user_id="test_user")

    # Mock CrossCurrencyFXHedgingService to return a deficit block
    with patch(
        "src.services.cross_currency_fx_hedging_service.CrossCurrencyFXHedgingService.evaluate_order_fx_liquidity",
        AsyncMock(
            return_value=FXHedgingDecision(
                ticker="NVDA",
                action="BUY",
                order_amount_usd=50000.0,
                allowed=False,
                buffer_status=FXBufferStatus.DEFICIT,
                current_headroom_base=5000.0,
                projected_headroom_base=-45000.0,
                reason="[FX Liquidity Buffer] Test deficit breach",
            )
        ),
    ):
        result = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="BUY",
            amount_usd=50000.0,
            current_price=135.0,
        )
        assert result.allowed is False
        assert result.primary_blocker == "FXLiquidityBufferDeficit"
        assert any("Test deficit breach" in r for r in result.reasons)

    # SELL order must remain allowed (Fail-Open on SELL)
    with patch(
        "src.services.cross_currency_fx_hedging_service.CrossCurrencyFXHedgingService.evaluate_order_fx_liquidity",
        AsyncMock(
            return_value=FXHedgingDecision(
                ticker="NVDA",
                action="SELL",
                order_amount_usd=50000.0,
                allowed=True,
                buffer_status=FXBufferStatus.SUFFICIENT,
                current_headroom_base=5000.0,
                projected_headroom_base=55000.0,
                reason="SELL/EXIT 訂單放行",
            )
        ),
    ):
        result_sell = await gateway.evaluate_trade_risk(
            ticker="NVDA",
            action="SELL",
            amount_usd=50000.0,
            current_price=135.0,
        )
        assert result_sell.allowed is True


def test_format_fx_report_and_suggestions(fx_service):
    """Test output formatting for markdown / HTML cards."""
    report = FXExposureReport(
        base_currency="TWD",
        rate_usd_to_base=32.20,
        total_equity_usd=10000.0,
        total_cash_usd=2000.0,
        usd_exposure_pct=0.80,
        total_equity_base=322000.0,
        total_cash_base=64400.0,
        regime=FXRegime.ACTIVE_HEDGING_DEFICIT,
        recommended_hedge_ratio=0.75,
        hedged_amount_usd=6000.0,
        unhedged_exposure_usd=2000.0,
        fx_var_99_10d_usd=300.0,
        fx_var_99_10d_base=9660.0,
        required_buffer_base=25760.0,
        available_buffer_base=64400.0,
        buffer_headroom_base=38640.0,
        buffer_status=FXBufferStatus.SUFFICIENT,
        regime_rationale="測試空頭破位",
        hedge_suggestions=["🚨 建議對沖：將 $6,000 USD 進行遠期鎖匯"],
    )

    card = fx_service.format_fx_report(report)
    assert "跨市場即時外匯對沖與多幣種保證金流動性儀表" in card
    assert "ACTIVE_HEDGING_DEFICIT" in card
    assert "32.2000 TWD" in card

    hedge_card = fx_service.format_hedge_suggestion(report)
    assert "外匯動態避險與利潤結匯執行方案" in card or "執行方案" in hedge_card
    assert "Profit Repatriation" in hedge_card
    assert "$6,000.00 USD" in hedge_card
