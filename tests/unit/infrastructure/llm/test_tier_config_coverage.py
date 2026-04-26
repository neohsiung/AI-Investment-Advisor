"""
Tests for TierConfig and SettingsAwareModelRouter to improve coverage.
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.llm.tier_config import (
    TierSpec,
    TierConfig,
    SettingsAwareModelRouter,
    DEFAULT_TIERS,
)


class TestTierSpec:
    """Test TierSpec dataclass."""

    def test_blended_cost_per_mtok(self):
        spec = TierSpec(
            name="fast",
            display_name="Fast",
            env_key="AI_MODEL_FAST",
            input_cost_per_mtok=0.30,
            output_cost_per_mtok=2.50,
        )
        # (0.30 * 3 + 2.50) / 4 = (0.90 + 2.50) / 4 = 3.40 / 4 = 0.85
        assert spec.blended_cost_per_mtok == pytest.approx(0.85)

    def test_resolve_model_from_db(self):
        spec = TierSpec(name="fast", display_name="Fast", env_key="AI_MODEL_FAST")
        db_settings = {"AI_MODEL_FAST": "google/gemini-2.5-flash"}
        result = spec.resolve_model(db_settings)
        assert result == "google/gemini-2.5-flash"

    def test_resolve_model_strips_quotes(self):
        spec = TierSpec(name="fast", display_name="Fast", env_key="AI_MODEL_FAST")
        db_settings = {"AI_MODEL_FAST": '"google/gemini-2.5-flash"'}
        result = spec.resolve_model(db_settings)
        assert result == "google/gemini-2.5-flash"

    def test_resolve_model_no_env_fallback(self, monkeypatch):
        """DB-only mode: env vars are NOT used as fallback; returns None."""
        spec = TierSpec(name="fast", display_name="Fast", env_key="AI_MODEL_FAST")
        monkeypatch.setenv("AI_MODEL_FAST", "google/gemini-2.5-flash-env")
        result = spec.resolve_model({})
        # DB-only: env var is NOT consulted — returns None when DB has no entry
        assert result is None

    def test_resolve_model_returns_none_when_no_source(self, monkeypatch):
        spec = TierSpec(name="fast", display_name="Fast", env_key="AI_MODEL_FAST")
        monkeypatch.delenv("AI_MODEL_FAST", raising=False)
        result = spec.resolve_model({})
        # DB-only: no DB entry → returns None
        assert result is None

    def test_resolve_model_empty_db_settings(self, monkeypatch):
        spec = TierSpec(name="nano", display_name="Nano", env_key="AI_MODEL_NANO")
        monkeypatch.delenv("AI_MODEL_NANO", raising=False)
        result = spec.resolve_model(None)
        # DB-only: no DB entry → returns None
        assert result is None


class TestTierConfig:
    """Test TierConfig class."""

    def setup_method(self):
        self.config = TierConfig()

    def test_default_tiers_exist(self):
        assert "nano" in DEFAULT_TIERS
        assert "fast" in DEFAULT_TIERS
        assert "smart" in DEFAULT_TIERS
        assert "advanced" in DEFAULT_TIERS

    def test_resolve_known_tier_no_db_returns_none(self, monkeypatch):
        """DB-only: env var is ignored; resolving with no DB settings returns None."""
        monkeypatch.setenv("AI_MODEL_FAST", "google/gemini-2.5-flash")
        result = self.config.resolve("fast")
        # DB-only policy: no DB entry → None (env var not consulted)
        assert result is None

    def test_resolve_known_tier_from_db(self):
        db_settings = {"AI_MODEL_FAST": "google/gemini-2.5-flash"}
        result = self.config.resolve("fast", db_settings)
        assert result == "google/gemini-2.5-flash"

    def test_resolve_unknown_tier_falls_back_to_fast_spec(self, monkeypatch):
        """Unknown tier resolves via fast spec; returns None when fast has no DB entry."""
        monkeypatch.setenv("AI_MODEL_FAST", "google/gemini-2.5-flash")
        result = self.config.resolve("nonexistent_tier")
        # DB-only: fast spec resolves to None when no DB entry
        assert result is None

    def test_resolve_with_db_settings(self):
        db_settings = {"AI_MODEL_SMART": "google/gemini-2.5-pro"}
        result = self.config.resolve("smart", db_settings)
        assert result == "google/gemini-2.5-pro"

    def test_get_spec_known_tier(self):
        spec = self.config.get_spec("fast")
        assert spec is not None
        assert spec.name == "fast"

    def test_get_spec_unknown_tier(self):
        spec = self.config.get_spec("nonexistent")
        assert spec is None

    def test_list_tiers_sorted_by_cost(self):
        tiers = self.config.list_tiers()
        costs = [t.blended_cost_per_mtok for t in tiers]
        assert costs == sorted(costs)

    def test_list_tiers_returns_all(self):
        tiers = self.config.list_tiers()
        names = [t.name for t in tiers]
        assert "nano" in names
        assert "fast" in names
        assert "smart" in names
        assert "advanced" in names

    def test_estimate_daily_cost(self):
        call_counts = {"nano": 100, "fast": 50, "smart": 10, "advanced": 2}
        cost = self.config.estimate_daily_cost(call_counts, avg_tokens_per_call=1500)
        assert cost > 0.0

    def test_estimate_daily_cost_empty(self):
        cost = self.config.estimate_daily_cost({})
        assert cost == 0.0

    def test_estimate_daily_cost_unknown_tier(self):
        cost = self.config.estimate_daily_cost({"unknown_tier": 100})
        assert cost == 0.0

    def test_recommend_tier_classify(self):
        assert self.config.recommend_tier("classify") == "nano"

    def test_recommend_tier_route(self):
        assert self.config.recommend_tier("route") == "nano"

    def test_recommend_tier_summarize(self):
        assert self.config.recommend_tier("summarize") == "fast"

    def test_recommend_tier_analyze(self):
        assert self.config.recommend_tier("analyze") == "smart"

    def test_recommend_tier_decide(self):
        assert self.config.recommend_tier("decide") == "advanced"

    def test_recommend_tier_cio(self):
        assert self.config.recommend_tier("cio") == "advanced"

    def test_recommend_tier_unknown_defaults_to_fast(self):
        assert self.config.recommend_tier("unknown_task") == "fast"

    def test_recommend_tier_case_insensitive(self):
        assert self.config.recommend_tier("CLASSIFY") == "nano"

    def test_print_budget_report(self):
        call_counts = {"nano": 50, "fast": 30, "smart": 10, "advanced": 2}
        report = self.config.print_budget_report(call_counts)
        assert "Cost Estimate" in report or "成本" in report
        assert "Total" in report

    def test_custom_tiers(self):
        """TierConfig can be initialized with custom tiers."""
        custom_spec = TierSpec(
            name="custom",
            display_name="Custom",
            env_key="AI_MODEL_CUSTOM",
        )
        config = TierConfig(tiers={"custom": custom_spec})
        assert config.get_spec("custom") is not None
        assert config.get_spec("fast") is None


class TestSettingsAwareModelRouter:
    """Test SettingsAwareModelRouter class."""

    def test_init_without_repo(self):
        router = SettingsAwareModelRouter()
        assert router.settings_repo is None
        assert router.tier_config is not None

    def test_get_model_empty_user_id(self, monkeypatch):
        monkeypatch.setenv("AI_MODEL_FAST", "google/gemini-2.5-flash")
        router = SettingsAwareModelRouter()
        result = router.get_model("", "fast")
        # DB-only: empty user_id falls back to tier_config.resolve which is DB-only → returns ""
        assert result == "" or result is None

    def test_get_model_from_db(self):
        mock_repo = MagicMock()
        mock_repo.get.return_value = "custom-model-from-db"
        router = SettingsAwareModelRouter(settings_repo=mock_repo)
        result = router.get_model("user123", "fast")
        assert result == "custom-model-from-db"

    def test_get_model_db_returns_none_no_env_fallback(self, monkeypatch):
        """DB-only: when DB returns None, result is '' (no env fallback)."""
        monkeypatch.setenv("AI_MODEL_FAST", "google/gemini-2.5-flash")
        mock_repo = MagicMock()
        mock_repo.get.return_value = None
        router = SettingsAwareModelRouter(settings_repo=mock_repo)
        result = router.get_model("user123", "fast")
        # DB-only: no DB entry, env var is NOT consulted
        assert result == "" or result is None

    def test_get_model_db_exception_returns_empty(self, monkeypatch):
        """DB-only: DB exception does not fall back to env var."""
        monkeypatch.setenv("AI_MODEL_FAST", "google/gemini-2.5-flash")
        mock_repo = MagicMock()
        mock_repo.get.side_effect = Exception("DB error")
        router = SettingsAwareModelRouter(settings_repo=mock_repo)
        result = router.get_model("user123", "fast")
        # DB-only: exception handled, no env fallback
        assert result == "" or result is None

    def test_get_model_strips_quotes_from_db(self):
        mock_repo = MagicMock()
        mock_repo.get.return_value = '"google/gemini-2.5-pro"'
        router = SettingsAwareModelRouter(settings_repo=mock_repo)
        result = router.get_model("user123", "smart")
        assert result == "google/gemini-2.5-pro"

    def test_get_model_unknown_tier_no_repo(self, monkeypatch):
        monkeypatch.setenv("AI_MODEL_FAST", "google/gemini-2.5-flash")
        router = SettingsAwareModelRouter()
        # Unknown tier falls back to fast in TierConfig.resolve
        result = router.get_model("user123", "unknown_tier")
        assert isinstance(result, str)

    def test_get_all_models(self):
        """get_all_models returns dict with all four tier keys (values may be None/empty in DB-only mode)."""
        router = SettingsAwareModelRouter()
        models = router.get_all_models("user123")
        assert "nano" in models
        assert "fast" in models
        assert "smart" in models
        assert "advanced" in models

    def test_get_model_without_repo_returns_empty(self, monkeypatch):
        """DB-only: without repo, env var is NOT consulted — returns empty."""
        monkeypatch.setenv("AI_MODEL_NANO", "gpt-4.1-nano")
        router = SettingsAwareModelRouter(settings_repo=None)
        result = router.get_model("user123", "nano")
        # DB-only: no repo, no DB entry → None/empty
        assert result == "" or result is None
