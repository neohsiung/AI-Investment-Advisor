"""
API Endpoints for Portfolio Adaptive Intelligence (D1 Central Orchestrator).
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any, Optional, Tuple
import pandas as pd

from src.api.v1.dependencies import get_current_user_id
from src.api.v1.schemas.adaptive_intelligence_schemas import (
    AdaptiveHealthSummaryResponse,
    HealthRadarSchema,
    DiagnosePortfolioRequest,
    DiagnosePortfolioResponse,
    RebalancePlanRequest,
    RebalancePlanResponse,
)
from src.services.portfolio_adaptive_intelligence_service import (
    PortfolioAdaptiveIntelligenceService,
    AdaptiveDiagnosticReport,
)
from src.services.dashboard_service import DashboardService
from src.utils.logger import setup_logger
from src.utils.api_cache import cached_api_response

logger = setup_logger("API_AdaptiveIntelligence")
router = APIRouter()


def get_adaptive_service(user_id: str = Depends(get_current_user_id)) -> PortfolioAdaptiveIntelligenceService:
    """Dependency provider for PortfolioAdaptiveIntelligenceService"""
    return PortfolioAdaptiveIntelligenceService(user_id=user_id)


def get_dashboard_service(user_id: str = Depends(get_current_user_id)) -> DashboardService:
    """Dependency provider for DashboardService"""
    return DashboardService(user_id=user_id)


async def _extract_user_holdings(
    dashboard_service: DashboardService,
) -> Tuple[Dict[str, float], float, Dict[str, float]]:
    """Helper to extract live portfolio weights, total value, and prices from database."""
    try:
        data = await dashboard_service.prepare_dashboard_data(dashboard_service.user_id)
        positions_df = data.get("positions_df", pd.DataFrame())
        metrics = data.get("metrics", {})
        nlv = float(metrics.get("nlv", 100000.0))
        cash = float(metrics.get("cash_balance", 10000.0))

        weights: Dict[str, float] = {}
        prices: Dict[str, float] = {}

        if not positions_df.empty and "symbol" in positions_df.columns:
            for _, row in positions_df.iterrows():
                sym = str(row.get("symbol", "")).upper()
                mv = float(row.get("market_value", 0.0))
                p = float(row.get("current_price", row.get("price", 100.0)))
                if sym and mv > 0:
                    weights[sym] = mv / nlv if nlv > 0 else 0.0
                    prices[sym] = p

        cash_pct = cash / nlv if nlv > 0 else 0.10
        weights["CASH"] = cash_pct

        # If empty, fallback to balanced template
        if len(weights) <= 1:
            weights = {
                "SPY": 0.35,
                "QQQ": 0.25,
                "TLT": 0.15,
                "GLD": 0.05,
                "CASH": 0.20,
            }
            prices = {"SPY": 510.0, "QQQ": 440.0, "TLT": 92.0, "GLD": 215.0}

        return weights, nlv, prices
    except Exception as e:
        logger.warning(f"Failed to fetch live portfolio context: {e}, falling back to defaults")
        return (
            {"SPY": 0.35, "QQQ": 0.25, "TLT": 0.15, "GLD": 0.05, "CASH": 0.20},
            100000.0,
            {"SPY": 510.0, "QQQ": 440.0, "TLT": 92.0, "GLD": 215.0},
        )


@router.get("/health", response_model=AdaptiveHealthSummaryResponse)
@cached_api_response(ttl_seconds=30)
async def get_adaptive_health(
    service: PortfolioAdaptiveIntelligenceService = Depends(get_adaptive_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    """
    獲取即時投組自適應健康總評分、五維雷達摘要與體制洞察。
    """
    try:
        weights, nlv, prices = await _extract_user_holdings(dashboard_service)
        report: AdaptiveDiagnosticReport = service.diagnose_portfolio(
            current_weights=weights,
            portfolio_value=nlv,
            asset_prices=prices,
        )

        radar_data = HealthRadarSchema(
            regime_alignment=report.radar_dimensions.regime_alignment,
            diversification_efficiency=report.radar_dimensions.diversification_efficiency,
            factor_balance=report.radar_dimensions.factor_balance,
            tail_risk_resilience=report.radar_dimensions.tail_risk_resilience,
            capital_safety=report.radar_dimensions.capital_safety,
        )

        return AdaptiveHealthSummaryResponse(
            status="success",
            health_score=report.health_score,
            health_rating=report.health_rating.value,
            radar=radar_data,
            current_regime=report.regime_analysis.get("current_regime", "NEUTRAL_RANGE"),
            regime_confidence=report.regime_analysis.get("regime_confidence", 0.75),
            needs_rebalance=report.rebalance_recommendation.get("needs_rebalance", False),
            summary_insights=report.summary_insights,
        )
    except Exception as e:
        logger.exception(f"Error evaluating adaptive health: {e}")
        raise HTTPException(status_code=500, detail=f"Adaptive health diagnostic failed: {str(e)}")


@router.post("/diagnose", response_model=DiagnosePortfolioResponse)
async def diagnose_portfolio(
    request: DiagnosePortfolioRequest = Body(...),
    service: PortfolioAdaptiveIntelligenceService = Depends(get_adaptive_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    """
    全方位深度診斷：整合 M1~M6、E1、O1 演算法，回傳完整的 8 維度協同分析報告。
    """
    try:
        weights = request.current_weights
        nlv = request.portfolio_value or 100000.0
        prices = request.asset_prices

        if not weights:
            weights, nlv, live_prices = await _extract_user_holdings(dashboard_service)
            if not prices:
                prices = live_prices

        report: AdaptiveDiagnosticReport = service.diagnose_portfolio(
            current_weights=weights,
            portfolio_value=nlv,
            asset_prices=prices,
            asset_advs=request.asset_advs,
            market_observation=request.market_observation,
            current_drawdown=request.current_drawdown or 0.05,
            recent_win_rate=request.recent_win_rate or 0.55,
            recent_payoff_ratio=request.recent_payoff_ratio or 1.8,
        )

        return DiagnosePortfolioResponse(
            status="success",
            data=report.to_dict(),
        )
    except Exception as e:
        logger.exception(f"Error diagnosing portfolio: {e}")
        raise HTTPException(status_code=500, detail=f"Diagnostic error: {str(e)}")


@router.post("/rebalance-plan", response_model=RebalancePlanResponse)
async def generate_rebalance_plan(
    request: RebalancePlanRequest = Body(...),
    service: PortfolioAdaptiveIntelligenceService = Depends(get_adaptive_service),
):
    """
    端到端調倉建議與 SOR 執行排程：整合 M3 換庫與 E1 SOR TWAP/VWAP 拆單排程。
    """
    try:
        report: AdaptiveDiagnosticReport = service.diagnose_portfolio(
            current_weights=request.current_weights,
            portfolio_value=request.portfolio_value,
            asset_prices=request.asset_prices,
            asset_advs=request.asset_advs,
        )

        rebal_data = report.rebalance_recommendation

        return RebalancePlanResponse(
            status="success",
            data={
                "health_score": report.health_score,
                "health_rating": report.health_rating.value,
                "current_regime": report.regime_analysis.get("current_regime"),
                "rebalance_recommendation": rebal_data,
            },
        )
    except Exception as e:
        logger.exception(f"Error generating rebalance plan: {e}")
        raise HTTPException(status_code=500, detail=f"Rebalance plan error: {str(e)}")
