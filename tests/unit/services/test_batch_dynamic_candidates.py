"""
Dynamic candidate selection for batch cash deployment (replaces the hardcoded 8-ticker batches).
分批建倉動態候選選擇（取代寫死的 8 檔批次）。
"""
import pytest

from src.services.batch_cash_deployment_service import BatchCashDeploymentService

rank = BatchCashDeploymentService.rank_candidates


def _t(sym, w, c):
    return {"ticker": sym, "target_weight": w, "confidence_score": c}


def test_only_active_universe_members_are_eligible():
    out = rank([_t("NVDA", 0.1, 0.7), _t("ZZZZ", 0.1, 0.9)], {"NVDA"}, {}, 1000.0, 100.0, 3, 5.5)
    assert [c["ticker"] for c in out] == ["NVDA"]


def test_ranked_by_confidence_then_gap_and_limited_to_top_n():
    targets = [_t("A", 0.10, 0.60), _t("B", 0.10, 0.80), _t("C", 0.20, 0.80), _t("D", 0.10, 0.70)]
    out = rank(targets, {"A", "B", "C", "D"}, {}, 1000.0, 100.0, 3, 5.5)
    assert [c["ticker"] for c in out] == ["C", "B", "D"]


def test_order_amount_capped_and_gap_aware():
    out = rank([_t("A", 0.5, 0.9), _t("B", 0.05, 0.9)], {"A", "B"}, {"B": 40.0}, 1000.0, 100.0, 3, 5.5)
    by = {c["ticker"]: c for c in out}
    assert by["A"]["base_amount"] == 100.0          # gap 500 -> capped at max order
    assert by["B"]["base_amount"] == 10.0           # gap 50-40 = 10 -> exact gap


def test_below_min_gap_or_confidence_excluded_and_unresearched_default_excluded():
    targets = [_t("FULL", 0.10, 0.9), _t("LOW", 0.10, 0.4), _t("UNRES", 0.10, 0.5), _t("NOCONF", 0.1, None)]
    out = rank(targets, {"FULL", "LOW", "UNRES", "NOCONF"}, {"FULL": 100.0}, 1000.0, 100.0, 5, 5.5)
    assert out == []  # FULL satisfied (gap 0), LOW/UNRES below 5.5, NOCONF has no score


def test_cash_row_and_zero_weight_ignored():
    out = rank([_t("CASH", 0.4, 0.9), _t("A", 0.0, 0.9)], {"CASH", "A"}, {}, 1000.0, 100.0, 3, 5.5)
    assert out == []


@pytest.mark.asyncio
async def test_active_batch_zero_when_no_candidates_and_one_when_candidates(monkeypatch):
    svc = BatchCashDeploymentService.__new__(BatchCashDeploymentService)
    svc.user_id = "u1"

    async def status():
        return {"deployable_cash": 500.0, "total_equity": 1000.0}

    async def holdings():
        return {}

    svc.get_portfolio_status = status
    svc._load_holdings = holdings

    async def none(**kw):
        return []

    async def some(**kw):
        return [{"ticker": "A"}]

    svc._select_dynamic_candidates = none
    assert await svc.get_active_batch_number() == 0
    svc._select_dynamic_candidates = some
    assert await svc.get_active_batch_number() == 1


@pytest.mark.asyncio
async def test_active_batch_zero_when_cash_below_minimum():
    svc = BatchCashDeploymentService.__new__(BatchCashDeploymentService)
    svc.user_id = "u1"

    async def status():
        return {"deployable_cash": 5.0, "total_equity": 1000.0}

    svc.get_portfolio_status = status
    assert await svc.get_active_batch_number() == 0
