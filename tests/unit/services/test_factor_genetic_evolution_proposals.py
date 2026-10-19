"""
G3: the genetic evolution engine proposes, it never writes live settings.
G3：遺傳演化引擎只提案，不再直接寫入實盤設定。
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from src.services.factor_genetic_evolution_engine import FactorGeneticEvolutionEngine
from src.services.factor_rotation_replay_engine import FactorWeightMatrix


def _engine(writer):
    settings = MagicMock()
    settings.get_setting.side_effect = lambda k, default=None, user_id=None: default
    return FactorGeneticEvolutionEngine(user_id="u1", settings_service=settings, proposal_writer=writer), settings


def test_engine_writes_proposal_not_setting():
    writer = MagicMock(return_value="prop-1")
    engine, settings = _engine(writer)
    matrix = FactorWeightMatrix()

    pid = engine._propose_matrix(matrix, run_id="run-1", evidence={"wfo_efficiency": 0.9})

    assert pid == "prop-1"
    settings.set_setting.assert_not_called()
    settings.set.assert_not_called()
    (payload,), _ = writer.call_args
    assert payload["user_id"] == "u1" and payload["source"] == "genetic_evolution"
    assert set(payload["proposed_values"]) == {
        "tactical_phase_factor_weights", "tactical_rotation_min_edge_pct", "factor_liquidity_premium_weight"}
    assert json.loads(payload["proposed_values"]["tactical_phase_factor_weights"]) == matrix.to_dict()
    assert payload["evidence"]["wfo_efficiency"] == 0.9


def test_proposal_write_failure_is_visible_not_faked():
    engine, _ = _engine(MagicMock(side_effect=RuntimeError("db down")))
    assert engine._propose_matrix(FactorWeightMatrix(), run_id="r", evidence={}) is None


def test_gate_off_runs_nothing():
    from src.infrastructure import tasks

    with patch("src.services.evolution_gate.synthetic_evolution_enabled", return_value=False), \
            patch("src.services.strategy_auto_evolution_service.StrategyAutoEvolutionService") as svc, \
            patch("src.services.factor_genetic_evolution_engine.FactorGeneticEvolutionEngine.evolve") as evolve:
        out = tasks.run_factor_genetic_evolution(user_id="u1", force=True)

    assert "skipped" in str(out).lower()
    svc.assert_not_called()
    evolve.assert_not_called()
