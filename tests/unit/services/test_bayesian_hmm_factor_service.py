"""
Unit Tests for Bayesian Hidden Markov Model Continuous Multi-Factor Allocator (Phase 38)
========================================================================================
驗證在線連續貝葉斯濾波、隱馬爾可夫轉移矩陣、4 大風格體制高斯似然度、
連續平滑多因子混合權重、香農熵模糊守衛、批次建倉與對話路由器快速指令。
"""

from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from src.services.bayesian_hmm_factor_service import (
    BayesianHMMFactorService,
    DEFENSIVE_ANCHOR_WEIGHTS,
    DEFAULT_PHASE_BASE_WEIGHTS,
    FACTOR_NAMES,
    HMMFactorObservation,
    HMMFactorPosterior,
    TacticalMarketPhase,
)
from src.services.batch_cash_deployment_service import BatchCashDeploymentService
from src.services.conversation_router import ConversationRouter
from src.services.tactical_factor_rotation_service import TacticalFactorRotationService


class TestBayesianHMMFactorService:
    @pytest.fixture
    def mock_settings_service(self):
        settings = MagicMock()
        config_map = {
            "enable_bayesian_hmm_factor_allocation": True,
            "bayesian_hmm_transition_stickiness": 0.94,
            "bayesian_hmm_entropy_defense_threshold": 1.15,
            "enable_bayesian_hmm_entropy_guard": True,
            "bayesian_hmm_observation_lookback": 30,
        }
        settings.get_setting.side_effect = lambda k, default=None, user_id=None: config_map.get(k, default)
        return settings

    @pytest.fixture
    def hmm_service(self, mock_settings_service):
        return BayesianHMMFactorService(
            user_id="test_hmm_user",
            settings_service=mock_settings_service,
        )

    def test_hmm_initialization_and_transition_matrix(self, hmm_service):
        """Verify HMM 4x4 transition matrix stochastic property and persistence."""
        assert hmm_service.is_enabled is True
        assert hmm_service.transition_persistence == 0.94
        assert hmm_service.entropy_defense_threshold == 1.15
        assert hmm_service.is_entropy_guard_enabled is True

        P = hmm_service.get_transition_matrix()
        assert P.shape == (4, 4)

        # Row stochastic property: sum of each row == 1.0
        row_sums = P.sum(axis=1)
        for s in row_sums:
            assert abs(s - 1.0) < 1e-6

        # Diagonal persistence
        for i in range(4):
            assert abs(P[i, i] - 0.94) < 1e-4

    def test_gaussian_pdf_and_numerical_stability(self):
        """Verify Gaussian pdf calculations and numerical underflow limits."""
        # Standard standard normal at 0: 1/sqrt(2pi) ~ 0.3989
        pdf_0 = BayesianHMMFactorService._gaussian_pdf(0.0, 0.0, 1.0)
        assert abs(pdf_0 - 0.39894) < 1e-4

        # Extreme outlier should not crash or return 0, but floor at 1e-20
        pdf_outlier = BayesianHMMFactorService._gaussian_pdf(100.0, 0.0, 1.0)
        assert pdf_outlier == 1e-20

    def test_bull_regime_bayesian_update(self, hmm_service):
        """Verify strong Bull market observation converges to BULL_ACCELERATION."""
        obs = hmm_service.simulate_observation("BULL")
        posterior = hmm_service.update_beliefs_sync(obs, persist=False)

        assert posterior.dominant_phase == TacticalMarketPhase.BULL_ACCELERATION
        p_bull = posterior.probabilities[TacticalMarketPhase.BULL_ACCELERATION.value]
        assert p_bull > 0.90
        assert posterior.confidence > 0.85
        assert posterior.entropy < 0.50
        assert posterior.is_entropy_guard_active is False

        # Continuous factor weights should match Bull Acceleration base weights closely
        w = posterior.continuous_weights
        assert w["momentum"] >= 0.30
        assert w["smart_money"] >= 0.20
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_early_rebound_bayesian_update(self, hmm_service):
        """Verify sharp recovery observation converges to EARLY_REBOUND."""
        obs = hmm_service.simulate_observation("REBOUND")
        posterior = hmm_service.update_beliefs_sync(obs, persist=False)

        assert posterior.dominant_phase == TacticalMarketPhase.EARLY_REBOUND
        p_reb = posterior.probabilities[TacticalMarketPhase.EARLY_REBOUND.value]
        assert p_reb > 0.80
        # Rebound weights prize momentum + liquidity premium
        w = posterior.continuous_weights
        assert w["liquidity_premium"] > 0.18
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_late_cycle_value_bayesian_update(self, hmm_service):
        """Verify inverted yield curve & low momentum observation converges to LATE_CYCLE_VALUE."""
        obs = hmm_service.simulate_observation("VALUE")
        posterior = hmm_service.update_beliefs_sync(obs, persist=False)

        assert posterior.dominant_phase == TacticalMarketPhase.LATE_CYCLE_VALUE
        p_val = posterior.probabilities[TacticalMarketPhase.LATE_CYCLE_VALUE.value]
        assert p_val > 0.80
        w = posterior.continuous_weights
        assert w["value"] > 0.25
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_defensive_consolidation_bayesian_update(self, hmm_service):
        """Verify market crash/spike in VIX converges to DEFENSIVE_CONSOLIDATION."""
        obs = hmm_service.simulate_observation("DEFENSE")
        posterior = hmm_service.update_beliefs_sync(obs, persist=False)

        assert posterior.dominant_phase == TacticalMarketPhase.DEFENSIVE_CONSOLIDATION
        p_def = posterior.probabilities[TacticalMarketPhase.DEFENSIVE_CONSOLIDATION.value]
        assert p_def > 0.80
        w = posterior.continuous_weights
        assert w["low_vol"] > 0.25
        assert w["quality"] > 0.25
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_continuous_factor_mixture_and_smooth_transition(self, hmm_service):
        """Verify smooth mixture expectation across intermediate regime distributions."""
        # 50% Bull, 50% Late Cycle prior
        custom_prior = {
            TacticalMarketPhase.BULL_ACCELERATION.value: 0.50,
            TacticalMarketPhase.EARLY_REBOUND.value: 0.00,
            TacticalMarketPhase.LATE_CYCLE_VALUE.value: 0.50,
            TacticalMarketPhase.DEFENSIVE_CONSOLIDATION.value: 0.00,
        }
        obs = HMMFactorObservation(
            trend_ratio=0.035,
            vix=17.0,
            vix_z_score=-0.1,
            yield_spread=0.20,
            return_5d=0.008,
        )
        posterior = hmm_service.update_beliefs_sync(obs, prior_probs=custom_prior, persist=False)

        # Both Bull and Value should have non-zero mass
        probs = posterior.probabilities
        assert probs[TacticalMarketPhase.BULL_ACCELERATION.value] > 0.20
        assert probs[TacticalMarketPhase.LATE_CYCLE_VALUE.value] > 0.20

        # Continuous weights should blend between Bull and Late Cycle
        w = posterior.continuous_weights
        assert w["momentum"] > 0.10
        assert w["value"] > 0.15
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_entropy_ambiguity_guard_activation(self, hmm_service):
        """Verify high Shannon entropy triggers defensive anchor allocation."""
        # Set low threshold to test guard activation
        hmm_service.settings_service.get_setting.side_effect = lambda k, default=None, user_id=None: (
            0.80 if "entropy_defense_threshold" in k else default
        )
        assert hmm_service.entropy_defense_threshold == 0.80

        # Uniform prior representing extreme ambiguity
        uniform_prior = {s.value: 0.25 for s in hmm_service.STATES}
        ambiguous_obs = HMMFactorObservation(
            trend_ratio=0.00,
            vix=21.0,
            vix_z_score=0.0,
            yield_spread=0.10,
            return_5d=0.00,
        )
        posterior = hmm_service.update_beliefs_sync(ambiguous_obs, prior_probs=uniform_prior, persist=False)

        assert posterior.entropy >= 0.80
        assert posterior.is_entropy_guard_active is True
        assert posterior.guarded_weights["quality"] > posterior.continuous_weights["quality"]
        assert posterior.guarded_weights["low_vol"] > posterior.continuous_weights["low_vol"]
        assert abs(sum(posterior.guarded_weights.values()) - 1.0) < 0.01

    def test_batch_historical_filtering(self, hmm_service):
        """Verify sequential chronological batch filtering across market shifts."""
        stream = [
            hmm_service.simulate_observation("BULL"),
            hmm_service.simulate_observation("BULL"),
            hmm_service.simulate_observation("DEFENSE"),
            hmm_service.simulate_observation("DEFENSE"),
            hmm_service.simulate_observation("REBOUND"),
        ]
        posteriors = hmm_service.batch_filter(stream)
        assert len(posteriors) == 5

        # Initial steps Bull
        assert posteriors[0].dominant_phase == TacticalMarketPhase.BULL_ACCELERATION
        assert posteriors[1].dominant_phase == TacticalMarketPhase.BULL_ACCELERATION
        # Crisis step should switch to Defense
        assert posteriors[3].dominant_phase == TacticalMarketPhase.DEFENSIVE_CONSOLIDATION
        # Rebound step should shift to Early Rebound
        assert posteriors[4].dominant_phase == TacticalMarketPhase.EARLY_REBOUND

    def test_redis_persistence_mocked(self, hmm_service):
        """Verify Redis saving and loading of belief vectors."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=mock_redis):
            obs = hmm_service.simulate_observation("BULL")
            hmm_service.update_beliefs_sync(obs, persist=True)
            mock_redis.setex.assert_called_once()

            # Now test loading from redis
            mock_redis.get.return_value = '{"BULL_ACCELERATION": 0.95, "EARLY_REBOUND": 0.02, "LATE_CYCLE_VALUE": 0.02, "DEFENSIVE_CONSOLIDATION": 0.01}'
            cached = hmm_service._load_belief_from_redis()
            assert cached is not None
            assert cached["BULL_ACCELERATION"] == 0.95

            # Test reset
            hmm_service.reset_state()
            mock_redis.delete.assert_called_once()

    def test_tactical_factor_rotation_service_integration(self, mock_settings_service, hmm_service):
        """Verify TacticalFactorRotationService seamlessly utilizes BayesianHMMFactorService."""
        rotation_service = TacticalFactorRotationService(
            user_id="test_rot_user",
            settings_service=mock_settings_service,
            bayesian_hmm_service=hmm_service,
        )

        # Test determine_market_phase_bayesian
        phase, rationale, post = rotation_service.determine_market_phase_bayesian(
            vix=15.0, vix_z_score=-0.6, spy_price=550.0, spy_sma200=500.0
        )
        assert phase == TacticalMarketPhase.BULL_ACCELERATION
        assert "在線貝葉斯隱馬爾可夫濾波" in rationale
        assert post is not None

        # Test get_continuous_factor_weights
        weights = rotation_service.get_continuous_factor_weights()
        assert isinstance(weights, dict)
        assert abs(sum(weights.values()) - 1.0) < 0.02

        # Test get_phase_factor_weights with apply_continuous_hmm=True
        blended_w = rotation_service.get_phase_factor_weights(
            TacticalMarketPhase.BULL_ACCELERATION, apply_continuous_hmm=True
        )
        assert blended_w is not None
        assert abs(sum(blended_w.values()) - 1.0) < 0.02

    @pytest.mark.asyncio
    async def test_batch_cash_deployment_summary_integration(self, mock_settings_service, hmm_service):
        """Verify BatchCashDeploymentService includes bayesian_hmm_summary in plan."""
        deploy_service = BatchCashDeploymentService(
            user_id="test_deploy_user",
            settings_service=mock_settings_service,
            bayesian_hmm_factor=hmm_service,
        )

        with patch("src.repositories.ticker_universe_repository.TickerUniverseRepository.get_target_allocations") as mock_targets, \
             patch.object(deploy_service, "_get_broker") as mock_broker_getter:
            mock_targets.return_value = [
                {"ticker": "NVDA", "target_weight": 0.10, "confidence_score": 0.95},
                {"ticker": "TSM", "target_weight": 0.10, "confidence_score": 0.90},
            ]
            mock_broker = MagicMock()
            account = MagicMock()
            account.total_equity = 1000.0
            account.available_cash = 400.0
            mock_broker.get_account = AsyncMock(return_value=account)
            mock_broker.get_positions = AsyncMock(return_value=[])
            mock_broker_getter.return_value = mock_broker

            plan = await deploy_service.get_deployment_plan(batch_number=1)
            assert "bayesian_hmm_summary" in plan
            summary = plan["bayesian_hmm_summary"]
            assert "dominant_phase" in summary
            assert "probabilities" in summary
            assert "continuous_weights" in summary

    @pytest.mark.asyncio
    async def test_router_handles_hmm_commands(self):
        """Verify ConversationRouter handles /hmm, /hmm sim, /hmm clear."""
        router = ConversationRouter()

        # Mock SettingsService inside router handler to prevent real DB queries
        with patch("src.services.settings_service.SettingsService") as mock_settings_cls:
            mock_inst = MagicMock()
            mock_inst.get_setting.return_value = True
            mock_settings_cls.return_value = mock_inst

            # 1. /hmm status
            resp = await router._handle_system_command(None, "user_1", "/hmm", "user_1")
            assert resp is not None
            assert "在線連續貝葉斯濾波與隱馬爾可夫因子動態配置報告" in resp
            assert "4 大隱馬爾可夫風格體制連續後驗機率分佈" in resp

            # 2. /hmm sim bull
            resp_sim = await router._handle_system_command(None, "user_1", "/hmm sim bull", "user_1")
            assert resp_sim is not None
            assert "BULL_ACCELERATION" in resp_sim
            assert "情境模擬更新: BULL" in resp_sim

            # 3. /hmm clear
            resp_clear = await router._handle_system_command(None, "user_1", "/hmm clear", "user_1")
            assert resp_clear is not None
            assert "貝葉斯隱馬爾可夫狀態已重置" in resp_clear
