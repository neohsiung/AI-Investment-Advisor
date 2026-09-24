"""
Skill Implementation: cash_deployment
技能實作：現金部署建議

Extracted from: cash_deployment CLI tool
Reusable in: Portfolio Analysis, Deployment Strategy
"""

import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)


async def cash_deployment(user_id: str) -> str:
    """
    Analyze idle cash in portfolio and provide deployment suggestions.
    分析投資組合中的閒置現金並提供部署建議。

    Returns a JSON-formatted deployment analysis and candidates.
    """
    try:
        from src.services.broker_factory import BrokerFactory
        from src.repositories.settings_repository import AlchemySettingsRepository
        from src.agents.skills.ticker_discovery.impl import ticker_discovery

        # 1. Initialize resources
        settings_repo = AlchemySettingsRepository()
        broker = BrokerFactory.get_broker(user_id)

        if not broker:
            logger.error(f"No broker found for user {user_id}")
            return json.dumps({
                "error": f"No broker found for user {user_id}",
                "status": "error"
            })

        # 2. Retrieve account data
        account = await broker.get_account()
        if not account or account.total_equity <= 0:
            logger.error(f"Failed to retrieve account data for user {user_id}")
            return json.dumps({
                "error": "Failed to retrieve account data or equity is zero",
                "status": "error"
            })

        # Get target_cash_ratio from settings (default 10%)
        target_val = settings_repo.get(user_id, "target_cash_ratio", 0.10)
        try:
            target_cash_ratio = float(target_val)
        except (ValueError, TypeError):
            target_cash_ratio = 0.10

        available_cash = account.available_cash
        total_equity = account.total_equity

        actual_ratio = available_cash / total_equity
        target_cash_amount = total_equity * target_cash_ratio
        excess_cash = available_cash - target_cash_amount

        # 3. Determine status
        if excess_cash <= 1.0:  # Ignore dust
            return json.dumps({
                "status": "balanced",
                "cash_ratio": round(actual_ratio, 4),
                "target_ratio": round(target_cash_ratio, 4),
                "excess_cash": 0.0,
                "currency": account.currency,
                "message": f"Cash ratio is healthy ({actual_ratio*100:.1f}%)"
            }, ensure_ascii=False)

        # 4. Get deployment candidates
        candidates = await _get_deployment_candidates(user_id, excess_cash)

        return json.dumps({
            "status": "overweight",
            "cash_ratio": round(actual_ratio, 4),
            "target_ratio": round(target_cash_ratio, 4),
            "excess_cash": round(excess_cash, 2),
            "currency": account.currency,
            "candidates": candidates,
            "message": f"Excess cash detected: ${excess_cash:,.2f}. Ready for deployment."
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"cash_deployment skill failed for user {user_id}: {e}", exc_info=True)
        return json.dumps({"error": str(e), "status": "error"})


async def _get_deployment_candidates(user_id: str, amount: float) -> list:
    """
    獲取建議部署的標的清單 (Get recommended deployment candidates).
    v10.1: Removed hardcoded benchmarks in favor of dynamic discovery.
    """
    from src.agents.skills.ticker_discovery.impl import ticker_discovery
    
    results = []
    
    # Try discovery for different strategies to diversify
    strategies = ["growth", "value", "quality"]
    discovery_tasks = []
    
    # We'll just use growth for now as it's the most common "buy" signal source
    # but we could expand this to a loop of tasks if needed.
    
    try:
        from src.services.quality_gate_service import QualityGateService
        qg = QualityGateService(user_id=user_id)
    except Exception as qge:
        logger.warning(f"Could not initialize QualityGateService: {qge}")
        qg = None

    try:
        discovery_res_json = await ticker_discovery(user_id, strategy="growth")
        discovery_data = json.loads(discovery_res_json)

        if discovery_data.get("status") == "success":
            discovered = discovery_data.get("tickers", [])
            if discovered:
                vetted_candidates = []
                for item in discovered:
                    sym = item.get("ticker", "").upper().strip()
                    if not sym or sym == "CASH":
                        continue

                    if qg:
                        try:
                            assessment = await qg.evaluate_ticker(sym)
                            if assessment.passed and assessment.overall_score >= 6.5:
                                vetted_candidates.append({
                                    "ticker": sym,
                                    "reason": f"Quality Gate Passed ({assessment.overall_score:.1f}/10): {item.get('reason', '')}",
                                    "score": assessment.overall_score,
                                })
                            else:
                                logger.info(
                                    f"Cash deployment candidate {sym} rejected by Quality Gate: "
                                    f"score={assessment.overall_score:.1f}, reasons={assessment.reasons[:1]}"
                                )
                        except Exception as eval_err:
                            logger.warning(f"Error evaluating candidate {sym} with Quality Gate: {eval_err}")
                            vetted_candidates.append({
                                "ticker": sym,
                                "reason": f"AI Dynamic Discovery: {item.get('reason', '')}",
                                "score": 7.0,
                            })
                    else:
                        vetted_candidates.append({
                            "ticker": sym,
                            "reason": f"AI Dynamic Discovery: {item.get('reason', '')}",
                            "score": 7.0,
                        })

                if vetted_candidates:
                    vetted_candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
                    target_candidates = vetted_candidates[:5]
                    count = len(target_candidates)
                    amount_per_ticker = amount / count

                    for item in target_candidates:
                        results.append({
                            "ticker": item["ticker"],
                            "allocated_amount": round(amount_per_ticker, 2),
                            "reason": item["reason"],
                            "source": "ticker_discovery",
                        })
            else:
                logger.warning(f"No tickers discovered for user {user_id}")
        else:
            logger.error(f"Ticker discovery failed for user {user_id}: {discovery_data.get('error')}")

    except Exception as e:
        logger.error(f"Error in dynamic deployment discovery: {e}")

    # Fallback 1: Source from user's active ticker universe
    if not results:
        try:
            from src.repositories.ticker_universe_repository import TickerUniverseRepository
            univ_repo = TickerUniverseRepository()
            active_univ = univ_repo.get_all(user_id, status="active")
            if active_univ:
                target_candidates = active_univ[:5]
                count = len(target_candidates)
                amount_per = amount / count
                for item in target_candidates:
                    sym = item.get("ticker", "").upper().strip()
                    if sym and sym != "CASH":
                        results.append({
                            "ticker": sym,
                            "allocated_amount": round(amount_per, 2),
                            "reason": f"Active Universe Allocation: deploy to active universe holding {sym}",
                            "source": "universe_active",
                        })
                logger.info(f"Cash deployment sourced {len(results)} candidates from active universe.")
        except Exception as ue:
            logger.warning(f"Active universe lookup failed: {ue}")

    # Fallback 2: use existing portfolio positions when discovery and universe return nothing
    if not results:
        logger.info("Discovery and universe returned no candidates, falling back to existing portfolio positions.")
        try:
            from src.repositories.transaction_repository import AlchemyTransactionRepository
            from src.data.database import get_db_engine
            repo = AlchemyTransactionRepository(get_db_engine())
            holdings = repo.get_holdings(user_id)
            if holdings:
                total_candidates = min(len(holdings), 5)
                amount_per = amount / total_candidates
                for h in holdings[:total_candidates]:
                    ticker = h.get("ticker", "").upper()
                    if ticker and ticker != "CASH":
                        results.append({
                            "ticker": ticker,
                            "allocated_amount": round(amount_per, 2),
                            "reason": f"Portfolio rebalancing: add to existing position {ticker}",
                            "source": "portfolio_fallback"
                        })
                logger.info(f"Fallback: allocated ${amount_per:.2f} each to {total_candidates} existing positions.")
            else:
                logger.info("No existing holdings to deploy to. Portfolio remains in cash.")
        except Exception as e:
            logger.error(f"Fallback deployment failed: {e}")

    return results

