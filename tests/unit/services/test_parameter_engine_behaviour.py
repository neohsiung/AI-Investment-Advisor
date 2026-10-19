"""Behaviour of the loosening rule over time (G6): zero effect never loosens, a true edge loosens only once both
window conditions can hold, a negative 2x-cost series blocks.
放寬規則隨時間的行為：零效應不放寬；真實優勢要等兩個窗口條件都可能成立才放寬；2 倍成本為負則擋下。
"""
import numpy as np

from src.evaluation.regime import RegimeCheck
from src.evaluation.sequential import loosening_alpha
from src.services import parameter_engine as pe
from tests.charter_synth import series_dict, stream

KEY = "batch_deploy_min_confidence"
OK_REGIME = RegimeCheck(True, True, {"up_lovol": 60})
ALPHA = loosening_alpha(40)


def _verdict_at(x, n, x2=None, min_n=30):
    s = series_dict(KEY, x[:n], x2=None if x2 is None else x2[:n])
    return pe.loosening_conditions(s, ALPHA, min_n, OK_REGIME)


def test_zero_effect_never_loosens_500_runs():
    rng = np.random.default_rng(20261019)
    loosenings = 0
    for _ in range(500):
        x = rng.normal(0.0, 0.02, 252)
        for n in range(30, 253, 3):                       # every third trading day; the CS bound is any-time valid
            if _verdict_at(x, n)["all"] is True:
                loosenings += 1
                break
    assert loosenings == 0


def test_true_positive_loosens_only_after_3x21_and_2x63():
    firsts = []
    for seed in range(5):
        x = stream(0.012, 0.006, 252, 100 + seed)
        first = next((n for n in range(1, 253) if _verdict_at(x, n)["all"] is True), None)
        assert first is not None, "a strong edge must loosen within a year"
        c = _verdict_at(x, first)
        assert first >= 126 and first >= 30
        assert c["w21x3_x1.0"] and c["w63x2_x1.0"] and c["w21x3_x2.0"] and c["w63x2_x2.0"]
        assert _verdict_at(x, 125)["all"] is False
        firsts.append(first)
    assert min(firsts) >= 126


def test_two_x_cost_negative_blocks_even_if_one_x_positive():
    x = stream(0.012, 0.006, 200, 7)
    x2 = x - 0.03                                         # at 2x cost the same decisions lose money
    c = _verdict_at(x, 200, x2=x2)
    assert c["cs_lower_gt0_63d_x1.0"] is True
    assert c["cs_lower_gt0_63d_x2.0"] is False and c["all"] is False
