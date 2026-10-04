"""
Unit tests for Council Debate Memory & Vector Retrieval Service (A3 Engine).
Tests:
- Vector retrieval and text fallback for historical council minutes
- Ex-post outcome enrichment from decision_outcomes
- Multi-factor re-ranking (similarity, recency decay, attribution confidence, ticker boost)
- Precedent prompt synthesis for LLM injection
- API endpoints: POST /api/v1/council/memory/search & GET /api/v1/council/memory/{session_id}
- CouncilService integration and CIO prompt injection
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import council as council_ep
from src.services.council_debate_memory_service import (
    CouncilDebateMemoryService,
    DebateOutcomeRecord,
    DebatePrecedent,
    DebateRetrievalResult,
)


@pytest.fixture
def mock_vector_repo():
    repo = MagicMock()
    return repo


@pytest.fixture
def memory_service(mock_vector_repo):
    service = CouncilDebateMemoryService(
        user_id="test_user_a3",
        vector_repo=mock_vector_repo,
    )
    return service


def test_service_initialization_and_settings(memory_service):
    """Test default parameters and dynamic setting retrieval."""
    assert memory_service.user_id == "test_user_a3"
    assert memory_service.is_enabled is True
    assert memory_service.similarity_threshold == 0.60
    assert memory_service.default_top_k == 3

    # Dynamic settings override
    mock_settings = MagicMock()
    mock_settings.get_setting.side_effect = lambda k, d: {
        "council_memory_retrieval_enabled": False,
        "council_memory_similarity_threshold": 0.75,
        "council_memory_top_k": 5,
    }.get(k, d)

    custom_service = CouncilDebateMemoryService(
        user_id="test_user_a3",
        settings_service=mock_settings,
    )
    assert custom_service.is_enabled is False
    assert custom_service.similarity_threshold == 0.75
    assert custom_service.default_top_k == 5


def test_retrieve_similar_precedents_disabled(mock_vector_repo):
    """When disabled, returns empty precedents immediately."""
    mock_settings = MagicMock()
    mock_settings.get_setting.return_value = False
    service = CouncilDebateMemoryService(user_id="u1", settings_service=mock_settings)

    result = service.retrieve_similar_precedents("NVDA GPU cycle")
    assert result.total_found == 0
    assert result.precedents == []
    assert result.synthesized_prompt_context == ""


def test_retrieve_similar_precedents_vector_and_ranking(memory_service, mock_vector_repo):
    """Test vector candidate search, outcome attribution joining, and composite re-ranking."""
    candidates = [
        {
            "id": "min-1",
            "session_id": "sess-1",
            "topic": "NVDA AI chip momentum and valuation",
            "consensus": "Consensus was to BUY NVDA with 3% allocation.",
            "similarity": 0.88,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "participants": "Fundamental, Momentum, Risk",
        },
        {
            "id": "min-2",
            "session_id": "sess-2",
            "topic": "TSLA delivery numbers and margin compression",
            "consensus": "Consensus was to HOLD TSLA.",
            "similarity": 0.70,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "participants": "Fundamental, Sentiment",
        },
    ]

    mock_outcomes = {
        "sess-1": [
            DebateOutcomeRecord(
                outcome_id="out-1",
                ticker="NVDA",
                agent_name="CIO",
                signal="BUY",
                realized_return_pct=14.5,
                benchmark_return_pct=4.2,
                alpha_pct=10.3,
                lesson="Strong demand validated thesis despite high multiple.",
                resolved_at="2026-09-01T00:00:00Z",
            )
        ]
    }

    with patch.object(memory_service, "_embed_query", return_value=[0.1] * 768), \
         patch.object(mock_vector_repo, "search_similar_minutes_by_embedding", return_value=candidates), \
         patch.object(memory_service, "_fetch_outcomes_for_sessions", return_value=mock_outcomes):

        result = memory_service.retrieve_similar_precedents(topic="NVDA AI chip", ticker="NVDA", limit=2)

        assert result.total_found == 2
        assert len(result.precedents) == 2

        # First precedent should be NVDA with higher similarity, outcome bonus, and ticker boost
        top_p = result.precedents[0]
        assert top_p.minute_id == "min-1"
        assert top_p.session_id == "sess-1"
        assert top_p.has_attribution is True
        assert top_p.avg_alpha_pct == 10.3
        assert len(top_p.outcomes) == 1
        assert "評議會歷史相似辯論前例與事後歸因" in result.synthesized_prompt_context
        assert "NVDA" in result.synthesized_prompt_context
        assert "+10.30%" in result.synthesized_prompt_context


def test_fallback_to_text_search(memory_service, mock_vector_repo):
    """When embedding fails or returns no vector matches, falls back to text search."""
    text_candidates = [
        {
            "id": "min-text-1",
            "session_id": "sess-text-1",
            "topic": "Semiconductor cycle analysis",
            "consensus": "Trim semi exposure.",
            "rank": 0.65,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    with patch.object(memory_service, "_embed_query", return_value=None), \
         patch.object(mock_vector_repo, "search_similar_minutes", return_value=text_candidates), \
         patch.object(memory_service, "_fetch_outcomes_for_sessions", return_value={}):

        result = memory_service.retrieve_similar_precedents(topic="Semiconductor cycle")
        assert len(result.precedents) == 1
        assert result.precedents[0].minute_id == "min-text-1"


def test_synthesize_precedents_for_prompt(memory_service):
    """Test markdown block generation for prompt injection."""
    # Empty precedents
    empty_block = memory_service.synthesize_precedents_for_prompt([])
    assert empty_block == "No historical council precedents found for this market context."

    # Populated precedents
    p1 = DebatePrecedent(
        minute_id="m1",
        session_id="s1",
        topic="AAPL Q3 earnings review",
        consensus="Maintain overweight on service margin expansion.",
        created_at="2026-08-15T12:00:00Z",
        similarity=0.82,
        relevance_score=0.91,
        outcomes=[
            DebateOutcomeRecord(
                outcome_id="o1",
                ticker="AAPL",
                agent_name="CIO",
                signal="BUY",
                realized_return_pct=6.5,
                benchmark_return_pct=2.0,
                alpha_pct=4.5,
                lesson="Service revenue resilience offset hardware weakness.",
                resolved_at="2026-09-15T00:00:00Z",
            )
        ],
    )
    p2 = DebatePrecedent(
        minute_id="m2",
        session_id="s2",
        topic="Energy sector hedging",
        consensus="Hedge long positions with XLE puts.",
        created_at="2026-08-20T12:00:00Z",
        similarity=0.74,
        relevance_score=0.78,
        outcomes=[],  # pending resolution
    )

    prompt = memory_service.synthesize_precedents_for_prompt([p1, p2])
    assert "評議會歷史相似辯論前例與事後歸因" in prompt
    assert "AAPL Q3 earnings review" in prompt
    assert "基準超額 Alpha=+4.50%" in prompt
    assert "Service revenue resilience offset hardware weakness." in prompt
    assert "Energy sector hedging" in prompt
    assert "[尚未結算 / 觀測期中]" in prompt


def test_search_debates_api_filtering(memory_service):
    """Test min_alpha filtering in search_debates_api."""
    p1 = DebatePrecedent(
        minute_id="m1", session_id="s1", topic="High Alpha Trade",
        consensus="BUY", created_at="2026-01-01", similarity=0.8, relevance_score=0.9,
        outcomes=[DebateOutcomeRecord("o1", "NVDA", "CIO", "BUY", 15.0, 5.0, 10.0, "Great call", "2026-02-01")]
    )
    p2 = DebatePrecedent(
        minute_id="m2", session_id="s2", topic="Negative Alpha Trade",
        consensus="BUY", created_at="2026-01-01", similarity=0.8, relevance_score=0.85,
        outcomes=[DebateOutcomeRecord("o2", "TSLA", "CIO", "BUY", -5.0, 2.0, -7.0, "Bad call", "2026-02-01")]
    )

    with patch.object(memory_service, "retrieve_similar_precedents") as mock_ret:
        mock_ret.return_value = DebateRetrievalResult(
            precedents=[p1, p2],
            synthesized_prompt_context="guidance",
            total_found=2,
            query="test",
        )

        filtered = memory_service.search_debates_api(query="test", min_alpha=5.0)
        assert len(filtered) == 1
        assert filtered[0].minute_id == "m1"


def test_get_debate_detail(memory_service):
    """Test fetching full debate minute and outcomes."""
    mock_row = MagicMock()
    mock_row.id = "min-100"
    mock_row.session_id = "sess-100"
    mock_row.user_id = "test_user_a3"
    mock_row.topic = "Detailed Topic"
    mock_row.participants = "CIO, Risk"
    mock_row.consensus = "Clear consensus"
    mock_row.transcript = "Full debate transcript..."
    mock_row.created_at = datetime.now(timezone.utc)

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = mock_row

    with patch.object(memory_service.engine, "connect") as mock_connect, \
         patch.object(memory_service, "_fetch_outcomes_for_sessions", return_value={"sess-100": []}):
        mock_connect.return_value.__enter__.return_value = mock_conn

        detail = memory_service.get_debate_detail("sess-100")
        assert detail is not None
        assert detail["minute_id"] == "min-100"
        assert detail["session_id"] == "sess-100"
        assert detail["topic"] == "Detailed Topic"
        assert detail["transcript"] == "Full debate transcript..."


def test_council_memory_api_endpoints():
    """Verify POST /api/v1/council/memory/search and GET /api/v1/council/memory/{session_id}."""
    app = FastAPI()
    app.include_router(council_ep.router, prefix="/api/v1/council")

    mock_service = MagicMock()
    app.dependency_overrides[council_ep.get_debate_memory_service] = lambda: mock_service
    app.dependency_overrides[council_ep.get_current_user_id] = lambda: "test_user_a3"
    client = TestClient(app)

    # 1. POST /memory/search
    precedent = DebatePrecedent(
        minute_id="min-api-1",
        session_id="sess-api-1",
        topic="API Test Topic",
        consensus="Approved with caution",
        created_at="2026-10-01T00:00:00Z",
        similarity=0.85,
        relevance_score=0.92,
        outcomes=[
            DebateOutcomeRecord(
                outcome_id="o-api-1",
                ticker="MSFT",
                agent_name="CIO",
                signal="BUY",
                realized_return_pct=8.0,
                benchmark_return_pct=3.0,
                alpha_pct=5.0,
                lesson="Cloud growth sustained.",
                resolved_at="2026-10-02T00:00:00Z",
            )
        ],
    )
    mock_service.search_debates_api.return_value = [precedent]
    mock_service.synthesize_precedents_for_prompt.return_value = "### Precedent Context"

    search_payload = {"query": "Cloud software trends", "limit": 5, "min_alpha": 2.0}
    resp = client.post("/api/v1/council/memory/search", json=search_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_found"] == 1
    assert data["precedents"][0]["minute_id"] == "min-api-1"
    assert data["precedents"][0]["outcomes"][0]["alpha_pct"] == 5.0
    assert data["synthesized_prompt_context"] == "### Precedent Context"

    # 2. GET /memory/{session_id} Success
    mock_service.get_debate_detail.return_value = {
        "minute_id": "min-api-1",
        "session_id": "sess-api-1",
        "user_id": "test_user_a3",
        "topic": "API Test Topic",
        "participants": "CIO, Risk",
        "consensus": "Approved",
        "transcript": "Transcript content",
        "created_at": "2026-10-01T00:00:00Z",
        "outcomes": [],
    }
    detail_resp = client.get("/api/v1/council/memory/sess-api-1")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["status"] == "success"
    assert detail_data["session_id"] == "sess-api-1"
    assert detail_data["topic"] == "API Test Topic"

    # 3. GET /memory/{session_id} Not Found
    mock_service.get_debate_detail.return_value = None
    not_found_resp = client.get("/api/v1/council/memory/nonexistent-session")
    assert not_found_resp.status_code == 404


@pytest.mark.asyncio
async def test_council_service_cio_precedent_injection():
    """Verify CouncilService _call_agent_llm injects A3 precedents for CIO/CouncilSynthesis."""
    from src.services.council_service import CouncilService

    council = CouncilService(user_id="test_user_a3")
    assert hasattr(council, "debate_memory_service")

    # Mock pipeline to capture generated system prompt
    captured_messages = []

    class MockPipeline:
        def __init__(self, *args, **kwargs):
            pass
        async def execute(self, messages, *args, **kwargs):
            captured_messages.extend(messages)
            return "CIO consensus verdict", {}

    context_with_precedents = {
        "market_data": {"price": 100},
        "historical_precedents": "### 🏛️ 評議會歷史相似辯論前例與事後歸因:\n- 【先例 #1】議題: \"NVDA Cycle\" (+10.3% Alpha)",
    }

    with patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline", MockPipeline), \
         patch("src.infrastructure.llm.llm_config_chain.build_config_chain", return_value=["dummy-model"]):

        res = await council._call_agent_llm("CIO", context_with_precedents)
        assert res == "CIO consensus verdict"

        sys_msg = next((m for m in captured_messages if m.role == "system"), None)
        assert sys_msg is not None
        assert "Historical Debate Precedents & Decision Lessons (A3 Attribution)" in sys_msg.content
        assert "NVDA Cycle" in sys_msg.content
