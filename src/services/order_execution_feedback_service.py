"""
Order Execution Feedback & Real-Time Slippage Analytics Service (E2)
即時訂單執行監控與成交回報反饋服務
=============================================================================
Provides closed-loop post-trade execution intelligence, Perold Implementation
Shortfall (IS) attribution decomposition, dynamic Almgren-Chriss (2000) market
impact parameter calibration, and execution venue quality scoring.

Key Architecture:
1. Execution Fill Recording & Slippage Tracking:
   - Records granular child/parent execution fills across venues (IBKR, eToro, Paper).
   - Computes realized execution slippage in basis points relative to arrival price.
   - Evaluates adverse selection and market maker toxic order flow anomalies.
2. Perold Implementation Shortfall (IS) 4-Part Decomposition:
   - Decomposes total trading friction into Delay Cost, Market Impact, Timing Drift,
     Explicit Fees, and Unfilled Opportunity Cost.
3. Closed-Loop Almgren-Chriss Impact Parameter Calibration (η):
   - Ingests empirical fill samples and continuously recalibrates market impact
     coefficient η (eta) via Square-Root Law and EWMA filtering.
   - Dynamically feeds back calibrated η to E1 Smart Order Routing to adaptively
     scale execution time windows and limit price safety buffers.
4. Execution Venue Quality & Benchmark Scoring:
   - Aggregates fill rates, mean slippage, slippage volatility, and fee drag across
     venues to produce a comprehensive 0-100 Execution Quality Index.
"""
from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class ExecutionVenue(str, Enum):
    """Trading venue or broker backend."""
    IBKR = "IBKR"
    ETORO = "ETORO"
    PAPER = "PAPER"
    BINANCE = "BINANCE"
    TWSE = "TWSE"
    MOCK = "MOCK"


class OrderAction(str, Enum):
    """Order transaction direction."""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class ExecutionFill:
    """Individual execution fill record."""
    fill_id: str
    order_id: str
    symbol: str
    action: OrderAction
    venue: str
    fill_price: float
    fill_quantity: float
    arrival_price: float
    parent_plan_id: Optional[str] = None
    market_price_at_fill: Optional[float] = None
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fee_usd: float = 0.0
    realized_slippage_bps: float = 0.0
    market_impact_bps: Optional[float] = None
    is_anomaly: bool = False
    anomaly_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "parent_plan_id": self.parent_plan_id,
            "symbol": self.symbol,
            "action": self.action.value if isinstance(self.action, OrderAction) else str(self.action),
            "venue": self.venue,
            "fill_price": round(self.fill_price, 4),
            "fill_quantity": round(self.fill_quantity, 4),
            "arrival_price": round(self.arrival_price, 4),
            "market_price_at_fill": round(self.market_price_at_fill, 4) if self.market_price_at_fill is not None else None,
            "executed_at": self.executed_at,
            "fee_usd": round(self.fee_usd, 4),
            "realized_slippage_bps": round(self.realized_slippage_bps, 2),
            "market_impact_bps": round(self.market_impact_bps, 2) if self.market_impact_bps is not None else None,
            "is_anomaly": self.is_anomaly,
            "anomaly_reason": self.anomaly_reason,
        }


@dataclass
class ImplementationShortfallDecomposition:
    """Perold (1988) Implementation Shortfall multi-part cost breakdown."""
    delay_cost_bps: float = 0.0
    market_impact_bps: float = 0.0
    timing_drift_bps: float = 0.0
    fee_cost_bps: float = 0.0
    unfilled_opportunity_cost_bps: float = 0.0
    total_shortfall_bps: float = 0.0
    total_shortfall_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "delay_cost_bps": round(self.delay_cost_bps, 2),
            "market_impact_bps": round(self.market_impact_bps, 2),
            "timing_drift_bps": round(self.timing_drift_bps, 2),
            "fee_cost_bps": round(self.fee_cost_bps, 2),
            "unfilled_opportunity_cost_bps": round(self.unfilled_opportunity_cost_bps, 2),
            "total_shortfall_bps": round(self.total_shortfall_bps, 2),
            "total_shortfall_usd": round(self.total_shortfall_usd, 2),
        }


@dataclass
class PlanExecutionReport:
    """Post-trade execution report for an algorithmic order plan (E1/SOR)."""
    plan_id: str
    symbol: str
    action: OrderAction
    venue: str
    total_ordered_shares: float
    total_filled_shares: float
    fill_rate_pct: float
    arrival_price: float
    vwap_executed_price: float
    total_fees_usd: float
    realized_slippage_bps: float
    shortfall_decomposition: ImplementationShortfallDecomposition
    num_fills: int
    fills: list[ExecutionFill] = field(default_factory=list)
    execution_efficiency: float = 1.0
    adverse_selection_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "symbol": self.symbol,
            "action": self.action.value if isinstance(self.action, OrderAction) else str(self.action),
            "venue": self.venue,
            "total_ordered_shares": round(self.total_ordered_shares, 4),
            "total_filled_shares": round(self.total_filled_shares, 4),
            "fill_rate_pct": round(self.fill_rate_pct, 2),
            "arrival_price": round(self.arrival_price, 4),
            "vwap_executed_price": round(self.vwap_executed_price, 4),
            "total_fees_usd": round(self.total_fees_usd, 4),
            "realized_slippage_bps": round(self.realized_slippage_bps, 2),
            "shortfall_decomposition": self.shortfall_decomposition.to_dict(),
            "num_fills": self.num_fills,
            "fills": [f.to_dict() for f in self.fills],
            "execution_efficiency": round(self.execution_efficiency, 4),
            "adverse_selection_detected": self.adverse_selection_detected,
        }


@dataclass
class VenueQualityMetrics:
    """Execution performance benchmark for a broker or venue."""
    venue: str
    total_orders: int
    total_volume_usd: float
    avg_fill_rate: float
    avg_slippage_bps: float
    slippage_std_bps: float
    p95_slippage_bps: float
    avg_fee_bps: float
    quality_score: float  # 0.0 to 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "total_orders": self.total_orders,
            "total_volume_usd": round(self.total_volume_usd, 2),
            "avg_fill_rate": round(self.avg_fill_rate, 4),
            "avg_slippage_bps": round(self.avg_slippage_bps, 2),
            "slippage_std_bps": round(self.slippage_std_bps, 2),
            "p95_slippage_bps": round(self.p95_slippage_bps, 2),
            "avg_fee_bps": round(self.avg_fee_bps, 2),
            "quality_score": round(self.quality_score, 1),
        }


@dataclass
class AlmgrenChrissImpactState:
    """Dynamically calibrated market impact state for a specific asset."""
    symbol: str
    calibrated_eta: float
    sample_count: int
    last_updated: str
    baseline_eta: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "calibrated_eta": round(self.calibrated_eta, 4),
            "sample_count": self.sample_count,
            "last_updated": self.last_updated,
            "baseline_eta": round(self.baseline_eta, 4),
        }


class OrderExecutionFeedbackService:
    """
    Execution Feedback & Real-Time Slippage Analytics Engine (E2).
    """

    DEFAULT_SLIPPAGE_ALERT_THRESHOLD_BPS = 25.0
    DEFAULT_ALMGREN_CHRISS_ETA = 0.15
    DEFAULT_EWMA_DECAY = 0.15
    MIN_ETA = 0.01
    MAX_ETA = 2.50

    def __init__(self, user_id: str = "default_user", settings_repo: Any = None):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo

        # In-memory storage buffers
        self._fills_buffer: list[ExecutionFill] = []
        self._plan_reports: dict[str, PlanExecutionReport] = {}
        self._impact_states: dict[str, AlmgrenChrissImpactState] = {}
        self._symbol_slippage_history: dict[str, list[float]] = {}

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
        return self._get_setting("execution_feedback_enabled", True, bool)

    @property
    def slippage_alert_threshold_bps(self) -> float:
        return float(self._get_setting("execution_slippage_alert_threshold_bps", self.DEFAULT_SLIPPAGE_ALERT_THRESHOLD_BPS, float))

    @property
    def default_eta(self) -> float:
        return float(self._get_setting("almgren_chriss_eta_default", self.DEFAULT_ALMGREN_CHRISS_ETA, float))

    @property
    def dynamic_calibration_enabled(self) -> bool:
        return self._get_setting("execution_dynamic_eta_calibration", True, bool)

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
        Record a trade fill, calculate realized slippage and market impact,
        check for adverse selection anomalies, and calibrate Almgren-Chriss eta.
        """
        sym = symbol.upper()
        act_val = getattr(action, "value", str(action)).upper()
        act = OrderAction(act_val)
        ven = getattr(venue, "value", str(venue)).upper()

        p_fill = max(0.00001, float(fill_price))
        p_arr = max(0.00001, float(arrival_price))
        qty = abs(float(fill_quantity))
        fee = max(0.0, float(fee_usd))
        timestamp = executed_at or datetime.now(timezone.utc).isoformat()

        # 1. Realized Slippage Calculation (bps)
        # For BUY: higher fill price is adverse (positive slippage)
        # For SELL: lower fill price is adverse (positive slippage)
        if act == OrderAction.BUY:
            slippage_bps = round(((p_fill - p_arr) / p_arr) * 10000.0, 4)
        else:
            slippage_bps = round(((p_arr - p_fill) / p_arr) * 10000.0, 4)

        # 2. Market Impact Bps (if contemporaneous market price provided)
        impact_bps: Optional[float] = None
        if market_price_at_fill is not None:
            p_mkt = max(0.00001, float(market_price_at_fill))
            if act == OrderAction.BUY:
                impact_bps = round(((p_mkt - p_arr) / p_arr) * 10000.0, 4)
            else:
                impact_bps = round(((p_arr - p_mkt) / p_arr) * 10000.0, 4)

        # 3. Adverse Selection / Toxic Flow Anomaly Detection
        is_anomaly = False
        anomaly_reason: Optional[str] = None
        threshold_bps = self.slippage_alert_threshold_bps

        history = self._symbol_slippage_history.setdefault(sym, [])
        if slippage_bps > threshold_bps:
            is_anomaly = True
            anomaly_reason = (
                f"Slippage {slippage_bps:.1f} bps exceeded static tolerance threshold {threshold_bps:.1f} bps"
            )
        elif len(history) >= 5:
            # Statistical 3-sigma outlier check
            mean_slip = sum(history) / len(history)
            variance = sum((x - mean_slip) ** 2 for x in history) / len(history)
            std_slip = math.sqrt(variance)
            if slippage_bps > (mean_slip + 3.0 * max(2.0, std_slip)):
                is_anomaly = True
                anomaly_reason = (
                    f"Slippage {slippage_bps:.1f} bps exceeded 3-sigma statistical threshold "
                    f"({mean_slip + 3.0 * std_slip:.1f} bps)"
                )

        if is_anomaly:
            logger.warning(
                f"🚨 ADVERSE SELECTION DETECTED on {sym} ({ven}): {anomaly_reason} "
                f"[Arrival: {p_arr:.2f}, Fill: {p_fill:.2f}]"
            )

        fill_record = ExecutionFill(
            fill_id=str(uuid.uuid4()),
            order_id=order_id,
            parent_plan_id=parent_plan_id,
            symbol=sym,
            action=act,
            venue=ven,
            fill_price=p_fill,
            fill_quantity=qty,
            arrival_price=p_arr,
            market_price_at_fill=market_price_at_fill,
            executed_at=timestamp,
            fee_usd=fee,
            realized_slippage_bps=slippage_bps,
            market_impact_bps=impact_bps,
            is_anomaly=is_anomaly,
            anomaly_reason=anomaly_reason,
        )

        # Store in buffers
        self._fills_buffer.append(fill_record)
        history.append(slippage_bps)
        if len(history) > 200:
            history.pop(0)

        # 4. Almgren-Chriss Dynamic η Calibration
        if self.dynamic_calibration_enabled and adv_20 is not None and adv_20 > 0:
            self.calibrate_almgren_chriss_eta(
                symbol=sym,
                order_quantity=qty,
                adv_20=adv_20,
                realized_slippage_bps=slippage_bps,
            )

        return fill_record

    def record_plan_fills(
        self,
        plan_id: str,
        symbol: str,
        action: str | OrderAction,
        total_ordered_shares: float,
        arrival_price: float,
        fills: list[ExecutionFill],
        venue: str = "COMPOSITE",
        initial_quote_price: Optional[float] = None,
        final_market_price: Optional[float] = None,
    ) -> PlanExecutionReport:
        """
        Aggregate multi-slice fills from an algorithmic execution plan (E1 SOR),
        calculate VWAP, and perform Perold Implementation Shortfall (IS) 4-part decomposition.
        """
        sym = symbol.upper()
        act_val = getattr(action, "value", str(action)).upper()
        act = OrderAction(act_val)
        tot_ordered = max(0.0001, float(total_ordered_shares))
        p_arr = max(0.0001, float(arrival_price))

        if not fills:
            # Completely unfilled plan
            p_final = final_market_price or p_arr
            if act == OrderAction.BUY:
                unfilled_bps = ((p_final - p_arr) / p_arr) * 10000.0
            else:
                unfilled_bps = ((p_arr - p_final) / p_arr) * 10000.0

            shortfall_usd = abs(p_final - p_arr) * tot_ordered if act == OrderAction.BUY else (p_arr - p_final) * tot_ordered
            decomp = ImplementationShortfallDecomposition(
                unfilled_opportunity_cost_bps=unfilled_bps,
                total_shortfall_bps=unfilled_bps,
                total_shortfall_usd=shortfall_usd,
            )
            report = PlanExecutionReport(
                plan_id=plan_id,
                symbol=sym,
                action=act,
                venue=venue,
                total_ordered_shares=tot_ordered,
                total_filled_shares=0.0,
                fill_rate_pct=0.0,
                arrival_price=p_arr,
                vwap_executed_price=p_arr,
                total_fees_usd=0.0,
                realized_slippage_bps=0.0,
                shortfall_decomposition=decomp,
                num_fills=0,
                fills=[],
                execution_efficiency=0.0,
                adverse_selection_detected=False,
            )
            self._plan_reports[plan_id] = report
            return report

        total_filled_shares = sum(f.fill_quantity for f in fills)
        total_fees = sum(f.fee_usd for f in fills)
        total_traded_val = sum(f.fill_quantity * f.fill_price for f in fills)
        vwap_price = total_traded_val / total_filled_shares if total_filled_shares > 0 else p_arr
        fill_rate_pct = min(100.0, (total_filled_shares / tot_ordered) * 100.0)

        # Realized overall slippage (bps)
        if act == OrderAction.BUY:
            cum_slippage_bps = ((vwap_price - p_arr) / p_arr) * 10000.0
        else:
            cum_slippage_bps = ((p_arr - vwap_price) / p_arr) * 10000.0

        # --- Perold Implementation Shortfall (IS) 4-part Decomposition ---
        # 1. Delay Cost: Price movement between decision arrival and first fill/order submission
        first_fill_price = initial_quote_price or fills[0].fill_price
        if act == OrderAction.BUY:
            delay_cost_bps = ((first_fill_price - p_arr) / p_arr) * 10000.0
        else:
            delay_cost_bps = ((p_arr - first_fill_price) / p_arr) * 10000.0
        delay_cost_bps = max(-50.0, min(100.0, delay_cost_bps))

        # 2. Market Impact Cost: Slippage from first quote to executed VWAP
        if act == OrderAction.BUY:
            impact_cost_bps = ((vwap_price - first_fill_price) / p_arr) * 10000.0
        else:
            impact_cost_bps = ((first_fill_price - vwap_price) / p_arr) * 10000.0

        # 3. Explicit Fee Cost (bps)
        fee_cost_bps = (total_fees / total_traded_val * 10000.0) if total_traded_val > 0 else 0.0

        # 4. Unfilled Opportunity Cost: Friction on unexecuted shares relative to final market price
        unfilled_shares = max(0.0, tot_ordered - total_filled_shares)
        unfilled_opportunity_bps = 0.0
        unfilled_usd = 0.0
        if unfilled_shares > 0 and final_market_price is not None:
            if act == OrderAction.BUY:
                unfilled_opportunity_bps = ((final_market_price - p_arr) / p_arr) * (unfilled_shares / tot_ordered) * 10000.0
                unfilled_usd = (final_market_price - p_arr) * unfilled_shares
            else:
                unfilled_opportunity_bps = ((p_arr - final_market_price) / p_arr) * (unfilled_shares / tot_ordered) * 10000.0
                unfilled_usd = (p_arr - final_market_price) * unfilled_shares

        # Timing Drift / Residual Volatility
        timing_drift_bps = cum_slippage_bps - (delay_cost_bps + impact_cost_bps)

        # Total Implementation Shortfall
        total_is_bps = cum_slippage_bps * (total_filled_shares / tot_ordered) + fee_cost_bps + unfilled_opportunity_bps
        if act == OrderAction.BUY:
            executed_shortfall_usd = (vwap_price - p_arr) * total_filled_shares + total_fees
        else:
            executed_shortfall_usd = (p_arr - vwap_price) * total_filled_shares + total_fees
        total_is_usd = executed_shortfall_usd + unfilled_usd

        decomp = ImplementationShortfallDecomposition(
            delay_cost_bps=round(delay_cost_bps, 2),
            market_impact_bps=round(impact_cost_bps, 2),
            timing_drift_bps=round(timing_drift_bps, 2),
            fee_cost_bps=round(fee_cost_bps, 2),
            unfilled_opportunity_cost_bps=round(unfilled_opportunity_bps, 2),
            total_shortfall_bps=round(total_is_bps, 2),
            total_shortfall_usd=round(total_is_usd, 2),
        )

        # Execution efficiency: starts at 1.0, penalized by slippage bps
        eff = max(0.0, min(1.0, 1.0 - (max(0.0, cum_slippage_bps) / 100.0)))

        any_adverse = any(f.is_anomaly for f in fills)

        report = PlanExecutionReport(
            plan_id=plan_id,
            symbol=sym,
            action=act,
            venue=venue,
            total_ordered_shares=tot_ordered,
            total_filled_shares=round(total_filled_shares, 4),
            fill_rate_pct=round(fill_rate_pct, 2),
            arrival_price=p_arr,
            vwap_executed_price=round(vwap_price, 4),
            total_fees_usd=round(total_fees, 4),
            realized_slippage_bps=round(cum_slippage_bps, 2),
            shortfall_decomposition=decomp,
            num_fills=len(fills),
            fills=fills,
            execution_efficiency=round(eff, 4),
            adverse_selection_detected=any_adverse,
        )

        self._plan_reports[plan_id] = report
        return report

    def calibrate_almgren_chriss_eta(
        self,
        symbol: str,
        order_quantity: float,
        adv_20: float,
        realized_slippage_bps: float,
        decay_rate: Optional[float] = None,
    ) -> float:
        """
        Dynamically calibrate Almgren-Chriss (2000) temporary market impact coefficient η.
        Formula:
            Participation Rate P_R = V / ADV_20
            Expected Slippage (bps) = η * sqrt(P_R) * 10,000
            Observed η = (realized_slippage_bps / 10,000) / sqrt(P_R)
            η_new = (1 - λ) * η_old + λ * Observed η
        """
        sym = symbol.upper()
        lam = decay_rate or self.DEFAULT_EWMA_DECAY
        adv = max(1.0, float(adv_20))
        qty = max(0.0001, float(order_quantity))

        # Square root participation rate
        p_rate = max(0.00001, qty / adv)
        sqrt_p = math.sqrt(p_rate)

        # Non-negative observed slippage in decimal
        slip_dec = max(0.0, float(realized_slippage_bps) / 10000.0)

        # Back out empirical eta
        raw_observed_eta = slip_dec / sqrt_p
        clamped_observed_eta = max(self.MIN_ETA, min(self.MAX_ETA, raw_observed_eta))

        # Retrieve current or baseline state
        current_state = self._impact_states.get(sym)
        if current_state is None:
            current_eta = self.default_eta
            count = 1
        else:
            current_eta = current_state.calibrated_eta
            count = current_state.sample_count + 1

        # EWMA update
        updated_eta = (1.0 - lam) * current_eta + lam * clamped_observed_eta
        updated_eta = max(self.MIN_ETA, min(self.MAX_ETA, updated_eta))

        self._impact_states[sym] = AlmgrenChrissImpactState(
            symbol=sym,
            calibrated_eta=round(updated_eta, 4),
            sample_count=count,
            last_updated=datetime.now(timezone.utc).isoformat(),
            baseline_eta=self.default_eta,
        )

        logger.debug(
            f"Almgren-Chriss η calibrated for {sym}: {current_eta:.4f} -> {updated_eta:.4f} "
            f"(Observed: {clamped_observed_eta:.4f}, Sample #{count})"
        )

        return updated_eta

    def get_calibrated_eta(self, symbol: str) -> float:
        """Retrieve the current calibrated market impact parameter η for a symbol."""
        sym = symbol.upper()
        state = self._impact_states.get(sym)
        if state is not None:
            return state.calibrated_eta
        return self.default_eta

    def estimate_expected_slippage(
        self,
        symbol: str,
        order_quantity: float,
        adv_20: float,
    ) -> float:
        """
        Estimate expected execution slippage (in bps) for a planned order slice
        using the calibrated Almgren-Chriss Square-Root law.
        """
        eta = self.get_calibrated_eta(symbol)
        adv = max(1.0, float(adv_20))
        qty = max(0.0, float(order_quantity))

        p_rate = qty / adv
        expected_bps = eta * math.sqrt(p_rate) * 10000.0
        return round(expected_bps, 2)

    def get_venue_quality_report(self) -> dict[str, VenueQualityMetrics]:
        """
        Calculate execution quality benchmarks and composite score (0-100) across venues.
        Scoring Model:
            Base = 100
            Penalties:
              - Average slippage drag: avg_slippage * 1.2
              - Slippage inconsistency (std dev): slippage_std * 0.8
              - Fee friction: avg_fee_bps * 0.5
            Multiplied by Fill Rate penalty factor (2.0 - fill_rate).
        """
        venue_groups: dict[str, list[ExecutionFill]] = {}
        for fill in self._fills_buffer:
            venue_groups.setdefault(fill.venue, []).append(fill)

        metrics: dict[str, VenueQualityMetrics] = {}
        for ven, fills in venue_groups.items():
            tot_orders = len(fills)
            tot_vol = sum(f.fill_quantity * f.fill_price for f in fills)
            tot_fees = sum(f.fee_usd for f in fills)

            avg_fee_bps = (tot_fees / tot_vol * 10000.0) if tot_vol > 0 else 0.0

            slippage_list = [f.realized_slippage_bps for f in fills]
            avg_slip = sum(slippage_list) / tot_orders

            variance = sum((s - avg_slip) ** 2 for s in slippage_list) / tot_orders
            std_slip = math.sqrt(variance)

            # 95th percentile slippage
            sorted_slip = sorted(slippage_list)
            p95_idx = min(tot_orders - 1, int(tot_orders * 0.95))
            p95_slip = sorted_slip[p95_idx]

            # Match associated plan reports if available to estimate fill rate
            matched_plans = [p for p in self._plan_reports.values() if p.venue == ven]
            if matched_plans:
                avg_fill_rate = sum(p.fill_rate_pct for p in matched_plans) / (100.0 * len(matched_plans))
            else:
                avg_fill_rate = 1.0

            # Composite Score Calculation
            slip_penalty = min(40.0, max(0.0, avg_slip) * 1.2)
            std_penalty = min(25.0, std_slip * 0.8)
            fee_penalty = min(15.0, avg_fee_bps * 0.5)

            fill_factor = 2.0 - min(1.0, max(0.0, avg_fill_rate))
            total_penalty = (slip_penalty + std_penalty + fee_penalty) * fill_factor
            score = max(0.0, min(100.0, 100.0 - total_penalty))

            metrics[ven] = VenueQualityMetrics(
                venue=ven,
                total_orders=tot_orders,
                total_volume_usd=tot_vol,
                avg_fill_rate=avg_fill_rate,
                avg_slippage_bps=avg_slip,
                slippage_std_bps=std_slip,
                p95_slippage_bps=p95_slip,
                avg_fee_bps=avg_fee_bps,
                quality_score=score,
            )

        return metrics

    def get_slippage_distribution(self, symbol: Optional[str] = None) -> dict[str, float]:
        """
        Compute parametric and empirical slippage distribution statistics.
        """
        if symbol:
            target_fills = [f for f in self._fills_buffer if f.symbol == symbol.upper()]
        else:
            target_fills = self._fills_buffer

        if not target_fills:
            return {
                "count": 0.0,
                "mean_bps": 0.0,
                "median_bps": 0.0,
                "std_bps": 0.0,
                "p95_bps": 0.0,
                "p99_bps": 0.0,
                "min_bps": 0.0,
                "max_bps": 0.0,
            }

        slips = sorted(f.realized_slippage_bps for f in target_fills)
        n = len(slips)
        mean_v = sum(slips) / n
        median_v = slips[n // 2] if n % 2 != 0 else (slips[n // 2 - 1] + slips[n // 2]) / 2.0
        var_v = sum((x - mean_v) ** 2 for x in slips) / n
        std_v = math.sqrt(var_v)

        p95 = slips[min(n - 1, int(n * 0.95))]
        p99 = slips[min(n - 1, int(n * 0.99))]

        return {
            "count": float(n),
            "mean_bps": round(mean_v, 2),
            "median_bps": round(median_v, 2),
            "std_bps": round(std_v, 2),
            "p95_bps": round(p95, 2),
            "p99_bps": round(p99, 2),
            "min_bps": round(slips[0], 2),
            "max_bps": round(slips[-1], 2),
        }

    def get_anomaly_fills(self, limit: int = 50) -> list[ExecutionFill]:
        """Retrieve recent execution fills flagged for adverse selection or extreme slippage."""
        anomalies = [f for f in self._fills_buffer if f.is_anomaly]
        return anomalies[-limit:]

    def clear_buffers(self) -> None:
        """Clear all in-memory buffers (primarily for test teardown)."""
        self._fills_buffer.clear()
        self._plan_reports.clear()
        self._impact_states.clear()
        self._symbol_slippage_history.clear()
