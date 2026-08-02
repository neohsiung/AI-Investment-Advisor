"""
Backtest API (P4/P5, 2026-07-11) — run + list + fetch PortfolioBacktestEngine
results. Powers the new backtest results UI (frontend/src/app/backtest).
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.v1.router import get_current_user_id
from src.repositories.backtest_repository import AlchemyBacktestRepository
from src.services.market_data_service import MarketDataService
from src.services.portfolio_backtest_engine import PortfolioBacktestEngine, simple_ma_crossover_signal
from src.utils.logger import setup_logger

logger = setup_logger("API_Backtest")
router = APIRouter()


class RunBacktestRequest(BaseModel):
    ticker: str
    days: int = Field(default=180, ge=30, le=1000)
    fast_ma: int = Field(default=10, ge=2, le=100)
    slow_ma: int = Field(default=30, ge=5, le=250)
    initial_cash: float = Field(default=100_000.0, gt=0)
    stoploss_pct: Optional[float] = Field(default=0.08, ge=0, le=0.5)
    position_size_pct: float = Field(default=0.20, gt=0, le=1.0)


def get_backtest_repo() -> AlchemyBacktestRepository:
    return AlchemyBacktestRepository()


@router.post("/run")
async def run_backtest(
    req: RunBacktestRequest,
    user_id: str = Depends(get_current_user_id),
    repo: AlchemyBacktestRepository = Depends(get_backtest_repo),
) -> Dict[str, Any]:
    """
    Run a deterministic MA-crossover backtest for `ticker` and persist the
    result. Strategy is intentionally simple/fast (the engine's `signal_fn`
    is pluggable — this is the reference baseline strategy, not the council's
    LLM reasoning, which is too slow/costly to replay bar-by-bar).
    """
    try:
        market_service = MarketDataService(user_id=user_id)
        ohlcv = market_service.get_ohlcv(req.ticker, days=req.days)
        if not ohlcv or not ohlcv.get("close") or len(ohlcv["close"]) < req.slow_ma + 5:
            raise HTTPException(status_code=422, detail=f"Not enough historical data for {req.ticker}")

        engine = PortfolioBacktestEngine(
            initial_cash=req.initial_cash,
            stoploss_pct=req.stoploss_pct,
            position_size_pct=req.position_size_pct,
        )
        signal_fn = simple_ma_crossover_signal(req.fast_ma, req.slow_ma)
        result = engine.run(req.ticker, ohlcv, signal_fn)

        strategy_name = f"ma_crossover_{req.fast_ma}_{req.slow_ma}"
        run_id = repo.save_run(
            user_id=user_id, ticker=req.ticker, strategy_name=strategy_name,
            initial_cash=req.initial_cash, final_cash=result.final_cash,
            metrics=result.metrics, trades=result.trades,
            equity_curve=result.equity_curve, dates=result.dates,
            params={"fast_ma": req.fast_ma, "slow_ma": req.slow_ma, "stoploss_pct": req.stoploss_pct},
        )
        return {"status": "success", "run_id": run_id, "metrics": result.metrics,
                "final_cash": result.final_cash, "trade_count": len(result.trades)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backtest run failed for {req.ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


@router.get("/history")
async def list_backtest_runs(
    ticker: Optional[str] = None,
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
    repo: AlchemyBacktestRepository = Depends(get_backtest_repo),
) -> Dict[str, Any]:
    """List past backtest runs (metrics + metadata only, no equity curve — use /history/{run_id} for that)."""
    try:
        runs = repo.list_runs(user_id=user_id, ticker=ticker, limit=limit)
        return {"status": "success", "runs": runs}
    except Exception as e:
        logger.error(f"list_backtest_runs failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{run_id}")
async def get_backtest_run(
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    repo: AlchemyBacktestRepository = Depends(get_backtest_repo),
) -> Dict[str, Any]:
    """Fetch a single backtest run in full: metrics, trades, equity curve."""
    run = repo.get_run(run_id)
    if not run or run.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return {"status": "success", "run": run}
