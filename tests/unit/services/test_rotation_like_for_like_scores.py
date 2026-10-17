"""Rotation must compare holdings and candidates on the SAME entry-side scale (cached research score),
never a holding's inverted exit urgency against a candidate's entry score."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.services.sentinel_service import SentinelService
from src.services.unified_risk_gateway_service import RiskGatewayResult, RiskSeverity

SETTINGS = {"capital_rotation_enabled": True, "rotation_min_score_delta": 2.0, "rotation_min_holding_days": 5}


@pytest.fixture
def sentinel():
    st = MagicMock()
    st.get_setting.side_effect = lambda k, default=None, user_id=None: SETTINGS.get(k, default)
    tx = MagicMock()
    tx.get_transactions.return_value = pd.DataFrame(
        [{"ticker": "GOOGL", "action": "BUY", "trade_date": datetime.now() - timedelta(days=10)}])
    buf = MagicMock(); buf.try_acquire = AsyncMock(return_value=True)
    repo = MagicMock(); repo.engine = MagicMock(); repo.get_all_thresholds.return_value = {}
    with patch("src.infrastructure.redis_sentinel_buffer.RedisSentinelBuffer", return_value=buf), \
         patch("src.services.search_service.InternetSearchService"), \
         patch("src.services.council_service.CouncilService"), \
         patch("src.repositories.snapshot_repository.AlchemySnapshotRepository"), \
         patch("src.services.token_logger_service.TokenLoggerService"):
        s = SentinelService(user_id="u_lfl", repo=repo, market_service=MagicMock(), transaction_service=tx,
                            settings_service=st, keyword_service=MagicMock())
    s._acquire_cooldown = AsyncMock(return_value=True)
    return s


async def _rotate(s, research, exit_score=4.3, candidates=None):
    s._research_score = lambda t: research.get(t)
    holdings = {"GOOGL": {"shares": 0.3, "current_price": 340.0, "avg_price": 340.0, "weight": 5.0}}
    compositor = MagicMock()
    with patch("src.services.trading_protections_service.TradingProtectionsService.check", return_value=None), \
         patch("src.services.exit_compositor_service.ExitCompositorService.score_exit",
               new=AsyncMock(return_value={"composite_score": exit_score, "breakdown": []})), \
         patch("src.services.confidence_compositor_service.CompositorService", compositor), \
         patch("src.services.unified_risk_gateway_service.UnifiedRiskGatewayService.evaluate_trade_risk",
               new=AsyncMock(return_value=RiskGatewayResult(True, RiskSeverity.NORMAL, None, [], {}, "t"))):
        trig = await s._check_capital_rotation_opportunities(
            current_allocation=holdings,
            candidates_override=candidates or [{"ticker": "NVDA", "source": "ticker_universe"}])
    return trig, compositor


@pytest.mark.asyncio
async def test_strong_new_holding_is_not_rotated_out_for_a_lower_scored_candidate(sentinel):
    # GOOGL 9.4 on the research scale; NVDA 8.0. Old logic inverted exit urgency (10-4.3=5.7) and "rotated".
    trig, _ = await _rotate(sentinel, {"GOOGL": 9.4, "NVDA": 8.0})
    assert trig == []


@pytest.mark.asyncio
async def test_clearly_weaker_holding_rotates_into_stronger_candidate(sentinel):
    trig, _ = await _rotate(sentinel, {"GOOGL": 5.0, "NVDA": 8.2})
    assert len(trig) == 1 and trig[0]["holding_conviction"] == pytest.approx(5.0) and trig[0]["candidate_score"] == pytest.approx(8.2)


@pytest.mark.asyncio
async def test_deteriorating_holding_uses_exit_urgency_when_worse(sentinel):
    # research still 9.0 but the exit model screams (8.5 -> conviction 1.5): safety side wins
    trig, _ = await _rotate(sentinel, {"GOOGL": 9.0, "NVDA": 8.0}, exit_score=8.5)
    assert len(trig) == 1 and trig[0]["holding_conviction"] == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_candidate_without_research_score_is_skipped_and_no_llm_scoring(sentinel):
    trig, compositor = await _rotate(sentinel, {"GOOGL": 5.0})        # NVDA has no cached score
    assert trig == []
    compositor.assert_not_called()                                    # no live 4-agent LLM scoring fallback


@pytest.mark.asyncio
async def test_holding_without_research_score_cannot_be_rotated_out(sentinel):
    trig, _ = await _rotate(sentinel, {"NVDA": 8.5})                  # GOOGL has no cached score -> incomparable
    assert trig == []
