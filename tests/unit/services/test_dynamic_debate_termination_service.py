"""
Unit tests for Dynamic Debate Termination & Marginal Information Gain Service (A5 Engine).
"""
from datetime import datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.council import router as council_router
from src.services.dynamic_debate_termination_service import (
    AgentDebateTurn,
    DebateRoundSnapshot,
    DynamicDebateTerminationService,
    TerminationEvaluation,
    TerminationStatus,
)


@pytest.fixture
def termination_service() -> DynamicDebateTerminationService:
    return DynamicDebateTerminationService(
        user_id="test_user",
        default_min_rounds=2,
        default_max_rounds=5,
        default_marginal_info_gain_threshold=0.12,
        default_argument_similarity_threshold=0.85,
    )


def test_min_rounds_not_reached(termination_service: DynamicDebateTerminationService):
    round1 = DebateRoundSnapshot(
        round_number=1,
        turns=[
            AgentDebateTurn(
                agent_name="Technical",
                stance="BUY",
                confidence=0.85,
                arguments="Strong breakout above 50-day moving average on rising volume.",
                key_points=["50MA breakout", "RSI neutral"],
            ),
            AgentDebateTurn(
                agent_name="Fundamental",
                stance="BUY",
                confidence=0.80,
                arguments="Solid revenue expansion and operating margins improving.",
                key_points=["Revenue +15%", "Operating margin expansion"],
            ),
        ],
    )

    res = termination_service.evaluate_termination([round1])
    assert res.decision == TerminationStatus.CONTINUE_DEBATE
    assert res.round_number == 1
    assert res.estimated_tokens_saved == 0
    assert "Minimum debate rounds" in res.rationale


def test_converged_termination_early_stopping(termination_service: DynamicDebateTerminationService):
    # Round 1
    round1 = DebateRoundSnapshot(
        round_number=1,
        turns=[
            AgentDebateTurn(
                agent_name="Technical",
                stance="BUY",
                confidence=0.85,
                arguments="Strong breakout above 50-day moving average on rising volume and positive momentum.",
                key_points=["50MA breakout", "momentum"],
            ),
            AgentDebateTurn(
                agent_name="Fundamental",
                stance="BUY",
                confidence=0.80,
                arguments="Solid revenue expansion and operating margins improving with strong cash flow.",
                key_points=["Revenue +15%", "Cash flow"],
            ),
        ],
    )

    # Round 2: Repeating essentially the exact same arguments with identical stance
    round2 = DebateRoundSnapshot(
        round_number=2,
        turns=[
            AgentDebateTurn(
                agent_name="Technical",
                stance="BUY",
                confidence=0.86,
                arguments="Confirmed strong breakout above 50-day moving average with rising volume and momentum.",
                key_points=["50MA breakout", "momentum"],
            ),
            AgentDebateTurn(
                agent_name="Fundamental",
                stance="BUY",
                confidence=0.80,
                arguments="Solid revenue expansion and operating margins continue improving with cash flow.",
                key_points=["Revenue +15%", "Cash flow"],
            ),
        ],
    )

    res = termination_service.evaluate_termination([round1, round2])
    assert res.decision == TerminationStatus.CONVERGED_TERMINATION
    assert res.round_number == 2
    assert res.semantic_similarity >= 0.80
    assert res.marginal_info_gain < 0.12
    # Saved 3 rounds (5 - 2 = 3), 2 agents * 750 tokens * 3 rounds = 4500
    assert res.estimated_tokens_saved == 4500
    assert res.estimated_latency_saved_seconds == 13.5
    assert "Solidified consensus achieved early" in res.rationale


def test_continue_debate_high_information_gain(termination_service: DynamicDebateTerminationService):
    round1 = DebateRoundSnapshot(
        round_number=1,
        turns=[
            AgentDebateTurn(
                agent_name="Valuation",
                stance="SELL",
                confidence=0.85,
                arguments="Severe multiple expansion, EV/EBITDA is 28x vs historic median 18x.",
                key_points=["Overvalued", "Multiple expansion"],
            ),
            AgentDebateTurn(
                agent_name="Sentiment",
                stance="BUY",
                confidence=0.75,
                arguments="Social sentiment and options flow indicate extreme bullish call skew.",
                key_points=["Bullish call skew"],
            ),
        ],
    )

    # Round 2: Valuation radically changes perspective due to AI revenue surprise
    round2 = DebateRoundSnapshot(
        round_number=2,
        turns=[
            AgentDebateTurn(
                agent_name="Valuation",
                stance="HOLD",
                confidence=0.55,
                arguments="New guidance shows cloud gross margin +600bps, DCF fair value revised upward significantly.",
                key_points=["Fair value revised", "Margin expansion"],
            ),
            AgentDebateTurn(
                agent_name="Sentiment",
                stance="BUY",
                confidence=0.90,
                arguments="Options gamma squeeze intensifying with record call volume.",
                key_points=["Gamma squeeze"],
            ),
        ],
    )

    res = termination_service.evaluate_termination([round1, round2])
    assert res.decision == TerminationStatus.CONTINUE_DEBATE
    assert res.marginal_info_gain >= 0.12
    assert res.estimated_tokens_saved == 0
    assert "Sufficient marginal information gain detected" in res.rationale


def test_deadlock_termination(termination_service: DynamicDebateTerminationService):
    # Round 1
    round1 = DebateRoundSnapshot(
        round_number=1,
        turns=[
            AgentDebateTurn(
                agent_name="Fundamental",
                stance="BUY",
                confidence=0.90,
                arguments="Strong balance sheet, zero net debt, recurring revenue moat.",
                key_points=["Moat", "Zero debt"],
            ),
            AgentDebateTurn(
                agent_name="Technical",
                stance="SELL",
                confidence=0.90,
                arguments="Death cross formed, head-and-shoulders breakdown with heavy distribution volume.",
                key_points=["Death cross", "Distribution"],
            ),
        ],
    )

    # Round 2: Repeated entrenched arguments, neither side yields
    round2 = DebateRoundSnapshot(
        round_number=2,
        turns=[
            AgentDebateTurn(
                agent_name="Fundamental",
                stance="BUY",
                confidence=0.90,
                arguments="Reiterating strong balance sheet, zero net debt and recurring revenue moat.",
                key_points=["Moat", "Zero debt"],
            ),
            AgentDebateTurn(
                agent_name="Technical",
                stance="SELL",
                confidence=0.90,
                arguments="Reiterating death cross formed, head-and-shoulders breakdown with heavy distribution volume.",
                key_points=["Death cross", "Distribution"],
            ),
        ],
    )

    res = termination_service.evaluate_termination([round1, round2])
    assert res.decision == TerminationStatus.DEADLOCK_TERMINATION
    assert "Entrenched debate deadlock detected" in res.rationale
    assert "escalating to CIO" in res.rationale


def test_max_rounds_reached_hard_cap(termination_service: DynamicDebateTerminationService):
    history = [
        DebateRoundSnapshot(
            round_number=r,
            turns=[
                AgentDebateTurn(
                    agent_name="Risk",
                    stance="HOLD",
                    confidence=0.60,
                    arguments=f"Ongoing market volatility in round {r}.",
                )
            ],
        )
        for r in range(1, 6)
    ]

    res = termination_service.evaluate_termination(history)
    assert res.decision == TerminationStatus.MAX_ROUNDS_REACHED
    assert res.round_number == 5
    assert "Hard upper round limit" in res.rationale


def test_disabled_configuration():
    class MockSettings:
        def get(self, key):
            if key == "debate_termination_enabled":
                return False
            return None

    service = DynamicDebateTerminationService(
        user_id="test_user",
        settings_service=MockSettings(),
    )
    assert service.is_enabled is False

    round1 = DebateRoundSnapshot(
        round_number=1,
        turns=[AgentDebateTurn(agent_name="A1", stance="BUY", confidence=0.8, arguments="Test argument")],
    )
    round2 = DebateRoundSnapshot(
        round_number=2,
        turns=[AgentDebateTurn(agent_name="A1", stance="BUY", confidence=0.8, arguments="Test argument")],
    )

    res = service.evaluate_termination([round1, round2])
    assert res.decision == TerminationStatus.CONTINUE_DEBATE
    assert "Dynamic debate termination is disabled" in res.rationale


def test_bilingual_similarity_computation():
    text1 = "公司毛利率顯著承壓，本益比過高，短期缺乏催化劑"
    text2 = "公司毛利率承壓，且本益比偏高，缺乏短期催化劑"
    sim = DynamicDebateTerminationService.compute_text_similarity(text1, text2)
    assert sim >= 0.70

    # Completely disparate texts
    text3 = "生技新藥取得 FDA 三期臨床試驗重大突破"
    sim_diff = DynamicDebateTerminationService.compute_text_similarity(text1, text3)
    assert sim_diff < 0.20


def test_api_terminate_check_endpoint():
    app = FastAPI()
    app.include_router(council_router, prefix="/api/v1/council")
    client = TestClient(app)

    payload = {
        "symbol": "AAPL",
        "history_rounds": [
            {
                "round_number": 1,
                "turns": [
                    {
                        "agent_name": "Technical",
                        "stance": "BUY",
                        "confidence": 0.85,
                        "arguments": "Clear ascending triangle breakout.",
                        "key_points": ["Breakout"],
                    },
                    {
                        "agent_name": "Fundamental",
                        "stance": "BUY",
                        "confidence": 0.80,
                        "arguments": "Services revenue hitting all-time record.",
                        "key_points": ["Record services"],
                    },
                ],
            },
            {
                "round_number": 2,
                "turns": [
                    {
                        "agent_name": "Technical",
                        "stance": "BUY",
                        "confidence": 0.85,
                        "arguments": "Clear ascending triangle breakout.",
                        "key_points": ["Breakout"],
                    },
                    {
                        "agent_name": "Fundamental",
                        "stance": "BUY",
                        "confidence": 0.80,
                        "arguments": "Services revenue hitting all-time record.",
                        "key_points": ["Record services"],
                    },
                ],
            },
        ],
    }

    resp = client.post("/api/v1/council/debate/terminate-check", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["round_number"] == 2
    assert data["decision"] in ["CONVERGED_TERMINATION", "DEADLOCK_TERMINATION"]
    assert data["estimated_tokens_saved"] > 0
    assert "rationale" in data
