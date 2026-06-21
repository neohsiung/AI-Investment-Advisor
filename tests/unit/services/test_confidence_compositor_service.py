"""
Tests for ConfidenceCompositorService (src/services/confidence_compositor_service.py).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.confidence_compositor_service import CompositorService, AgentSubScore


@pytest.fixture
def compositor():
    return CompositorService(user_id="test-user")


def test_compositor_init(compositor):
    assert compositor.user_id == "test-user"
    assert compositor.min_threshold == 5.0
    assert compositor.max_single_allocation == 0.25
    assert compositor.min_allocation == 0.05
    assert compositor.agent_weights["fundamental"] == 0.35


def test_ticker_hash(compositor):
    h1 = compositor._ticker_hash("AAPL")
    h2 = compositor._ticker_hash("AAPL")
    assert h1 == h2
    assert isinstance(h1, int)


def test_fallback_score(compositor):
    score, factors = compositor._fallback_score("AAPL", "Fundamental")
    assert 0.0 <= score <= 10.0
    assert "key_factor" in factors
    assert "details" in factors
    assert factors["details"].startswith("LLM unavailable")


def test_aggregate_scores(compositor):
    sub_scores = [
        AgentSubScore("Fundamental", "AAPL", 8.0, {}, "", ""),
        AgentSubScore("Momentum", "AAPL", 6.0, {}, "", ""),
        AgentSubScore("Sentiment", "AAPL", 7.0, {}, "", ""),
        AgentSubScore("Risk", "AAPL", 5.0, {}, "", ""),
    ]
    score, execute = compositor._aggregate_scores(sub_scores)
    # Weighted score: 8*0.35 + 6*0.25 + 7*0.20 + 5*0.20 = 2.8 + 1.5 + 1.4 + 1.0 = 6.7
    assert abs(score - 6.7) < 0.01
    assert execute is True

    # Under threshold
    low_scores = [
        AgentSubScore("Fundamental", "AAPL", 4.0, {}, "", ""),
        AgentSubScore("Momentum", "AAPL", 4.0, {}, "", ""),
        AgentSubScore("Sentiment", "AAPL", 4.0, {}, "", ""),
        AgentSubScore("Risk", "AAPL", 4.0, {}, "", ""),
    ]
    score_low, execute_low = compositor._aggregate_scores(low_scores)
    assert execute_low is False

    # Empty sub-scores
    score_empty, execute_empty = compositor._aggregate_scores([])
    assert score_empty == 5.0
    assert execute_empty is False


def test_compute_cash_reserve_factor(compositor):
    assert compositor._compute_cash_reserve_factor(9.0, 0.20) == 0.20
    assert compositor._compute_cash_reserve_factor(7.0, 0.20) == 0.35
    assert compositor._compute_cash_reserve_factor(5.5, 0.20) == 0.60
    assert compositor._compute_cash_reserve_factor(4.0, 0.20) == 0.83


def test_compute_allocation_pct(compositor):
    alloc1 = compositor._compute_allocation_pct(8.0, 10000.0, 0.20, 16.0)
    # raw: (8/16) * (1-0.20) = 0.5 * 0.8 = 0.40 -> capped at max_single_allocation (0.25)
    assert alloc1 == 0.25

    alloc2 = compositor._compute_allocation_pct(2.0, 10000.0, 0.20, 16.0)
    # raw: (2/16) * (1-0.20) = 0.125 * 0.8 = 0.10
    assert alloc2 == 0.10

    alloc_zero = compositor._compute_allocation_pct(0, 0, 0.20, 0)
    assert alloc_zero == 0.0


def test_build_decision(compositor):
    sub_scores = [
        AgentSubScore("Fundamental", "AAPL", 8.0, {"key_factor": "Strong earnings"}, "Strong earnings", ""),
    ]
    decision = compositor._build_decision(
        ticker="AAPL",
        candidate={"ticker": "AAPL"},
        sub_scores=sub_scores,
        composite_score=8.0,
        allocation_pct=0.20,
        should_execute=True,
        cash_reserve_recommendation=0.20,
        excess_cash=10000.0
    )
    assert decision["ticker"] == "AAPL"
    assert decision["composite_score"] == 8.0
    assert decision["allocation_pct"] == 0.20
    assert decision["allocation_amount"] == 2000.0
    assert decision["should_execute"] is True
    assert decision["breakdown"][0]["agent"] == "Fundamental"


def test_normalize_allocations(compositor):
    decisions = [
        {"ticker": "AAPL", "allocation_pct": 0.25, "should_execute": True},
        {"ticker": "GOOG", "allocation_pct": 0.25, "should_execute": True},
    ]
    res = compositor._normalize_allocations(decisions, 10000.0)
    assert res[0]["allocation_amount"] == 2500.0

    # Scale down case (>1.0 total)
    decisions_over = [
        {"ticker": "AAPL", "allocation_pct": 0.60, "should_execute": True},
        {"ticker": "GOOG", "allocation_pct": 0.60, "should_execute": True},
    ]
    res_over = compositor._normalize_allocations(decisions_over, 10000.0)
    # Total is 1.20 -> scaled by 1/1.20 = 0.8333
    # AAPL target: 0.60 * 0.8333 = 0.50
    assert abs(res_over[0]["allocation_pct"] - 0.50) < 0.01
    assert res_over[0]["allocation_amount"] == 5000.0

    # Empty decisions
    assert compositor._normalize_allocations([], 10000.0) == []
    # No executables
    no_exec = [{"ticker": "AAPL", "allocation_pct": 0.20, "should_execute": False}]
    assert compositor._normalize_allocations(no_exec, 10000.0) == no_exec


def test_build_rationale(compositor):
    sub_scores = [
        AgentSubScore("Fundamental", "AAPL", 8.0, {"key_factor": "Strong earnings"}, "Strong earnings", ""),
    ]
    rationale = compositor._build_rationale(sub_scores, 8.0)
    assert "Composite confidence: 8.0/10" in rationale
    assert "Fundamental: 8.0/10 (Strong earnings)" in rationale


@pytest.mark.asyncio
async def test_compute_composite_decision(compositor):
    compositor._gather_agent_scores = AsyncMock(return_value=[
        AgentSubScore("Fundamental", "AAPL", 8.0, {"key_factor": "Strong"}, "Strong", ""),
        AgentSubScore("Momentum", "AAPL", 7.0, {"key_factor": "Strong"}, "Strong", ""),
        AgentSubScore("Sentiment", "AAPL", 6.0, {"key_factor": "Strong"}, "Strong", ""),
        AgentSubScore("Risk", "AAPL", 7.0, {"key_factor": "Strong"}, "Strong", ""),
    ])

    candidates = [{"ticker": "AAPL", "expected_return": 0.12}]
    decisions = await compositor.compute_composite_decision(
        candidates=candidates,
        excess_cash=10000.0,
        cash_ratio=0.15,
        target_cash_ratio=0.10
    )
    assert len(decisions) == 1
    assert decisions[0]["ticker"] == "AAPL"
    assert decisions[0]["should_execute"] is True
    assert decisions[0]["allocation_amount"] > 0


@pytest.mark.asyncio
async def test_score_via_llm_success(compositor):
    mock_pipeline = AsyncMock()
    mock_response = '{"score": 8.5, "key_factor": "Excellent revenue", "rationale": "High growth", "details": "all good"}'
    mock_pipeline.execute.return_value = (mock_response, 1)
    compositor._get_pipeline = AsyncMock(return_value=mock_pipeline)

    score, factors = await compositor._score_via_llm("AAPL", "Fundamental", "System prompt {ticker}", "User prompt")
    assert score == 8.5
    assert factors["key_factor"] == "Excellent revenue"


@pytest.mark.asyncio
async def test_score_via_llm_failure(compositor):
    compositor._get_pipeline = AsyncMock(side_effect=Exception("LLM crash"))
    # Should fallback to deterministic hash score
    score, factors = await compositor._score_via_llm("AAPL", "Fundamental", "System prompt", "User prompt")
    assert 0.0 <= score <= 10.0
    assert "Fallback" in factors["key_factor"]
    assert "_fallback_reason" in factors


@pytest.mark.asyncio
async def test_query_agents(compositor):
    mock_pipeline = AsyncMock()
    mock_response = '{"score": 8.0, "key_factor": "good", "rationale": "High growth", "details": "all good", "beta": "1.0", "volatility": "Low", "liquidity": "High"}'
    mock_pipeline.execute.return_value = (mock_response, 1)
    compositor._get_pipeline = AsyncMock(return_value=mock_pipeline)
    
    f_score, f_factors = await compositor._query_fundamental_agent("AAPL")
    assert f_score == 8.0
    
    m_score, m_factors = await compositor._query_momentum_agent("AAPL")
    assert m_score == 8.0
    
    s_score, s_factors = await compositor._query_sentiment_agent("AAPL")
    assert s_score == 8.0
    
    r_score, r_factors = await compositor._query_risk_agent("AAPL", 0.20)
    assert r_score == 8.0


@pytest.mark.asyncio
async def test_gather_agent_scores(compositor):
    compositor._query_fundamental_agent = AsyncMock(return_value=(8.0, {"key_factor": "good"}))
    compositor._query_momentum_agent = AsyncMock(return_value=(7.0, {"key_factor": "good"}))
    compositor._query_sentiment_agent = AsyncMock(return_value=(6.0, {"key_factor": "good"}))
    compositor._query_risk_agent = AsyncMock(return_value=(7.0, {"key_factor": "good"}))
    
    sub_scores = await compositor._gather_agent_scores("AAPL", 0.15, 0.10)
    assert len(sub_scores) == 4
    assert sub_scores[0].confidence == 8.0


@pytest.mark.asyncio
async def test_query_risk_agent_failure(compositor):
    compositor._score_via_llm = AsyncMock(side_effect=Exception("LLM fail"))
    score, factors = await compositor._query_risk_agent("AAPL", 0.20)
    assert 0.0 <= score <= 10.0


@pytest.mark.asyncio
async def test_get_pipeline(compositor):
    mock_router = MagicMock()
    mock_pipeline = MagicMock()
    mock_router.get_resilient_gateway.return_value = mock_pipeline
    
    with patch("src.infrastructure.llm.budget_aware_model_router.BudgetAwareModelRouter", return_value=mock_router), \
         patch("src.services.settings_service.SettingsService", return_value=MagicMock()), \
         patch("src.services.token_logger_service.TokenLoggerService", return_value=MagicMock()):
         
        pipeline1 = await compositor._get_pipeline("smart")
        assert pipeline1 == mock_pipeline
        
        # Test cache hit
        pipeline2 = await compositor._get_pipeline("smart")
        assert pipeline2 == mock_pipeline
