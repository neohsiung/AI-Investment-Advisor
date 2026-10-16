"""
Rebalance guard (mission invariants). Includes a replay of the 2026-09-29 incident: 11 holdings sold in one run.
再平衡護欄測試，含 2026-09-29 一次賣 11 檔事故的回放。
"""
from src.services.rebalance_guard import evaluate_sells, scale_buys_to_budget

NAV = 1700.0


def _sell(t, amt, conf=7.0):
    return {"ticker": t, "delta_amount": -amt, "delta_weight": -amt / NAV * 100, "confidence": conf, "action": "SELL"}


def _buy(t, amt):
    return {"ticker": t, "delta_amount": amt, "delta_weight": amt / NAV * 100, "confidence": 8.0, "action": "BUY"}


def test_replay_0929_eleven_sells_are_cut_to_the_daily_cap():
    sells = [_sell(f"OLD{i}", 40.0, conf=5.0 + i * 0.1) for i in range(11)]
    buys = [_buy(f"NEW{i}", 60.0) for i in range(7)]
    d = evaluate_sells(sells, buys, NAV, data_healthy=True)
    assert len(d.approved) == 2                      # mission: max 2 non-safety sells per day
    assert {r["guard_reason"] for r in d.rejected} == {"daily_sell_count_cap"}
    # weakest-scored sells go first
    assert [a["ticker"] for a in d.approved] == ["OLD0", "OLD1"]


def test_sells_without_replacement_plan_are_blocked():
    d = evaluate_sells([_sell("A", 100.0)], [], NAV, data_healthy=True)
    assert d.approved == [] and d.rejected[0]["guard_reason"] == "no_replacement_plan"
    d = evaluate_sells([_sell("A", 100.0)], [_buy("B", 70.0)], NAV, data_healthy=True)   # 70% < 80% coverage
    assert d.approved == []
    d = evaluate_sells([_sell("A", 100.0)], [_buy("B", 85.0)], NAV, data_healthy=True)
    assert [a["ticker"] for a in d.approved] == ["A"]


def test_unscored_sells_are_never_executed():
    d = evaluate_sells([_sell("A", 50.0, conf=None), _sell("B", 50.0, conf=0)], [_buy("C", 100.0)], NAV, True)
    assert d.approved == [] and {r["guard_reason"] for r in d.rejected} == {"no_score"}


def test_unhealthy_data_blocks_everything_fail_closed():
    d = evaluate_sells([_sell("A", 50.0)], [_buy("C", 60.0)], NAV, data_healthy=False)
    assert d.approved == [] and d.rejected[0]["guard_reason"] == "data_unhealthy"
    d = evaluate_sells([_sell("A", 50.0)], [_buy("C", 60.0)], 0.0, data_healthy=True)
    assert d.approved == []


def test_oversized_sell_is_trimmed_to_the_percentage_cap():
    # 20% of 1700 = 340; a single 400 sell is trimmed to 340 (unwound over several days)
    d = evaluate_sells([_sell("A", 400.0)], [_buy("B", 400.0)], NAV, True)
    assert len(d.approved) == 1
    assert abs(d.approved[0]["delta_amount"]) == 340.0 and d.approved[0]["guard_trimmed"] is True


def test_remaining_cap_below_minimum_trade_rejects():
    d = evaluate_sells([_sell("A", 100.0)], [_buy("B", 110.0)], NAV, True, sold_today_count=1, sold_today_amount=335.0)
    assert d.approved == [] and d.rejected[0]["guard_reason"] == "daily_sell_value_cap"


def test_original_ordering_is_preserved():
    sells = [_sell("Z", 50.0, conf=9.0), _sell("A", 40.0, conf=5.0)]
    d = evaluate_sells(sells, [_buy("B", 100.0)], NAV, True)
    assert [a["ticker"] for a in d.approved] == ["Z", "A"]


def test_sells_already_done_today_count_against_the_caps():
    d = evaluate_sells([_sell("A", 50.0)], [_buy("B", 60.0)], NAV, True, sold_today_count=2, sold_today_amount=100.0)
    assert d.approved == [] and d.rejected[0]["guard_reason"] == "daily_sell_count_cap"
    d = evaluate_sells([_sell("A", 100.0)], [_buy("B", 110.0)], NAV, True, sold_today_count=1, sold_today_amount=335.0)
    assert d.approved == [] and d.rejected[0]["guard_reason"] == "daily_sell_value_cap"


def test_no_sells_is_a_noop():
    d = evaluate_sells([], [_buy("B", 60.0)], NAV, True)
    assert d.approved == [] and d.rejected == []


def test_scale_buys_never_exceed_budget():
    buys = [_buy("A", 100.0), _buy("B", 100.0)]
    out = scale_buys_to_budget(buys, 100.0, 10.0)
    assert sum(b["delta_amount"] for b in out) <= 100.0 + 0.01
    assert scale_buys_to_budget(buys, 0.0, 10.0) == []
    assert scale_buys_to_budget(buys, 500.0, 10.0) == buys
    tiny = scale_buys_to_budget([_buy("A", 100.0), _buy("B", 5.0)], 50.0, 10.0)
    assert all(b["delta_amount"] >= 10.0 for b in tiny)
