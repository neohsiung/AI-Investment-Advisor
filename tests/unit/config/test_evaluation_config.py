"""config/evaluation.yaml: honest-lab inputs (cost per side, ETF universe, cost multipliers) are valid and cannot be
silently weakened. / 誠實實驗室的輸入（單邊成本、ETF 宇宙、成本倍數）必須有效，且不能被悄悄弱化。"""
import pytest
from pydantic import ValidationError

from src.config.evaluation import EvaluationConfig, load_evaluation

_OK = {"cost_bps_per_side": 10.0, "cost_multipliers": [1.0, 2.0], "etf_universe": ["XLK", "XLF"]}


def test_strategy_lab_evaluation_yaml_loads():
    cfg = load_evaluation()
    assert cfg.cost_bps_per_side > 0
    assert cfg.etf_universe, "ETF universe must not be empty"


def test_strategy_lab_universe_is_etf_only_and_clean():
    cfg = load_evaluation()
    assert len(set(cfg.etf_universe)) == len(cfg.etf_universe)
    assert all(s == s.upper() and s.isalpha() for s in cfg.etf_universe)
    # the large-cap winners that caused survivorship bias must not creep back in
    assert not {"AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"} & set(cfg.etf_universe)


def test_strategy_lab_cost_levels_always_include_1x_and_a_stress_level():
    cfg = load_evaluation()
    assert 1.0 in cfg.cost_multipliers and max(cfg.cost_multipliers) >= 2.0


@pytest.mark.parametrize("mults", [[1.0], [2.0], [1.0, 1.5], [], [1.0, 1.0, 2.0]])
def test_strategy_lab_rejects_weakened_multipliers(mults):
    with pytest.raises(ValidationError):
        EvaluationConfig(**{**_OK, "cost_multipliers": mults})


def test_strategy_lab_rejects_empty_or_duplicate_universe_and_bad_cost():
    with pytest.raises(ValidationError):
        EvaluationConfig(**{**_OK, "etf_universe": []})
    with pytest.raises(ValidationError):
        EvaluationConfig(**{**_OK, "etf_universe": ["XLK", "xlk"]})
    with pytest.raises(ValidationError):
        EvaluationConfig(**{**_OK, "cost_bps_per_side": 0})


def test_strategy_lab_fee_is_marked_unverified_until_measured():
    """No silent number: the default must carry an explicit verification status. / 預設值必須明示未驗證。"""
    cfg = load_evaluation()
    assert cfg.cost_basis_status in ("unverified_conservative_default", "measured")
    if cfg.cost_basis_status == "measured":
        assert cfg.cost_basis_note
