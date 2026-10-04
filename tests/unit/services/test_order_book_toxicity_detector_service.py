import pytest
from datetime import datetime, timezone
from src.services.order_book_toxicity_detector_service import (
    OrderBookDepthSnapshot,
    OrderBookToxicityDetectorService,
    ToxicityLevel,
    TradeDirection,
    TradeTick,
)
from src.services.adaptive_execution_slippage_compensator import (
    AdaptiveExecutionSlippageCompensator,
)
from src.services.smart_order_routing_service import (
    ExecutionStrategy,
    OrderAction,
    SmartOrderRoutingService,
)


class MockSettingsRepo:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, user_id: str, key: str, default=None):
        return self.data.get(key, default)


def test_order_book_imbalance_calculation():
    """Test OBI formula under balanced, skewed, and zero-depth conditions."""
    service = OrderBookToxicityDetectorService()

    # Balanced book
    snap_balanced = OrderBookDepthSnapshot(
        symbol="AAPL",
        bid_price=150.0,
        ask_price=150.05,
        bid_size=1000.0,
        ask_size=1000.0,
    )
    service.record_quote(snap_balanced)
    assert pytest.approx(service.calculate_obi("AAPL"), 0.01) == 0.0

    # Bid-skewed book (buying pressure)
    snap_bid = OrderBookDepthSnapshot(
        symbol="AAPL",
        bid_price=150.0,
        ask_price=150.05,
        bid_size=1800.0,
        ask_size=200.0,
    )
    service.record_quote(snap_bid)
    assert pytest.approx(service.calculate_obi("AAPL"), 0.01) == 0.80

    # Ask-skewed book (selling pressure)
    snap_ask = OrderBookDepthSnapshot(
        symbol="AAPL",
        bid_price=150.0,
        ask_price=150.05,
        bid_size=200.0,
        ask_size=1800.0,
    )
    service.record_quote(snap_ask)
    assert pytest.approx(service.calculate_obi("AAPL"), 0.01) == -0.80

    # Zero depth
    snap_empty = OrderBookDepthSnapshot(
        symbol="XYZ",
        bid_price=10.0,
        ask_price=10.1,
        bid_size=0.0,
        ask_size=0.0,
    )
    service.record_quote(snap_empty)
    assert service.calculate_obi("XYZ") == 0.0


def test_vpin_calculation_balanced_vs_toxic():
    """Test VPIN under balanced trade flow vs pure informed aggressive selling."""
    repo = MockSettingsRepo({
        "vpin_bucket_size": 1000.0,
        "vpin_window_buckets": 5,
    })
    service = OrderBookToxicityDetectorService(settings_repo=repo)

    # 1. Balanced flow (alternating BUY and SELL)
    for _ in range(5):
        service.record_trade(TradeTick(symbol="MSFT", price=300.0, volume=500.0, direction=TradeDirection.BUY))
        service.record_trade(TradeTick(symbol="MSFT", price=300.0, volume=500.0, direction=TradeDirection.SELL))

    vpin_balanced = service.calculate_vpin("MSFT")
    # In each 1000 share bucket, buy=500, sell=500 -> imbalance = 0
    assert pytest.approx(vpin_balanced, 0.01) == 0.0

    # 2. Pure toxic seller flow on TSLA
    for _ in range(5):
        service.record_trade(TradeTick(symbol="TSLA", price=250.0, volume=1000.0, direction=TradeDirection.SELL))

    vpin_toxic = service.calculate_vpin("TSLA")
    # Pure selling -> |0 - 1000| / 1000 = 1.0
    assert pytest.approx(vpin_toxic, 0.01) == 1.0


def test_toxicity_level_evaluation():
    """Test comprehensive toxicity grading (NORMAL, ELEVATED, CRITICAL)."""
    repo = MockSettingsRepo({
        "vpin_bucket_size": 500.0,
        "vpin_window_buckets": 4,
        "vpin_elevated_threshold": 0.50,
        "vpin_critical_threshold": 0.75,
        "obi_extreme_threshold": 0.60,
    })
    service = OrderBookToxicityDetectorService(settings_repo=repo)

    # Normal state
    service.record_quote(OrderBookDepthSnapshot(
        symbol="NVDA", bid_price=120.0, ask_price=120.05, bid_size=1000.0, ask_size=1000.0
    ))
    eval_norm = service.evaluate_toxicity("NVDA")
    assert eval_norm.toxicity_level == ToxicityLevel.NORMAL
    assert not eval_norm.is_toxic
    assert eval_norm.recommended_action == "PROCEED"
    assert eval_norm.recommended_slippage_boost == 0.0

    # Elevated toxicity via extreme OBI
    service.record_quote(OrderBookDepthSnapshot(
        symbol="NVDA", bid_price=120.0, ask_price=120.05, bid_size=2000.0, ask_size=300.0
    ))
    eval_elev = service.evaluate_toxicity("NVDA")
    assert eval_elev.toxicity_level == ToxicityLevel.ELEVATED_TOXICITY
    assert eval_elev.is_toxic
    assert eval_elev.recommended_action == "THROTTLE_SLICES"

    # Critical toxicity via high VPIN
    for _ in range(5):
        service.record_trade(TradeTick(symbol="NVDA", price=120.0, volume=500.0, direction=TradeDirection.SELL))

    eval_crit = service.evaluate_toxicity("NVDA")
    assert eval_crit.toxicity_level == ToxicityLevel.CRITICAL_TOXICITY
    assert eval_crit.is_toxic
    assert eval_crit.recommended_action == "HALT_AGGRESSIVE_FLOW"
    assert eval_crit.recommended_slippage_boost == 1.0
    assert service.is_execution_halted("NVDA") is True


def test_closed_loop_slippage_compensator_integration():
    """Test automatic boost propagation to P6 Slippage Compensator."""
    p6_compensator = AdaptiveExecutionSlippageCompensator()
    repo = MockSettingsRepo({
        "vpin_bucket_size": 500.0,
        "vpin_window_buckets": 2,
    })
    service = OrderBookToxicityDetectorService(
        settings_repo=repo,
        slippage_compensator=p6_compensator,
    )

    # Ingest toxic trades to trigger critical toxicity
    service.record_trade(TradeTick(symbol="AMD", price=140.0, volume=1500.0, direction=TradeDirection.BUY))
    service.record_quote(OrderBookDepthSnapshot(
        symbol="AMD", bid_price=140.0, ask_price=140.05, bid_size=2000.0, ask_size=100.0
    ))

    assessment = service.evaluate_toxicity("AMD")
    assert assessment.is_toxic
    # Verify P6 compensator received spillover multiplier >= 1.0 + boost
    p6_mult = p6_compensator.get_spillover_multiplier("AMD")
    assert p6_mult >= 1.5


def test_closed_loop_sor_integration():
    """Test E1 SOR plan generation when E3 detects toxic order flow."""
    repo = MockSettingsRepo({
        "vpin_bucket_size": 500.0,
        "vpin_window_buckets": 2,
    })
    service = OrderBookToxicityDetectorService(settings_repo=repo)
    sor = SmartOrderRoutingService(toxicity_service=service)

    # 1. Normal state -> normal plan
    plan_norm = sor.generate_plan(
        symbol="GOOGL",
        action=OrderAction.BUY,
        requested_quantity=100.0,
        arrival_price=175.0,
        adv_20=50000.0,
        execution_window_minutes=20,
    )
    assert plan_norm.status != "TOXICITY_HALTED"
    assert plan_norm.circuit_breaker_triggered is False

    # 2. Critical toxic flow -> SOR plan halted immediately
    for _ in range(4):
        service.record_trade(TradeTick(symbol="GOOGL", price=175.0, volume=600.0, direction=TradeDirection.SELL))

    plan_toxic = sor.generate_plan(
        symbol="GOOGL",
        action=OrderAction.BUY,
        requested_quantity=100.0,
        arrival_price=175.0,
        adv_20=50000.0,
        execution_window_minutes=20,
    )
    assert plan_toxic.status == "TOXICITY_HALTED"
    assert plan_toxic.circuit_breaker_triggered is True
    assert "Microstructure Toxic Order Flow Detected" in plan_toxic.circuit_breaker_reason
    assert plan_toxic.approved_quantity == 0.0


def test_api_endpoints_flow():
    """Test API endpoint functions for quote, trade, and toxicity query."""
    from src.api.v1.endpoints.execution import (
        get_orderbook_toxicity,
        record_orderbook_quote,
        record_orderbook_trade,
    )
    from src.api.v1.schemas.toxicity_schemas import RecordQuoteRequest, RecordTradeRequest

    service = OrderBookToxicityDetectorService()

    # 1. Post quote snapshot
    quote_resp = record_orderbook_quote(
        payload=RecordQuoteRequest(
            symbol="META",
            bid_price=500.0,
            ask_price=500.10,
            bid_size=2500.0,
            ask_size=500.0,
        ),
        service=service,
    )
    assert quote_resp.symbol == "META"
    assert pytest.approx(quote_resp.order_book_imbalance, 0.01) == (2500 - 500) / 3000

    # 2. Post trade tick
    trade_resp = record_orderbook_trade(
        payload=RecordTradeRequest(
            symbol="META",
            price=500.05,
            volume=800.0,
            direction="BUY",
        ),
        service=service,
    )
    assert trade_resp.symbol == "META"

    # 3. Query toxicity evaluation
    query_resp = get_orderbook_toxicity(
        symbol="META",
        action="SELL",
        service=service,
    )
    assert query_resp.symbol == "META"
    assert query_resp.toxicity_level in ("NORMAL", "ELEVATED_TOXICITY", "CRITICAL_TOXICITY")
    assert query_resp.recommended_action in ("PROCEED", "THROTTLE_SLICES", "HALT_AGGRESSIVE_FLOW")
