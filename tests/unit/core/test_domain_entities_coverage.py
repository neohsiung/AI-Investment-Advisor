"""
Tests for domain entities to improve coverage.
"""
import pytest
from datetime import datetime
from src.domain.entities import (
    SignalType,
    SecurityContext,
    AgentSignal,
    FeedbackExample,
    Position,
    Portfolio,
    AnalysisReport,
    RiskCategory,
    RiskKeyword,
    ReportMemoryItem,
    MemoryContext,
)


class TestSignalType:
    def test_buy(self):
        assert SignalType.BUY.value == "BUY"

    def test_sell(self):
        assert SignalType.SELL.value == "SELL"

    def test_hold(self):
        assert SignalType.HOLD.value == "HOLD"


class TestSecurityContext:
    def test_basic_creation(self):
        ctx = SecurityContext(
            ticker="AAPL",
            date=datetime(2024, 1, 1),
            price=150.0,
        )
        assert ctx.ticker == "AAPL"
        assert ctx.price == 150.0
        assert ctx.indicators == {}
        assert ctx.news_headlines == []
        assert ctx.financials == {}

    def test_to_json(self):
        import json
        ctx = SecurityContext(
            ticker="AAPL",
            date=datetime(2024, 1, 1),
            price=150.0,
            indicators={"RSI": 50.0},
            news_headlines=["Apple reports earnings"],
            financials={"PE": 25.0},
        )
        result = ctx.to_json()
        data = json.loads(result)
        assert data["ticker"] == "AAPL"
        assert data["price"] == 150.0
        assert data["indicators"]["RSI"] == 50.0
        assert "Apple reports earnings" in data["news"]
        assert data["financials"]["PE"] == 25.0

    def test_to_json_date_format(self):
        import json
        ctx = SecurityContext(
            ticker="GOOG",
            date=datetime(2024, 6, 15, 10, 30),
            price=200.0,
        )
        result = ctx.to_json()
        data = json.loads(result)
        assert "2024-06-15" in data["date"]


class TestAgentSignal:
    def test_basic_creation(self):
        signal = AgentSignal(
            agent_name="MomentumAgent",
            ticker="AAPL",
            signal=SignalType.BUY,
            confidence=0.85,
            reasoning="Strong momentum",
        )
        assert signal.agent_name == "MomentumAgent"
        assert signal.ticker == "AAPL"
        assert signal.signal == SignalType.BUY
        assert signal.confidence == 0.85
        assert signal.reasoning == "Strong momentum"
        assert isinstance(signal.timestamp, datetime)


class TestPosition:
    def test_market_value(self):
        pos = Position(
            ticker="AAPL",
            quantity=10.0,
            average_cost=140.0,
            current_price=150.0,
        )
        assert pos.market_value == pytest.approx(1500.0)

    def test_unrealized_pnl_profit(self):
        pos = Position(
            ticker="AAPL",
            quantity=10.0,
            average_cost=140.0,
            current_price=150.0,
        )
        assert pos.unrealized_pnl == pytest.approx(100.0)

    def test_unrealized_pnl_loss(self):
        pos = Position(
            ticker="AAPL",
            quantity=10.0,
            average_cost=160.0,
            current_price=150.0,
        )
        assert pos.unrealized_pnl == pytest.approx(-100.0)

    def test_default_leverage(self):
        pos = Position(ticker="AAPL", quantity=5.0, average_cost=100.0)
        assert pos.leverage == 1.0


class TestPortfolio:
    def test_total_market_value_empty(self):
        portfolio = Portfolio(user_id="user1", cash_balance=10000.0)
        assert portfolio.total_market_value == 0.0

    def test_total_market_value_with_positions(self):
        pos1 = Position(ticker="AAPL", quantity=10.0, average_cost=140.0, current_price=150.0)
        pos2 = Position(ticker="GOOG", quantity=5.0, average_cost=200.0, current_price=210.0)
        portfolio = Portfolio(
            user_id="user1",
            cash_balance=5000.0,
            positions={"AAPL": pos1, "GOOG": pos2},
        )
        assert portfolio.total_market_value == pytest.approx(1500.0 + 1050.0)

    def test_net_liquidation_value(self):
        pos = Position(ticker="AAPL", quantity=10.0, average_cost=140.0, current_price=150.0)
        portfolio = Portfolio(
            user_id="user1",
            cash_balance=5000.0,
            positions={"AAPL": pos},
        )
        assert portfolio.net_liquidation_value == pytest.approx(5000.0 + 1500.0)


class TestRiskCategory:
    def test_all_categories(self):
        assert RiskCategory.LEGAL.value == "legal"
        assert RiskCategory.FINANCIAL.value == "financial"
        assert RiskCategory.OPERATIONAL.value == "operational"
        assert RiskCategory.GEOPOLITICAL.value == "geopolitical"
        assert RiskCategory.MARKET.value == "market"
        assert RiskCategory.MACRO.value == "macro"
        assert RiskCategory.SENTIMENT.value == "sentiment"
        assert RiskCategory.SECTOR.value == "sector"
        assert RiskCategory.CUSTOM.value == "custom"


class TestRiskKeyword:
    def test_basic_creation(self):
        kw = RiskKeyword(keyword="SEC investigation", weight=0.8)
        assert kw.keyword == "SEC investigation"
        assert kw.weight == 0.8
        assert kw.is_active is True
        assert kw.hit_count == 0

    def test_score_match(self):
        kw = RiskKeyword(keyword="bankruptcy", weight=0.9)
        score = kw.score("Company files for bankruptcy protection")
        assert score == pytest.approx(0.9)

    def test_score_no_match(self):
        kw = RiskKeyword(keyword="bankruptcy", weight=0.9)
        score = kw.score("Company reports strong earnings")
        assert score == 0.0

    def test_score_case_insensitive(self):
        kw = RiskKeyword(keyword="SEC", weight=0.7)
        score = kw.score("sec investigation launched")
        assert score == pytest.approx(0.7)

    def test_score_inactive_returns_zero(self):
        kw = RiskKeyword(keyword="fraud", weight=0.8, is_active=False)
        score = kw.score("fraud detected at company")
        assert score == 0.0

    def test_default_category(self):
        kw = RiskKeyword(keyword="test")
        assert kw.category == RiskCategory.CUSTOM

    def test_custom_category(self):
        kw = RiskKeyword(keyword="war", category=RiskCategory.GEOPOLITICAL)
        assert kw.category == RiskCategory.GEOPOLITICAL


class TestReportMemoryItem:
    def test_basic_creation(self):
        item = ReportMemoryItem(
            user_id="user1",
            report_type="daily",
            report_date="2024-01-01",
            full_content="Full report content here",
        )
        assert item.user_id == "user1"
        assert item.report_type == "daily"
        assert item.compressed_summary is None
        assert item.key_findings is None


class TestMemoryContext:
    def test_get_compressed_context_empty(self):
        ctx = MemoryContext(
            user_id="user1",
            report_type="daily",
            lookback_window=7,
            recent_items=[],
        )
        result = ctx.get_compressed_context()
        assert result == ""

    def test_get_compressed_context_with_summary(self):
        item = ReportMemoryItem(
            user_id="user1",
            report_type="daily",
            report_date="2024-01-01",
            full_content="Full content",
            compressed_summary="Summary here",
        )
        ctx = MemoryContext(
            user_id="user1",
            report_type="daily",
            lookback_window=7,
            recent_items=[item],
        )
        result = ctx.get_compressed_context()
        assert "Summary here" in result
        assert "T-1" in result
        assert "2024-01-01" in result

    def test_get_compressed_context_without_summary_truncates(self):
        long_content = "A" * 1000
        item = ReportMemoryItem(
            user_id="user1",
            report_type="daily",
            report_date="2024-01-02",
            full_content=long_content,
        )
        ctx = MemoryContext(
            user_id="user1",
            report_type="daily",
            lookback_window=7,
            recent_items=[item],
        )
        result = ctx.get_compressed_context()
        assert "..." in result
        assert "T-1" in result

    def test_get_compressed_context_multiple_items(self):
        items = [
            ReportMemoryItem(
                user_id="user1",
                report_type="daily",
                report_date=f"2024-01-0{i+1}",
                full_content=f"Content {i+1}",
                compressed_summary=f"Summary {i+1}",
            )
            for i in range(3)
        ]
        ctx = MemoryContext(
            user_id="user1",
            report_type="daily",
            lookback_window=7,
            recent_items=items,
        )
        result = ctx.get_compressed_context()
        assert "T-1" in result
        assert "T-2" in result
        assert "T-3" in result
        assert "---" in result
