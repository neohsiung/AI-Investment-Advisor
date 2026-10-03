"""
Unit Test Suite: Bayesian Hidden Markov Model Regime Transition Service (O1)
=============================================================================
Verifies online forward filtering, Gaussian emission likelihoods, transition
persistence, Shannon entropy, confidence index, and soft mixture policy blending.
"""
import math
import pytest

from src.services.regime_hmm_service import (
    BayesianRegimeHMMService,
    RegimeObservation,
    RegimePosterior,
    RegimeState,
)


class MockSettingsRepo:
    def __init__(self, settings: dict):
        self.settings = settings

    def get(self, user_id: str, key: str):
        return self.settings.get(key)


@pytest.fixture
def hmm_service():
    return BayesianRegimeHMMService(user_id="test_user")


def test_bull_regime_online_filtering(hmm_service):
    """Verify strong positive trend and calm VIX produce high-confidence Bull posterior."""
    obs = RegimeObservation(
        spy_price=550.0,
        spy_sma200=500.0,      # trend_ratio = +10.0%
        vix=13.5,              # low calm VIX
        return_5d=0.020,       # +2.0% return
    )

    posterior = hmm_service.update_beliefs(obs)

    assert posterior.dominant_regime == RegimeState.BULL
    assert posterior.probabilities[RegimeState.BULL.value] > 0.90
    assert posterior.probabilities[RegimeState.BEAR.value] < 0.01
    assert posterior.confidence > 0.80
    # Bullish blended cash reserve should be very close to 5.0%
    assert 4.5 <= posterior.blended_cash_reserve_pct <= 6.0
    # Bullish target beta should be close to 1.10
    assert 1.05 <= posterior.blended_target_beta <= 1.12


def test_bear_crisis_online_filtering(hmm_service):
    """Verify broken trend and panic VIX produce high-confidence Bear Crisis posterior."""
    obs = RegimeObservation(
        spy_price=440.0,
        spy_sma200=500.0,      # trend_ratio = -12.0%
        vix=38.0,              # spiking panic VIX
        return_5d=-0.045,      # sharp drawdown
    )

    posterior = hmm_service.update_beliefs(obs)

    assert posterior.dominant_regime == RegimeState.BEAR
    assert posterior.probabilities[RegimeState.BEAR.value] > 0.90
    assert posterior.probabilities[RegimeState.BULL.value] < 0.01
    assert posterior.confidence > 0.85
    # Defensive blended cash reserve should be close to 50.0%
    assert 48.0 <= posterior.blended_cash_reserve_pct <= 50.0
    # Defensive target beta should be close to 0.40
    assert 0.38 <= posterior.blended_target_beta <= 0.45


def test_neutral_transition_state(hmm_service):
    """Verify trend near 200MA and baseline VIX produce Neutral regime with moderate confidence."""
    obs = RegimeObservation(
        spy_price=502.0,
        spy_sma200=500.0,      # trend_ratio = +0.4%
        vix=21.0,              # baseline VIX
        return_5d=0.002,       # flat return
    )

    posterior = hmm_service.update_beliefs(obs)

    assert posterior.dominant_regime == RegimeState.NEUTRAL
    assert posterior.probabilities[RegimeState.NEUTRAL.value] > 0.70
    assert 17.0 <= posterior.blended_cash_reserve_pct <= 23.0
    assert 0.80 <= posterior.blended_target_beta <= 0.90


def test_transition_matrix_row_stochastic_and_persistence(hmm_service):
    """Verify transition matrix is valid row-stochastic matrix with diagonal persistence."""
    matrix = hmm_service.get_transition_matrix(persistence=0.92)

    assert len(matrix) == 3
    for row in matrix:
        assert len(row) == 3
        # Each row must sum to 1.0
        assert abs(sum(row) - 1.0) < 1e-6
        # All probabilities must be positive
        for prob in row:
            assert prob >= 0.0

    # Diagonals must match persistence
    assert abs(matrix[0][0] - 0.92) < 1e-6
    assert abs(matrix[1][1] - 0.92) < 1e-6
    assert abs(matrix[2][2] - 0.92) < 1e-6

    # Verify structural topology: Bull transitions more easily to Neutral than Bear
    assert matrix[0][1] > matrix[0][2]
    # Bear transitions more easily to Neutral than Bull
    assert matrix[2][1] > matrix[2][0]


def test_shannon_entropy_and_confidence(hmm_service):
    """Verify extreme distributions yield accurate Shannon entropy and confidence bounds."""
    # 1. Pure certainty: [1.0, 0.0, 0.0] -> Entropy ~ 0, Confidence ~ 1.0
    obs_bull = RegimeObservation(spy_price=600.0, spy_sma200=500.0, vix=12.0, return_5d=0.03)
    post_bull = hmm_service.update_beliefs(obs_bull)
    assert post_bull.confidence > 0.90
    assert post_bull.entropy < 0.30

    # 2. Ambiguity check on edge state
    obs_ambig = RegimeObservation(spy_price=500.0, spy_sma200=500.0, vix=24.0, return_5d=-0.005)
    post_ambig = hmm_service.update_beliefs(obs_ambig)
    # Ambiguous state should have lower confidence than pure bull
    assert post_ambig.confidence < post_bull.confidence


def test_soft_mixture_blend_weights(hmm_service):
    """Verify blend_weights calculates exact probability-weighted linear combinations."""
    bull_weights = {"momentum": 0.40, "quality": 0.15, "low_vol": 0.10}
    neutral_weights = {"momentum": 0.10, "quality": 0.35, "low_vol": 0.15}
    bear_weights = {"momentum": 0.05, "quality": 0.35, "low_vol": 0.40}

    probs = {
        RegimeState.BULL.value: 0.50,
        RegimeState.NEUTRAL.value: 0.30,
        RegimeState.BEAR.value: 0.20,
    }

    blended = hmm_service.blend_weights(bull_weights, neutral_weights, bear_weights, probs)

    # Expected:
    # momentum: 0.50*0.40 + 0.30*0.10 + 0.20*0.05 = 0.20 + 0.03 + 0.01 = 0.2400
    # quality:  0.50*0.15 + 0.30*0.35 + 0.20*0.35 = 0.075 + 0.105 + 0.07 = 0.2500
    # low_vol:  0.50*0.10 + 0.30*0.15 + 0.20*0.40 = 0.05 + 0.045 + 0.08 = 0.1750
    assert abs(blended["momentum"] - 0.2400) < 1e-4
    assert abs(blended["quality"] - 0.2500) < 1e-4
    assert abs(blended["low_vol"] - 0.1750) < 1e-4


def test_k_step_forward_regime_prediction(hmm_service):
    """Verify k-step prediction transitions smoothly according to Markov chain power."""
    current_probs = {
        RegimeState.BULL.value: 0.85,
        RegimeState.NEUTRAL.value: 0.10,
        RegimeState.BEAR.value: 0.05,
    }

    # 1-day step should stay very close to current due to 0.92 persistence
    p_1d = hmm_service.predict_next_regime(current_probs, horizon_days=1)
    assert p_1d[RegimeState.BULL.value] > 0.75
    assert abs(sum(p_1d.values()) - 1.0) < 1e-4

    # 10-day step should show decay/diffusion towards steady state
    p_10d = hmm_service.predict_next_regime(current_probs, horizon_days=10)
    assert p_10d[RegimeState.BULL.value] < p_1d[RegimeState.BULL.value]
    assert abs(sum(p_10d.values()) - 1.0) < 1e-4


def test_batch_historical_filtering(hmm_service):
    """Verify batch filtering sequentially propagates posterior beliefs over time."""
    history = [
        RegimeObservation(spy_price=550.0, spy_sma200=500.0, vix=14.0),  # Bull
        RegimeObservation(spy_price=530.0, spy_sma200=500.0, vix=17.0),  # Cooling Bull
        RegimeObservation(spy_price=505.0, spy_sma200=500.0, vix=21.0),  # Transitioning Neutral
        RegimeObservation(spy_price=470.0, spy_sma200=500.0, vix=29.0),  # Slipping into Bear
        RegimeObservation(spy_price=440.0, spy_sma200=500.0, vix=35.0),  # Crisis Bear
    ]

    posteriors = hmm_service.batch_filter(history)

    assert len(posteriors) == 5
    # Day 1: Bull
    assert posteriors[0].dominant_regime == RegimeState.BULL
    # Day 5: Bear
    assert posteriors[4].dominant_regime == RegimeState.BEAR
    # Cash reserve should gradually and smoothly climb from ~5% to ~50%
    assert posteriors[0].blended_cash_reserve_pct < posteriors[2].blended_cash_reserve_pct
    assert posteriors[2].blended_cash_reserve_pct < posteriors[4].blended_cash_reserve_pct


def test_settings_repo_dynamic_overrides():
    """Verify service respects custom repository settings."""
    mock_repo = MockSettingsRepo({
        "hmm_regime_enabled": True,
        "hmm_transition_persistence": 0.96,
        "hmm_min_confidence_threshold": 0.50,
        "hmm_vix_bear_threshold": 30.0,
        "hmm_vix_bull_threshold": 17.0,
    })

    svc = BayesianRegimeHMMService(user_id="u1", settings_repo=mock_repo)

    assert svc.transition_persistence == 0.96
    assert svc.min_confidence_threshold == 0.50
    assert svc.vix_bear_threshold == 30.0
    assert svc.vix_bull_threshold == 17.0

    matrix = svc.get_transition_matrix()
    assert abs(matrix[0][0] - 0.96) < 1e-6


def test_edge_case_zero_or_corrupt_observation(hmm_service):
    """Verify degenerate inputs produce safe neutral fallback without crashing."""
    corrupt_obs = RegimeObservation(
        spy_price=0.0,
        spy_sma200=0.0,
        vix=0.0,
        return_5d=0.0,
    )

    posterior = hmm_service.update_beliefs(corrupt_obs)

    assert isinstance(posterior, RegimePosterior)
    assert abs(sum(posterior.probabilities.values()) - 1.0) < 1e-4
    assert 0.0 <= posterior.confidence <= 1.0
    assert 5.0 <= posterior.blended_cash_reserve_pct <= 50.0
