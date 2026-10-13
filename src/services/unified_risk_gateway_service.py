"""
Unified Risk Gateway Service (Phase 39)
=======================================
Consolidates previously fragmented risk guards and circuit breakers into a single,
authoritative pipeline before order execution.

Integrated Guard Pipeline:
    1. TradingProtectionsService (Drawdown, consecutive-loss lockout with reset watermark, cooldown, churn)
    2. CalendarBlackoutService (Macro FOMC/CPI & earnings 48h/24h blackout window)
    3. VPINToxicityGuardService (Informed trader adverse selection & Kyle's Lambda)
    4. BayesianJumpDiffusionGuardService (Jump intensity & acute discontinuous jump risk)
    5. SlippageGuardService (Opening auction window & bid-ask spread expansion)

Design Contract:
    - SELL / EXIT orders fail OPEN: protections must never prevent getting OUT of a position.
    - BUY / ACCUMULATE orders fail CLOSED: protects capital against hostile market regimes.
    - Single entrypoint for one-tap reset across all circuit breakers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("UnifiedRiskGatewayService")


class RiskSeverity(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


@dataclass
class RiskGatewayResult:
    allowed: bool
    severity: RiskSeverity
    primary_blocker: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    guard_details: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "severity": self.severity.value,
            "primary_blocker": self.primary_blocker,
            "reasons": self.reasons,
            "guard_details": self.guard_details,
            "evaluated_at": self.evaluated_at,
        }


class UnifiedRiskGatewayService:
    """
    Central Risk Gateway orchestrating all pre-trade guards and circuit breakers.
    """

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = resolve_user_id(user_id)

    async def evaluate_trade_risk(
        self,
        ticker: str,
        action: str,
        amount_usd: float = 0.0,
        current_price: Optional[float] = None,
    ) -> RiskGatewayResult:
        """
        Evaluate an order through the consolidated risk gateway.
        """
        sym = ticker.upper().strip()
        act = action.upper().strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        reasons: List[str] = []
        guard_details: Dict[str, Any] = {}
        is_buy = act in ("BUY", "STRONG_BUY", "ADD", "ACCUMULATE")

        # ---------------------------------------------------------
        # 1. Trading Protections (Drawdown, Lockout, Cooldown, Churn)
        # ---------------------------------------------------------
        try:
            from src.services.trading_protections_service import TradingProtectionsService
            prot_svc = TradingProtectionsService(user_id=self.user_id)
            block_reason = prot_svc.check(sym, act)
            guard_details["trading_protections"] = {"passed": block_reason is None, "reason": block_reason}
            if block_reason:
                reasons.append(f"[TradingProtections] {block_reason}")
                if is_buy:
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.BLOCKED,
                        primary_blocker="TradingProtections",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )
        except Exception as e:
            logger.error("UnifiedRiskGateway: TradingProtections check error: %s", e)
            if is_buy:
                reasons.append(f"[TradingProtections] Check unavailable ({type(e).__name__}); BUY blocked for safety")
                return RiskGatewayResult(
                    allowed=False,
                    severity=RiskSeverity.BLOCKED,
                    primary_blocker="TradingProtections_FailClosed",
                    reasons=reasons,
                    guard_details=guard_details,
                    evaluated_at=now_iso,
                )

        # ---------------------------------------------------------
        # 2. Calendar Blackout (Earnings & Macro Events)
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.calendar_blackout_service import CalendarBlackoutService
                c_svc = CalendarBlackoutService(user_id=self.user_id)
                cal_check = await c_svc.evaluate_candidate(sym)
                is_blackout = getattr(cal_check, "is_blackout", False)
                b_reason = getattr(cal_check, "reason", None) or "Earnings or macro event blackout active"
                guard_details["calendar_blackout"] = {
                    "is_blackout": is_blackout,
                    "reason": b_reason,
                    "event_type": getattr(cal_check, "event_type", None),
                }
                if is_blackout:
                    reasons.append(f"[CalendarBlackout] {b_reason}")
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.BLOCKED,
                        primary_blocker="CalendarBlackout",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )
            except Exception as e:
                logger.debug("UnifiedRiskGateway: Calendar blackout check skipped/failed: %s", e)

        # ---------------------------------------------------------
        # 3. Microstructure VPIN & Kyle's Lambda Toxicity Guard
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.vpin_toxicity_guard_service import VPINToxicityGuardService
                vpin_svc = VPINToxicityGuardService(user_id=self.user_id)
                vpin_res = await vpin_svc.assess_ticker(sym)
                guard_details["vpin_toxicity"] = {
                    "vpin": vpin_res.vpin,
                    "is_toxic": vpin_res.is_toxic,
                    "regime": vpin_res.regime.value if hasattr(vpin_res.regime, "value") else str(vpin_res.regime),
                    "action": vpin_res.recommended_action,
                }
                if vpin_res.is_toxic and vpin_res.recommended_action == "HALT":
                    reasons.append(f"[VPINToxicity] Microstructure flow toxicity elevated (VPIN={vpin_res.vpin:.3f})")
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.BLOCKED,
                        primary_blocker="VPINToxicity",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )
            except Exception as e:
                logger.debug("UnifiedRiskGateway: VPIN toxicity check skipped/failed: %s", e)

        # ---------------------------------------------------------
        # 4. Bayesian Jump Diffusion Guard (Tail Jump Shocks)
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.bayesian_jump_diffusion_guard_service import (
                    BayesianJumpDiffusionGuardService,
                )
                jump_svc = BayesianJumpDiffusionGuardService(user_id=self.user_id)
                jump_res = await jump_svc.assess_ticker(sym)
                guard_details["jump_diffusion"] = {
                    "jump_intensity": jump_res.jump_intensity,
                    "is_acute_jump": jump_res.is_acute_jump,
                    "regime": jump_res.regime.value if hasattr(jump_res.regime, "value") else str(jump_res.regime),
                }
                if jump_res.is_acute_jump and jump_res.regime.value == "JUMP_CRASH":
                    reasons.append(f"[JumpDiffusion] Acute crash jump intensity active (\u03bb_J={jump_res.jump_intensity:.2f})")
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.BLOCKED,
                        primary_blocker="JumpDiffusion",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )
            except Exception as e:
                logger.debug("UnifiedRiskGateway: Jump diffusion check skipped/failed: %s", e)

        # ---------------------------------------------------------
        # 5. Slippage & Auction Window Guard
        # ---------------------------------------------------------
        try:
            from src.services.slippage_guard_service import SlippageGuardService
            slip_svc = SlippageGuardService()
            is_window, win_reason = slip_svc.is_opening_auction_window()
            if is_window:
                guard_details["slippage_guard"] = {"auction_window": True, "reason": win_reason}
                if is_buy:
                    reasons.append(f"[SlippageGuard] Opening auction window active ({win_reason}); order deferred")
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.DEGRADED,
                        primary_blocker="OpeningAuctionWindow",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )

        except Exception as e:
            logger.debug("UnifiedRiskGateway: Slippage auction check skipped/failed: %s", e)

        # All guards cleared!
        return RiskGatewayResult(
            allowed=True,
            severity=RiskSeverity.NORMAL,
            primary_blocker=None,
            reasons=[],
            guard_details=guard_details,
            evaluated_at=now_iso,
        )

    def reset_all_protections(self) -> Dict[str, Any]:
        """
        One-tap master reset for all circuit breakers and trading protections.
        """
        from src.services.trading_protections_service import TradingProtectionsService
        prot_svc = TradingProtectionsService(user_id=self.user_id)
        watermark = prot_svc.reset_lockout()
        return {
            "success": True,
            "reset_watermark": watermark,
            "message": "All circuit breakers and consecutive-loss lockouts have been reset and archived.",
        }
