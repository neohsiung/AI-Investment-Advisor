"""WP3a: direction-signed alpha / 方向校正後的 alpha。"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.services.signed_alpha import signed_alpha, direction_of_signal
from src.services.outcome_reflection_service import OutcomeReflectionService


def test_buy_unchanged():
    assert signed_alpha(5.0, "BUY") == 5.0
    assert signed_alpha(-2.0, "buy") == -2.0


def test_sell_flips_sign():
    assert signed_alpha(-4.0, "SELL") == 4.0
    assert signed_alpha(3.0, "SELL") == -3.0


@pytest.mark.parametrize("bad", ["HOLD", "", None, "LONG", "x"])
def test_unknown_direction_raises(bad):
    with pytest.raises(ValueError):
        signed_alpha(1.0, bad)


def test_direction_of_signal_five_value_scale():
    assert direction_of_signal("STRONG_BUY") == "BUY"
    assert direction_of_signal("BUY") == "BUY"
    assert direction_of_signal("SELL") == "SELL"
    assert direction_of_signal("STRONG_SELL") == "SELL"
    with pytest.raises(ValueError):
        direction_of_signal("WHATEVER")


def _service():
    with patch("src.services.outcome_reflection_service.get_db_engine", return_value=MagicMock()), \
         patch("src.services.outcome_reflection_service.resolve_user_id", return_value="u"):
        return OutcomeReflectionService(user_id="u")


def _resolve(signal, price_now):
    svc = _service()
    row = {"id": "d1", "ticker": "AAPL", "signal": signal, "agent_name": "A",
           "price_at_decision": 100.0,
           "decided_at": datetime(2026, 9, 25, tzinfo=timezone.utc), "horizon_days": 5}
    conn = MagicMock()
    svc.engine.begin.return_value.__enter__.return_value = conn
    with patch.object(svc, "_fetch_price", return_value=price_now), \
         patch.object(svc, "_fetch_benchmark_window", return_value=(700.0, 700.0)), \
         patch.object(svc, "_generate_lesson", return_value="l") as lesson, \
         patch.object(svc, "_distill_failure") as distill, \
         patch("src.services.rule_lifecycle_service.RuleLifecycleService") as rls:
        assert svc._resolve_one(row) is True
    return conn, lesson, distill, rls.return_value.backfill_score


def test_profitable_sell_is_a_win_not_a_failure():
    conn, lesson, distill, backfill = _resolve("SELL", 90.0)  # price fell 10%
    distill.assert_not_called()
    # backfill_score receives raw alpha + direction and signs internally.
    assert backfill.call_args[0][1:] == (pytest.approx(-10.0), "SELL")
    assert lesson.call_args[0][4] == pytest.approx(10.0)
    # Stored column keeps the raw (undirected) alpha: realized - benchmark.
    assert conn.execute.call_args[0][1]["alpha"] == pytest.approx(-10.0)


def test_losing_sell_distills_failure_with_signed_alpha():
    _, _, distill, backfill = _resolve("SELL", 110.0)
    distill.assert_called_once()
    assert distill.call_args[0][5] == pytest.approx(-10.0)
    assert backfill.call_args[0][1:] == (pytest.approx(10.0), "SELL")


def test_buy_unchanged_in_resolve():
    _, _, distill, backfill = _resolve("BUY", 90.0)
    distill.assert_called_once()
    assert backfill.call_args[0][1:] == (pytest.approx(-10.0), "BUY")


def test_hold_keeps_legacy_unsigned_behaviour():
    _, _, distill, backfill = _resolve("HOLD", 110.0)
    assert backfill.call_args[0][1:] == (pytest.approx(10.0), "BUY")
