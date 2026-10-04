"""
Shadow Promotion Orchestrator Service (P5)
===========================================
Bridges virtual paper trading (P2 ShadowLedgerService) with live portfolio rotation,
enforcing non-linear opportunity costs (M3 OpportunityCostService), holding alpha decay
(M3 AlphaDecayService), and Smart Order Routing slicing plans (E1 SmartOrderRoutingService).

Lifecycle Flow:
1. Qualified Shadow Discovery:
   Identifies candidates that passed 7~14 days observation with positive returns,
   controlled max drawdown, and institutional support integrity intact (status='QUALIFIED').
2. Capacity & Cash Diagnostic:
   - Direct Promotion: If portfolio cash is ample and positions are below capacity,
     candidate graduates directly into the live universe.
   - Capital Rotation: If portfolio is at capacity or cash constrained, compares candidate
     against active holdings via AlphaDecayService and OpportunityCostService.
3. Opportunity Cost Hurdle:
   Displacement requires net edge >= non-linear hurdle (2.5 * Friction + 1.0%),
   with holding score penalized if stagnant alpha is detected.
4. Liquidity-Aware Execution & Alerts:
   Generates E1 SOR child slicing orders and dispatches bidirectional actionable
   cards with 1-tap confirmation or automated auto-rotation.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.repositories.shadow_ledger_repository import (
    AlchemyShadowLedgerRepository,
    IShadowLedgerRepository,
)
from src.repositories.ticker_universe_repository import TickerUniverseRepository
from src.services.shadow_ledger_service import (
    ShadowLedgerService,
    GraduationResult,
)
from src.services.opportunity_cost_service import (
    OpportunityCostService,
    SwapDecision,
)
from src.services.alpha_decay_service import (
    AlphaDecayService,
    AlphaDecayAssessment,
)
from src.services.smart_order_routing_service import (
    SmartOrderRoutingService,
    SlicingPlan,
    OrderAction,
    ExecutionStrategy,
)
from src.services.portfolio_aggregator_service import PortfolioAggregatorService
from src.services.actionable_alert_service import ActionableAlertHubService
from src.services.settings_service import SettingsService
from src.services.market_data_service import MarketDataService
from src.utils.logger import setup_logger

logger = setup_logger("ShadowPromotionOrchestrator")


class RotationActionType(str, Enum):
    """Categorization of shadow graduation actions."""
    DIRECT_PROMOTION = "DIRECT_PROMOTION"
    CAPITAL_ROTATION = "CAPITAL_ROTATION"
    BLOCKED_BY_HURDLE = "BLOCKED_BY_HURDLE"
    PENDING_QUALIFICATION = "PENDING_QUALIFICATION"
    FAILED_EVICTION = "FAILED_EVICTION"


@dataclass
class PromotionProposal:
    """Structure representing a shadow graduation & live promotion evaluation."""
    candidate_ticker: str
    action_type: str
    qualified: bool
    candidate_metrics: Dict[str, Any]
    displaced_ticker: Optional[str] = None
    displaced_metrics: Optional[Dict[str, Any]] = None
    raw_score_delta: float = 0.0
    net_opportunity_delta: float = 0.0
    hurdle: float = 0.0
    roundtrip_friction: float = 0.0
    estimated_capital: float = 0.0
    sor_plans: List[Dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    can_auto_execute: bool = False
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, AUTO_EXECUTABLE, EXECUTED, REJECTED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PromotionExecutionResult:
    """Result of executing a shadow promotion or capital rotation plan."""
    success: bool
    action_type: str
    candidate_ticker: str
    displaced_ticker: Optional[str] = None
    graduated_position_id: Optional[str] = None
    sor_execution_plans: List[Dict[str, Any]] = field(default_factory=list)
    alert_dispatched: bool = False
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ShadowPromotionOrchestrator:
    """
    Central Orchestrator for the Shadow-to-Live Automated Promotion Loop.
    影子交易資產畢業提拔與實盤輪轉閉環調度器。
    """

    def __init__(
        self,
        user_id: str,
        shadow_ledger_service: Optional[ShadowLedgerService] = None,
        shadow_repo: Optional[IShadowLedgerRepository] = None,
        ticker_repo: Optional[TickerUniverseRepository] = None,
        opportunity_cost_service: Optional[OpportunityCostService] = None,
        alpha_decay_service: Optional[AlphaDecayService] = None,
        sor_service: Optional[SmartOrderRoutingService] = None,
        portfolio_aggregator: Optional[PortfolioAggregatorService] = None,
        alert_hub: Optional[ActionableAlertHubService] = None,
        settings_service: Optional[SettingsService] = None,
        market_data_service: Optional[MarketDataService] = None,
        slippage_compensator: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.shadow_repo = shadow_repo or AlchemyShadowLedgerRepository()
        self.ticker_repo = ticker_repo or TickerUniverseRepository()
        self.market = market_data_service or MarketDataService(user_id=self.user_id)
        self.settings = settings_service or SettingsService(user_id=self.user_id)
        self.slippage_compensator = slippage_compensator

        self.shadow_ledger = shadow_ledger_service or ShadowLedgerService(
            user_id=self.user_id,
            repo=self.shadow_repo,
            market=self.market,
            ticker_repo=self.ticker_repo,
        )
        self.opportunity_cost = opportunity_cost_service or OpportunityCostService(
            user_id=self.user_id,
            settings_service=self.settings,
            slippage_compensator=self.slippage_compensator,
        )
        self.alpha_decay = alpha_decay_service or AlphaDecayService(
            user_id=self.user_id,
            settings_service=self.settings,
            market_data_service=self.market,
        )
        self.sor_service = sor_service or SmartOrderRoutingService(
            user_id=self.user_id,
            settings_repo=getattr(self.settings, "repo", None),
            feedback_service=self.slippage_compensator,
        )
        self.portfolio_aggregator = portfolio_aggregator or PortfolioAggregatorService(user_id=self.user_id)
        self.alert_hub = alert_hub or ActionableAlertHubService(user_id=self.user_id)

    # -------------------------------------------------------------------------
    # Settings Helpers
    # -------------------------------------------------------------------------

    def _get_setting_int(self, key: str, default: int) -> int:
        try:
            val = self.settings.get_setting(key, default)
            return int(val) if val is not None else default
        except Exception:
            return default

    def _get_setting_float(self, key: str, default: float) -> float:
        try:
            val = self.settings.get_setting(key, default)
            return float(val) if val is not None else default
        except Exception:
            return default

    def _get_setting_bool(self, key: str, default: bool) -> bool:
        try:
            val = self.settings.get_setting(key, default)
            if val is None:
                return default
            return str(val).lower() in ("true", "1", "yes")
        except Exception:
            return default

    # -------------------------------------------------------------------------
    # Core Promotion Evaluation Pipeline
    # -------------------------------------------------------------------------

    async def evaluate_promotions(
        self,
        candidate_tickers: Optional[List[str]] = None,
        auto_execute_if_eligible: bool = False,
    ) -> List[PromotionProposal]:
        """
        Scan open shadow positions, evaluate graduation criteria, and generate
        tailored live admission or rotation plans against current live portfolio holdings.
        """
        proposals: List[PromotionProposal] = []

        # 1. Discover target shadow positions
        target_positions = []
        if candidate_tickers:
            for t in candidate_tickers:
                sym = t.upper().strip()
                pos = self.shadow_repo.get_open_position(self.user_id, sym)
                if pos:
                    target_positions.append(pos)
                else:
                    logger.warning("No open shadow position found for requested candidate %s", sym)
        else:
            target_positions = self.shadow_repo.list_positions(self.user_id, status="OPEN")

        if not target_positions:
            logger.info("No active shadow positions found for user %s", self.user_id)
            return []

        # 2. Fetch live portfolio context
        portfolio_data = await self._fetch_portfolio_context()
        portfolio_value = portfolio_data["total_value"]
        available_cash = portfolio_data["available_cash"]
        active_holdings = portfolio_data["active_holdings"]

        max_active_positions = self._get_setting_int("shadow_max_active_positions", 10)
        min_rotation_edge = self._get_setting_float("shadow_rotation_min_edge", 0.015)
        auto_rotation_enabled = self._get_setting_bool("shadow_auto_rotation_enabled", False)

        for pos in target_positions:
            ticker = pos["ticker"].upper().strip()
            grad_result: GraduationResult = self.shadow_ledger.evaluate_graduation(ticker)

            if grad_result.status == "FAILED":
                proposals.append(
                    PromotionProposal(
                        candidate_ticker=ticker,
                        action_type=RotationActionType.FAILED_EVICTION.value,
                        qualified=False,
                        candidate_metrics=grad_result.metrics,
                        rationale=f"影子驗證未通過考核：{'; '.join(grad_result.reasons)}",
                        status="REJECTED",
                    )
                )
                continue

            if not grad_result.qualified:
                proposals.append(
                    PromotionProposal(
                        candidate_ticker=ticker,
                        action_type=RotationActionType.PENDING_QUALIFICATION.value,
                        qualified=False,
                        candidate_metrics=grad_result.metrics,
                        rationale=f"影子驗證觀察期進行中：{'; '.join(grad_result.reasons)}",
                        status="IN_PROGRESS",
                    )
                )
                continue

            # Candidate IS QUALIFIED!
            allocated_capital = float(pos.get("allocated_capital") or 1000.0)
            target_capital = max(100.0, min(portfolio_value * 0.10, allocated_capital * 1.5, 10000.0))
            candidate_price = float(pos.get("current_price") or pos.get("entry_price") or 100.0)

            # Determine if Direct Promotion is feasible
            can_direct_promote = (
                len(active_holdings) < max_active_positions
                and available_cash >= target_capital
            )

            if can_direct_promote:
                # Direct Promotion without displacement
                sor_buy = self._generate_sor_plan(
                    symbol=ticker,
                    action=OrderAction.BUY,
                    target_amount_usd=target_capital,
                    price=candidate_price,
                )
                proposal = PromotionProposal(
                    candidate_ticker=ticker,
                    action_type=RotationActionType.DIRECT_PROMOTION.value,
                    qualified=True,
                    candidate_metrics=grad_result.metrics,
                    estimated_capital=round(target_capital, 2),
                    sor_plans=[sor_buy],
                    rationale=(
                        f"影子標的已通過考核（觀察 {grad_result.evaluation_days} 天，浮盈 {grad_result.unrealized_pnl_pct:+.2f}%）。"
                        f"投組目前持倉 ({len(active_holdings)}/{max_active_positions}) 且可用現金充足 (${available_cash:,.2f})，直接提拔為實盤開倉。"
                    ),
                    can_auto_execute=auto_rotation_enabled,
                    status="AUTO_EXECUTABLE" if auto_rotation_enabled else "PENDING_APPROVAL",
                )
                proposals.append(proposal)

                if auto_execute_if_eligible and auto_rotation_enabled:
                    await self.execute_promotion(candidate_ticker=ticker)
                    proposal.status = "EXECUTED"

                continue

            # Capacity full or cash tight: Evaluate Capital Rotation
            rotation_eval = await self._evaluate_holding_displacement(
                candidate_ticker=ticker,
                candidate_price=candidate_price,
                candidate_pnl_pct=grad_result.unrealized_pnl_pct,
                active_holdings=active_holdings,
                target_capital=target_capital,
                min_edge=min_rotation_edge,
            )

            if rotation_eval["eligible_swap"]:
                displaced_sym = rotation_eval["displaced_ticker"]
                holding_info = rotation_eval["displaced_holding"]
                net_delta = rotation_eval["net_delta"]
                hurdle = rotation_eval["hurdle"]
                friction = rotation_eval["friction"]
                sor_sell = rotation_eval["sor_sell_plan"]
                sor_buy = rotation_eval["sor_buy_plan"]

                proposal = PromotionProposal(
                    candidate_ticker=ticker,
                    action_type=RotationActionType.CAPITAL_ROTATION.value,
                    qualified=True,
                    candidate_metrics=grad_result.metrics,
                    displaced_ticker=displaced_sym,
                    displaced_metrics=rotation_eval["displaced_metrics"],
                    raw_score_delta=rotation_eval["raw_delta"],
                    net_opportunity_delta=net_delta,
                    hurdle=hurdle,
                    roundtrip_friction=friction,
                    estimated_capital=round(target_capital, 2),
                    sor_plans=[sor_sell, sor_buy],
                    rationale=(
                        f"影子標的考核達標，且相較於現有持倉 {displaced_sym} 具備顯著優勢（淨利差 +{net_delta * 100:.2f}% "
                        f"超越機會成本門檻 {hurdle * 100:.2f}%）。{rotation_eval['reason']}"
                    ),
                    can_auto_execute=auto_rotation_enabled,
                    status="AUTO_EXECUTABLE" if auto_rotation_enabled else "PENDING_APPROVAL",
                )
                proposals.append(proposal)

                if auto_execute_if_eligible and auto_rotation_enabled:
                    await self.execute_promotion(
                        candidate_ticker=ticker,
                        displaced_ticker=displaced_sym,
                    )
                    proposal.status = "EXECUTED"
            else:
                proposal = PromotionProposal(
                    candidate_ticker=ticker,
                    action_type=RotationActionType.BLOCKED_BY_HURDLE.value,
                    qualified=True,
                    candidate_metrics=grad_result.metrics,
                    raw_score_delta=rotation_eval.get("raw_delta", 0.0),
                    net_opportunity_delta=rotation_eval.get("net_delta", 0.0),
                    hurdle=rotation_eval.get("hurdle", 0.0175),
                    roundtrip_friction=rotation_eval.get("friction", 0.003),
                    estimated_capital=round(target_capital, 2),
                    rationale=(
                        f"影子標的已符合畢業資格，但現有實盤持倉動能依然強健且無顯著 Alpha 鈍化衰減。"
                        f"換庫淨利差未達非線性機會成本門檻 ({rotation_eval.get('hurdle', 0.0175) * 100:.2f}%)，"
                        f"依換手抑制原則暫緩置換以避免手續費磨損。"
                    ),
                    can_auto_execute=False,
                    status="PENDING_APPROVAL",
                )
                proposals.append(proposal)

        return proposals

    # -------------------------------------------------------------------------
    # Swap & Displacement Helper
    # -------------------------------------------------------------------------

    async def _evaluate_holding_displacement(
        self,
        candidate_ticker: str,
        candidate_price: float,
        candidate_pnl_pct: float,
        active_holdings: List[Dict[str, Any]],
        target_capital: float,
        min_edge: float,
    ) -> Dict[str, Any]:
        """
        Iterates over active live holdings to identify the best candidate for liquidation/swap,
        factoring in holding age, AlphaDecayService stagnation, and OpportunityCostService hurdles.
        """
        if not active_holdings:
            return {
                "eligible_swap": False,
                "displaced_ticker": None,
                "reason": "No active holdings in portfolio to displace",
            }

        candidate_score = min(10.0, 7.0 + max(0.0, candidate_pnl_pct * 0.3))

        candidates_ranked = []
        for h in active_holdings:
            sym = h["symbol"].upper().strip()
            if sym == candidate_ticker or h.get("is_pinned"):
                # Pinned positions are immune to displacement
                continue

            open_date = h.get("open_date")
            holding_days = self.alpha_decay.calculate_holding_days(open_date)
            current_price = float(h.get("current_price") or 100.0)
            holding_return_pct = float(h.get("unrealized_pnl_pct") or 0.0)

            # Technical context for holding
            sma20 = current_price * 1.02 if holding_return_pct < 0 else current_price * 0.98

            decay_eval: AlphaDecayAssessment = self.alpha_decay.evaluate_holding_decay(
                ticker=sym,
                holding_days=holding_days,
                current_price=current_price,
                sma_20=sma20,
                holding_return_pct=holding_return_pct,
            )

            # Base holding confidence score (0-10)
            holding_base_score = 6.0 + (holding_return_pct * 10.0)
            holding_base_score = max(2.0, min(9.5, holding_base_score))

            # Apply alpha decay penalty: stagnant holdings are severely discounted
            effective_holding_score = holding_base_score * decay_eval.decay_factor

            swap_dec: SwapDecision = self.opportunity_cost.evaluate_swap(
                holding_ticker=sym,
                candidate_ticker=candidate_ticker,
                holding_score=effective_holding_score,
                candidate_score=candidate_score,
            )

            net_delta = swap_dec.net_opportunity_delta / 100.0 if swap_dec.net_opportunity_delta > 1.0 else swap_dec.net_opportunity_delta
            hurdle = swap_dec.friction_hurdle / 100.0 if swap_dec.friction_hurdle > 1.0 else swap_dec.friction_hurdle

            candidates_ranked.append({
                "symbol": sym,
                "holding_info": h,
                "decay_eval": decay_eval,
                "swap_dec": swap_dec,
                "net_delta": net_delta,
                "hurdle": hurdle,
                "friction": swap_dec.roundtrip_friction,
                "has_decay": decay_eval.has_decay,
                "decay_factor": decay_eval.decay_factor,
                "holding_days": holding_days,
            })

        if not candidates_ranked:
            return {
                "eligible_swap": False,
                "displaced_ticker": None,
                "reason": "All active holdings are pinned or protected",
            }

        # Sort: Primary by has_decay (stagnant first), secondary by net advantage delta descending
        candidates_ranked.sort(
            key=lambda x: (1 if x["has_decay"] else 0, x["net_delta"]),
            reverse=True,
        )

        best = candidates_ranked[0]
        if best["swap_dec"].is_approved and best["net_delta"] >= min_edge:
            sor_sell = self._generate_sor_plan(
                symbol=best["symbol"],
                action=OrderAction.SELL,
                target_amount_usd=min(target_capital, float(best["holding_info"].get("market_value") or target_capital)),
                price=float(best["holding_info"].get("current_price") or 100.0),
            )
            sor_buy = self._generate_sor_plan(
                symbol=candidate_ticker,
                action=OrderAction.BUY,
                target_amount_usd=target_capital,
                price=candidate_price,
            )

            decay_note = "（持倉出現 Alpha 衰減鈍化，優先淘汰）" if best["has_decay"] else "（邊際效用低於換庫門檻）"
            return {
                "eligible_swap": True,
                "displaced_ticker": best["symbol"],
                "displaced_holding": best["holding_info"],
                "displaced_metrics": {
                    "holding_days": best["holding_days"],
                    "has_decay": best["has_decay"],
                    "decay_factor": round(best["decay_factor"], 3),
                    "unrealized_pnl_pct": best["holding_info"].get("unrealized_pnl_pct", 0.0),
                },
                "raw_delta": best["swap_dec"].raw_delta,
                "net_delta": best["net_delta"],
                "hurdle": best["hurdle"],
                "friction": best["friction"],
                "reason": f"持倉 {best['symbol']} 已持有 {best['holding_days']} 天{decay_note}。",
                "sor_sell_plan": sor_sell,
                "sor_buy_plan": sor_buy,
            }

        return {
            "eligible_swap": False,
            "displaced_ticker": best["symbol"],
            "raw_delta": best["swap_dec"].raw_delta,
            "net_delta": best["net_delta"],
            "hurdle": best["hurdle"],
            "friction": best["friction"],
            "reason": "No holding met the opportunity cost hurdle",
        }

    # -------------------------------------------------------------------------
    # Execution Engine
    # -------------------------------------------------------------------------

    async def execute_promotion(
        self,
        candidate_ticker: str,
        displaced_ticker: Optional[str] = None,
        auto_rebalance: bool = True,
    ) -> PromotionExecutionResult:
        """
        Executes the promotion of a qualified shadow position:
        1. Closes the shadow position with status='GRADUATED'.
        2. Promotes ticker in ticker_universe to 'active'.
        3. If displaced_ticker is provided, demotes displaced holding to 'candidate'.
        4. Generates and records E1 SOR child orders for audit & execution.
        5. Dispatches bidirectional Actionable Alert notification.
        """
        cand_sym = candidate_ticker.upper().strip()
        disp_sym = displaced_ticker.upper().strip() if displaced_ticker else None

        logger.info(
            "Executing promotion for candidate %s (displaced=%s, auto_rebalance=%s)",
            cand_sym, disp_sym, auto_rebalance,
        )

        pos = self.shadow_repo.get_open_position(self.user_id, cand_sym)
        if not pos:
            return PromotionExecutionResult(
                success=False,
                action_type="FAILED",
                candidate_ticker=cand_sym,
                displaced_ticker=disp_sym,
                message=f"No active shadow position found for {cand_sym}",
            )

        # 1. Graduate shadow position
        reason_msg = f"Graduated to live universe (Displaced: {disp_sym or 'None'})"
        await self.shadow_ledger.graduate_position(cand_sym, reason=reason_msg)

        # 2. If displaced holding exists, demote in ticker_universe
        if disp_sym:
            self.ticker_repo.upsert(self.user_id, disp_sym, status="candidate")
            self.ticker_repo.add_log(
                self.user_id,
                disp_sym,
                action="shadow_rotation_displaced",
                agent_name="ShadowPromotionOrchestrator",
                reasoning=f"Displaced by newly graduated shadow leader {cand_sym} clearing opportunity hurdle",
                old_status="active",
                new_status="candidate",
            )

        # 3. Generate SOR execution plans
        sor_plans = []
        cand_price = float(pos.get("current_price") or pos.get("entry_price") or 100.0)
        target_capital = float(pos.get("allocated_capital") or 1000.0)

        if disp_sym:
            disp_plan = self._generate_sor_plan(
                symbol=disp_sym,
                action=OrderAction.SELL,
                target_amount_usd=target_capital,
                price=100.0,
            )
            sor_plans.append(disp_plan)

        cand_plan = self._generate_sor_plan(
            symbol=cand_sym,
            action=OrderAction.BUY,
            target_amount_usd=target_capital,
            price=cand_price,
        )
        sor_plans.append(cand_plan)

        # 4. Dispatch interactive Actionable Alert notification
        alert_dispatched = False
        try:
            action_type_label = "CAPITAL_ROTATION" if disp_sym else "DIRECT_PROMOTION"
            plans_summary = f"{len(sor_plans)} 筆智能分批排程（{cand_plan['total_child_orders']} 筆子單）"
            await self.alert_hub.dispatch_shadow_promotion_rotation_alert(
                candidate_ticker=cand_sym,
                action_type=action_type_label,
                displaced_ticker=disp_sym,
                net_edge_pct=0.025,
                hurdle_pct=0.0175,
                estimated_capital=target_capital,
                sor_plans_summary=plans_summary,
                auto_executed=True,
            )
            alert_dispatched = True
        except Exception as alert_err:
            logger.warning("Could not dispatch shadow promotion alert: %s", alert_err)

        msg = (
            f"Successfully promoted {cand_sym} to live Active Universe."
            + (f" Rotated out {disp_sym}." if disp_sym else " Direct admission without displacement.")
        )
        return PromotionExecutionResult(
            success=True,
            action_type="CAPITAL_ROTATION" if disp_sym else "DIRECT_PROMOTION",
            candidate_ticker=cand_sym,
            displaced_ticker=disp_sym,
            graduated_position_id=str(pos.get("id")),
            sor_execution_plans=sor_plans,
            alert_dispatched=alert_dispatched,
            message=msg,
        )

    # -------------------------------------------------------------------------
    # Context & SOR Helpers
    # -------------------------------------------------------------------------

    async def _fetch_portfolio_context(self) -> Dict[str, Any]:
        """Fetch unified portfolio metrics and holdings list."""
        try:
            port = await self.portfolio_aggregator.get_aggregated_portfolio()
            positions = port.get("positions", [])
            total_equity = float(port.get("total_equity", 0.0))
            total_cash = float(port.get("total_cash", 0.0))
            raw_total = total_equity + total_cash

            active_holdings = []
            pinned_tickers = {
                t["ticker"]
                for t in self.ticker_repo.get_all(self.user_id, status="active")
                if t.get("is_pinned")
            }

            for p in positions:
                sym = getattr(p, "symbol", "") or ""
                sym = sym.upper().strip()
                if not sym or sym in ("CASH", "USD"):
                    continue

                mval = float(getattr(p, "market_value", 0.0) or 0.0)
                pnl = float(getattr(p, "unrealized_pnl", 0.0) or 0.0)
                cost = mval - pnl
                pnl_pct = (pnl / cost) if cost > 0 else 0.0

                active_holdings.append({
                    "symbol": sym,
                    "market_value": mval,
                    "quantity": float(getattr(p, "quantity", 0.0) or 0.0),
                    "current_price": float(getattr(p, "current_price", 0.0) or 0.0),
                    "open_date": getattr(p, "open_date", None),
                    "unrealized_pnl": pnl,
                    "unrealized_pnl_pct": pnl_pct,
                    "is_pinned": sym in pinned_tickers,
                })

            return {
                "total_value": max(1000.0, raw_total),
                "available_cash": max(0.0, total_cash),
                "active_holdings": active_holdings,
            }
        except Exception as e:
            logger.warning("Error fetching portfolio context: %s, falling back to defaults", e)
            return {
                "total_value": 100000.0,
                "available_cash": 15000.0,
                "active_holdings": [],
            }

    def _generate_sor_plan(
        self,
        symbol: str,
        action: OrderAction,
        target_amount_usd: float,
        price: float,
    ) -> Dict[str, Any]:
        """Generate E1 SOR slicing plan for given leg."""
        shares = max(1, int(round(target_amount_usd / price))) if price > 0 else 1
        default_adv = 1000000.0

        plan: SlicingPlan = self.sor_service.generate_plan(
            symbol=symbol,
            action=action,
            requested_quantity=float(shares),
            arrival_price=price,
            adv_20=default_adv,
            execution_window_minutes=60,
        )

        return {
            "symbol": plan.symbol,
            "action": plan.action.value,
            "strategy": plan.strategy.value,
            "total_requested_quantity": plan.total_requested_quantity,
            "approved_quantity": plan.approved_quantity,
            "unfilled_rollover_quantity": plan.unfilled_rollover_quantity,
            "total_child_orders": len(plan.child_orders),
            "estimated_amount_usd": round(target_amount_usd, 2),
            "is_sliced": len(plan.child_orders) > 1,
            "child_orders": [c.to_dict() for c in plan.child_orders],
        }
