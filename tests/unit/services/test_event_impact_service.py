"""
Unit tests for EventImpact domain model, repository, and service.
驗證事件量化偏置雙軌模型、指數衰減、資料庫存取與多租戶防護。
"""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine

from src.domain.event_impact import EventImpact, EventScope, EventSentiment
from src.repositories.event_impact_repository import AlchemyEventImpactRepository
from src.services.event_impact_service import EventImpactService


@pytest.fixture
def sqlite_engine():
    """Isolated in-memory SQLite engine for tests."""
    return create_engine("sqlite:///:memory:")


@pytest.fixture
def event_repo(sqlite_engine):
    """Event impact repository using sqlite in-memory."""
    return AlchemyEventImpactRepository(engine=sqlite_engine)


@pytest.fixture
def event_service(event_repo):
    """EventImpactService with in-memory repo."""
    return EventImpactService(user_id="test_user_001", repository=event_repo)


def test_event_impact_decay_math():
    """Verify exponential half-life decay formula: I(t) = I_0 * 2^(-Δt / T_half)."""
    now = datetime.now(timezone.utc)
    half_life = 36.0

    impact = EventImpact(
        user_id="test_user_001",
        scope=EventScope.MICRO,
        ticker="NKE",
        headline="BofA Downgrades Nike",
        initial_impact=-1.5,
        half_life_hours=half_life,
        created_at=now,
    )

    # At t = 0
    assert impact.compute_decayed_impact(now) == -1.50
    assert impact.is_active(now) is True

    # At t = 36h (1 half-life)
    t_36h = now + timedelta(hours=36)
    assert impact.compute_decayed_impact(t_36h) == -0.75

    # At t = 72h (2 half-lives)
    t_72h = now + timedelta(hours=72)
    assert impact.compute_decayed_impact(t_72h) == -0.38

    # At t = 108h (3 half-lives)
    t_108h = now + timedelta(hours=108)
    assert impact.compute_decayed_impact(t_108h) == -0.19

    # At t = 200h (negligible threshold cutoff < 0.03)
    t_200h = now + timedelta(hours=200)
    assert impact.compute_decayed_impact(t_200h) == 0.0
    assert impact.is_active(t_200h) is False


def test_event_impact_serialization():
    """Test to_dict and from_dict roundtrip."""
    now = datetime.now(timezone.utc)
    imp = EventImpact(
        user_id="u123",
        scope=EventScope.MACRO,
        ticker=None,
        category="monetary_policy",
        headline="FOMC Rate Decision",
        summary="Rates held steady",
        sentiment=EventSentiment.BEARISH,
        initial_impact=-0.7,
        half_life_hours=96.0,
        created_at=now,
        metadata={"source": "reuters"},
    )

    data = imp.to_dict()
    assert data["scope"] == "macro"
    assert data["ticker"] is None
    assert data["initial_impact"] == -0.7
    assert data["metadata"]["source"] == "reuters"

    restored = EventImpact.from_dict(data)
    assert restored.scope == EventScope.MACRO
    assert restored.initial_impact == -0.7
    assert restored.sentiment == EventSentiment.BEARISH


def test_repository_crud_and_multitenancy(event_repo):
    """Verify raw SQL CRUD operations and multi-tenant isolation."""
    # User 1 inserts a micro impact for NKE
    imp1 = EventImpact(
        user_id="user_alice",
        scope=EventScope.MICRO,
        ticker="NKE",
        category="analyst_rating",
        headline="Alice NKE downgrade",
        initial_impact=-1.5,
    )
    event_repo.insert_impact(imp1)

    # User 2 inserts a micro impact for NKE
    imp2 = EventImpact(
        user_id="user_bob",
        scope=EventScope.MICRO,
        ticker="NKE",
        category="analyst_rating",
        headline="Bob NKE downgrade",
        initial_impact=-0.8,
    )
    event_repo.insert_impact(imp2)

    # Alice queries NKE
    alice_impacts = event_repo.get_active_impacts(user_id="user_alice", ticker="NKE")
    assert len(alice_impacts) == 1
    assert alice_impacts[0].headline == "Alice NKE downgrade"

    # Bob queries NKE
    bob_impacts = event_repo.get_active_impacts(user_id="user_bob", ticker="NKE")
    assert len(bob_impacts) == 1
    assert bob_impacts[0].headline == "Bob NKE downgrade"

    # Alice dismisses her impact
    success = event_repo.dismiss_impact(user_id="user_alice", impact_id=imp1.id)
    assert success is True

    # Alice queries again - now empty
    alice_active = event_repo.get_active_impacts(user_id="user_alice", ticker="NKE")
    assert len(alice_active) == 0

    # Bob's impact is still active
    bob_active = event_repo.get_active_impacts(user_id="user_bob", ticker="NKE")
    assert len(bob_active) == 1


def test_event_service_micro_bias_calculation(event_service):
    """Verify EventImpactService micro bias retrieval and clamping."""
    # Record NKE downgrade
    event_service.record_event_impact(
        scope=EventScope.MICRO,
        ticker="NKE",
        headline="Bank of America Downgrades Nike to Underperform",
        category="analyst_rating",
        sentiment=EventSentiment.BEARISH,
        initial_impact=-1.5,
    )

    delta, active_events = event_service.get_ticker_micro_bias("NKE")
    assert delta == -1.50
    assert len(active_events) == 1
    assert "Bank of America" in active_events[0]["headline"]

    # Other tickers have 0 bias
    aapl_delta, aapl_events = event_service.get_ticker_micro_bias("AAPL")
    assert aapl_delta == 0.0
    assert len(aapl_events) == 0


def test_event_service_macro_stress_and_cash_reserve(event_service):
    """Verify EventImpactService macro stress and extra cash reserve calculation."""
    # Record FOMC Hawkish Surprise
    event_service.record_event_impact(
        scope=EventScope.MACRO,
        headline="FOMC Signals Higher for Longer Rates",
        category="monetary_policy",
        sentiment=EventSentiment.BEARISH,
        initial_impact=-0.8,
    )

    stress_index, extra_cash, active_events = event_service.get_macro_stress_bias()
    assert stress_index == -0.80
    # max_cash_buffer is 0.15 default, so 0.8 * 0.15 = 0.12 (12% extra cash buffer)
    assert extra_cash == 0.12
    assert len(active_events) == 1

    summary = event_service.get_all_active_biases()
    assert summary["macro"]["stress_index"] == -0.80
    assert summary["macro"]["extra_cash_reserve_ratio"] == 0.12
