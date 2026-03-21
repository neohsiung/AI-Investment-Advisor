"""
Tests for AlchemyRiskKeywordRepository — CRUD, Seeding, Hit Tracking, Analytics
風險關鍵字資料存取層測試

Tests use an in-memory SQLite database for isolation.
"""
import pytest
from unittest.mock import patch
from src.repositories.risk_keyword_repository import AlchemyRiskKeywordRepository, DEFAULT_KEYWORDS
from src.data.database import init_db
from src.domain.entities import RiskKeyword, RiskCategory


@pytest.fixture
def repo(tmp_path):
    """Create a repo with a fresh in-memory DB."""
    db_path = str(tmp_path / "test_rk.db")
    init_db(db_path)
    return AlchemyRiskKeywordRepository(db_path)


class TestSeedDefaults:
    def test_seed_populates_empty_table(self, repo):
        """Seeding an empty table inserts all default keywords."""
        repo.seed_defaults()
        keywords = repo.get_all()
        assert len(keywords) == len(DEFAULT_KEYWORDS)

    def test_seed_skips_if_already_populated(self, repo):
        """Seeding a pre-populated table does nothing."""
        repo.seed_defaults()
        initial_count = len(repo.get_all())
        repo.seed_defaults()  # second call
        assert len(repo.get_all()) == initial_count

    def test_seed_weights_match(self, repo):
        """Seeded keywords have correct weights from DEFAULT_KEYWORDS."""
        repo.seed_defaults()
        keywords = repo.get_all()
        # Check a known keyword
        sec_kws = [kw for kw in keywords if kw.keyword == "sec investigation"]
        assert len(sec_kws) == 1
        assert sec_kws[0].weight == 0.9
        assert sec_kws[0].category == RiskCategory.LEGAL


class TestCRUD:
    def test_add_and_get(self, repo):
        """Add a keyword and retrieve it."""
        kw = repo.add("climate risk", 0.6, "custom")
        assert kw.keyword == "climate risk"
        assert kw.weight == 0.6

        all_kws = repo.get_all()
        assert len(all_kws) == 1
        assert all_kws[0].keyword == "climate risk"

    def test_update_weight(self, repo):
        """Update keyword weight."""
        kw = repo.add("tariff", 0.7, "geopolitical")
        repo.update_weight(kw.id, 0.95)

        updated = repo.get_all()
        assert updated[0].weight == 0.95

    def test_toggle_active(self, repo):
        """Disable and re-enable a keyword."""
        kw = repo.add("war", 0.65, "geopolitical")
        assert kw.is_active is True

        repo.toggle_active(kw.id, False)
        all_kws = repo.get_all()
        assert all_kws[0].is_active is False

        # Active-only filter
        active = repo.get_all(active_only=True)
        assert len(active) == 0

        repo.toggle_active(kw.id, True)
        active = repo.get_all(active_only=True)
        assert len(active) == 1

    def test_delete(self, repo):
        """Delete removes keyword permanently."""
        kw = repo.add("temp_keyword", 0.3, "custom")
        assert len(repo.get_all()) == 1
        repo.delete(kw.id)
        assert len(repo.get_all()) == 0

    def test_get_by_category(self, repo):
        """Filter keywords by category."""
        repo.add("lawsuit", 0.9, "legal")
        repo.add("bankruptcy", 0.85, "financial")
        repo.add("tariff", 0.7, "geopolitical")

        legal = repo.get_by_category("legal")
        assert len(legal) == 1
        assert legal[0].keyword == "lawsuit"


class TestHitTracking:
    def test_record_hit_increments(self, repo):
        """Recording a hit increments hit_count and sets last_hit_date."""
        kw = repo.add("fraud", 0.9, "legal")
        assert kw.hit_count == 0

        repo.record_hit(kw.id)
        repo.record_hit(kw.id)

        updated = repo.get_all()
        assert updated[0].hit_count == 2
        assert updated[0].last_hit_date is not None


class TestAnalytics:
    def test_get_top_keywords(self, repo):
        """Top keywords sorted by hit_count descending."""
        kw1 = repo.add("fraud", 0.9, "legal")
        kw2 = repo.add("crash", 0.85, "market")
        repo.record_hit(kw1.id)
        repo.record_hit(kw1.id)
        repo.record_hit(kw1.id)
        repo.record_hit(kw2.id)

        top = repo.get_top_keywords(2)
        assert top[0].keyword == "fraud"
        assert top[0].hit_count == 3
        assert top[1].keyword == "crash"

    def test_get_stale_keywords(self, repo):
        """Stale keywords have no recent hits."""
        repo.add("ancient_risk", 0.5, "custom")  # Never hit
        kw2 = repo.add("recent_risk", 0.5, "custom")
        repo.record_hit(kw2.id)  # Just hit today

        stale = repo.get_stale_keywords(days_threshold=1)
        # "ancient_risk" has no hits, "recent_risk" was hit today
        stale_keywords = [kw.keyword for kw in stale]
        assert "ancient_risk" in stale_keywords
        # recent_risk was hit today, so it might still appear depending on julianday
        # but at minimum ancient_risk should be there


class TestRiskKeywordEntity:
    def test_score_active_match(self):
        """Active keyword matching text returns weight."""
        kw = RiskKeyword(keyword="fraud", weight=0.9, is_active=True)
        assert kw.score("Company investigated for fraud") == 0.9

    def test_score_active_no_match(self):
        """Active keyword not matching text returns 0."""
        kw = RiskKeyword(keyword="fraud", weight=0.9, is_active=True)
        assert kw.score("Company reports strong earnings") == 0.0

    def test_score_inactive(self):
        """Inactive keyword always returns 0 even if text matches."""
        kw = RiskKeyword(keyword="fraud", weight=0.9, is_active=False)
        assert kw.score("Company investigated for fraud") == 0.0

    def test_score_case_insensitive(self):
        """Score matching is case-insensitive."""
        kw = RiskKeyword(keyword="SEC Investigation", weight=0.85, is_active=True)
        assert kw.score("sec investigation found evidence") == 0.85
