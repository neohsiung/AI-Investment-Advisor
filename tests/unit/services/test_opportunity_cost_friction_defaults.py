"""Production friction defaults: conservative, configurable, and the fallback is loud."""
from unittest.mock import MagicMock

import pytest

from src.services.opportunity_cost_service import OpportunityCostService


def _settings(value):
    s = MagicMock()
    s.get_setting.side_effect = lambda k, d=None, *a, **kw: value if k == "rotation_roundtrip_friction_pct" else d
    return s


def test_default_roundtrip_friction_is_one_percent_not_the_old_guess():
    svc = OpportunityCostService(user_id="u", settings_service=_settings(OpportunityCostService.FALLBACK_ROUNDTRIP_FRICTION_PCT))
    assert svc.friction_hurdle_score == pytest.approx(1.0)
    assert svc.calculate_roundtrip_friction() == pytest.approx(0.010)       # was 0.003


def test_setting_overrides_friction_and_moves_the_swap_decision():
    low = OpportunityCostService(user_id="u", settings_service=_settings(0.3))
    high = OpportunityCostService(user_id="u", settings_service=_settings(1.5))
    assert low.friction_hurdle_score == pytest.approx(0.3) and high.friction_hurdle_score == pytest.approx(1.5)
    kw = dict(holding_ticker="A", candidate_ticker="B", holding_score=5.0, candidate_score=7.6, min_delta_override=2.0)
    assert low.evaluate_swap(**kw).should_swap is True       # raw 2.6 - 0.3 = 2.3 >= 2.0
    assert high.evaluate_swap(**kw).should_swap is False     # raw 2.6 - 1.5 = 1.1 <  2.0
