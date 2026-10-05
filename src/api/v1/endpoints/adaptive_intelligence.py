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
    ProvenanceSchema,
    DiagnosePortfolioRequest,
    DiagnosePortfolioResponse,
    RebalancePlanRequest,
    RebalancePlanResponse,
)
from src.services.portfolio_adaptive_intelligence_service import (
    PortfolioAdaptiveIntelligenceService,
    AdaptiveDiagnosticReport,
)
from src.services.macro_surprise_service import MacroSurpriseService
from src.api.v1.schemas.macro_surprise_schemas import (
    MacroSurpriseAssessmentResponse,
    MacroSurpriseEvaluateRequest,
)
from src.services.regime_hmm_service import RegimeObservation
from src.services.dashboard_service import DashboardService
from src.utils.logger import setup_logger
from src.utils.api_cache import cached_api_response

logger = setup_logger("API_AdaptiveIntelligence")
router = APIRouter()


def get_macro_surprise_service(user_id: str = Depends(get_current_user_id)) -> MacroSurpriseService:
    """Dependency provider for MacroSurpriseService"""
    return MacroSurpriseService(user_id=user_id)


def get_adaptive_service(
    user_id: str = Depends(get_current_user_id),
    macro_service: MacroSurpriseService = Depends(get_macro_surprise_service),
) -> PortfolioAdaptiveIntelligenceService:
    """Dependency provider for PortfolioAdaptiveIntelligenceService"""
    return PortfolioAdaptiveIntelligenceService(user_id=user_id, macro_surprise_service=macro_service)


def get_dashboard_service(user_id: str = Depends(get_current_user_id)) -> DashboardService:
    """Dependency provider for DashboardService"""
    return DashboardService(user_id=user_id)


async def _extract_user_holdings(
    dashboard_service: DashboardService,
) -> Tuple[Dict[str, float], float, Dict[str, float], str]:
    """Helper to extract live portfolio weights, total value, prices, and provenance."""
    holdings_provenance = "template"
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

        if len(weights) > 1 and any(k != "CASH" for k in weights):
            holdings_provenance = "live"
        else:
            weights = {
                "SPY": 0.35,
                "QQQ": 0.25,
                "TLT": 0.15,
                "GLD": 0.05,
                "CASH": 0.20,
            }
            prices = {"SPY": 510.0, "QQQ": 440.0, "TLT": 92.0, "GLD": 215.0}
            holdings_provenance = "template"

        return weights, nlv, prices, holdings_provenance
    except Exception as e:
        logger.warning(f"Failed to fetch live portfolio context: {e}, falling back to defaults")
        return (
            {"SPY": 0.35, "QQQ": 0.25, "TLT": 0.15, "GLD": 0.05, "CASH": 0.20},
            100000.0,
            {"SPY": 510.0, "QQQ": 440.0, "TLT": 92.0, "GLD": 215.0},
            "template",
        )


async def _extract_market_observation(
    dashboard_service: DashboardService,
) -> Tuple[Optional[RegimeObservation], str]:
    """Helper to fetch live macro observations for regime classification."""
    try:
        market_service = getattr(dashboard_service, "market_service", None)
        spy_price = 0.0
        spy_sma200 = 0.0
        vix = 18.5

        if market_service:
            if hasattr(market_service, "get_technical_indicators"):
                try:
                    ind = market_service.get_technical_indicators("SPY")
                    sma_dict = ind.get("sma", {}) if ind else {}
                    spy_sma200 = float(sma_dict.get("sma_200") or 0.0)
                except Exception as e:
                    logger.debug(f"Failed to fetch SPY technicals: {e}")

            if hasattr(market_service, "get_macro_data"):
                try:
                    macro = market_service.get_macro_data()
                    indicators_macro = macro.get("market_indicators", {}) if macro else {}
                    spy_price = float(indicators_macro.get("SPY") or 0.0)
                    vix_val = indicators_macro.get("^VIX") or indicators_macro.get("VIX")
                    if vix_val and float(vix_val) > 0:
                        vix = float(vix_val)
                except Exception as e:
                    logger.debug(f"Failed to fetch macro data: {e}")

            if spy_price <= 0 and hasattr(market_service, "get_current_prices"):
                try:
                    prices = await market_service.get_current_prices(["SPY"])
                    spy_price = float(prices.get("SPY") or 0.0)
                except Exception as e:
                    logger.debug(f"Failed to fetch current SPY price: {e}")

        if spy_price > 0:
            if spy_sma200 <= 0:
                spy_sma200 = spy_price
            obs = RegimeObservation(
                spy_price=spy_price,
                spy_sma200=spy_sma200,
                vix=vix,
                return_5d=0.015,
                realized_vol_20d=0.16,
            )
            return obs, "live"
    except Exception as e:
        logger.warning(f"Failed to fetch live macro observation: {e}")

    return None, "default"


async def _extract_returns_history(
    dashboard_service: DashboardService,
    weights: Dict[str, float],
) -> Tuple[Optional[pd.DataFrame], str]:
    """Helper to extract portfolio or weighted asset return history."""
    try:
        from src.services.analytics_service import AnalyticsService
        analytics = AnalyticsService(user_id=dashboard_service.user_id, db_path=dashboard_service.db_path)
        history_df = analytics.get_performance_history()
        if history_df is not None and len(history_df) >= 20 and "nlv" in history_df.columns:
            daily_returns = history_df["nlv"].pct_change().dropna().tolist()
            if len(daily_returns) >= 20:
                return pd.DataFrame({"PORTFOLIO": daily_returns}), "live_portfolio"

        tickers = [k for k in weights.keys() if k.upper() != "CASH"]
        market_service = getattr(dashboard_service, "market_service", None)
        if tickers and market_service and hasattr(market_service, "get_ohlcv_batch"):
            try:
                ohlcv_map = market_service.get_ohlcv_batch(tickers, days=60)
                series_dict = {}
                for t in tickers:
                    t_data = ohlcv_map.get(t, {})
                    closes = t_data.get("close", [])
                    if closes and len(closes) >= 20:
                        ret = pd.Series(closes).pct_change().dropna().tolist()
                        series_dict[t] = ret

                if series_dict and all(t in series_dict for t in tickers):
                    min_len = min(len(s) for s in series_dict.values())
                    if min_len >= 20:
                        weighted_rets = []
                        total_equity_w = sum(weights[t] for t in tickers)
                        for i in range(min_len):
                            day_r = sum((weights[t] / max(0.01, total_equity_w)) * series_dict[t][i] for t in tickers)
                            weighted_rets.append(day_r)
                        return pd.DataFrame({"PORTFOLIO": weighted_rets}), "weighted_assets"
            except Exception as e:
                logger.debug(f"Failed to compute weighted asset returns: {e}")
    except Exception as e:
        logger.warning(f"Failed to extract live return history: {e}")

    return None, "synthetic"


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
        weights, nlv, prices, holdings_provenance = await _extract_user_holdings(dashboard_service)
        market_obs, market_provenance = await _extract_market_observation(dashboard_service)
        returns_df, tail_provenance = await _extract_returns_history(dashboard_service, weights)

        provenance_dict = {
            "holdings": holdings_provenance,
            "market_observation": market_provenance,
            "tail_risk": tail_provenance,
        }

        report: AdaptiveDiagnosticReport = service.diagnose_portfolio(
            current_weights=weights,
            portfolio_value=nlv,
            asset_prices=prices,
            market_observation=market_obs,
            returns_history=returns_df,
            provenance=provenance_dict,
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
            provenance=ProvenanceSchema(**report.provenance),
        )
    except Exception as e:
        logger.exception(f"Error evaluating adaptive health: {e}")
        raise HTTPException(status_code=500, detail=f"Adaptive health diagnostic failed: {str(e)}")


@router.get("/diagnose", response_model=DiagnosePortfolioResponse)
async def get_diagnose_portfolio(
    service: PortfolioAdaptiveIntelligenceService = Depends(get_adaptive_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    """
    全方位深度診斷 (GET 查詢)：從即時帳戶持倉、宏觀指標與歷史報酬率直接產生 8 維度協同分析報告。
    """
    return await diagnose_portfolio(
        request=DiagnosePortfolioRequest(),
        service=service,
        dashboard_service=dashboard_service,
    )


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
            weights, nlv, live_prices, holdings_provenance = await _extract_user_holdings(dashboard_service)
            if not prices:
                prices = live_prices
        else:
            holdings_provenance = "live"

        market_obs = request.market_observation
        if market_obs is None:
            market_obs, market_provenance = await _extract_market_observation(dashboard_service)
        else:
            market_provenance = "custom"

        returns_df, tail_provenance = await _extract_returns_history(dashboard_service, weights)

        provenance_dict = {
            "holdings": holdings_provenance,
            "market_observation": market_provenance,
            "tail_risk": tail_provenance,
        }

        report: AdaptiveDiagnosticReport = service.diagnose_portfolio(
            current_weights=weights,
            portfolio_value=nlv,
            asset_prices=prices,
            asset_advs=request.asset_advs,
            market_observation=market_obs,
            returns_history=returns_df,
            current_drawdown=request.current_drawdown or 0.05,
            recent_win_rate=request.recent_win_rate or 0.55,
            recent_payoff_ratio=request.recent_payoff_ratio or 1.8,
            provenance=provenance_dict,
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


@router.post("/macro/surprise", response_model=MacroSurpriseAssessmentResponse)
async def evaluate_macro_surprise(
    request: Optional[MacroSurpriseEvaluateRequest] = Body(None),
    service: MacroSurpriseService = Depends(get_macro_surprise_service),
):
    """
    評估宏觀經濟數據驚奇指數 (MSI) 與流動性 Beta 阻尼乘數 (M8)。
    """
    try:
        custom_indicators = request.custom_indicators if request else None
        assessment = service.evaluate_surprises(custom_indicators=custom_indicators)
        return MacroSurpriseAssessmentResponse(**assessment.to_dict())
    except Exception as e:
        logger.exception(f"Error evaluating macro surprise index: {e}")
        raise HTTPException(status_code=500, detail=f"Macro surprise evaluation error: {str(e)}")

