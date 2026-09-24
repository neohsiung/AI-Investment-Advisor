"""
Confidence Rebalance Service — Phase 3
Bridges ticker_universe target allocations into portfolio rebalance execution.

Flow:
  1. Run optimize_allocations() → computes target weights from confidence scores
  2. Read current portfolio weights from PortfolioAggregatorService
  3. Calculate deltas: target_weight - current_weight
  4. Generate trade plan: sell overweights → free cash → buy underweights
  5. Execute via AutomatedTradingService.evaluate_and_execute_trade()
"""

from typing import Dict, List, Any, Optional
import asyncio
import math
from decimal import Decimal
from src.repositories.ticker_universe_repository import TickerUniverseRepository
from src.services.ticker_universe_service import TickerUniverseService
from src.utils.logger import setup_logger
from src.config.owner import resolve_user_id

logger = setup_logger("ConfidenceRebalanceService")


class ConfidenceRebalanceService:
    """Bridges ticker_universe targets into portfolio rebalance execution."""

    MIN_TRADE_PCT = 0.5   # Skip trades smaller than 0.5% of portfolio (in percentage points)
    MAX_SINGLE_WEIGHT = 25.0  # Cap any single position at 25%
    CASH_BUFFER = 5.0     # Keep 5% cash reserve

    def __init__(self, user_id: str):
        self.user_id = resolve_user_id(user_id)
        self.repo = TickerUniverseRepository()
        self.ticker_service = TickerUniverseService(user_id=user_id)

    async def get_rebalance_plan(self) -> Dict[str, Any]:
        """
        Full pipeline: optimize targets → compare with current → generate trade plan.
        Returns a complete rebalance plan with all details.
        """
        # Step 1: Optimize target allocations from confidence scores
        opt_result = self.ticker_service.optimize_allocations()
        if not opt_result.get("success"):
            return {"success": False, "message": opt_result.get("message", "Optimization failed"), "trades": []}

        targets = opt_result.get("targets", [])
        target_map = {t["ticker"]: t["target_weight"] for t in targets}

        # Step 2: Get current portfolio weights
        current = await self._get_current_weights()
        if current is None:
            return {"success": False, "message": "Could not fetch current portfolio", "trades": []}

        total_portfolio_value = current.get("total_value", 1.0)
        current_weights = current.get("weights", {})

        # Step 3: Calculate deltas and generate trade plan
        trades = []
        cash_weight = current.get("cash_weight", 0.0)

        # Read broker minimum trade threshold (eToro minimum order size)
        min_trade_usd = 10.0
        try:
            from src.services.settings_service import SettingsService
            min_trade_usd = float(SettingsService(user_id=self.user_id).get_setting("min_trade_amount"))
        except Exception:
            min_trade_usd = 10.0

        for t in targets:
            ticker = t["ticker"]
            target_w = t["target_weight"]  # decimal (0.086 = 8.6%)
            # Convert current_weight from percentage (1.43=1.43%) to decimal (0.0143) for comparison
            current_w = current_weights.get(ticker, 0.0) / 100.0
            delta = target_w - current_w  # decimal
            delta_amount = delta * total_portfolio_value

            # Skip insignificant trades (both percentage threshold and broker minimum dollar trade amount)
            if abs(delta) * 100 < self.MIN_TRADE_PCT or abs(delta_amount) < min_trade_usd:
                continue

            trades.append({
                "ticker": ticker,
                "target_weight": round(target_w * 100, 2),       # percentage
                "current_weight": round(current_w * 100, 2),     # percentage
                "delta_weight": round(delta * 100, 2),            # percentage points
                "delta_amount": round(delta_amount, 2),  # USD
                "action": "BUY" if delta > 0 else "SELL",
                "confidence": t.get("confidence_score", 0.5),
            })

        # Also inspect positions currently held that are NOT in target allocations (e.g. evicted tickers)
        for held_ticker, held_pct in current_weights.items():
            if held_ticker == "CASH" or held_ticker in target_map:
                continue
            held_w = held_pct / 100.0
            delta = 0.0 - held_w
            delta_amount = delta * total_portfolio_value
            if held_w * 100 < self.MIN_TRADE_PCT or abs(delta_amount) < min_trade_usd:
                continue
            trades.append({
                "ticker": held_ticker,
                "target_weight": 0.0,
                "current_weight": round(held_pct, 2),
                "delta_weight": round(delta * 100, 2),
                "delta_amount": round(delta_amount, 2),
                "action": "SELL",
                "confidence": 0.0,
            })

        # Sort: sells first (most overweighted first), then buys (most underweighted first)
        sells = sorted([t for t in trades if t["action"] == "SELL"], key=lambda x: x["delta_weight"])
        buys = sorted([t for t in trades if t["action"] == "BUY"], key=lambda x: x["delta_weight"], reverse=True)

        # Estimate freed cash from sells
        total_sell_amount = sum(abs(t["delta_amount"]) for t in sells)
        total_buy_amount = sum(t["delta_amount"] for t in buys)

        # Check if cash is sufficient for buys (sells first, then available cash)
        available_cash = total_sell_amount + (cash_weight / 100.0 * total_portfolio_value) * 0.8  # 80% of cash usable
        cash_shortfall = total_buy_amount - available_cash

        return {
            "success": True,
            "targets": targets,
            "current_weights": current_weights,
            "cash_weight": round(cash_weight, 2),
            "total_value": round(total_portfolio_value, 2),
            "trades": {
                "all": trades,
                "sells": sells,
                "buys": buys,
            },
            "summary": {
                "total_trades": len(trades),
                "sells": len(sells),
                "buys": len(buys),
                "total_sell_amount": round(total_sell_amount, 2),
                "total_buy_amount": round(total_buy_amount, 2),
                "available_cash": round(available_cash, 2),
                "cash_shortfall": round(max(cash_shortfall, 0), 2),
                "total_value": round(total_portfolio_value, 2),
            },
        }

    async def execute_rebalance(self) -> Dict[str, Any]:
        """
        Execute the rebalance plan:
          1. Generate plan
          2. Sell all overweighted positions first
          3. Wait for sell fills (conceptual — in real system use broker status)
          4. Buy all underweighted positions with freed cash
        """
        plan = await self.get_rebalance_plan()
        if not plan.get("success"):
            return plan

        sells = plan["trades"]["sells"]
        buys = plan["trades"]["buys"]
        total_value = plan["summary"]["total_value"]

        executed_trades = []
        errors = []

        # Step 1: Execute all sells first
        logger.info(f"Rebalance: Executing {len(sells)} sells first")
        max_liquidated_score = 0.0
        for trade in sells:
            try:
                conf = float(trade.get("confidence") or 0.0)
                if 0.0 <= conf <= 1.0:
                    conf *= 10.0
                max_liquidated_score = max(max_liquidated_score, conf)

                result = await self._execute_trade(
                    ticker=trade["ticker"],
                    action="SELL",
                    delta_weight=trade["delta_weight"] / 100.0,
                    portfolio_value=total_value,
                    confidence_score=conf,
                    rationale=f"Confidence-driven rebalance: SELL {trade['ticker']} (delta={trade['delta_weight']/100.0:+.2%})",
                )
                executed_trades.append({**trade, "status": result.get("status", "executed")})
                if result.get("status") != "executed":
                    errors.append(f"{trade['ticker']} sell: {result.get('reason', 'unknown')}")
            except Exception as e:
                logger.error(f"{trade['ticker']} sell error: {e}")
                errors.append(f"{trade['ticker']} sell error: Internal error")
                executed_trades.append({**trade, "status": "error", "error": "Internal error"})

        # Step 2: Execute all buys (after sells freed cash)
        logger.info(f"Rebalance: Executing {len(buys)} buys (after sells)")
        for trade in buys:
            try:
                conf = float(trade.get("confidence") or 0.0)
                if 0.0 <= conf <= 1.0:
                    conf *= 10.0

                # Capital rotation opportunity cost check:
                # If capital was liquidated from active holdings (max_liquidated_score > 0),
                # ensure the buy candidate offers sufficient edge (delta >= 2.0 or score >= 8.0)
                if sells and max_liquidated_score > 0.0:
                    if (conf - max_liquidated_score < 2.0) and conf < 8.0:
                        logger.warning(
                            f"Skipping rotation buy for {trade['ticker']}: Score {conf:.1f} "
                            f"fails opportunity cost edge vs liquidated asset ({max_liquidated_score:.1f})."
                        )
                        continue

                result = await self._execute_trade(
                    ticker=trade["ticker"],
                    action="BUY",
                    delta_weight=trade["delta_weight"] / 100.0,
                    portfolio_value=total_value,
                    confidence_score=conf,
                    rationale=f"Confidence-driven rebalance: BUY {trade['ticker']} (delta={trade['delta_weight']/100.0:+.2%})",
                )
                executed_trades.append({**trade, "status": result.get("status", "executed")})
                if result.get("status") != "executed":
                    errors.append(f"{trade['ticker']} buy: {result.get('reason', 'unknown')}")
            except Exception as e:
                logger.error(f"{trade['ticker']} buy error: {e}")
                errors.append(f"{trade['ticker']} buy error: Internal error")
                executed_trades.append({**trade, "status": "error", "error": "Internal error"})

        # Log to audit
        self.repo.add_log(
            self.user_id, "ALL", "rebalance_executed",
            "ConfidenceRebalanceService",
            f"Executed {len(executed_trades)} trades ({len(sells)} sells, {len(buys)} buys)",
            "", "",
        )

        return {
            "success": len(errors) == 0,
            "executed_trades": executed_trades,
            "errors": errors,
            "summary": plan["summary"],
        }

    async def _get_current_weights(self) -> Optional[Dict[str, Any]]:
        """Get current portfolio weights from PortfolioAggregator."""
        try:
            from src.services.portfolio_aggregator_service import PortfolioAggregatorService
            from src.services.capital_policy import tradable_capital
            aggregator = PortfolioAggregatorService(user_id=self.user_id)
            portfolio = await aggregator.get_aggregated_portfolio()

            positions = portfolio.get("positions", [])
            total_equity = portfolio.get("total_equity", 0.0)
            total_cash = portfolio.get("total_cash", 0.0)

            if total_equity <= 0:
                logger.warning("ConfidenceRebalance: Total equity is zero")
                return None

            # Align with capital policy: respect tradable_capital mandate ($500 cap)
            # 對齊受託資本政策：以 tradable_capital 上限為基準計算部位與權重
            raw_total = total_equity + total_cash
            effective_capital = tradable_capital(self.user_id, raw_total)
            total_portfolio_value = min(raw_total, effective_capital) if effective_capital > 0 else raw_total

            base_for_weights = total_portfolio_value if total_portfolio_value > 0 else total_equity

            weights = {}
            for p in positions:
                weight = (getattr(p, "market_value", 0) / base_for_weights) * 100.0
                weights[getattr(p, "symbol", "")] = round(weight, 2)

            cash_weight = (total_cash / base_for_weights) * 100.0 if base_for_weights > 0 else 0.0

            return {
                "weights": weights,
                "cash_weight": cash_weight,
                "total_value": total_portfolio_value,
            }
        except Exception as e:
            logger.error(f"Failed to get current weights: {e}")
            return None

    async def _execute_trade(self, ticker: str, action: str,
                             delta_weight: float, portfolio_value: float,
                             confidence_score: Optional[float] = None,
                             rationale: Optional[str] = None) -> Dict[str, Any]:
        """Execute a single trade via AutomatedTradingService."""
        from src.services.automated_trading_service import AutomatedTradingService
        from src.services.settings_service import SettingsService
        from src.services.notification_service import NotificationService

        settings = SettingsService(user_id=self.user_id)
        notification = NotificationService.create_with_settings(settings_service=settings, user_id=self.user_id)
        trading = AutomatedTradingService(
            settings_repo=settings.settings_repo, notification_service=notification
        )

        score_to_use = 8.0 if confidence_score is None else confidence_score
        rationale_to_use = rationale or f"Confidence-driven rebalance: {action} {ticker} (delta={delta_weight:+.2%})"

        return await trading.evaluate_and_execute_trade(
            user_id=self.user_id,
            ticker=ticker,
            action=action,
            delta_weight=delta_weight,
            portfolio_value=portfolio_value,
            confidence_score=score_to_use,
            rationale=rationale_to_use,
        )