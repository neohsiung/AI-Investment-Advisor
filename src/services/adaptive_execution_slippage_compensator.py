"""
Adaptive Execution Slippage Compensator & Feedback Loop Service (P6)
自適應訂單執行滑價補償與成交回報反饋環
=============================================================================
Provides a real-time closed-loop feedback mechanism between empirical execution
fills and forward-looking algorithmic order routing (E1), non-linear opportunity
cost evaluation (M3), and shadow asset promotion (P5).

Key Capabilities:
1. Realized vs. Expected Slippage Ingestion & Tracking:
   - Compares observed execution slippage against pre-trade model-predicted slippage (Almgren-Chriss Square-Root Law).
   - Computes statistical deviations and EWMA-filtered slippage compensation multipliers (M_slip).
2. Dynamic Parameter Adaptation for SOR (E1):
   - High slippage regime (M_slip > 1.25): scales up slice counts, extends execution windows,
     and tightens dynamic circuit breaker limit buffers to reduce market footprint.
   - Low slippage regime (M_slip < 0.80): relaxes execution constraints to minimize opportunity cost.
3. Opportunity Cost Dynamic Calibration for M3 / P5:
   - Injects calibrated asset-level two-way execution frictions into OpportunityCostService.
   - Raises rotation hurdles when targets face high slippage, suppressing churn into illiquid traps.
4. Adverse Selection Safety Penalty:
   - Dynamically adds a safety penalty buffer when recent fills show toxic order flow or 3-sigma outliers.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.config.owner import resolve_user_id
from src.services.order_execution_feedback_service import (
    ExecutionFill,
    ExecutionVenue,
    OrderAction,
    OrderExecutionFeedbackService,
)

logger = logging.getLogger(__name__)


@dataclass
class SlippageCompensationMetrics:
    """Asset-level calibrated slippage metrics and compensation state."""
    symbol: str
    realized_slippage_bps_mean: float
    expected_slippage_bps_mean: float
    slippage_multiplier: float  # M_slip (e.g. 1.20 = 20% higher than model expected)
    adverse_selection_count: int
    adverse_penalty_bps: float
    calibrated_effective_slippage_bps: float
    calibrated_effective_slippage_pct: float
    sample_count: int
    last_updated: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "realized_slippage_bps_mean": round(self.realized_slippage_bps_mean, 2),
            "expected_slippage_bps_mean": round(self.expected_slippage_bps_mean, 2),
            "slippage_multiplier": round(self.slippage_multiplier, 4),
            "adverse_selection_count": self.adverse_selection_count,
            "adverse_penalty_bps": round(self.adverse_penalty_bps, 2),
            "calibrated_effective_slippage_bps": round(self.calibrated_effective_slippage_bps, 2),
            "calibrated_effective_slippage_pct": round(self.calibrated_effective_slippage_pct, 6),
            "sample_count": self.sample_count,
            "last_updated": self.last_updated,
        }


@dataclass
class SORAdaptationParameters:
    """Dynamic tuning parameters recommended for Smart Order Routing (E1)."""
    symbol: str
    recommended_slices: int
    recommended_window_minutes: int
    recommended_max_slippage_bps: float
    recommended_jitter_pct: float
    slippage_multiplier: float
    effective_slippage_bps: float
    strategy_hint: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "recommended_slices": self.recommended_slices,
            "recommended_window_minutes": self.recommended_window_minutes,
            "recommended_max_slippage_bps": round(self.recommended_max_slippage_bps, 2),
            "recommended_jitter_pct": round(self.recommended_jitter_pct, 4),
            "slippage_multiplier": round(self.slippage_multiplier, 4),
            "effective_slippage_bps": round(self.effective_slippage_bps, 2),
            "strategy_hint": self.strategy_hint,
            "reason": self.reason,
        }


@dataclass
class RoundtripFrictionAssessment:
    """Two-way calibrated execution friction assessment for Opportunity Cost (M3)."""
    sell_ticker: str
    buy_ticker: str
    sell_slippage_pct: float
    buy_slippage_pct: float
    sell_fee_pct: float
    buy_fee_pct: float
    total_roundtrip_friction: float
    friction_multiplier: float
    hurdle_rate: float
    calibrated_hurdle: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sell_ticker": self.sell_ticker,
            "buy_ticker": self.buy_ticker,
            "sell_slippage_pct": round(self.sell_slippage_pct, 6),
            "buy_slippage_pct": round(self.buy_slippage_pct, 6),
            "sell_fee_pct": round(self.sell_fee_pct, 6),
            "buy_fee_pct": round(self.buy_fee_pct, 6),
            "total_roundtrip_friction": round(self.total_roundtrip_friction, 6),
            "friction_multiplier": round(self.friction_multiplier, 2),
            "hurdle_rate": round(self.hurdle_rate, 4),
            "calibrated_hurdle": round(self.calibrated_hurdle, 6),
        }


class AdaptiveExecutionSlippageCompensator:
    """
    Real-Time Execution Slippage Compensator & Feedback Orchestrator.
    """

    DEFAULT_EWMA_ALPHA = 0.20
    DEFAULT_MIN_MULTIPLIER = 0.50
    DEFAULT_MAX_MULTIPLIER = 3.00
    DEFAULT_ADVERSE_PENALTY_BPS = 5.00
    DEFAULT_BASELINE_SLIPPAGE_BPS = 10.00

    def __init__(
        self,
        user_id: str = "default_user",
        settings_repo: Any = None,
        feedback_service: Optional[OrderExecutionFeedbackService] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo
        self.feedback_service = feedback_service or OrderExecutionFeedbackService(
            user_id=self.user_id,
            settings_repo=settings_repo,
        )

        # Internal state tracking per asset
        self._metrics_map: Dict[str, SlippageCompensationMetrics] = {}
        self._recent_fills_per_symbol: Dict[str, List[ExecutionFill]] = {}
        self._expected_vs_realized_history: Dict[str, List[tuple[float, float]]] = {}

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
        """Helper to retrieve dynamic setting with fallback."""
        if not self.settings_repo:
            return default
        try:
            val = self.settings_repo.get(self.user_id, key)
            if val is None:
                return default
            if val_type is bool:
                return str(val).lower() in ("true", "1", "yes")
            return val_type(val)
        except Exception as e:
            logger.warning(f"Error loading setting '{key}' ({e}); using default {default}")
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting("slippage_compensator_enabled", True, bool)

    @property
    def ewma_alpha(self) -> float:
        return float(self._get_setting("slippage_ewma_alpha", self.DEFAULT_EWMA_ALPHA, float))

    @property
    def min_multiplier(self) -> float:
        return float(self._get_setting("slippage_min_multiplier", self.DEFAULT_MIN_MULTIPLIER, float))

    @property
    def max_multiplier(self) -> float:
        return float(self._get_setting("slippage_max_multiplier", self.DEFAULT_MAX_MULTIPLIER, float))

    @property
    def adverse_penalty_bps(self) -> float:
        return float(self._get_setting("slippage_adverse_penalty_bps", self.DEFAULT_ADVERSE_PENALTY_BPS, float))

    @property
    def baseline_slippage_bps(self) -> float:
        return float(self._get_setting("slippage_baseline_bps", self.DEFAULT_BASELINE_SLIPPAGE_BPS, float))

    def estimate_expected_slippage(
        self,
        symbol: str,
        order_quantity: float,
        adv_20: float,
    ) -> float:
        """
        Estimate model baseline expected slippage (bps) via Almgren-Chriss Square-Root law.
        Delegates to feedback_service.
        """
        return self.feedback_service.estimate_expected_slippage(
            symbol=symbol,
            order_quantity=order_quantity,
            adv_20=adv_20,
        )

    def record_fill(
        self,
        order_id: str,
        symbol: str,
        action: str | OrderAction,
        venue: str | ExecutionVenue,
        fill_price: float,
        fill_quantity: float,
        arrival_price: float,
        parent_plan_id: Optional[str] = None,
        market_price_at_fill: Optional[float] = None,
        fee_usd: float = 0.0,
        executed_at: Optional[str] = None,
        adv_20: Optional[float] = None,
    ) -> ExecutionFill:
        """
        Record fill execution, compute slippage deviation ratio, and update EWMA compensation metrics.
        """
        sym = symbol.upper().strip()
        p_arr = max(0.0001, float(arrival_price))
        qty = abs(float(fill_quantity))
        adv = max(1.0, float(adv_20 or 100000.0))

        # 1. Pre-trade expected slippage from current model
        expected_bps = self.estimate_expected_slippage(sym, qty, adv)
        expected_bps = max(0.5, expected_bps)

        # 2. Ingest into feedback service (records fill, calculates realized slippage & adverse anomalies)
        fill = self.feedback_service.record_fill(
            order_id=order_id,
            symbol=sym,
            action=action,
            venue=venue,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            arrival_price=p_arr,
            parent_plan_id=parent_plan_id,
            market_price_at_fill=market_price_at_fill,
            fee_usd=fee_usd,
            executed_at=executed_at,
            adv_20=adv,
        )

        realized_bps = max(0.0, float(fill.realized_slippage_bps))

        # 3. Update deviation history
        sym_history = self._expected_vs_realized_history.setdefault(sym, [])
        sym_history.append((expected_bps, realized_bps))
        if len(sym_history) > 100:
            sym_history.pop(0)

        recent_fills = self._recent_fills_per_symbol.setdefault(sym, [])
        recent_fills.append(fill)
        if len(recent_fills) > 50:
            recent_fills.pop(0)

        # 4. Calibrate EWMA Slippage Multiplier
        self._update_asset_metrics(sym, expected_bps, realized_bps, fill.is_anomaly)

        return fill

    def _update_asset_metrics(
        self,
        symbol: str,
        current_expected_bps: float,
        current_realized_bps: float,
        is_anomaly: bool,
    ) -> SlippageCompensationMetrics:
        """Recalculate EWMA compensation multiplier and effective slippage for an asset."""
        sym = symbol.upper()
        alpha = self.ewma_alpha
        min_mult = self.min_multiplier
        max_mult = self.max_multiplier

        # Observed ratio for this execution (with floor at 0.5 bps to prevent div-by-zero or extreme spikes)
        observed_ratio = max(0.5, current_realized_bps) / max(0.5, current_expected_bps)

        existing = self._metrics_map.get(sym)
        if existing is None:
            new_multiplier = max(min_mult, min(max_mult, observed_ratio))
            sample_cnt = 1
            mean_realized = current_realized_bps
            mean_expected = current_expected_bps
            adverse_cnt = 1 if is_anomaly else 0
        else:
            old_mult = existing.slippage_multiplier
            raw_mult = (1.0 - alpha) * old_mult + alpha * observed_ratio
            new_multiplier = max(min_mult, min(max_mult, raw_mult))
            sample_cnt = existing.sample_count + 1
            mean_realized = (existing.realized_slippage_bps_mean * existing.sample_count + current_realized_bps) / sample_cnt
            mean_expected = (existing.expected_slippage_bps_mean * existing.sample_count + current_expected_bps) / sample_cnt
            adverse_cnt = existing.adverse_selection_count + (1 if is_anomaly else 0)

        # Compute adverse selection penalty (if any anomalies in recent 5 fills)
        recent = self._recent_fills_per_symbol.get(sym, [])
        recent_window = recent[-5:] if recent else []
        has_recent_anomaly = any(f.is_anomaly for f in recent_window) or is_anomaly
        penalty_bps = self.adverse_penalty_bps if has_recent_anomaly else 0.0

        # Effective calibrated slippage (bps)
        base_expected = mean_expected if mean_expected > 0.0 else self.baseline_slippage_bps
        effective_bps = max(1.0, (base_expected * new_multiplier) + penalty_bps)
        effective_pct = effective_bps / 10000.0

        metrics = SlippageCompensationMetrics(
            symbol=sym,
            realized_slippage_bps_mean=mean_realized,
            expected_slippage_bps_mean=mean_expected,
            slippage_multiplier=new_multiplier,
            adverse_selection_count=adverse_cnt,
            adverse_penalty_bps=penalty_bps,
            calibrated_effective_slippage_bps=effective_bps,
            calibrated_effective_slippage_pct=effective_pct,
            sample_count=sample_cnt,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        self._metrics_map[sym] = metrics
        return metrics

    def get_metrics(self, symbol: str) -> SlippageCompensationMetrics:
        """Retrieve current calibrated compensation metrics for an asset."""
        sym = symbol.upper().strip()
        if sym in self._metrics_map:
            return self._metrics_map[sym]

        # Return default initialized metrics
        default_bps = self.baseline_slippage_bps
        return SlippageCompensationMetrics(
            symbol=sym,
            realized_slippage_bps_mean=default_bps,
            expected_slippage_bps_mean=default_bps,
            slippage_multiplier=1.0,
            adverse_selection_count=0,
            adverse_penalty_bps=0.0,
            calibrated_effective_slippage_bps=default_bps,
            calibrated_effective_slippage_pct=default_bps / 10000.0,
            sample_count=0,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    def get_all_metrics(self) -> Dict[str, SlippageCompensationMetrics]:
        """Retrieve all asset calibrated metrics."""
        return dict(self._metrics_map)

    def estimate_calibrated_slippage_pct(
        self,
        symbol: str,
        order_quantity: Optional[float] = None,
        adv_20: Optional[float] = None,
    ) -> float:
        """
        Get the calibrated expected slippage in percentage (decimal) for an asset.
        Used by OpportunityCostService and ShadowPromotionOrchestrator.
        """
        sym = symbol.upper().strip()
        if not self.is_enabled:
            return self.baseline_slippage_bps / 10000.0

        metrics = self.get_metrics(sym)
        if order_quantity is not None and adv_20 is not None and adv_20 > 0:
            # Scale dynamically with current order size
            raw_expected = self.estimate_expected_slippage(sym, order_quantity, adv_20)
            calibrated_bps = max(1.0, (raw_expected * metrics.slippage_multiplier) + metrics.adverse_penalty_bps)
            return round(calibrated_bps / 10000.0, 6)

        return round(metrics.calibrated_effective_slippage_pct, 6)

    def get_sor_adaptation_parameters(
        self,
        symbol: str,
        base_slices: int = 5,
        base_window_minutes: int = 30,
        base_max_slippage_bps: float = 35.0,
        base_jitter_pct: float = 0.15,
        order_quantity: Optional[float] = None,
        adv_20: Optional[float] = None,
    ) -> SORAdaptationParameters:
        """
        Generate adaptive slicing parameters for E1 Smart Order Routing.
        Modulates slice counts, execution window, jitter, and safety limits.
        """
        sym = symbol.upper().strip()
        metrics = self.get_metrics(sym)
        mult = metrics.slippage_multiplier if self.is_enabled else 1.0
        eff_bps = metrics.calibrated_effective_slippage_bps if self.is_enabled else base_max_slippage_bps

        if not self.is_enabled:
            return SORAdaptationParameters(
                symbol=sym,
                recommended_slices=base_slices,
                recommended_window_minutes=base_window_minutes,
                recommended_max_slippage_bps=base_max_slippage_bps,
                recommended_jitter_pct=base_jitter_pct,
                slippage_multiplier=1.0,
                effective_slippage_bps=eff_bps,
                strategy_hint="STANDARD_TWAP",
                reason="Slippage compensator is disabled; using baseline parameters.",
            )

        # 1. Slice Scaling: If slippage is higher than model (mult > 1.25), slice finer to reduce footprint
        if mult >= 1.25 or metrics.adverse_penalty_bps > 0:
            slice_scale = min(2.0, max(1.2, mult))
            recommended_slices = min(24, max(base_slices + 2, int(round(base_slices * slice_scale))))
            # Extend time window to lower participation rate
            window_scale = min(2.5, 1.0 + (mult - 1.0) * 0.8)
            recommended_window = min(240, max(base_window_minutes, int(round(base_window_minutes * window_scale))))
            # Tighten or adjust max slippage tolerance
            # In high adverse selection, increase random jitter to evade predatory algorithms
            recommended_jitter = min(0.35, round(base_jitter_pct * 1.3, 4))
            # Adaptive circuit breaker: scale slightly with sqrt of mult to avoid premature tripping while guarding tail risk
            rec_circuit_breaker = min(100.0, max(15.0, round(base_max_slippage_bps * math.sqrt(mult), 2)))
            hint = "AGGRESSIVE_SLICING"
            reason = (
                f"Elevated realized slippage (M_slip={mult:.2f}, penalty={metrics.adverse_penalty_bps:.1f} bps); "
                f"fine-sliced to {recommended_slices} chunks across {recommended_window} mins to mitigate market impact."
            )
        elif mult <= 0.80:
            # Low slippage regime: high liquidity allows streamlined execution
            recommended_slices = max(2, min(base_slices, int(round(base_slices * 0.8))))
            recommended_window = max(10, min(base_window_minutes, int(round(base_window_minutes * 0.8))))
            recommended_jitter = base_jitter_pct
            rec_circuit_breaker = max(15.0, round(base_max_slippage_bps * 0.9, 2))
            hint = "STREAMLINED_EXECUTION"
            reason = (
                f"Favorable execution liquidity (M_slip={mult:.2f}); "
                f"condensed schedule into {recommended_slices} slices ({recommended_window} mins) to minimize delay risk."
            )
        else:
            # Neutral / standard regime
            recommended_slices = base_slices
            recommended_window = base_window_minutes
            recommended_jitter = base_jitter_pct
            rec_circuit_breaker = base_max_slippage_bps
            hint = "STANDARD_TWAP"
            reason = f"Normal execution conditions (M_slip={mult:.2f}); baseline slicing maintained."

        return SORAdaptationParameters(
            symbol=sym,
            recommended_slices=recommended_slices,
            recommended_window_minutes=recommended_window,
            recommended_max_slippage_bps=rec_circuit_breaker,
            recommended_jitter_pct=recommended_jitter,
            slippage_multiplier=mult,
            effective_slippage_bps=eff_bps,
            strategy_hint=hint,
            reason=reason,
        )

    def get_calibrated_roundtrip_friction(
        self,
        sell_ticker: str,
        buy_ticker: str,
        sell_fee_pct: float = 0.0005,
        buy_fee_pct: float = 0.0005,
        friction_multiplier: float = 2.5,
        hurdle_rate: float = 0.010,
    ) -> RoundtripFrictionAssessment:
        """
        Calculate empirically calibrated two-way friction for M3 OpportunityCostService.
        """
        s_sym = sell_ticker.upper().strip()
        b_sym = buy_ticker.upper().strip()

        slip_s = self.estimate_calibrated_slippage_pct(s_sym)
        slip_b = self.estimate_calibrated_slippage_pct(b_sym)

        # Two-way roundtrip friction: selling leg (slip + fee) + buying leg (slip + fee)
        total_friction = (slip_s + sell_fee_pct) + (slip_b + buy_fee_pct)

        calibrated_hurdle = (friction_multiplier * total_friction) + hurdle_rate

        return RoundtripFrictionAssessment(
            sell_ticker=s_sym,
            buy_ticker=b_sym,
            sell_slippage_pct=slip_s,
            buy_slippage_pct=slip_b,
            sell_fee_pct=sell_fee_pct,
            buy_fee_pct=buy_fee_pct,
            total_roundtrip_friction=total_friction,
            friction_multiplier=friction_multiplier,
            hurdle_rate=hurdle_rate,
            calibrated_hurdle=calibrated_hurdle,
        )

    def clear_metrics(self) -> None:
        """Clear all metrics and history (for testing)."""
        self._metrics_map.clear()
        self._recent_fills_per_symbol.clear()
        self._expected_vs_realized_history.clear()
        if hasattr(self.feedback_service, "clear_buffers"):
            self.feedback_service.clear_buffers()
