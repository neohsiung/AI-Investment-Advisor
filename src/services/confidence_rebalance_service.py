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
    CASH_BUFFER = 5.0     # Baseline fallback cash reserve (overridden dynamically by MarketRegimeService)

    def __init__(
        self,
        user_id: str,
        regime_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.repo = TickerUniverseRepository()
        self.ticker_service = TickerUniverseService(user_id=user_id)
        from src.services.long_term_winner_service import LongTermWinnerService, ProtectionStatus
        self.winner_service = LongTermWinnerService(user_id=user_id)
        self.ProtectionStatus = ProtectionStatus
        from src.services.market_regime_service import MarketRegimeService, MarketRegime, RegimePolicy
        self.MarketRegime = MarketRegime
        self.RegimePolicy = RegimePolicy
        self.regime_service = regime_service or MarketRegimeService(market_data_service=market_data_service)
        self.market_data_service = market_data_service
        from src.services.opportunity_cost_service import OpportunityCostService
        from src.services.alpha_decay_service import AlphaDecayService
        self.opportunity_cost_service = OpportunityCostService(user_id=user_id)
        self.alpha_decay_service = AlphaDecayService(user_id=user_id, market_data_service=market_data_service)

    async def _get_regime_policy(self) -> Any:
        """Query current market regime to determine adaptive cash buffer and buy permission."""
        try:
            if hasattr(self.regime_service, "get_current_regime"):
                return await self.regime_service.get_current_regime()
            elif hasattr(self.regime_service, "classify_regime"):
                return self.regime_service.classify_regime(450.0, 440.0, 15.0)
        except Exception as e:
            logger.warning(f"Failed to query market regime: {e}; defaulting to NEUTRAL_RANGE")
        return self.regime_service._build_policy(
            self.MarketRegime.NEUTRAL_RANGE, "Defaulting to neutral risk cushion"
        )

    async def get_rebalance_plan(self) -> Dict[str, Any]:
        """
        Full pipeline: optimize targets → compare with current → generate trade plan.
        Returns a complete rebalance plan with all details.
        """
        policy = await self._get_regime_policy()

        # Step 1: Get current portfolio weights and holdings
        current = await self._get_current_weights()
        if current is None:
            return {"success": False, "message": "Could not fetch current portfolio", "trades": []}

        total_portfolio_value = current.get("total_value", 1.0)
        current_weights = current.get("weights", {})
        cash_weight = current.get("cash_weight", 0.0)
        positions_map = current.get("positions_map", {})

        current_holdings = {}
        for held_ticker, p_info in positions_map.items():
            if held_ticker != "CASH":
                open_date = p_info.get("open_date")
                holding_days = self.alpha_decay_service.calculate_holding_days(open_date)
                current_holdings[held_ticker] = {
                    "holding_days": holding_days,
                    "open_date": open_date,
                    "current_price": p_info.get("current_price", 0.0),
                    "open_price": p_info.get("open_price", 0.0),
                    "unrealized_pnl_pct": p_info.get("unrealized_pnl_pct", 0.0),
                }

        # Step 2: Optimize target allocations from confidence scores (with Alpha Decay)
        try:
            opt_result = self.ticker_service.optimize_allocations(current_holdings=current_holdings)
        except TypeError:
            opt_result = self.ticker_service.optimize_allocations()

        if not opt_result.get("success"):
            return {
                "success": False,
                "message": opt_result.get("message", "Optimization failed"),
                "trades": [],
                "regime": getattr(policy, "regime", self.MarketRegime.NEUTRAL_RANGE).value if hasattr(getattr(policy, "regime", None), "value") else str(getattr(policy, "regime", "NEUTRAL_RANGE")),
            }

        targets = opt_result.get("targets", [])
        target_map = {t["ticker"]: t["target_weight"] for t in targets}

        # Step 3: Identify sells (pruned dead capital & non-protected overweights)
        sells = []
        holding_runners = []

        # Read broker minimum trade threshold (eToro minimum order size)
        min_trade_usd = 10.0
        try:
            from src.services.settings_service import SettingsService
            min_trade_usd = float(SettingsService(user_id=self.user_id).get_setting("min_trade_amount"))
        except Exception:
            min_trade_usd = 10.0

        protect_winners = True
        try:
            from src.services.settings_service import SettingsService
            protect_winners = str(
                SettingsService(user_id=self.user_id).get_setting("protect_winning_compounders", "true")
            ).lower() in ("true", "1")
        except Exception:
            protect_winners = True

        # 3a. Inspect positions held that are NOT in target allocations (evicted tickers / dead capital)
        # 淘汰標的與死資本：全額平倉以最大化釋放流動性
        pruned_lots = []
        for held_ticker, held_pct in current_weights.items():
            if held_ticker == "CASH" or held_ticker in target_map:
                continue
            held_w = held_pct / 100.0
            delta = 0.0 - held_w
            # Full liquidation sells 100% of the holding
            delta_amount = delta * total_portfolio_value
            if abs(delta_amount) < 1.0 and held_w * 100 < 0.05:
                continue
            trade_item = {
                "ticker": held_ticker,
                "target_weight": 0.0,
                "current_weight": round(held_pct, 2),
                "delta_weight": round(delta * 100, 2),
                "delta_amount": round(delta_amount, 2),
                "action": "SELL",
                "confidence": 8.5,
                "is_pruning": True,
            }
            sells.append(trade_item)
            pruned_lots.append(trade_item)

        candidate_scores = {
            t["ticker"]: (
                float(t.get("confidence_score", 0.5)) * 10.0
                if float(t.get("confidence_score", 0.5)) <= 1.0
                else float(t.get("confidence_score", 0.5))
            )
            for t in targets
        }

        # 3b. Deep Research Winner Qualification & Short-Term Opportunity Cost Evaluation
        # 贏家保護深度研究：確認標的中長期仍是結構性贏家，且無短期死錢與機會成本喪失
        for t in targets:
            ticker = t["ticker"]
            target_w = t["target_weight"]  # decimal
            current_w = current_weights.get(ticker, 0.0) / 100.0
            delta = target_w - current_w  # decimal
            delta_amount = delta * total_portfolio_value
            market_val = current_w * total_portfolio_value

            if delta < 0:
                if protect_winners:
                    try:
                        assessment = await self.winner_service.evaluate_winner(
                            ticker=ticker,
                            current_weight=current_w * 100.0,
                            target_weight=target_w * 100.0,
                            market_value=market_val,
                            total_portfolio_value=total_portfolio_value,
                            candidate_scores=candidate_scores,
                        )
                    except Exception as eval_err:
                        logger.warning(f"Failed to evaluate winner status for {ticker}: {eval_err}")
                        from src.services.long_term_winner_service import ProtectionStatus, WinnerAssessment
                        assessment = WinnerAssessment(
                            ticker=ticker,
                            is_long_term_winner=True,
                            has_short_term_opportunity_cost=False,
                            status=ProtectionStatus.FULL_PROTECT_COMPOUNDING,
                            long_term_score=7.0,
                            short_term_momentum_score=7.0,
                            long_term_reasons=["預設贏家保護防線放行"],
                            action_summary="狀態良好核心持倉，持續複利",
                        )

                    if assessment.status.value == "FULL_PROTECT_COMPOUNDING":
                        # Full protection: certified medium/long-term winner + healthy short-term momentum
                        reason_msg = (
                            f"中長期結構贏家認證：{'; '.join(assessment.long_term_reasons[:2])}。"
                            f"短線動能健康無機會成本喪失，依狀態驅動原則不砍贏家，全額保護複利。"
                        )
                        holding_runners.append({
                            "ticker": ticker,
                            "target_weight": round(target_w * 100, 2),
                            "current_weight": round(current_w * 100, 2),
                            "delta_weight": round(delta * 100, 2),
                            "delta_amount": round(delta_amount, 2),
                            "action": "HOLD_COMPOUNDING",
                            "protection_status": assessment.status.value,
                            "confidence": t.get("confidence_score", 0.5),
                            "reason": reason_msg,
                            "assessment": assessment,
                        })
                    elif assessment.status.value == "TRIM_EXCESS_FOR_OPPORTUNITY":
                        # Long-term winner BUT short-term opportunity cost gap ->
                        # Protect core base, trim excess to eliminate short-term dead money
                        excess_amount = abs(delta_amount)
                        reason_msg = (
                            f"中長期贏家但短線機會成本警示：{'; '.join(assessment.short_term_reasons[:2])}。"
                            f"長線核心底倉 ({target_w*100:.1f}%) 堅定保留，戰術調節超額部分 (${excess_amount:.2f}) 轉投高動能機會，避免短線死錢拖累。"
                        )
                        sells.append({
                            "ticker": ticker,
                            "target_weight": round(target_w * 100, 2),
                            "current_weight": round(current_w * 100, 2),
                            "delta_weight": round(delta * 100, 2),
                            "delta_amount": round(delta_amount, 2),
                            "action": "SELL",
                            "protection_status": assessment.status.value,
                            "confidence": t.get("confidence_score", 0.5),
                            "reason": reason_msg,
                            "is_tactical_trim": True,
                        })
                    else:
                        # NO_PROTECTION_REBALANCE: Failed long-term winner criteria -> regular rebalance
                        if abs(delta) * 100 >= self.MIN_TRADE_PCT and abs(delta_amount) >= min_trade_usd:
                            sells.append({
                                "ticker": ticker,
                                "target_weight": round(target_w * 100, 2),
                                "current_weight": round(current_w * 100, 2),
                                "delta_weight": round(delta * 100, 2),
                                "delta_amount": round(delta_amount, 2),
                                "action": "SELL",
                                "protection_status": assessment.status.value,
                                "confidence": t.get("confidence_score", 0.5),
                                "reason": f"長線結構破壞或基本面品質未達標，不具備贏家保護資格：{'; '.join(assessment.long_term_reasons[:1])}",
                            })
                else:
                    if abs(delta) * 100 >= self.MIN_TRADE_PCT and abs(delta_amount) >= min_trade_usd:
                        sells.append({
                            "ticker": ticker,
                            "target_weight": round(target_w * 100, 2),
                            "current_weight": round(current_w * 100, 2),
                            "delta_weight": round(delta * 100, 2),
                            "delta_amount": round(delta_amount, 2),
                            "action": "SELL",
                            "confidence": t.get("confidence_score", 0.5),
                        })

        # Step 4: Calculate deployable liquidity from sells and cash
        total_sell_amount = sum(abs(t["delta_amount"]) for t in sells)
        current_cash_usd = (cash_weight / 100.0) * total_portfolio_value

        # Dynamic Regime-Aware Cash Defense:
        # Enforce dynamic cash reserve (Bull: 5%, Neutral: 20%, Bear/Crisis: 50%)
        effective_cash_reserve_pct = float(getattr(policy, "cash_reserve_pct", self.CASH_BUFFER))
        target_cash_usd = total_portfolio_value * (effective_cash_reserve_pct / 100.0)
        cash_buffer_usd = min(current_cash_usd, target_cash_usd)
        gross_cash = current_cash_usd + total_sell_amount
        available_cash = total_sell_amount + max(0.0, current_cash_usd - cash_buffer_usd)

        # Step 5: Smart Cash Deployment for under-allocated targets
        allow_new_buys = bool(getattr(policy, "allow_new_buys", True))
        buys = []
        buy_candidates = []

        if not allow_new_buys:
            logger.warning(
                "Market regime %s blocks new buy allocations (allow_new_buys=False). "
                "Preserving all liquidity ($%.2f) as defensive cash cushion.",
                getattr(policy, "regime", "UNKNOWN"), gross_cash,
            )
        else:
            for t in targets:
                ticker = t["ticker"]
                target_w = t["target_weight"]
                current_w = current_weights.get(ticker, 0.0) / 100.0
                delta = target_w - current_w
                raw_need_amount = delta * total_portfolio_value
                if delta * 100 >= self.MIN_TRADE_PCT and raw_need_amount >= min_trade_usd:
                    buy_candidates.append({
                        "ticker": ticker,
                        "target_weight": target_w,
                        "current_weight": current_w,
                        "delta": delta,
                        "raw_need_amount": raw_need_amount,
                        "confidence": t.get("confidence_score", 0.5),
                    })

            total_buy_need = sum(c["raw_need_amount"] for c in buy_candidates)
            if buy_candidates and available_cash >= min_trade_usd:
                # Scale proportionally so each candidate gets funded to match available cash
                scale_factor = min(1.0, available_cash / total_buy_need) if total_buy_need > 0 else 1.0

                for c in buy_candidates:
                    allocated_amount = round(c["raw_need_amount"] * scale_factor, 2)
                    if allocated_amount >= min_trade_usd:
                        allocated_delta_w = round((allocated_amount / total_portfolio_value) * 100.0, 2)
                        buys.append({
                            "ticker": c["ticker"],
                            "target_weight": round(c["target_weight"] * 100, 2),
                            "current_weight": round(c["current_weight"] * 100, 2),
                            "delta_weight": allocated_delta_w,
                            "delta_amount": allocated_amount,
                            "action": "BUY",
                            "confidence": c["confidence"],
                        })

        # Sort: sells first (largest delta points first), buys by confidence score descending
        sells = sorted(sells, key=lambda x: x["delta_weight"])
        buys = sorted(buys, key=lambda x: (x.get("confidence", 0), x["delta_weight"]), reverse=True)

        # M3: Filter discretionary rebalance swaps via OpportunityCostService
        suppressed_swaps = []
        if sells and buys:
            filter_res = self.opportunity_cost_service.filter_rebalance_trades(
                sells=sells,
                buys=buys,
                total_portfolio_value=total_portfolio_value,
            )
            sells = filter_res["approved_sells"]
            suppressed_swaps = filter_res["suppressed_sells"]
            holding_runners.extend(suppressed_swaps)

        total_buy_amount = sum(t["delta_amount"] for t in buys)
        total_sell_amount = sum(abs(t["delta_amount"]) for t in sells)
        pruned_amount = sum(abs(t["delta_amount"]) for t in pruned_lots)
        cash_shortfall = max(0.0, total_buy_amount - (total_sell_amount + current_cash_usd))
        trades = sells + buys

        regime_val = getattr(policy, "regime", self.MarketRegime.NEUTRAL_RANGE)
        regime_str = regime_val.value if hasattr(regime_val, "value") else str(regime_val)

        return {
            "success": True,
            "targets": targets,
            "current_weights": current_weights,
            "cash_weight": round(cash_weight, 2),
            "total_value": round(total_portfolio_value, 2),
            "regime": regime_str,
            "regime_policy": {
                "regime": regime_str,
                "cash_reserve_pct": round(effective_cash_reserve_pct, 2),
                "target_cash_usd": round(target_cash_usd, 2),
                "allow_new_buys": allow_new_buys,
                "buy_confidence_threshold": getattr(policy, "buy_confidence_threshold", 7.5),
                "rationale": getattr(policy, "rationale", ""),
            },
            "trades": {
                "all": trades + holding_runners,
                "sells": sells,
                "buys": buys,
                "holding_runners": holding_runners,
                "suppressed_swaps": suppressed_swaps,
            },
            "summary": {
                "total_trades": len(trades),
                "sells": len(sells),
                "buys": len(buys),
                "holding_runners": len(holding_runners),
                "suppressed_swaps": len(suppressed_swaps),
                "total_sell_amount": round(total_sell_amount, 2),
                "total_buy_amount": round(total_buy_amount, 2),
                "target_cash_pct": round(effective_cash_reserve_pct, 2),
                "target_cash_usd": round(target_cash_usd, 2),
                "regime": regime_str,
                "allow_new_buys": allow_new_buys,
                "available_cash": round(available_cash, 2),
                "cash_shortfall": round(cash_shortfall, 2),
                "total_value": round(total_portfolio_value, 2),
                "pruning_summary": {
                    "pruned_count": len(pruned_lots),
                    "pruned_tickers": [p["ticker"] for p in pruned_lots],
                    "pruned_amount": round(pruned_amount, 2),
                },
            },
        }

    async def execute_rebalance(self, enforce_market_hours: bool = False) -> Dict[str, Any]:
        """
        Execute the rebalance plan:
          0. Market timing check: Verify regular trading session (if enforce_market_hours=True)
          1. Generate plan
          2. Sell all overweighted positions first
          3. Wait for sell fills (conceptual — in real system use broker status)
          4. Buy all underweighted positions with freed cash
        """
        if enforce_market_hours:
            from src.utils.market_clock import MarketClock
            clock = getattr(self, "market_clock", None) or MarketClock()
            if not clock.is_market_open():
                status = clock.get_market_status()
                logger.warning(
                    f"Rebalance execution blocked: US Market is closed (Current: {status.get('current_time')}). "
                    f"Next regular session opens at {status.get('next_open')}."
                )
                return {
                    "success": False,
                    "status": "market_closed",
                    "message": f"美股市場休市中（下次開市：{status.get('next_open')}）。為避免休市掛單滑點，請待週一 09:35 EST 定時任務或開盤後執行。",
                    "market_status": status,
                }

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
                is_pruning = trade.get("is_pruning", False)
                conf = float(trade.get("confidence") or 0.0)
                if conf <= 0.0:
                    conf = 8.5
                elif 0.0 < conf <= 1.0:
                    conf *= 10.0

                # 淘汰標的 (is_pruning) 釋放死資本不應抬高買進標的的機會成本比較門檻
                if not is_pruning:
                    max_liquidated_score = max(max_liquidated_score, conf)

                result = await self._execute_trade(
                    ticker=trade["ticker"],
                    action="SELL",
                    delta_weight=trade["delta_weight"] / 100.0,
                    portfolio_value=total_value,
                    confidence_score=conf,
                    rationale=f"Confidence-driven rebalance: SELL {trade['ticker']} (delta={trade['delta_weight']/100.0:+.2%})",
                    strategy_name="rebalance_diversification",
                )
                is_ok = result.get("status") in ("success", "executed") or result.get("execution_status") in ("executed", "pending")
                trade_status = "executed" if is_ok else result.get("status", "failed")
                executed_trades.append({**trade, "status": trade_status, "order_id": result.get("order_id")})
                if not is_ok:
                    errors.append(f"{trade['ticker']} sell: {result.get('reason', 'unknown')}")
                else:
                    import asyncio
                    await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"{trade['ticker']} sell error: {e}")
                errors.append(f"{trade['ticker']} sell error: Internal error")
                executed_trades.append({**trade, "status": "error", "error": "Internal error"})

        # Step 2: Execute all buys (after sells freed cash)
        if sells and buys:
            import asyncio
            logger.info("Rebalance: Waiting 3.0s for broker liquidity to settle before executing buys...")
            await asyncio.sleep(3.0)

        logger.info(f"Rebalance: Executing {len(buys)} buys (after sells)")
        for trade in buys:
            try:
                conf = float(trade.get("confidence") or 0.0)
                if 0.0 <= conf <= 1.0:
                    conf *= 10.0

                # Capital rotation opportunity cost check:
                # If capital was liquidated from active holdings (max_liquidated_score > 0),
                # ensure the buy candidate offers sufficient edge over friction
                if sells and max_liquidated_score > 0.0:
                    swap_check = self.opportunity_cost_service.evaluate_swap(
                        selling_ticker="LIQUIDATED_HOLDING",
                        buying_ticker=trade["ticker"],
                        sell_confidence=max_liquidated_score / 10.0,
                        buy_confidence=conf / 10.0,
                    )
                    if not swap_check.is_approved and conf < 8.0:
                        logger.warning(
                            f"Skipping rotation buy for {trade['ticker']}: {swap_check.reason}"
                        )
                        continue

                result = await self._execute_trade(
                    ticker=trade["ticker"],
                    action="BUY",
                    delta_weight=trade["delta_weight"] / 100.0,
                    portfolio_value=total_value,
                    confidence_score=conf,
                    rationale=f"Confidence-driven rebalance: BUY {trade['ticker']} (delta={trade['delta_weight']/100.0:+.2%})",
                    strategy_name="portfolio_rebalance",
                )
                is_ok = result.get("status") in ("success", "executed") or result.get("execution_status") in ("executed", "pending")
                trade_status = "executed" if is_ok else result.get("status", "failed")
                executed_trades.append({**trade, "status": trade_status, "order_id": result.get("order_id")})
                if not is_ok:
                    errors.append(f"{trade['ticker']} buy: {result.get('reason', 'unknown')}")
                else:
                    import asyncio
                    await asyncio.sleep(1.0)
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

    async def reclaim_capital_for_buy(
        self,
        candidate_ticker: str,
        target_amount: float,
        candidate_score: float = 8.5,
        execute: bool = False,
    ) -> Dict[str, Any]:
        """
        Active Capital Rotation: Reclaim capital by liquidating lowest-conviction or
        micro positions to fund a high-conviction buy opportunity.
        主動資本置換：清倉末位低置信度或微型持倉，釋放資金以執行高置信度買入。
        """
        current = await self._get_current_weights()
        if not current:
            return {"status": "error", "message": "Failed to fetch portfolio weights", "sells": []}

        total_value = current.get("total_value", 1.0)
        current_weights = current.get("weights", {})
        cash_weight = current.get("cash_weight", 0.0)
        available_cash = (cash_weight / 100.0) * total_value

        if available_cash >= target_amount:
            return {
                "status": "sufficient_cash",
                "available_cash": round(available_cash, 2),
                "target_amount": round(target_amount, 2),
                "reclaimed_amount": 0.0,
                "sells": [],
            }

        shortfall = target_amount - available_cash
        reclaimed = 0.0
        candidate_sells = []

        # Read targets to identify non-target holdings
        targets = self.ticker_service.get_targets()
        target_map = {t["ticker"]: t.get("target_weight", 0.0) for t in targets}

        # Gather latest confidence for all held positions
        held_scores = {}
        for ticker, weight in current_weights.items():
            if ticker == "CASH":
                continue
            research = self.ticker_service.repo.get_research(self.user_id, ticker, limit=3)
            scores = [float(r["confidence_score"]) for r in research if r.get("confidence_score")]
            score_val = max(scores) if scores else 5.0
            if score_val <= 1.0:
                score_val *= 10.0
            held_scores[ticker] = score_val

        # Sort positions: 1. not in targets, 2. lowest confidence score, 3. smallest position
        sortable_holdings = []
        for ticker, weight in current_weights.items():
            if ticker in ("CASH", candidate_ticker):
                continue
            score = held_scores.get(ticker, 5.0)
            in_target = ticker in target_map and target_map[ticker] > 0
            val = (weight / 100.0) * total_value
            sortable_holdings.append({
                "ticker": ticker,
                "weight": weight,
                "value": val,
                "score": score,
                "in_target": in_target,
            })

        # Evicted / non-target first (in_target=False), then lowest score, then smallest value
        sortable_holdings.sort(key=lambda x: (x["in_target"], x["score"], x["value"]))

        for item in sortable_holdings:
            if reclaimed >= shortfall:
                break
            # Edge check via OpportunityCostService: ensure candidate offers sufficient profit edge over friction
            swap_eval = self.opportunity_cost_service.evaluate_swap(
                selling_ticker=item["ticker"],
                buying_ticker=candidate_ticker,
                sell_confidence=item["score"] / 10.0,
                buy_confidence=candidate_score / 10.0,
                is_pruning=(not item["in_target"]),
            )
            if not swap_eval.is_approved:
                logger.info(
                    f"Reclaim skipped for {item['ticker']} -> {candidate_ticker}: {swap_eval.reason}"
                )
                continue

            delta_w = item["weight"] / 100.0
            reclaim_val = item["value"]
            reclaimed += reclaim_val
            candidate_sells.append({
                "ticker": item["ticker"],
                "action": "SELL",
                "delta_weight": -delta_w,
                "amount": round(reclaim_val, 2),
                "confidence": item["score"],
                "reason": f"Capital rotation for {candidate_ticker}: liquidate {item['ticker']} (score={item['score']:.1f} vs {candidate_score:.1f})",
            })

        executed = []
        if execute and candidate_sells:
            for s in candidate_sells:
                res = await self._execute_trade(
                    ticker=s["ticker"],
                    action="SELL",
                    delta_weight=s["delta_weight"],
                    portfolio_value=total_value,
                    confidence_score=s["confidence"],
                    rationale=s["reason"],
                )
                executed.append({**s, "status": res.get("status", "executed")})

        return {
            "status": "reclaimed",
            "candidate_ticker": candidate_ticker,
            "target_amount": round(target_amount, 2),
            "available_cash_before": round(available_cash, 2),
            "reclaimed_amount": round(reclaimed, 2),
            "shortfall_remaining": round(max(0.0, shortfall - reclaimed), 2),
            "sells": executed if execute else candidate_sells,
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

            # Portfolio weights MUST always sum to 100% of the actual portfolio (raw_total).
            # 持倉權重與現金比例之分母必須為真實總資產 (raw_total)，確保全帳戶權重加總恆等於 100.0%，
            # 避免因 tradable_capital 上限導致權重虛胖至 200%+ 而扭曲再平衡與買賣判斷。
            stock_value = sum(float(getattr(p, "market_value", 0.0) or 0.0) for p in positions)
            if total_equity >= (stock_value + total_cash * 0.8) and total_equity > 0:
                raw_total = total_equity
            else:
                raw_total = total_equity + total_cash
            effective_capital = tradable_capital(self.user_id, raw_total)

            base_for_weights = raw_total if raw_total > 0 else total_equity
            # Use raw_total as the portfolio base to manage real existing holdings,
            # avoiding artificial clipping when managing an account with existing positions.
            total_portfolio_value = raw_total if (effective_capital <= 0 or effective_capital >= raw_total or raw_total > effective_capital) else effective_capital

            weights = {}
            positions_map = {}
            for p in positions:
                sym = getattr(p, "symbol", "")
                weight = (getattr(p, "market_value", 0) / base_for_weights) * 100.0
                weights[sym] = round(weight, 2)
                pnl = float(getattr(p, "unrealized_pnl", 0.0) or 0.0)
                mval = float(getattr(p, "market_value", 0.0) or 0.0)
                cost_basis = mval - pnl
                pnl_pct = (pnl / cost_basis) if cost_basis > 0 else 0.0
                positions_map[sym] = {
                    "open_date": getattr(p, "open_date", None),
                    "current_price": float(getattr(p, "current_price", 0.0) or 0.0),
                    "open_price": float(getattr(p, "open_price", 0.0) or 0.0),
                    "market_value": mval,
                    "unrealized_pnl": pnl,
                    "unrealized_pnl_pct": pnl_pct,
                }

            cash_weight = (total_cash / base_for_weights) * 100.0 if base_for_weights > 0 else 0.0

            return {
                "weights": weights,
                "cash_weight": cash_weight,
                "total_value": total_portfolio_value,
                "raw_total": raw_total,
                "total_equity": total_equity,
                "total_cash": total_cash,
                "positions_map": positions_map,
            }
        except Exception as e:
            logger.error(f"Failed to get current weights: {e}")
            return None

    async def _execute_trade(self, ticker: str, action: str,
                             delta_weight: float, portfolio_value: float,
                             confidence_score: Optional[float] = None,
                             rationale: Optional[str] = None,
                             strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Execute a single trade via AutomatedTradingService."""
        from src.services.automated_trading_service import AutomatedTradingService
        from src.services.settings_service import SettingsService
        from src.services.notification_service import NotificationService

        settings = SettingsService(user_id=self.user_id)
        notification = NotificationService.create_with_settings(settings_service=settings, user_id=self.user_id)
        trading = AutomatedTradingService(
            settings_repo=settings.settings_repo, notification_service=notification
        )

        strat = strategy_name or ("rebalance_diversification" if action.upper() == "SELL" else "portfolio_rebalance")
        score_to_use = 8.5 if (confidence_score is None or confidence_score <= 0.0) else confidence_score
        rationale_to_use = rationale or f"Confidence-driven rebalance: {action} {ticker} (delta={delta_weight:+.2%})"

        return await trading.evaluate_and_execute_trade(
            user_id=self.user_id,
            ticker=ticker,
            action=action,
            delta_weight=delta_weight,
            portfolio_value=portfolio_value,
            confidence_score=score_to_use,
            rationale=rationale_to_use,
            strategy_name=strat,
        )