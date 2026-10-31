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
    6. DynamicIVSurfaceSkewHedgingService (Phase 61A: Extreme tail inversion & IV skew panic)
    7. MicrostructureOrderFlowImbalanceService (Phase 61B: Order flow imbalance & liquidity vacuum freeze)
    8. KalmanPairsTradingService (Phase 62B: Structural break & co-integration breakdown)
    9. TrendHysteresisLockoutService (Phase 63A: Schmitt Trigger Hysteresis & Macro Bull Long-Only Lock)
    10. FrictionAwareTrancheSizingService (Phase 63B/64A: Turnover Friction Hurdle & Tranche Sizing)
    11. CrossCurrencyFXHedgingService (Phase 65: Multi-currency margin liquidity buffer & FX VaR guard)

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
from src.services import charter_state_service
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
        strategy_name: Optional[str] = None,
        confidence_score: Optional[float] = None,
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

        # 0. Charter halt (G7, R3, ADR-005): while frozen / human_stop only whitelisted exit strategies pass, BUY and
        # SELL alike. An unreadable state blocks a BUY; a SELL goes through but carries a visible marker.
        # 章程停機：凍結或人工停止時，買賣都只放行白名單內的出場策略；狀態讀不到時買單擋、賣單放行並帶標記。
        halt_ok, halt_why = charter_state_service.order_allowed(act, strategy_name, datetime.now(timezone.utc))
        if not halt_ok:
            guard_details["charter_halt"] = {"passed": False, "reason": halt_why}
            return RiskGatewayResult(
                allowed=False,
                severity=RiskSeverity.BLOCKED,
                primary_blocker="CharterHalt",
                reasons=[f"[Charter] {halt_why}"],
                guard_details=guard_details,
                evaluated_at=now_iso,
            )
        if charter_state_service.UNREADABLE_SELL_MARK in halt_why:
            guard_details["charter_halt"] = {
                "passed": True, "reason": halt_why, "marker": charter_state_service.UNREADABLE_SELL_MARK}

        # ---------------------------------------------------------
        # 1. Trading Protections (Drawdown, Lockout, Cooldown, Churn, Flip-Flop)
        # ---------------------------------------------------------
        try:
            from src.services.trading_protections_service import TradingProtectionsService
            prot_svc = TradingProtectionsService(user_id=self.user_id)
            block_reason = prot_svc.check(sym, act, strategy_name=strategy_name)
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
                self._guard_degraded(guard_details, "Calendar blackout", e)

        # ---------------------------------------------------------
        # 3. Microstructure VPIN & Kyle's Lambda Toxicity Guard
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.vpin_toxicity_guard_service import VPINToxicityGuardService
                vpin_svc = VPINToxicityGuardService(user_id=self.user_id)
                vpin_res = await vpin_svc.evaluate_ticker(sym)
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
                self._guard_degraded(guard_details, "VPIN toxicity", e)

        # ---------------------------------------------------------
        # 4. Bayesian Jump Diffusion Guard (Tail Jump Shocks)
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.bayesian_jump_diffusion_guard_service import (
                    BayesianJumpDiffusionGuardService,
                )
                jump_svc = BayesianJumpDiffusionGuardService(user_id=self.user_id)
                jump_res = await jump_svc.evaluate_ticker(sym)
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
                self._guard_degraded(guard_details, "Jump diffusion", e)

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
            self._guard_degraded(guard_details, "Slippage auction", e)

        # ---------------------------------------------------------
        # 6. Dynamic IV Surface Skew & Tail Risk Hedging (Phase 61A)
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.dynamic_iv_surface_skew_hedging_service import (
                    DynamicIVSurfaceSkewHedgingService,
                )
                iv_svc = DynamicIVSurfaceSkewHedgingService(user_id=self.user_id)
                if await iv_svc.is_enabled():
                    iv_metric = await iv_svc.assess_iv_surface(sym, current_price=current_price)
                    guard_details["iv_surface_skew"] = {
                        "regime": iv_metric.regime,
                        "skew_ratio": iv_metric.skew_ratio,
                        "tail_risk_index": iv_metric.tail_risk_index,
                        "term_structure_slope": iv_metric.term_structure_slope,
                        "risk_budget_multiplier": iv_metric.risk_budget_multiplier,
                        "recommended_downward_shift_pct": iv_metric.recommended_downward_shift_pct,
                    }
                    if iv_metric.regime == "EXTREME_TAIL_INVERSION":
                        reasons.append(
                            f"[IVSurfaceSkew] Extreme tail risk inversion active (Skew={iv_metric.skew_ratio:.2f}, Slope={iv_metric.term_structure_slope*100:.1f}%)"
                        )
                        return RiskGatewayResult(
                            allowed=False,
                            severity=RiskSeverity.DEGRADED,
                            primary_blocker="ExtremeIVTailInversion",
                            reasons=reasons,
                            guard_details=guard_details,
                            evaluated_at=now_iso,
                        )
            except Exception as e:
                self._guard_degraded(guard_details, "IV surface skew", e)

        # ---------------------------------------------------------
        # 7. Microstructure OFI & Liquidity Vacuum Defense (Phase 61B)
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.microstructure_order_flow_imbalance_service import (
                    MicrostructureOrderFlowImbalanceService,
                )
                ofi_svc = MicrostructureOrderFlowImbalanceService(user_id=self.user_id)
                if await ofi_svc.is_enabled():
                    is_frozen, freeze_reason, freeze_ttl = await ofi_svc.is_vacuum_frozen(sym)
                    if is_frozen:
                        guard_details["microstructure_ofi"] = {
                            "is_vacuum_frozen": True,
                            "reason": freeze_reason,
                            "remaining_seconds": freeze_ttl,
                        }
                        reasons.append(
                            f"[MicrostructureOFI] Market maker liquidity vacuum freeze active ({freeze_reason}, {freeze_ttl}s remaining)"
                        )
                        return RiskGatewayResult(
                            allowed=False,
                            severity=RiskSeverity.BLOCKED,
                            primary_blocker="LiquidityVacuumFreeze",
                            reasons=reasons,
                            guard_details=guard_details,
                            evaluated_at=now_iso,
                        )
            except Exception as e:
                self._guard_degraded(guard_details, "Microstructure OFI", e)

        # ---------------------------------------------------------
        # 8. Option Gamma Exposure (GEX) Volatility Accelerator (Phase 62A)
        # ---------------------------------------------------------
        if is_buy:
            try:
                from src.services.option_gamma_exposure_gex_service import OptionGammaExposureGEXService
                gex_svc = OptionGammaExposureGEXService(user_id=self.user_id)
                if await gex_svc.is_enabled():
                    gex_metric = await gex_svc.evaluate_ticker_gex(sym, spot_price=current_price)
                    if gex_metric.fallback_reason:
                        # Not a real measurement: mark as not applicable, never pass-with-numbers, never block.
                        # 非真實量測：標記為不適用，不當作帶數字的通過，也不阻擋。
                        guard_details["gamma_exposure_gex"] = {
                            "status": "not_applicable",
                            "fallback_reason": gex_metric.fallback_reason,
                        }
                        logger.warning(
                            "UnifiedRiskGateway: Option GEX not applicable for %s (%s)",
                            sym, gex_metric.fallback_reason,
                        )
                    else:
                        guard_details["gamma_exposure_gex"] = {
                            "regime": gex_metric.regime,
                            "net_gex": gex_metric.net_gex,
                            "zero_gamma_flip_point": gex_metric.zero_gamma_flip_point,
                            "distance_to_flip_pct": gex_metric.distance_to_flip_pct,
                            "volatility_damping_multiplier": gex_metric.volatility_damping_multiplier,
                            "requires_protection": gex_metric.requires_protection,
                        }
                        if gex_metric.regime == OptionGammaExposureGEXService.REGIME_NEGATIVE_GAMMA and gex_metric.distance_to_flip_pct < -0.05:
                            reasons.append(
                                f"[OptionGEX] Market maker negative gamma regime active (Net GEX=${gex_metric.net_gex/1e6:.2f}M, Spot < Flip ${gex_metric.zero_gamma_flip_point:.2f})"
                            )
                            return RiskGatewayResult(
                                allowed=False,
                                severity=RiskSeverity.DEGRADED,
                                primary_blocker="NegativeGammaVolatilityAccelerator",
                                reasons=reasons,
                                guard_details=guard_details,
                                evaluated_at=now_iso,
                            )
            except Exception as e:
                self._guard_degraded(guard_details, "Option GEX", e)

        # ---------------------------------------------------------
        # 9. Kalman Pairs Cointegration & Structural Break Defense (Phase 62B)
        # ---------------------------------------------------------
        try:
            strat_lower = str(strategy_name or "").lower()
            if "pair" in strat_lower or "arbitrage" in strat_lower:
                from src.services.kalman_pairs_cointegration_service import KalmanPairsCointegrationService
                pairs_svc = KalmanPairsCointegrationService(user_id=self.user_id)
                if await pairs_svc.is_enabled():
                    pair_x = guard_details.get("paired_ticker") or ("SPY" if sym != "SPY" else "QQQ")
                    pairs_metric = await pairs_svc.evaluate_pairs_cointegration(sym, str(pair_x))
                    if pairs_metric.fallback_reason:
                        # Synthetic series: not a measurement. Mark not applicable, never block.
                        # 合成序列：非量測，標記為不適用，不阻擋。
                        guard_details["kalman_pairs"] = {
                            "status": "not_applicable",
                            "fallback_reason": pairs_metric.fallback_reason,
                        }
                        logger.warning(
                            "UnifiedRiskGateway: Kalman pairs not applicable for %s/%s (%s)",
                            sym, pair_x, pairs_metric.fallback_reason,
                        )
                    else:
                        guard_details["kalman_pairs"] = {
                            "regime": pairs_metric.regime,
                            "dynamic_beta": pairs_metric.dynamic_beta,
                            "spread_zscore": pairs_metric.spread_zscore,
                            "ou_half_life_days": pairs_metric.ou_half_life_days,
                            "requires_circuit_breaker": pairs_metric.requires_circuit_breaker,
                        }
                        if pairs_metric.requires_circuit_breaker:
                            reasons.append(
                                f"[KalmanPairs] Structural break stop-loss triggered for pair {sym}/{pair_x} (Z={pairs_metric.spread_zscore:+.2f}σ, t1/2={pairs_metric.ou_half_life_days:.1f}d)"
                            )
                            return RiskGatewayResult(
                                allowed=False,
                                severity=RiskSeverity.BLOCKED,
                                primary_blocker="KalmanPairsStructuralBreak",
                                reasons=reasons,
                                guard_details=guard_details,
                                evaluated_at=now_iso,
                            )
        except Exception as e:
            self._guard_degraded(guard_details, "Kalman pairs", e)

        # ---------------------------------------------------------
        # 10. Trend Hysteresis Band & Macro Long-Only Lock (Phase 63A)
        # ---------------------------------------------------------
        try:
            from src.services.trend_hysteresis_lockout_service import TrendHysteresisLockoutService
            hyst_svc = TrendHysteresisLockoutService(user_id=self.user_id)
            if await hyst_svc.is_enabled():
                allowed_h, block_reason_h, hyst_details = await hyst_svc.evaluate_trade_action(
                    ticker=sym,
                    action=act,
                    strategy_name=strategy_name,
                    current_price=current_price,
                    confidence_score=confidence_score,
                )
                guard_details["trend_hysteresis"] = hyst_details
                is_routine_sell_to_block = (not is_buy) and any(
                    k in str(strategy_name or "").lower() for k in ("routine_rebalance", "routine_sell")
                )
                if not allowed_h and (is_buy or is_routine_sell_to_block):
                    reasons.append(block_reason_h or "[TrendHysteresis] Blocked by hysteresis or trend lock")
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.DEGRADED if is_buy else RiskSeverity.BLOCKED,
                        primary_blocker="TrendHysteresisLockout",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )
        except Exception as e:
            self._guard_degraded(guard_details, "Trend hysteresis", e)

        # ---------------------------------------------------------
        # 11. Turnover Friction Hurdle & Tranche Sizing (Phase 63B)
        # ---------------------------------------------------------
        try:
            from src.services.friction_aware_tranche_sizing_service import FrictionAwareTrancheSizingService
            tranche_svc = FrictionAwareTrancheSizingService(user_id=self.user_id)
            if await tranche_svc.is_enabled():
                f_metric = await tranche_svc.evaluate_order_friction_and_tranche(
                    ticker=sym,
                    action=act,
                    quantity=amount_usd,
                    current_price=current_price,
                    strategy_name=strategy_name,
                )
                guard_details["friction_tranche"] = f_metric.to_dict()
                if not f_metric.passed_hurdle and is_buy:
                    reasons.append(f_metric.reason)
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.DEGRADED,
                        primary_blocker="TurnoverFrictionHurdle",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )
        except Exception as e:
            self._guard_degraded(guard_details, "Turnover friction hurdle", e)

        # ---------------------------------------------------------
        # 12. Cross-Currency FX Dynamic Hedging & Liquidity Buffer (Phase 65)
        # ---------------------------------------------------------
        try:
            from src.services.cross_currency_fx_hedging_service import CrossCurrencyFXHedgingService
            fx_svc = CrossCurrencyFXHedgingService(user_id=self.user_id)
            if await fx_svc.is_enabled():
                fx_decision = await fx_svc.evaluate_order_fx_liquidity(
                    ticker=sym,
                    action=act,
                    order_amount_usd=amount_usd,
                )
                guard_details["fx_liquidity_buffer"] = fx_decision.to_dict()
                if not fx_decision.allowed and is_buy:
                    reasons.append(fx_decision.reason)
                    return RiskGatewayResult(
                        allowed=False,
                        severity=RiskSeverity.BLOCKED,
                        primary_blocker="FXLiquidityBufferDeficit",
                        reasons=reasons,
                        guard_details=guard_details,
                        evaluated_at=now_iso,
                    )
        except Exception as e:
            self._guard_degraded(guard_details, "FX liquidity buffer", e)

        # All guards cleared!
        return RiskGatewayResult(
            allowed=True,
            severity=RiskSeverity.NORMAL,
            primary_blocker=None,
            reasons=[],
            guard_details=guard_details,
            evaluated_at=now_iso,
        )

    def _guard_degraded(self, guard_details: Dict[str, Any], name: str, err: Exception) -> None:
        """A guard crashed. Never swallow quietly: log at WARNING and leave a marker in the result so the
        caller/UI can show that this check did NOT run (the order is evaluated by the remaining guards).
        某個護欄執行失敗：以 WARNING 記錄並在結果中留下標記（表示該項檢查未執行），不再靜默吞掉。"""
        logger.warning("UnifiedRiskGateway: %s check DEGRADED (did not run): %s", name, err)
        guard_details.setdefault("_degraded_guards", []).append({"guard": name, "error": str(err)[:200]})

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
