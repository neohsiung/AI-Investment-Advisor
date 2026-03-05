"""
Tests for RiskKeywordService — Discovery + Refine + Pruning
風險關鍵字服務測試 — 探索 + 精煉 + 修剪

Covers:
- discover_from_reports (LLM mock)
- discover_from_webhook_news (TF-IDF)
- discover_from_community_trends (API mocks)
- prune_if_over_limit
- discover_and_refine orchestrator
- max_keywords cap enforcement
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from collections import namedtuple

from src.services.risk_keyword_service import RiskKeywordService, _STOPWORDS
from src.domain.entities import RiskKeyword, RiskCategory


# ──────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────

@pytest.fixture
def mock_repo():
    """Create a mock repository with standard return values."""
    repo = MagicMock()
    repo.get_all.return_value = [
        RiskKeyword(id="k1", keyword="crash", weight=0.9, category=RiskCategory.MARKET,
                    hit_count=5, is_active=True),
        RiskKeyword(id="k2", keyword="recession", weight=0.8, category=RiskCategory.MACRO,
                    hit_count=3, is_active=True),
    ]
    repo.get_count.return_value = 161
    repo.seed_defaults.return_value = None
    repo.add_if_not_exists.return_value = True
    repo.prune_lowest.return_value = 0
    repo.get_stale_keywords.return_value = []
    repo.get_top_keywords.return_value = []
    return repo


@pytest.fixture
def service(mock_repo):
    """Create RiskKeywordService with mock repo."""
    return RiskKeywordService(repository=mock_repo)


# ──────────────────────────────────────────
# Source A: Reports (LLM)
# ──────────────────────────────────────────

class TestDiscoverFromReports:
    """Tests for _discover_from_reports."""

    @patch("src.data.database.get_db_connection")
    @patch("litellm.completion")
    def test_extracts_keywords_from_reports(self, mock_llm, mock_conn, service):
        """Should extract keywords from DB reports via LLM."""
        # Mock DB return
        FakeRow = namedtuple("FakeRow", ["content"])
        mock_connection = MagicMock()
        mock_connection.execute.return_value.fetchall.return_value = [
            FakeRow(content="Fed rate hike signals recession fears among investors"),
            FakeRow(content="NVIDIA earnings beat expectations, AI chip demand soaring"),
        ]
        mock_conn.return_value = mock_connection

        # Mock LLM response
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"keywords": [{"keyword": "rate hike", "weight": 0.7, "category": "macro"}, {"keyword": "ai chip", "weight": 0.6, "category": "sector"}]}'))]
        )

        result = service._discover_from_reports()

        assert len(result) == 2
        assert result[0][0] == "rate hike"
        assert result[0][3] == "report"  # source
        mock_llm.assert_called_once()

    @patch("src.data.database.get_db_connection")
    def test_no_reports_returns_empty(self, mock_conn, service):
        """Should return empty list when no recent reports."""
        mock_connection = MagicMock()
        mock_connection.execute.return_value.fetchall.return_value = []
        mock_conn.return_value = mock_connection

        result = service._discover_from_reports()
        assert result == []

    @patch("src.data.database.get_db_connection")
    @patch("litellm.completion")
    def test_llm_failure_returns_empty(self, mock_llm, mock_conn, service):
        """Should gracefully return empty on LLM failure."""
        FakeRow = namedtuple("FakeRow", ["content"])
        mock_connection = MagicMock()
        mock_connection.execute.return_value.fetchall.return_value = [
            FakeRow(content="Some report content"),
        ]
        mock_conn.return_value = mock_connection
        mock_llm.side_effect = Exception("LLM API error")

        result = service._discover_from_reports()
        assert result == []


# ──────────────────────────────────────────
# Source B: Webhook News (TF-IDF)
# ──────────────────────────────────────────

class TestDiscoverFromWebhookNews:
    """Tests for _discover_from_webhook_news."""

    @patch("src.data.database.get_db_connection")
    def test_extracts_keywords_from_events(self, mock_conn, service):
        """Should extract high-frequency terms from event_logs."""
        FakeRow = namedtuple("FakeRow", ["title", "content"])
        mock_connection = MagicMock()
        mock_connection.execute.return_value.fetchall.return_value = [
            FakeRow(title="Tariff hike announced", content="China tariff escalation impacts semiconductor tariff trade"),
            FakeRow(title="Tariff concerns", content="Global semiconductor shortage tariff impact"),
        ]
        mock_conn.return_value = mock_connection

        result = service._discover_from_webhook_news()

        # "tariff" and "semiconductor" should appear (freq >= 2, not in stopwords)
        keywords_found = [r[0] for r in result]
        assert any("tariff" in kw for kw in keywords_found)
        assert all(r[3] == "webhook" for r in result)  # source

    @patch("src.data.database.get_db_connection")
    def test_no_events_returns_empty(self, mock_conn, service):
        """Should return empty when no recent events."""
        mock_connection = MagicMock()
        mock_connection.execute.return_value.fetchall.return_value = []
        mock_conn.return_value = mock_connection

        result = service._discover_from_webhook_news()
        assert result == []


# ──────────────────────────────────────────
# Source C: Community Trends
# ──────────────────────────────────────────

class TestDiscoverFromCommunityTrends:
    """Tests for _discover_from_community_trends."""

    @patch.object(RiskKeywordService, "_fetch_google_trends", return_value=[])
    @patch.object(RiskKeywordService, "_fetch_finnhub_trending", return_value=[])
    @patch.object(RiskKeywordService, "_fetch_apewisdom", return_value=["TSLA", "tesla", "NVDA", "nvidia"])
    def test_apewisdom_provides_keywords(self, mock_ape, mock_finn, mock_gt, service):
        """Should get trending tickers from ApeWisdom."""
        result = service._discover_from_community_trends()

        # Should have at least some keywords (minus existing ones)
        assert len(result) > 0
        assert all(r[3] == "trends" for r in result)

    @patch.object(RiskKeywordService, "_fetch_google_trends", return_value=["bitcoin rally"])
    @patch.object(RiskKeywordService, "_fetch_finnhub_trending", return_value=[])
    @patch.object(RiskKeywordService, "_fetch_apewisdom", side_effect=Exception("API down"))
    def test_fallback_chain(self, mock_ape, mock_finn, mock_gt, service):
        """Should fallback to Google Trends when ApeWisdom fails."""
        result = service._discover_from_community_trends()

        keywords = [r[0] for r in result]
        assert "bitcoin rally" in keywords

    @patch.object(RiskKeywordService, "_fetch_google_trends", side_effect=Exception("No"))
    @patch.object(RiskKeywordService, "_fetch_finnhub_trending", side_effect=Exception("No"))
    @patch.object(RiskKeywordService, "_fetch_apewisdom", side_effect=Exception("No"))
    def test_all_providers_fail_returns_empty(self, mock_ape, mock_finn, mock_gt, service):
        """Should return empty when all providers fail (graceful degradation)."""
        result = service._discover_from_community_trends()
        assert result == []

    @patch.object(RiskKeywordService, "_fetch_google_trends", return_value=[])
    @patch.object(RiskKeywordService, "_fetch_finnhub_trending", return_value=[])
    @patch.object(RiskKeywordService, "_fetch_apewisdom", return_value=["crash"])
    def test_existing_keywords_skipped(self, mock_ape, mock_finn, mock_gt, service):
        """Should not duplicate existing keywords like 'crash'."""
        result = service._discover_from_community_trends()
        keywords = [r[0] for r in result]
        # "crash" is already in mock_repo's active keywords, should be skipped
        assert "crash" not in keywords


# ──────────────────────────────────────────
# Pruning
# ──────────────────────────────────────────

class TestPruning:
    """Tests for pruning logic."""

    def test_prune_called_when_over_max(self, service, mock_repo):
        """Should call prune_lowest when count > MAX_KEYWORDS."""
        mock_repo.get_count.return_value = 1050
        mock_repo.prune_lowest.return_value = 50

        with patch.object(service, "_discover_from_reports", return_value=[]):
            with patch.object(service, "_discover_from_webhook_news", return_value=[]):
                with patch.object(service, "_discover_from_community_trends", return_value=[]):
                    result = service.discover_and_refine(target=200)

        mock_repo.prune_lowest.assert_called_once_with(1000, protected_source="seed")
        assert result["pruned"] == 50

    def test_no_prune_when_under_max(self, service, mock_repo):
        """Should not prune when count <= MAX_KEYWORDS."""
        mock_repo.get_count.return_value = 200

        with patch.object(service, "_discover_from_reports", return_value=[]):
            with patch.object(service, "_discover_from_webhook_news", return_value=[]):
                with patch.object(service, "_discover_from_community_trends", return_value=[]):
                    result = service.discover_and_refine(target=200)

        mock_repo.prune_lowest.assert_not_called()
        assert result["pruned"] == 0


# ──────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────

class TestDiscoverAndRefine:
    """Tests for the full discover_and_refine orchestrator."""

    def test_full_pipeline(self, service, mock_repo):
        """Should run all 3 sources + insert + refine."""
        report_kws = [("rate hike", 0.7, "macro", "report")]
        webhook_kws = [("tariff", 0.5, "market", "webhook")]
        trend_kws = [("tsla", 0.5, "sentiment", "trends")]

        with patch.object(service, "_discover_from_reports", return_value=report_kws):
            with patch.object(service, "_discover_from_webhook_news", return_value=webhook_kws):
                with patch.object(service, "_discover_from_community_trends", return_value=trend_kws):
                    mock_repo.get_count.return_value = 164  # Under MAX
                    result = service.discover_and_refine(target=200)

        assert result["discovered"]["reports"] == 1
        assert result["discovered"]["webhook"] == 1
        assert result["discovered"]["trends"] == 1
        assert result["inserted"] == 3
        assert mock_repo.add_if_not_exists.call_count == 3
        assert mock_repo.seed_defaults.called

    def test_source_failure_non_blocking(self, service, mock_repo):
        """One source failing should not block others."""
        webhook_kws = [("sanction", 0.6, "geopolitical", "webhook")]

        with patch.object(service, "_discover_from_reports", side_effect=Exception("DB down")):
            with patch.object(service, "_discover_from_webhook_news", return_value=webhook_kws):
                with patch.object(service, "_discover_from_community_trends", return_value=[]):
                    mock_repo.get_count.return_value = 162
                    result = service.discover_and_refine(target=200)

        assert result["discovered"]["reports"] == 0
        assert result["discovered"]["webhook"] == 1
        assert "reports: DB down" in result["errors"][0]
        assert result["inserted"] == 1

    def test_refine_included_in_pipeline(self, service, mock_repo):
        """Should call refine after discovery."""
        stale_kw = RiskKeyword(id="s1", keyword="old_term", weight=0.5,
                               category=RiskCategory.MARKET, hit_count=0, is_active=True)
        mock_repo.get_stale_keywords.return_value = [stale_kw]
        mock_repo.get_top_keywords.return_value = []

        with patch.object(service, "_discover_from_reports", return_value=[]):
            with patch.object(service, "_discover_from_webhook_news", return_value=[]):
                with patch.object(service, "_discover_from_community_trends", return_value=[]):
                    mock_repo.get_count.return_value = 161
                    result = service.discover_and_refine(target=200)

        assert result["refined"]["decayed"] == 1
        mock_repo.update_weight.assert_called_once_with("s1", 0.4)


# ──────────────────────────────────────────
# TF-IDF Extraction Unit Tests
# ──────────────────────────────────────────

class TestTFIDFExtraction:
    """Unit tests for _extract_keywords_tfidf."""

    def test_extracts_frequent_terms(self, service):
        """Should extract terms appearing >= 2 times."""
        text = "inflation inflation inflation tariff tariff sanctions"
        result = service._extract_keywords_tfidf(text, source="test")

        keywords = [r[0] for r in result]
        assert "inflation" in keywords
        assert "tariff" in keywords

    def test_filters_stopwords(self, service):
        """Should not return stopwords."""
        text = "the the the market market market"
        result = service._extract_keywords_tfidf(text, source="test")

        keywords = [r[0] for r in result]
        assert "the" not in keywords

    def test_skips_existing_keywords(self, service):
        """Should not return keywords already in active cache."""
        text = "crash crash crash recession recession recession"
        result = service._extract_keywords_tfidf(text, source="test")

        keywords = [r[0] for r in result]
        # "crash" and "recession" are in mock_repo, should be skipped
        assert "crash" not in keywords
        assert "recession" not in keywords

    def test_weight_scales_with_frequency(self, service):
        """Higher frequency should produce higher weight (capped at 0.6)."""
        text = " ".join(["shortage"] * 20 + ["disruption"] * 2)
        result = service._extract_keywords_tfidf(text, source="test")

        weights = {r[0]: r[1] for r in result}
        # "shortage" (freq=20) should have higher weight than "disruption" (freq=2)
        if "shortage" in weights and "disruption" in weights:
            assert weights["shortage"] >= weights["disruption"]


# ──────────────────────────────────────────
# Constants Validation
# ──────────────────────────────────────────

class TestConstants:
    """Validate service constants."""

    def test_max_keywords(self):
        assert RiskKeywordService.MAX_KEYWORDS == 1000

    def test_default_target(self):
        assert RiskKeywordService.DEFAULT_TARGET == 200

    def test_cache_ttl(self):
        assert RiskKeywordService.CACHE_TTL_SECONDS == 300
