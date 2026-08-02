"""
Unit tests for UserPreferenceService (Loop 3, B-P2.2): aggregates
interaction_feedback into risk appetite / sector aversion / position
comfort signals plus a prose summary for council prompt injection.
用戶偏好服務單元測試。
"""
from unittest.mock import MagicMock, patch

import pytest

from src.services.user_preference_service import UserPreferenceService, SECTOR_AVERSION_THRESHOLD


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.begin.return_value.__enter__.return_value = conn
    return engine, conn


def _row(decision, reason_code=None, ticker=None):
    r = MagicMock()
    r.decision = decision
    r.reason_code = reason_code
    r.ticker = ticker
    return r


class TestRiskAppetite:
    def test_no_decided_rows_returns_zero(self):
        assert UserPreferenceService._compute_risk_appetite([_row("expired")]) == 0.0

    def test_all_approved_is_positive_one(self):
        rows = [_row("approved"), _row("approved")]
        assert UserPreferenceService._compute_risk_appetite(rows) == 1.0

    def test_all_rejected_is_negative_one(self):
        rows = [_row("rejected"), _row("rejected")]
        assert UserPreferenceService._compute_risk_appetite(rows) == -1.0

    def test_mixed_is_between(self):
        rows = [_row("approved"), _row("approved"), _row("rejected")]
        score = UserPreferenceService._compute_risk_appetite(rows)
        assert 0 < score < 1


class TestPositionComfort:
    def test_no_rejections_returns_zero(self):
        assert UserPreferenceService._compute_position_comfort([_row("approved")]) == 0.0

    def test_all_position_too_large_is_negative_one(self):
        rows = [_row("rejected", "position_too_large"), _row("rejected", "position_too_large")]
        assert UserPreferenceService._compute_position_comfort(rows) == -1.0

    def test_no_size_complaints_is_zero(self):
        rows = [_row("rejected", "too_risky")]
        assert UserPreferenceService._compute_position_comfort(rows) == 0.0


class TestSectorAversions:
    @pytest.mark.asyncio
    async def test_below_threshold_sectors_omitted(self):
        svc = UserPreferenceService(user_id="u1")
        rows = [_row("rejected", "too_risky", "AAPL")]  # only 1, threshold is 3
        with patch.object(svc, "_resolve_sector", return_value="Technology"):
            result = await svc._compute_sector_aversions(rows)
        assert result == {}

    @pytest.mark.asyncio
    async def test_at_or_above_threshold_sector_included(self):
        svc = UserPreferenceService(user_id="u1")
        rows = [_row("rejected", "too_risky", f"T{i}") for i in range(SECTOR_AVERSION_THRESHOLD)]
        with patch.object(svc, "_resolve_sector", return_value="Energy"):
            result = await svc._compute_sector_aversions(rows)
        assert result == {"Energy": SECTOR_AVERSION_THRESHOLD}

    @pytest.mark.asyncio
    async def test_non_conviction_reason_not_counted(self):
        """bad_timing/other are not 'conviction against the sector' reasons."""
        svc = UserPreferenceService(user_id="u1")
        rows = [_row("rejected", "bad_timing", f"T{i}") for i in range(5)]
        with patch.object(svc, "_resolve_sector", return_value="Energy"):
            result = await svc._compute_sector_aversions(rows)
        assert result == {}

    @pytest.mark.asyncio
    async def test_approved_rows_not_counted(self):
        svc = UserPreferenceService(user_id="u1")
        rows = [_row("approved", None, f"T{i}") for i in range(5)]
        result = await svc._compute_sector_aversions(rows)
        assert result == {}


class TestUpdatePreferences:
    @pytest.mark.asyncio
    async def test_no_feedback_history_returns_none(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchall.return_value = []
        svc = UserPreferenceService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            result = await svc.update_preferences()

        assert result is None

    @pytest.mark.asyncio
    async def test_with_history_persists_and_returns_profile(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchall.return_value = [_row("approved"), _row("rejected", "too_risky", "AAPL")]
        svc = UserPreferenceService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch.object(svc, "_resolve_sector", return_value=None), \
             patch("src.infrastructure.llm.llm_config_chain.build_config_chain", side_effect=Exception("no chain")):
            profile = await svc.update_preferences()

        assert profile is not None
        assert profile["sample_size"] == 2
        insert_calls = [c for c in conn.execute.call_args_list if "INSERT INTO user_preferences" in str(c[0][0])]
        assert len(insert_calls) == 1
        assert "ON CONFLICT (user_id) DO UPDATE" in str(insert_calls[0][0][0])


class TestSummaryFallback:
    def test_templated_summary_mentions_risk_seeking(self):
        summary = UserPreferenceService._templated_summary(0.5, 0.0, {})
        assert "risk-seeking" in summary

    def test_templated_summary_mentions_risk_averse(self):
        summary = UserPreferenceService._templated_summary(-0.5, 0.0, {})
        assert "risk-averse" in summary

    def test_templated_summary_mentions_sector_aversions(self):
        summary = UserPreferenceService._templated_summary(0.0, 0.0, {"Energy": 3})
        assert "Energy" in summary

    def test_templated_summary_mentions_position_size_complaints(self):
        summary = UserPreferenceService._templated_summary(0.0, -0.5, {})
        assert "position sizes" in summary.lower()


class TestReadAccessors:
    def test_get_summary_text_returns_empty_when_no_profile(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchone.return_value = None
        svc = UserPreferenceService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            result = svc.get_summary_text()

        assert result == ""

    def test_get_summary_text_returns_stored_value(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchone.return_value = ("User is risk-averse.",)
        svc = UserPreferenceService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            result = svc.get_summary_text()

        assert result == "User is risk-averse."

    def test_get_summary_text_swallows_db_errors(self):
        svc = UserPreferenceService(user_id="u1")
        with patch("src.data.database.get_db_engine", side_effect=Exception("db down")):
            assert svc.get_summary_text() == ""

    def test_get_sector_penalty_capped_at_point_three(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchone.return_value = ({"Energy": 10},)
        svc = UserPreferenceService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            penalty = svc.get_sector_penalty("Energy")

        assert penalty == 0.3

    def test_get_sector_penalty_zero_for_unmentioned_sector(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchone.return_value = ({"Energy": 5},)
        svc = UserPreferenceService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            penalty = svc.get_sector_penalty("Technology")

        assert penalty == 0.0

    def test_get_sector_penalty_zero_when_no_profile(self, mock_engine):
        engine, conn = mock_engine
        conn.execute.return_value.fetchone.return_value = None
        svc = UserPreferenceService(user_id="u1")

        with patch("src.data.database.get_db_engine", return_value=engine):
            assert svc.get_sector_penalty("Energy") == 0.0
