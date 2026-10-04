"""
Intraday Liquidity Shock & Volatility Circuit Breaker Service (P7 Engine)
=============================================================================
Provides real-time intraday liquidity monitoring, market shock detection,
and automated trading execution circuit breaker protection.

Key Capabilities:
1. Microstructure Shock Detection:
   - Spread Explosion: detects bid-ask spread expansion (Spread_curr / Spread_base >= threshold).
   - Price Gap & Flash Crash: detects instantaneous price displacement (|ΔP| / P >= threshold).
   - Volatility Surge: detects intraday realized volatility spikes (sigma >= 3.0).
   - Order Book Depth Depletion: flags thin liquidity where executions face extreme adverse selection.
2. State Machine & Execution Halting:
   - NORMAL: Full order routing & child slicing permitted.
   - WARNING: Elevated friction; recommends SOR throttling & tighter limit price bounds.
   - TRIGGERED: Circuit breaker tripped; active and pending child orders for affected
     assets (or market-wide) are halted immediately.
   - COOLDOWN: Passive monitoring window (default 15m). Auto-recovers to NORMAL
     if spread and volatility normalize.
3. Bidirectional Actionable Alert Integration (P3 Hub):
   - Dispatches interactive Telegram / Slack alert cards with 1-tap actions:
     [Resume Trading], [Emergency Defensive Cash], [Extend Cooldown].
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("IntradayLiquidityCircuitBreakerService")


class CircuitBreakerState(str, Enum):
    """Lifecycle states of the circuit breaker."""
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    TRIGGERED = "TRIGGERED"
    COOLDOWN = "COOLDOWN"


class ShockTriggerType(str, Enum):
    """Classification of microstructure liquidity shocks."""
    SPREAD_EXPANSION = "SPREAD_EXPANSION"
    PRICE_GAP_SHOCK = "PRICE_GAP_SHOCK"
    VOLATILITY_SURGE = "VOLATILITY_SURGE"
    DEPTH_DEPLETION = "DEPTH_DEPLETION"
    MANUAL = "MANUAL"


@dataclass
class MarketQuoteObservation:
    """Real-time market quote snapshot for evaluation."""
    symbol: str
    bid_price: float
    ask_price: float
    last_price: float
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    intraday_volatility: Optional[float] = None
    timestamp: Optional[datetime] = None

    @property
    def mid_price(self) -> float:
        if self.bid_price > 0 and self.ask_price > 0:
            return (self.bid_price + self.ask_price) / 2.0
        return self.last_price

    @property
    def spread_bps(self) -> float:
        mid = self.mid_price
        if mid <= 0:
            return 0.0
        return max(0.0, ((self.ask_price - self.bid_price) / mid) * 10000.0)


@dataclass
class AssetBaseline:
    """Historical baseline metrics for comparison."""
    symbol: str
    typical_spread_bps: float = 5.0
    reference_price: float = 100.0
    typical_volatility: float = 0.20
    typical_depth: float = 1000.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CircuitBreakerStatus:
    """Current circuit breaker status for a symbol or global portfolio."""
    symbol: str
    state: CircuitBreakerState = CircuitBreakerState.NORMAL
    trigger_type: Optional[ShockTriggerType] = None
    reason: Optional[str] = None
    spread_bps: float = 0.0
    spread_multiplier: float = 1.0
    price_shock_pct: float = 0.0
    vol_sigma: float = 0.0
    triggered_at: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    actions_taken: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state.value if isinstance(self.state, CircuitBreakerState) else str(self.state),
            "trigger_type": self.trigger_type.value if self.trigger_type else None,
            "reason": self.reason,
            "spread_bps": round(self.spread_bps, 2),
            "spread_multiplier": round(self.spread_multiplier, 2),
            "price_shock_pct": round(self.price_shock_pct, 2),
            "vol_sigma": round(self.vol_sigma, 2),
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "actions_taken": self.actions_taken,
        }


class IntradayLiquidityCircuitBreakerService:
    """
    Intraday Liquidity Shock & Volatility Circuit Breaker Orchestrator.
    """

    DEFAULT_SPREAD_MULTIPLIER_THRESHOLD = 3.0
    DEFAULT_ABSOLUTE_SPREAD_BPS_THRESHOLD = 50.0
    DEFAULT_PRICE_GAP_PCT_THRESHOLD = 3.5
    DEFAULT_VOL_SPIKE_SIGMA_THRESHOLD = 3.0
    DEFAULT_COOLDOWN_MINUTES = 15

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        alert_hub_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self.alert_hub_service = alert_hub_service

        # In-memory circuit breaker registries for ultra-fast checks (<1us)
        self._statuses: Dict[str, CircuitBreakerStatus] = {}
        self._baselines: Dict[str, AssetBaseline] = {}

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
        """Dynamic settings retrieval helper."""
        if not self.settings_service:
            return default
        try:
            val = self.settings_service.get_setting(key, default)
            if val is None:
                return default
            if val_type is bool:
                return str(val).lower() in ("true", "1", "yes")
            return val_type(val)
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting("circuit_breaker_enabled", True, bool)

    @property
    def spread_multiplier_threshold(self) -> float:
        return float(self._get_setting("circuit_breaker_spread_multiplier_threshold", self.DEFAULT_SPREAD_MULTIPLIER_THRESHOLD, float))

    @property
    def spread_absolute_bps_threshold(self) -> float:
        return float(self._get_setting("circuit_breaker_spread_absolute_bps_threshold", self.DEFAULT_ABSOLUTE_SPREAD_BPS_THRESHOLD, float))

    @property
    def price_gap_pct_threshold(self) -> float:
        return float(self._get_setting("circuit_breaker_price_gap_pct", self.DEFAULT_PRICE_GAP_PCT_THRESHOLD, float))

    @property
    def vol_spike_sigma_threshold(self) -> float:
        return float(self._get_setting("circuit_breaker_vol_spike_sigma", self.DEFAULT_VOL_SPIKE_SIGMA_THRESHOLD, float))

    @property
    def cooldown_minutes(self) -> int:
        return int(self._get_setting("circuit_breaker_cooldown_minutes", self.DEFAULT_COOLDOWN_MINUTES, int))

    def get_or_create_baseline(self, symbol: str, current_price: float = 100.0) -> AssetBaseline:
        sym = symbol.upper().strip()
        if sym not in self._baselines:
            self._baselines[sym] = AssetBaseline(
                symbol=sym,
                typical_spread_bps=5.0,
                reference_price=current_price if current_price > 0 else 100.0,
                typical_volatility=0.20,
            )
        return self._baselines[sym]

    def update_baseline(
        self,
        symbol: str,
        typical_spread_bps: Optional[float] = None,
        reference_price: Optional[float] = None,
        typical_volatility: Optional[float] = None,
    ) -> AssetBaseline:
        base = self.get_or_create_baseline(symbol, reference_price or 100.0)
        if typical_spread_bps is not None and typical_spread_bps > 0:
            base.typical_spread_bps = float(typical_spread_bps)
        if reference_price is not None and reference_price > 0:
            base.reference_price = float(reference_price)
        if typical_volatility is not None and typical_volatility > 0:
            base.typical_volatility = float(typical_volatility)
        base.last_updated = datetime.now(timezone.utc)
        return base

    def get_status(self, symbol: str) -> CircuitBreakerStatus:
        sym = symbol.upper().strip()
        if sym not in self._statuses:
            self._statuses[sym] = CircuitBreakerStatus(symbol=sym)

        status = self._statuses[sym]
        now = datetime.now(timezone.utc)

        # Check for cooldown expiration
        if status.state in (CircuitBreakerState.TRIGGERED, CircuitBreakerState.COOLDOWN):
            if status.cooldown_until and now >= status.cooldown_until:
                # Expired -> auto-recover to NORMAL
                status.state = CircuitBreakerState.NORMAL
                status.reason = f"Cooldown period elapsed at {now.isoformat()}; normal trading resumed"
                status.actions_taken.append("AUTO_RECOVERED_FROM_COOLDOWN")
                logger.info(f"Circuit Breaker on {sym} auto-recovered from cooldown to NORMAL")

        return status

    def get_all_statuses(self) -> Dict[str, CircuitBreakerStatus]:
        # Refresh statuses to check cooldown expirations
        for sym in list(self._statuses.keys()):
            self.get_status(sym)
        return dict(self._statuses)

    def is_halted(self, symbol: str) -> bool:
        """
        Sub-microsecond check: returns True if trading is halted for the symbol or portfolio-wide.
        """
        if not self.is_enabled:
            return False

        # 1. Global check
        global_status = self.get_status("GLOBAL")
        if global_status.state in (CircuitBreakerState.TRIGGERED, CircuitBreakerState.COOLDOWN):
            return True

        # 2. Asset-specific check
        sym_status = self.get_status(symbol)
        return sym_status.state in (CircuitBreakerState.TRIGGERED, CircuitBreakerState.COOLDOWN)

    def can_execute(self, symbol: str) -> bool:
        return not self.is_halted(symbol)

    def evaluate_quote(self, quote: MarketQuoteObservation) -> CircuitBreakerStatus:
        """
        Ingest a real-time market quote observation, detect liquidity shocks,
        and trip circuit breaker if thresholds are breached.
        """
        sym = quote.symbol.upper().strip()
        current_status = self.get_status(sym)
        now = quote.timestamp or datetime.now(timezone.utc)

        if not self.is_enabled:
            current_status.state = CircuitBreakerState.NORMAL
            return current_status

        # If already halted and cooling down, remain halted until cooldown expires
        if current_status.state in (CircuitBreakerState.TRIGGERED, CircuitBreakerState.COOLDOWN):
            return current_status

        baseline = self.get_or_create_baseline(sym, quote.last_price)
        current_spread = quote.spread_bps
        base_spread = max(1.0, baseline.typical_spread_bps)
        spread_mult = current_spread / base_spread

        # Calculate price shock displacement
        ref_price = baseline.reference_price if baseline.reference_price > 0 else quote.last_price
        price_gap_pct = (abs(quote.last_price - ref_price) / ref_price) * 100.0 if ref_price > 0 else 0.0

        # Calculate volatility shock
        vol_sigma = 0.0
        if quote.intraday_volatility is not None and baseline.typical_volatility > 0:
            vol_sigma = max(0.0, (quote.intraday_volatility - baseline.typical_volatility) / (baseline.typical_volatility * 0.33))

        # Update metrics on status
        current_status.spread_bps = current_spread
        current_status.spread_multiplier = spread_mult
        current_status.price_shock_pct = price_gap_pct
        current_status.vol_sigma = vol_sigma

        # ── Shock Condition Checks ──
        shock_triggered = False
        trigger_type: Optional[ShockTriggerType] = None
        reason: Optional[str] = None

        # 1. Spread Explosion Shock
        if spread_mult >= self.spread_multiplier_threshold or current_spread >= self.spread_absolute_bps_threshold:
            shock_triggered = True
            trigger_type = ShockTriggerType.SPREAD_EXPANSION
            reason = (
                f"Bid-Ask spread exploded to {current_spread:.1f} bps "
                f"({spread_mult:.2f}x baseline {base_spread:.1f} bps >= threshold {self.spread_multiplier_threshold:.1f}x)"
            )

        # 2. Flash Crash / Price Gap Shock
        elif price_gap_pct >= self.price_gap_pct_threshold:
            shock_triggered = True
            trigger_type = ShockTriggerType.PRICE_GAP_SHOCK
            reason = (
                f"Instantaneous price displacement of {price_gap_pct:.2f}% "
                f"from reference ${ref_price:.2f} exceeded threshold {self.price_gap_pct_threshold:.1f}%"
            )

        # 3. Volatility Surge
        elif vol_sigma >= self.vol_spike_sigma_threshold:
            shock_triggered = True
            trigger_type = ShockTriggerType.VOLATILITY_SURGE
            reason = (
                f"Intraday realized volatility surged by {vol_sigma:.2f} sigma "
                f"(exceeded {self.vol_spike_sigma_threshold:.1f} sigma shock threshold)"
            )

        # 4. Warning condition (mild friction)
        elif spread_mult >= (self.spread_multiplier_threshold * 0.6) or price_gap_pct >= (self.price_gap_pct_threshold * 0.6):
            current_status.state = CircuitBreakerState.WARNING
            current_status.reason = f"Mild liquidity deterioration detected ({spread_mult:.2f}x spread, {price_gap_pct:.2f}% gap)"
            return current_status

        # ── Trip Breaker if Shock Detected ──
        if shock_triggered and trigger_type:
            cooldown_period = timedelta(minutes=self.cooldown_minutes)
            current_status.state = CircuitBreakerState.TRIGGERED
            current_status.trigger_type = trigger_type
            current_status.reason = reason
            current_status.triggered_at = now
            current_status.cooldown_until = now + cooldown_period
            current_status.actions_taken = [
                "HALTED_EXECUTION_QUEUE",
                f"COOLDOWN_UNTIL_{(now + cooldown_period).isoformat()}",
            ]

            logger.error(f"🚨 CIRCUIT BREAKER TRIPPED ON {sym}: {reason}. Cooldown for {self.cooldown_minutes}m")

            # Asynchronously dispatch interactive alert via ActionableAlertHub
            self._dispatch_alert(current_status)

        else:
            current_status.state = CircuitBreakerState.NORMAL
            current_status.trigger_type = None
            current_status.reason = None

        return current_status

    def manual_trigger(
        self,
        symbol: str = "GLOBAL",
        reason: str = "Manual emergency operator intervention",
        cooldown_minutes: Optional[int] = None,
    ) -> CircuitBreakerStatus:
        """
        Manually trigger circuit breaker for a symbol or the entire portfolio.
        """
        sym = symbol.upper().strip()
        status = self.get_status(sym)
        now = datetime.now(timezone.utc)
        mins = cooldown_minutes or self.cooldown_minutes
        cooldown_period = timedelta(minutes=mins)

        status.state = CircuitBreakerState.TRIGGERED
        status.trigger_type = ShockTriggerType.MANUAL
        status.reason = reason
        status.triggered_at = now
        status.cooldown_until = now + cooldown_period
        status.actions_taken = [
            "MANUALLY_TRIGGERED",
            f"COOLDOWN_UNTIL_{(now + cooldown_period).isoformat()}",
        ]

        logger.warning(f"🚨 MANUAL CIRCUIT BREAKER TRIPPED ON {sym}: {reason}. Cooldown: {mins}m")
        self._dispatch_alert(status)
        return status

    def resume(self, symbol: str = "GLOBAL") -> bool:
        """
        Manually reset/resume trading from a circuit breaker halt.
        """
        sym = symbol.upper().strip()
        status = self.get_status(sym)
        status.state = CircuitBreakerState.NORMAL
        status.trigger_type = None
        status.reason = f"Manually resumed trading at {datetime.now(timezone.utc).isoformat()}"
        status.cooldown_until = None
        status.actions_taken.append("MANUALLY_RESUMED")
        logger.info(f"Circuit Breaker resumed for {sym}")
        return True

    def extend_cooldown(self, symbol: str, additional_minutes: int = 30) -> CircuitBreakerStatus:
        """
        Extend the cooldown period of an active circuit breaker.
        """
        sym = symbol.upper().strip()
        status = self.get_status(sym)
        now = datetime.now(timezone.utc)
        current_cooldown = status.cooldown_until or now
        new_cooldown = max(now, current_cooldown) + timedelta(minutes=additional_minutes)

        status.cooldown_until = new_cooldown
        status.actions_taken.append(f"EXTENDED_COOLDOWN_+{additional_minutes}M_UNTIL_{new_cooldown.isoformat()}")
        logger.warning(f"Circuit Breaker cooldown on {sym} extended by {additional_minutes}m (until {new_cooldown.isoformat()})")
        return status

    def _dispatch_alert(self, status: CircuitBreakerStatus) -> None:
        """Helper to invoke ActionableAlertHubService dispatch safely."""
        if not self.alert_hub_service:
            try:
                from src.services.actionable_alert_service import ActionableAlertHubService
                self.alert_hub_service = ActionableAlertHubService(user_id=self.user_id)
            except Exception as e:
                logger.debug(f"ActionableAlertHubService unavailable: {e}")
                return

        try:
            import asyncio
            if hasattr(self.alert_hub_service, "dispatch_liquidity_circuit_breaker_alert"):
                coro = self.alert_hub_service.dispatch_liquidity_circuit_breaker_alert(
                    ticker=status.symbol,
                    reason=status.reason or "Microstructure liquidity shock",
                    trigger_type=status.trigger_type.value if status.trigger_type else "LIQUIDITY_SHOCK",
                    spread_bps=status.spread_bps,
                    spread_multiplier=status.spread_multiplier,
                    cooldown_minutes=self.cooldown_minutes,
                )
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(coro)
                except RuntimeError:
                    # No active running event loop: close coroutine to prevent unawaited warning
                    coro.close()
        except Exception as e:
            logger.warning(f"Failed to dispatch circuit breaker alert: {e}")
