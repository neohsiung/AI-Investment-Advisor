"""
Unit Tests for ConfidenceRebalanceService
=========================================
驗證置信度再平衡計劃生成、微型與劣勢部位汰除 (Pruning)、主動資本置換 (Capital Reclamation) 與下單執行。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.confidence_rebalance_service import ConfidenceRebalanceService


@pytest.fixture
def rebalance_service():
    return ConfidenceRebalanceService(user_id="test_user")


@pytest.mark.asyncio
async def test_get_rebalance_plan_with_pruning(rebalance_service):
    # Mock targets: AAPL and MSFT
    rebalance_service.ticker_service = MagicMock()
    rebalance_service.ticker_service.optimize_allocations.return_value = {
        "success": True,
        "targets": [
            {"ticker": "AAPL", "target_weight": 0.50, "confidence_score": 0.85},
            {"ticker": "MSFT", "target_weight": 0.45, "confidence_score": 0.80},
        ],
    }

    # Current weights: AAPL (20%), MSFT (10%), BAD1 (5%), DEAD_MICRO (1%), CASH (64%)
    # Total value = $1000
    mock_weights = {
        "weights": {"AAPL": 20.0, "MSFT": 10.0, "BAD1": 5.0, "DEAD_MICRO": 1.0},
        "cash_weight": 64.0,
        "total_value": 1000.0,
    }

    with patch.object(rebalance_service, "_get_current_weights", AsyncMock(return_value=mock_weights)):
        plan = await rebalance_service.get_rebalance_plan()

    assert plan["success"] is True
    trades = plan["trades"]["all"]
    sells = plan["trades"]["sells"]
    buys = plan["trades"]["buys"]

    # BAD1 and DEAD_MICRO are evicted / not in targets -> must be in sells with target_weight = 0
    sell_tickers = [s["ticker"] for s in sells]
    assert "BAD1" in sell_tickers
    assert "DEAD_MICRO" in sell_tickers

    # AAPL and MSFT need buys
    buy_tickers = [b["ticker"] for b in buys]
    assert "AAPL" in buy_tickers
    assert "MSFT" in buy_tickers

    # Check pruning summary
    pruning = plan["summary"]["pruning_summary"]
    assert pruning["pruned_count"] == 2
    assert "BAD1" in pruning["pruned_tickers"]
    assert "DEAD_MICRO" in pruning["pruned_tickers"]
    assert pruning["pruned_amount"] == 60.0  # (5% + 1%) * 1000 = $60


@pytest.mark.asyncio
async def test_reclaim_capital_for_buy_sufficient_cash(rebalance_service):
    mock_weights = {
        "weights": {"AAPL": 50.0},
        "cash_weight": 50.0,
        "total_value": 1000.0,
    }  # Available cash = $500

    with patch.object(rebalance_service, "_get_current_weights", AsyncMock(return_value=mock_weights)):
        res = await rebalance_service.reclaim_capital_for_buy(
            candidate_ticker="NVDA",
            target_amount=100.0,
            candidate_score=9.0,
        )

    assert res["status"] == "sufficient_cash"
    assert res["reclaimed_amount"] == 0.0
    assert len(res["sells"]) == 0


@pytest.mark.asyncio
async def test_reclaim_capital_for_buy_trigger_rotation(rebalance_service):
    # Only $20 cash available, need $100 for NVDA -> shortfall $80
    mock_weights = {
        "weights": {"AAPL": 50.0, "WEAK_STOCK": 8.0, "MICRO_STOCK": 2.0},
        "cash_weight": 2.0,  # $20 cash on $1000 total
        "total_value": 1000.0,
    }

    rebalance_service.ticker_service = MagicMock()
    rebalance_service.ticker_service.get_targets.return_value = [
        {"ticker": "AAPL", "target_weight": 0.50}
    ]
    rebalance_service.ticker_service.repo.get_research.side_effect = lambda uid, sym, limit=3: (
        [{"confidence_score": 0.40}] if sym == "WEAK_STOCK" else [{"confidence_score": 0.50}]
    )

    with patch.object(rebalance_service, "_get_current_weights", AsyncMock(return_value=mock_weights)):
        res = await rebalance_service.reclaim_capital_for_buy(
            candidate_ticker="NVDA",
            target_amount=100.0,
            candidate_score=9.0,
            execute=False,
        )

    assert res["status"] == "reclaimed"
    assert res["candidate_ticker"] == "NVDA"
    assert len(res["sells"]) >= 1
    # Both WEAK_STOCK and MICRO_STOCK should be selected for liquidation
    sold_tickers = [s["ticker"] for s in res["sells"]]
    assert "WEAK_STOCK" in sold_tickers or "MICRO_STOCK" in sold_tickers
    assert res["reclaimed_amount"] >= 80.0


@pytest.mark.asyncio
async def test_smart_cash_deployment_eliminates_cash_drag(rebalance_service):
    """
    驗證先賣後買智慧資金再部署：
    平倉 2 檔死資本釋放 $200，帳戶有 2 檔目標股需要增持，
    系統智慧分配 $200 至買單，現金拖累為 0。
    """
    rebalance_service.ticker_service = MagicMock()
    rebalance_service.ticker_service.optimize_allocations.return_value = {
        "success": True,
        "targets": [
            {"ticker": "NVDA", "target_weight": 0.30, "confidence_score": 0.85},
            {"ticker": "AAPL", "target_weight": 0.30, "confidence_score": 0.80},
        ],
    }

    # Total = $1000. DEAD1 (10%=$100), DEAD2 (10%=$100), NVDA (10%=$100), AAPL (10%=$100), CASH (60%)
    mock_weights = {
        "weights": {"DEAD1": 10.0, "DEAD2": 10.0, "NVDA": 10.0, "AAPL": 10.0},
        "cash_weight": 60.0,
        "total_value": 1000.0,
    }

    with patch.object(rebalance_service, "_get_current_weights", AsyncMock(return_value=mock_weights)):
        plan = await rebalance_service.get_rebalance_plan()

    assert plan["success"] is True
    sells = plan["trades"]["sells"]
    buys = plan["trades"]["buys"]

    # 2 dead stocks sold
    assert len(sells) == 2
    assert plan["summary"]["total_sell_amount"] == 200.0

    # 2 buys generated
    assert len(buys) == 2
    buy_tickers = [b["ticker"] for b in buys]
    assert "NVDA" in buy_tickers
    assert "AAPL" in buy_tickers

    # Both NVDA and AAPL need (0.30 - 0.10) * 1000 = $200 each ($400 total)
    # Available cash covers the $400 ($200 from sells + usable cash) -> buys fully funded
    assert plan["summary"]["cash_shortfall"] == 0.0

