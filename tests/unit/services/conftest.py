"""
Shared fixtures for service unit tests.
服務單元測試共用 fixture。
"""
import pytest
from unittest.mock import patch

# Plan-arithmetic tests (blackout, cross-sector rotation, scaling, risk parity, ...) were written
# against the old hardcoded 3-batch list. Their subject is NOT candidate selection, so they keep
# that fixed list via this patch; selection itself is covered by test_batch_dynamic_candidates.py.
# 這些測試的主題是計畫金額運算（避開視窗、跨板塊輪動、縮放、風險平價…），非候選選擇；
# 故以固定名單替代動態選擇。候選選擇另由 test_batch_dynamic_candidates.py 涵蓋。
_LEGACY_BATCHES = {
    1: [
        {"ticker": "NVDA", "target_pct": 0.10, "base_amount": 114.00, "confidence": 6.86, "role": "Alpha Top 1"},
        {"ticker": "TSM", "target_pct": 0.10, "base_amount": 144.00, "confidence": 6.69, "role": "Alpha Top 2"},
        {"ticker": "AAPL", "target_pct": 0.10, "base_amount": 89.00, "confidence": 6.86, "role": "Top 3"},
    ],
    2: [
        {"ticker": "MSFT", "target_pct": 0.10, "base_amount": 91.00, "confidence": 6.47, "role": "MSFT"},
        {"ticker": "MU", "target_pct": 0.05, "base_amount": 79.00, "confidence": 6.86, "role": "MU"},
        {"ticker": "AMD", "target_pct": 0.05, "base_amount": 77.00, "confidence": 6.47, "role": "AMD"},
    ],
    3: [
        {"ticker": "SPCX", "target_pct": 0.05, "base_amount": 76.00, "confidence": 6.47, "role": "SPCX"},
    ],
}

_LEGACY_BATCH_MODULES = {
    "test_cross_sector_momentum_funnel",
    "test_slippage_guard_and_batch_deployment",
    "test_calendar_blackout_service",
    "test_macro_event_causal_graph_service",
    "test_fill_quality_and_dynamic_slippage",
    "test_risk_parity_cvar_service",
    "test_dark_pool_and_convex_sharpe",
}


@pytest.fixture(autouse=True)
def _legacy_batch_candidates(request):
    if request.module.__name__.split(".")[-1] not in _LEGACY_BATCH_MODULES:
        yield
        return

    async def _fixed(self, total_equity, holdings, target_records=None):
        # batch number is not visible here; tests asking for batch N set it via call args below
        n = getattr(self, "_test_batch_number", 1)
        return [dict(b) for b in _LEGACY_BATCHES.get(n, _LEGACY_BATCHES[1])]

    from src.services.batch_cash_deployment_service import BatchCashDeploymentService

    original = BatchCashDeploymentService.get_deployment_plan

    async def _plan(self, batch_number=1):
        self._test_batch_number = batch_number
        return await original(self, batch_number)

    with patch.object(BatchCashDeploymentService, "_select_dynamic_candidates", _fixed), \
         patch.object(BatchCashDeploymentService, "get_deployment_plan", _plan):
        yield
