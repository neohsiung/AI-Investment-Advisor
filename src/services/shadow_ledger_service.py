"""
Shadow Ledger Service
=====================
Core service for the Shadow Ledger & Paper Trading Validation Track (P2).
Simulates virtual order execution with realistic slippage and transaction costs,
tracks high-water marks and drawdowns mark-to-market, verifies institutional support
integrity, and evaluates graduation criteria before candidates are admitted into
the live Active Universe.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from src.config.owner import resolve_user_id
from src.repositories.settings_repository import AlchemySettingsRepository
from src.repositories.shadow_ledger_repository import (
    AlchemyShadowLedgerRepository,
    IShadowLedgerRepository,
)
from src.repositories.ticker_universe_repository import TickerUniverseRepository
from src.services.market_data_service import MarketDataService
from src.services.smart_money_support_service import SmartMoneySupportService
from src.utils.logger import setup_logger

logger = setup_logger("ShadowLedgerService")


@dataclass
class GraduationResult:
    """Evaluation outcome for a shadow position against graduation criteria."""
    ticker: str
    qualified: bool
    status: str                         # "QUALIFIED", "IN_PROGRESS", "FAILED"
    evaluation_days: int
    unrealized_pnl_pct: float
    max_drawdown_pct: float
    support_breached: bool
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ShadowLedgerService:
    """
    Manages virtual shadow positions for candidate tickers and unproven strategies:
    - Simulates order execution with slippage & commission friction.
    - Tracks mark-to-market valuations, peak high-water marks, and max drawdowns.
    - Monitors Smart Money institutional support price integrity.
    - Enforces graduation hurdles (7-14 days, return hurdle, drawdown limit).
    - Automatically promotes qualified tickers to 'active' or demotes failed ones.
    """

    def __init__(
        self,
        user_id: str,
        repo: Optional[IShadowLedgerRepository] = None,
        market: Optional[MarketDataService] = None,
        smart_money: Optional[SmartMoneySupportService] = None,
        ticker_repo: Optional[TickerUniverseRepository] = None,
        settings_repo: Optional[AlchemySettingsRepository] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.repo = repo or AlchemyShadowLedgerRepository()
        self.market = market or MarketDataService(user_id=self.user_id)
        self.smart_money = smart_money or SmartMoneySupportService(market_data_service=self.market)
        self.ticker_repo = ticker_repo or TickerUniverseRepository()
        self.settings_repo = settings_repo or AlchemySettingsRepository()

    # -------------------------------------------------------------------------
    # Settings & Policy Helpers
    # -------------------------------------------------------------------------

    def _get_setting_int(self, key: str, default: int) -> int:
        try:
            val = self.settings_repo.get(self.user_id, key)
            return int(val) if val is not None else default
        except Exception:
            return default

    def _get_setting_float(self, key: str, default: float) -> float:
        try:
            val = self.settings_repo.get(self.user_id, key)
            return float(val) if val is not None else default
        except Exception:
            return default

    def _get_setting_bool(self, key: str, default: bool) -> bool:
        try:
            val = self.settings_repo.get(self.user_id, key)
            if val is None:
                return default
            return str(val).lower() in ("true", "1", "yes")
        except Exception:
            return default

    # -------------------------------------------------------------------------
    # Core Operations
    # -------------------------------------------------------------------------

    async def open_shadow_position(
        self,
        ticker: str,
        strategy_name: str = "lifecycle_admission",
        allocated_capital: float = 1000.0,
        entry_price: Optional[float] = None,
        fee_pct: float = 0.001,
        slippage_pct: float = 0.0005,
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Open a new virtual shadow position with simulated friction.
        If an open shadow position already exists, it is returned without duplication.
        """
        ticker_sym = ticker.upper().strip()

        # Check existing open position
        existing = self.repo.get_open_position(self.user_id, ticker_sym)
        if existing:
            logger.info("Shadow position already active for %s (ID: %s)", ticker_sym, existing["id"])
            return existing

        # Fetch market price if not provided
        if entry_price is None or entry_price <= 0:
            prices = await self.market.get_current_prices([ticker_sym])
            raw_price = prices.get(ticker_sym)
            if not raw_price or raw_price <= 0:
                raise ValueError(f"Could not determine valid market entry price for {ticker_sym}")
            entry_price = float(raw_price)

        # Apply simulated execution slippage: buyer pays slightly higher
        simulated_entry_price = round(entry_price * (1.0 + slippage_pct), 4)
        fee_amount = round(allocated_capital * fee_pct, 2)
        investable_capital = max(1.0, allocated_capital - fee_amount)
        simulated_quantity = round(investable_capital / simulated_entry_price, 4)
        total_friction = round(fee_amount + (simulated_entry_price - entry_price) * simulated_quantity, 2)

        # Compute institutional smart money support baseline
        support_price = None
        try:
            support_result = self.smart_money.calculate_smart_money_support(ticker_sym)
            raw_support = getattr(support_result, "key_support_price", getattr(support_result, "institutional_support_price", None))
            if raw_support is not None:
                support_price = round(float(raw_support), 4)
            logger.info(
                "SmartMoney support established for shadow position %s: $%.2f",
                ticker_sym, support_price or 0.0
            )
        except Exception as ex:
            logger.warning("Could not calculate SmartMoney support for %s: %s", ticker_sym, ex)
            support_price = round(simulated_entry_price * 0.95, 4)

        # Persist shadow position
        pos = self.repo.create_position(
            user_id=self.user_id,
            ticker=ticker_sym,
            strategy_name=strategy_name,
            entry_price=simulated_entry_price,
            simulated_quantity=simulated_quantity,
            allocated_capital=allocated_capital,
            fees_and_slippage=total_friction,
            institutional_support_price=support_price,
            notes=notes or f"Simulated entry via {strategy_name}",
        )

        # Synchronize ticker_universe status to 'shadow'
        try:
            self.ticker_repo.upsert(self.user_id, ticker_sym, status="shadow")
            self.ticker_repo.add_log(
                self.user_id,
                ticker_sym,
                action="shadow_enrolled",
                agent_name="ShadowLedgerService",
                reasoning=(
                    f"Enrolled in Shadow Ledger validation at ${simulated_entry_price:.2f} "
                    f"with support ${support_price:.2f}"
                ),
                old_status="candidate",
                new_status="shadow",
            )
        except Exception as e:
            logger.warning("Failed to update ticker_universe log on shadow enrollment for %s: %s", ticker_sym, e)

        logger.info(
            "Opened shadow position: %s | Entry: $%.2f (Raw: $%.2f) | Qty: %.4f | Support: $%.2f",
            ticker_sym, simulated_entry_price, entry_price, simulated_quantity, support_price or 0.0
        )
        return pos

    async def mark_to_market(
        self,
        ticker: Optional[str] = None,
        prices_cache: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Mark all open shadow positions to market using current prices.
        Updates high-water mark peak, drawdown, unrealized PnL, and support breach status.
        """
        open_positions = self.repo.list_positions(self.user_id, status="OPEN", ticker=ticker)
        if not open_positions:
            return []

        tickers = list({p["ticker"] for p in open_positions})
        if prices_cache is None:
            prices_cache = await self.market.get_current_prices(tickers)

        updated_positions = []
        now_utc = datetime.now(timezone.utc)

        for pos in open_positions:
            sym = pos["ticker"]
            current_price = prices_cache.get(sym)
            if not current_price or current_price <= 0:
                logger.warning("No live price available for shadow MTM: %s", sym)
                continue

            current_price = float(current_price)
            entry_price = float(pos["entry_price"])
            quantity = float(pos["simulated_quantity"])
            allocated_capital = float(pos["allocated_capital"])
            prev_peak = float(pos.get("peak_price") or entry_price)
            prev_max_dd = float(pos.get("max_drawdown_pct") or 0.0)
            prev_peak_pnl = float(pos.get("peak_pnl_pct") or 0.0)
            support_price = float(pos.get("institutional_support_price") or 0.0)
            prev_breached = bool(pos.get("support_breached", False))

            # Valuations
            current_value = round(quantity * current_price, 2)
            unrealized_pnl = round(current_value - allocated_capital, 2)
            unrealized_pnl_pct = round(((current_price / entry_price) - 1.0) * 100, 4) if entry_price > 0 else 0.0

            # Peak tracking & drawdown from peak
            new_peak = max(prev_peak, current_price)
            new_peak_pnl = max(prev_peak_pnl, unrealized_pnl_pct)
            drawdown_from_peak = round(((new_peak - current_price) / new_peak) * 100, 4) if new_peak > 0 else 0.0
            new_max_dd = max(prev_max_dd, drawdown_from_peak)

            # Institutional support breach detection
            is_breached = prev_breached
            if support_price > 0 and current_price < support_price:
                is_breached = True

            # Calculate days active (do not decrement if already stepped)
            entry_dt = pos.get("entry_date")
            if isinstance(entry_dt, str):
                try:
                    entry_dt = datetime.fromisoformat(entry_dt.replace("Z", "+00:00"))
                except Exception:
                    entry_dt = now_utc
            if entry_dt and hasattr(entry_dt, "tzinfo") and entry_dt.tzinfo is None:
                entry_dt = entry_dt.replace(tzinfo=timezone.utc)

            elapsed_days = (now_utc - entry_dt).days if entry_dt else 0
            existing_eval_days = int(pos.get("evaluation_days") or 0)
            eval_days = max(existing_eval_days, elapsed_days)

            # Update DB
            self.repo.update_position(
                pos["id"],
                current_price=current_price,
                peak_price=new_peak,
                peak_pnl_pct=new_peak_pnl,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                max_drawdown_pct=new_max_dd,
                support_breached=is_breached,
                evaluation_days=eval_days,
            )

            updated = self.repo.get_position(pos["id"])
            if updated:
                updated_positions.append(updated)

        return updated_positions

    def evaluate_graduation(
        self,
        ticker: str,
        min_days: Optional[int] = None,
        min_return_pct: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
        require_support_held: Optional[bool] = None,
        max_eval_window_days: int = 21,
    ) -> GraduationResult:
        """
        Evaluate graduation status of an open shadow position.
        Graduation Hurdles:
          1. Observation Window: evaluation_days >= min_days (default: 7)
          2. Profitability: unrealized_pnl_pct >= min_return_pct (default: 0.0%)
          3. Risk Containment: max_drawdown_pct <= max_drawdown_pct (default: 5.0%)
          4. Smart Money Support: support_breached == False (if require_support_held is True)
        """
        ticker_sym = ticker.upper().strip()
        pos = self.repo.get_open_position(self.user_id, ticker_sym)
        if not pos:
            return GraduationResult(
                ticker=ticker_sym,
                qualified=False,
                status="NOT_FOUND",
                evaluation_days=0,
                unrealized_pnl_pct=0.0,
                max_drawdown_pct=0.0,
                support_breached=False,
                reasons=[f"No open shadow position found for {ticker_sym}"],
            )

        min_days = min_days if min_days is not None else self._get_setting_int("shadow_validation_min_days", 7)
        min_return_pct = (
            min_return_pct if min_return_pct is not None
            else self._get_setting_float("shadow_validation_min_return", 0.0)
        )
        max_drawdown_pct = (
            max_drawdown_pct if max_drawdown_pct is not None
            else self._get_setting_float("shadow_validation_max_drawdown", 5.0)
        )
        require_support_held = (
            require_support_held if require_support_held is not None
            else self._get_setting_bool("shadow_require_support_held", True)
        )

        eval_days = int(pos.get("evaluation_days") or 0)
        pnl_pct = float(pos.get("unrealized_pnl_pct") or 0.0)
        max_dd = float(pos.get("max_drawdown_pct") or 0.0)
        support_breached = bool(pos.get("support_breached", False))

        metrics = {
            "evaluation_days": eval_days,
            "min_days_required": min_days,
            "unrealized_pnl_pct": pnl_pct,
            "min_return_required": min_return_pct,
            "max_drawdown_pct": max_dd,
            "max_drawdown_allowed": max_drawdown_pct,
            "support_breached": support_breached,
            "entry_price": float(pos.get("entry_price") or 0.0),
            "current_price": float(pos.get("current_price") or 0.0),
            "peak_price": float(pos.get("peak_price") or 0.0),
            "institutional_support": float(pos.get("institutional_support_price") or 0.0),
        }

        # Check fatal failure conditions
        failure_reasons = []
        if require_support_held and support_breached:
            failure_reasons.append(
                f"Institutional Smart Money Support breached (Current: ${metrics['current_price']:.2f} "
                f"< Support: ${metrics['institutional_support']:.2f})"
            )

        if max_dd > max_drawdown_pct * 1.5:
            failure_reasons.append(
                f"Severe drawdown during shadow window ({max_dd:.2f}% > emergency cutoff {max_drawdown_pct * 1.5:.2f}%)"
            )

        if eval_days >= max_eval_window_days and pnl_pct < min_return_pct:
            failure_reasons.append(
                f"Expired evaluation window ({eval_days} days >= {max_eval_window_days}) without achieving positive return"
            )

        if failure_reasons:
            return GraduationResult(
                ticker=ticker_sym,
                qualified=False,
                status="FAILED",
                evaluation_days=eval_days,
                unrealized_pnl_pct=pnl_pct,
                max_drawdown_pct=max_dd,
                support_breached=support_breached,
                reasons=failure_reasons,
                metrics=metrics,
            )

        # Check qualification conditions
        pending_reasons = []
        if eval_days < min_days:
            pending_reasons.append(f"Observation period in progress ({eval_days}/{min_days} days)")
        if pnl_pct < min_return_pct:
            pending_reasons.append(f"Unrealized return {pnl_pct:.2f}% < required {min_return_pct:.2f}%")
        if max_dd > max_drawdown_pct:
            pending_reasons.append(f"Max drawdown {max_dd:.2f}% > threshold {max_drawdown_pct:.2f}%")

        if not pending_reasons:
            return GraduationResult(
                ticker=ticker_sym,
                qualified=True,
                status="QUALIFIED",
                evaluation_days=eval_days,
                unrealized_pnl_pct=pnl_pct,
                max_drawdown_pct=max_dd,
                support_breached=support_breached,
                reasons=["All shadow graduation criteria satisfied"],
                metrics=metrics,
            )

        return GraduationResult(
            ticker=ticker_sym,
            qualified=False,
            status="IN_PROGRESS",
            evaluation_days=eval_days,
            unrealized_pnl_pct=pnl_pct,
            max_drawdown_pct=max_dd,
            support_breached=support_breached,
            reasons=pending_reasons,
            metrics=metrics,
        )

    async def graduate_position(self, ticker: str, reason: str = "") -> Dict[str, Any]:
        """
        Promote a qualified shadow position to the live Active Universe.
        Closes shadow position with status='GRADUATED' and updates ticker_universe to 'active'.
        """
        ticker_sym = ticker.upper().strip()
        pos = self.repo.get_open_position(self.user_id, ticker_sym)
        if not pos:
            raise ValueError(f"No open shadow position found for {ticker_sym}")

        current_price = float(pos.get("current_price") or pos.get("entry_price"))
        metrics = {
            "evaluation_days": pos.get("evaluation_days"),
            "unrealized_pnl_pct": pos.get("unrealized_pnl_pct"),
            "max_drawdown_pct": pos.get("max_drawdown_pct"),
            "entry_price": pos.get("entry_price"),
            "final_price": current_price,
            "graduated_at": datetime.now(timezone.utc).isoformat(),
        }

        # 1. Close shadow position
        self.repo.close_position(
            pos["id"],
            status="GRADUATED",
            final_price=current_price,
            graduation_metrics=metrics,
            notes=reason or "Successfully graduated from shadow validation",
        )

        # 2. Update ticker_universe to 'active'
        self.ticker_repo.upsert(self.user_id, ticker_sym, status="active")
        self.ticker_repo.add_log(
            self.user_id,
            ticker_sym,
            action="shadow_graduated",
            agent_name="ShadowLedgerService",
            reasoning=(
                f"Graduated to Active Pool: {pos.get('evaluation_days')} days observed, "
                f"Return: {pos.get('unrealized_pnl_pct'):.2f}%, MaxDD: {pos.get('max_drawdown_pct'):.2f}%"
            ),
            old_status="shadow",
            new_status="active",
        )

        logger.info(
            "Graduated shadow position: %s -> active (Return: %.2f%%, MaxDD: %.2f%%)",
            ticker_sym, pos.get("unrealized_pnl_pct", 0.0), pos.get("max_drawdown_pct", 0.0)
        )

        # P3 Actionable Alert Hub: dispatch graduation promotion alert
        try:
            import asyncio
            from src.services.actionable_alert_service import ActionableAlertHubService
            hub = ActionableAlertHubService(user_id=self.user_id)
            asyncio.create_task(hub.dispatch_shadow_graduation_alert(
                ticker=ticker_sym,
                graduated=True,
                metrics=metrics,
                eval_days=int(pos.get("evaluation_days", 0)),
                unrealized_pnl_pct=float(pos.get("unrealized_pnl_pct", 0.0)),
                max_drawdown_pct=float(pos.get("max_drawdown_pct", 0.0)),
                support_breached=False,
            ))
        except Exception as alert_e:
            logger.debug("Failed to dispatch shadow graduation alert: %s", alert_e)

        return {
            "success": True,
            "ticker": ticker_sym,
            "status": "GRADUATED",
            "new_universe_status": "active",
            "metrics": metrics,
        }

    async def fail_position(
        self,
        ticker: str,
        reason: str = "",
        new_status: str = "candidate",
    ) -> Dict[str, Any]:
        """
        Terminate an underperforming shadow position.
        Closes shadow position with status='FAILED' and updates ticker_universe to candidate or removed.
        """
        ticker_sym = ticker.upper().strip()
        pos = self.repo.get_open_position(self.user_id, ticker_sym)
        if not pos:
            raise ValueError(f"No open shadow position found for {ticker_sym}")

        current_price = float(pos.get("current_price") or pos.get("entry_price"))
        metrics = {
            "evaluation_days": pos.get("evaluation_days"),
            "unrealized_pnl_pct": pos.get("unrealized_pnl_pct"),
            "max_drawdown_pct": pos.get("max_drawdown_pct"),
            "entry_price": pos.get("entry_price"),
            "final_price": current_price,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }

        # 1. Close shadow position
        self.repo.close_position(
            pos["id"],
            status="FAILED",
            final_price=current_price,
            graduation_metrics=metrics,
            notes=reason or "Failed shadow validation criteria",
        )

        # 2. Update ticker_universe
        self.ticker_repo.upsert(self.user_id, ticker_sym, status=new_status)
        self.ticker_repo.add_log(
            self.user_id,
            ticker_sym,
            action="shadow_failed",
            agent_name="ShadowLedgerService",
            reasoning=f"Shadow validation failed: {reason}",
            old_status="shadow",
            new_status=new_status,
        )

        logger.info(
            "Failed shadow position: %s -> %s (Reason: %s)",
            ticker_sym, new_status, reason
        )

        # P3 Actionable Alert Hub: dispatch shadow failure/eviction alert
        try:
            import asyncio
            from src.services.actionable_alert_service import ActionableAlertHubService
            hub = ActionableAlertHubService(user_id=self.user_id)
            asyncio.create_task(hub.dispatch_shadow_graduation_alert(
                ticker=ticker_sym,
                graduated=False,
                metrics=metrics,
                eval_days=int(pos.get("evaluation_days", 0)),
                unrealized_pnl_pct=float(pos.get("unrealized_pnl_pct", 0.0)),
                max_drawdown_pct=float(pos.get("max_drawdown_pct", 0.0)),
                support_breached=bool(pos.get("support_breached", False)),
            ))
        except Exception as alert_e:
            logger.debug("Failed to dispatch shadow fail alert: %s", alert_e)

        return {
            "success": True,
            "ticker": ticker_sym,
            "status": "FAILED",
            "new_universe_status": new_status,
            "metrics": metrics,
        }

    async def batch_step_and_evaluate(self, auto_promote: bool = True) -> Dict[str, Any]:
        """
        Batch process all open shadow positions:
        1. Marks all positions to market with live prices.
        2. Evaluates graduation for each position.
        3. If auto_promote is True, automatically graduates qualified tickers or fails breached ones.
        """
        open_positions = self.repo.list_positions(self.user_id, status="OPEN")
        if not open_positions:
            return {
                "success": True,
                "total_open": 0,
                "graduated": [],
                "failed": [],
                "in_progress": [],
            }

        # Step 1: Mark to Market
        await self.mark_to_market()

        graduated = []
        failed = []
        in_progress = []

        # Step 2 & 3: Evaluate & act
        for pos in open_positions:
            sym = pos["ticker"]
            eval_res = self.evaluate_graduation(sym)

            if eval_res.status == "QUALIFIED":
                if auto_promote:
                    grad_res = await self.graduate_position(sym, reason="; ".join(eval_res.reasons))
                    graduated.append(grad_res)
                else:
                    graduated.append(eval_res.to_dict())
            elif eval_res.status == "FAILED":
                if auto_promote:
                    fail_res = await self.fail_position(sym, reason="; ".join(eval_res.reasons))
                    failed.append(fail_res)
                else:
                    failed.append(eval_res.to_dict())
            else:
                in_progress.append(eval_res.to_dict())

        return {
            "success": True,
            "total_open": len(open_positions),
            "graduated_count": len(graduated),
            "failed_count": len(failed),
            "in_progress_count": len(in_progress),
            "graduated": graduated,
            "failed": failed,
            "in_progress": in_progress,
        }
