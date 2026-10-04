"""
Intraday Liquidity Hole & Stop-Hunt Guard Service (E4 Engine)
日內量價微結構流動性空洞與假突破獵殺防線
=============================================================================
Provides real-time intraday microstructure order book depth depletion (liquidity vacuum)
and predatory algorithmic stop-loss hunting (liquidity sweep / bull-bear traps) detection
before smart order routing (E1) or aggressive market orders suffer severe adverse execution slippage.

Key Capabilities:
1. Liquidity Hole Detection (Order Book Depth Depletion):
   - Monitors normalized order book depth: Depth_curr = Bid_size + Ask_size
   - Computes rolling baseline depth: Depth_base
   - Evaluates depth depletion ratio: DDR = max(0.0, 1.0 - Depth_curr / Depth_base)
   - Evaluates spread expansion ratio: SER = Spread_curr / Spread_base
   - Triggers LIQUIDITY_HOLE state when DDR >= threshold (default 0.70) and SER >= threshold (default 2.0).
2. Predatory Stop-Hunt & Liquidity Sweep Detection:
   - Tracks intraday price penetration beyond critical resistance (bull trap) or support (bear trap).
   - Evaluates immediate mean-reverting absorption (Reversion Ratio = |Peak - Close| / |Peak - Level|).
   - Measures sudden volume spike (VSR = Volume / Baseline_Volume >= 2.5x).
   - Computes composite Stop-Hunt Score (SHS in [0.0, 1.0]):
     SHS = w_rev * ReversionRatio + w_vol * VolumeSpikeScore + w_pen * PenetrationScore
   - Identifies predatory sweeps that trigger stops and reverse immediately.
3. Microstructure Guard State Machine & Closed-Loop Directives:
   - States: NORMAL, LIQUIDITY_HOLE, HUNT_SWEEP_ALERT, DEFENSIVE_PAUSE
   - Directives:
     * PROCEED_NORMAL: Normal child slicing.
     * DELAY_EXECUTION: Hold aggressive child orders until order book fills (15~60s cooldown).
     * FORCE_PASSIVE_LIMIT: Prevent market sweeps; route passive peg/iceberg orders only.
     * ABORT_BREAKOUT_CHASE: Drop false-breakout chase buy/sell orders.
   - Closed-loop integrations:
     * Informs E1 SOR to adapt timing windows or enforce limit boundaries.
     * Informs P6 Slippage Compensator with dynamic adverse buffer (15~35 bps).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
from typing import Any, Deque, Dict, List, Optional

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("IntradayLiquidityHuntGuardService")


class GuardState(str, Enum):
    """Lifecycle states of the microstructure guard."""
    NORMAL = "NORMAL"
    LIQUIDITY_HOLE = "LIQUIDITY_HOLE"
    HUNT_SWEEP_ALERT = "HUNT_SWEEP_ALERT"
    DEFENSIVE_PAUSE = "DEFENSIVE_PAUSE"


class GuardAction(str, Enum):
    """Recommended execution action under current microstructure conditions."""
    PROCEED_NORMAL = "PROCEED_NORMAL"
    DELAY_EXECUTION = "DELAY_EXECUTION"
    FORCE_PASSIVE_LIMIT = "FORCE_PASSIVE_LIMIT"
    ABORT_BREAKOUT_CHASE = "ABORT_BREAKOUT_CHASE"


class KeyLevelType(str, Enum):
    """Type of technical key level."""
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"


@dataclass
class OrderBookSnapshot:
    """Real-time top-of-book depth & spread observation."""
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TradeBar:
    """Intraday OHLCV trade bar observation."""
    symbol: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class KeyLevel:
    """Key price level for stop-hunt monitoring (e.g. daily high/low, support/resistance)."""
    level_type: KeyLevelType
    price: float
    description: Optional[str] = None


@dataclass
class LiquidityHoleAssessment:
    """Evaluation result for order book liquidity hole / depth depletion."""
    is_hole_detected: bool
    depth_depletion_ratio: float
    current_depth: float
    baseline_depth: float
    spread_bps: float
    spread_expansion_ratio: float
    details: str = ""


@dataclass
class StopHuntAssessment:
    """Evaluation result for predatory stop-hunt and liquidity sweep."""
    is_hunt_detected: bool
    stop_hunt_score: float
    swept_level: Optional[float] = None
    level_type: Optional[KeyLevelType] = None
    penetration_pct: float = 0.0
    reversion_ratio: float = 0.0
    volume_spike_ratio: float = 1.0
    details: str = ""


@dataclass
class GuardEvaluation:
    """Comprehensive microstructure guard evaluation response."""
    symbol: str
    state: GuardState
    action: GuardAction
    liquidity_hole: LiquidityHoleAssessment
    stop_hunt: StopHuntAssessment
    recommended_delay_seconds: int
    adverse_slippage_buffer_bps: float
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SymbolMicrostructureState:
    """In-memory rolling cache for asset microstructure metrics."""
    symbol: str
    snapshots: Deque[OrderBookSnapshot] = field(default_factory=lambda: deque(maxlen=50))
    trade_bars: Deque[TradeBar] = field(default_factory=lambda: deque(maxlen=30))
    current_state: GuardState = GuardState.NORMAL
    last_state_change: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cooldown_until: Optional[datetime] = None
    last_trigger_details: str = ""


class IntradayLiquidityHuntGuardService:
    """
    E4 Microstructure Guard: Detects liquidity holes and predatory stop-hunts in real time.
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        default_depth_depletion_threshold: float = 0.70,
        default_spread_expansion_threshold: float = 2.0,
        default_stop_hunt_score_threshold: float = 0.65,
        default_cooldown_seconds: int = 60,
    ) -> None:
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self._depth_depletion_threshold = default_depth_depletion_threshold
        self._spread_expansion_threshold = default_spread_expansion_threshold
        self._stop_hunt_score_threshold = default_stop_hunt_score_threshold
        self._cooldown_seconds = default_cooldown_seconds

        # In-memory tracking per symbol
        self._states: Dict[str, SymbolMicrostructureState] = {}

    def _get_symbol_state(self, symbol: str) -> SymbolMicrostructureState:
        sym = symbol.upper().strip()
        if sym not in self._states:
            self._states[sym] = SymbolMicrostructureState(symbol=sym)
        return self._states[sym]

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service and hasattr(self.settings_service, "get"):
            try:
                val = self.settings_service.get(key)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to fetch setting '{key}': {e}. Using default {default}")
        return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("liquidity_hunt_guard_enabled", True))

    @property
    def depth_depletion_threshold(self) -> float:
        return float(self._get_setting("liquidity_hole_depth_depletion_threshold", self._depth_depletion_threshold))

    @property
    def spread_expansion_threshold(self) -> float:
        return float(self._get_setting("liquidity_hole_spread_expansion_threshold", self._spread_expansion_threshold))

    @property
    def stop_hunt_score_threshold(self) -> float:
        return float(self._get_setting("stop_hunt_score_threshold", self._stop_hunt_score_threshold))

    @property
    def cooldown_seconds(self) -> int:
        return int(self._get_setting("hunt_guard_cooldown_seconds", self._cooldown_seconds))

    def record_quote(self, snapshot: OrderBookSnapshot) -> None:
        """Records a new order book quote snapshot into the symbol's rolling window."""
        sym_state = self._get_symbol_state(snapshot.symbol)
        sym_state.snapshots.append(snapshot)

    def record_trade_bar(self, bar: TradeBar) -> None:
        """Records a new trade bar into the symbol's rolling window."""
        sym_state = self._get_symbol_state(bar.symbol)
        sym_state.trade_bars.append(bar)

    def detect_liquidity_hole(
        self,
        symbol: str,
        snapshot: Optional[OrderBookSnapshot] = None,
    ) -> LiquidityHoleAssessment:
        """
        Evaluates order book depth depletion and spread expansion.
        Returns a structured LiquidityHoleAssessment.
        """
        sym_state = self._get_symbol_state(symbol)
        if snapshot:
            self.record_quote(snapshot)
            curr = snapshot
        elif sym_state.snapshots:
            curr = sym_state.snapshots[-1]
        else:
            return LiquidityHoleAssessment(
                is_hole_detected=False,
                depth_depletion_ratio=0.0,
                current_depth=0.0,
                baseline_depth=0.0,
                spread_bps=0.0,
                spread_expansion_ratio=1.0,
                details="No order book snapshots recorded.",
            )

        curr_depth = max(0.0, curr.bid_size + curr.ask_size)
        mid_price = (curr.bid_price + curr.ask_price) / 2.0 if (curr.bid_price + curr.ask_price) > 0 else 1.0
        curr_spread = max(0.0, curr.ask_price - curr.bid_price)
        curr_spread_bps = (curr_spread / mid_price) * 10000.0 if mid_price > 0 else 0.0

        # Compute rolling baseline depth and spread from historical snapshots (excluding the current one)
        history = list(sym_state.snapshots)[:-1] if len(sym_state.snapshots) > 1 else list(sym_state.snapshots)
        if not history:
            base_depth = curr_depth
            base_spread = curr_spread
        else:
            base_depth = sum(s.bid_size + s.ask_size for s in history) / len(history)
            base_spread = sum(max(0.0, s.ask_price - s.bid_price) for s in history) / len(history)

        base_depth = max(1e-6, base_depth)
        base_spread = max(1e-6, base_spread)

        # Depth depletion ratio: DDR in [0.0, 1.0]
        ddr = max(0.0, min(1.0, 1.0 - (curr_depth / base_depth)))
        # Spread expansion ratio: SER >= 0.0
        ser = curr_spread / base_spread if base_spread > 0 else 1.0

        is_hole = False
        details = "Depth and spread within baseline parameters."

        if not self.is_enabled:
            details = "Liquidity hunt guard is disabled."
        elif ddr >= self.depth_depletion_threshold and ser >= self.spread_expansion_threshold:
            is_hole = True
            details = (
                f"Liquidity Hole Tripped! DDR={ddr:.2%} (>= {self.depth_depletion_threshold:.2%}), "
                f"Spread Expansion={ser:.2f}x (>= {self.spread_expansion_threshold:.2f}x). "
                f"Current depth={curr_depth:.1f} vs base={base_depth:.1f}."
            )

        return LiquidityHoleAssessment(
            is_hole_detected=is_hole,
            depth_depletion_ratio=round(ddr, 4),
            current_depth=round(curr_depth, 2),
            baseline_depth=round(base_depth, 2),
            spread_bps=round(curr_spread_bps, 2),
            spread_expansion_ratio=round(ser, 3),
            details=details,
        )

    def detect_stop_hunt(
        self,
        symbol: str,
        bar: Optional[TradeBar] = None,
        key_levels: Optional[List[KeyLevel]] = None,
    ) -> StopHuntAssessment:
        """
        Evaluates predatory stop-loss hunting & liquidity sweep against technical key levels.
        Identifies bull/bear traps where price briefly sweeps beyond a level on high volume,
        then violently reverses back inside the range.
        """
        sym_state = self._get_symbol_state(symbol)
        if bar:
            self.record_trade_bar(bar)
            curr_bar = bar
        elif sym_state.trade_bars:
            curr_bar = sym_state.trade_bars[-1]
        else:
            return StopHuntAssessment(
                is_hunt_detected=False,
                stop_hunt_score=0.0,
                details="No trade bars recorded.",
            )

        if not key_levels:
            return StopHuntAssessment(
                is_hunt_detected=False,
                stop_hunt_score=0.0,
                details="No key levels provided for stop-hunt evaluation.",
            )

        # Compute baseline volume from historical trade bars
        history_bars = list(sym_state.trade_bars)[:-1] if len(sym_state.trade_bars) > 1 else list(sym_state.trade_bars)
        if history_bars:
            base_vol = max(1e-6, sum(b.volume for b in history_bars) / len(history_bars))
        else:
            base_vol = max(1e-6, curr_bar.volume)

        vol_spike_ratio = max(1.0, curr_bar.volume / base_vol)

        best_hunt: Optional[StopHuntAssessment] = None
        highest_score = 0.0

        for kl in key_levels:
            lvl = kl.price
            if lvl <= 0:
                continue

            # RESISTANCE SWEEP (Bull Trap):
            # Price spikes above resistance (High > Level), but closes back down (Close < High).
            if kl.level_type == KeyLevelType.RESISTANCE and curr_bar.high_price > lvl:
                pen_amt = curr_bar.high_price - lvl
                pen_pct = pen_amt / lvl

                # Meaningful penetration window: between 0.05% and 2.5%
                if 0.0005 <= pen_pct <= 0.025:
                    rev_amt = max(0.0, curr_bar.high_price - curr_bar.close_price)
                    rev_ratio = min(2.0, rev_amt / pen_amt) if pen_amt > 0 else 0.0

                    # If close is completely back below resistance, full reversal (>= 1.0)
                    if curr_bar.close_price <= lvl:
                        rev_ratio = max(1.0, rev_ratio)

                    # Scoring components
                    w_rev = 0.45 * min(1.0, rev_ratio)
                    w_vol = 0.35 * min(1.0, max(0.0, (vol_spike_ratio - 1.0) / 3.0))
                    w_pen = 0.20 * min(1.0, pen_pct / 0.005)
                    score = min(1.0, w_rev + w_vol + w_pen)

                    if score > highest_score:
                        highest_score = score
                        is_hunt = self.is_enabled and (score >= self.stop_hunt_score_threshold)
                        best_hunt = StopHuntAssessment(
                            is_hunt_detected=is_hunt,
                            stop_hunt_score=round(score, 4),
                            swept_level=round(lvl, 4),
                            level_type=KeyLevelType.RESISTANCE,
                            penetration_pct=round(pen_pct * 100.0, 3),
                            reversion_ratio=round(rev_ratio, 3),
                            volume_spike_ratio=round(vol_spike_ratio, 2),
                            details=(
                                f"Bull Trap Sweep: Pen={pen_pct*100:.2f}%, Reversion={rev_ratio:.2f}, "
                                f"VolSpike={vol_spike_ratio:.2f}x, Score={score:.3f} (>= {self.stop_hunt_score_threshold:.3f})"
                            ) if is_hunt else f"Sub-threshold resistance probe (Score={score:.3f}).",
                        )

            # SUPPORT SWEEP (Bear Trap):
            # Price dips below support (Low < Level), but closes back up (Close > Low).
            elif kl.level_type == KeyLevelType.SUPPORT and curr_bar.low_price < lvl:
                pen_amt = lvl - curr_bar.low_price
                pen_pct = pen_amt / lvl

                if 0.0005 <= pen_pct <= 0.025:
                    rev_amt = max(0.0, curr_bar.close_price - curr_bar.low_price)
                    rev_ratio = min(2.0, rev_amt / pen_amt) if pen_amt > 0 else 0.0

                    if curr_bar.close_price >= lvl:
                        rev_ratio = max(1.0, rev_ratio)

                    w_rev = 0.45 * min(1.0, rev_ratio)
                    w_vol = 0.35 * min(1.0, max(0.0, (vol_spike_ratio - 1.0) / 3.0))
                    w_pen = 0.20 * min(1.0, pen_pct / 0.005)
                    score = min(1.0, w_rev + w_vol + w_pen)

                    if score > highest_score:
                        highest_score = score
                        is_hunt = self.is_enabled and (score >= self.stop_hunt_score_threshold)
                        best_hunt = StopHuntAssessment(
                            is_hunt_detected=is_hunt,
                            stop_hunt_score=round(score, 4),
                            swept_level=round(lvl, 4),
                            level_type=KeyLevelType.SUPPORT,
                            penetration_pct=round(pen_pct * 100.0, 3),
                            reversion_ratio=round(rev_ratio, 3),
                            volume_spike_ratio=round(vol_spike_ratio, 2),
                            details=(
                                f"Bear Trap Sweep: Pen={pen_pct*100:.2f}%, Reversion={rev_ratio:.2f}, "
                                f"VolSpike={vol_spike_ratio:.2f}x, Score={score:.3f} (>= {self.stop_hunt_score_threshold:.3f})"
                            ) if is_hunt else f"Sub-threshold support probe (Score={score:.3f}).",
                        )

        if best_hunt:
            return best_hunt

        return StopHuntAssessment(
            is_hunt_detected=False,
            stop_hunt_score=round(highest_score, 4),
            details="No predatory liquidity sweeps identified across tested levels.",
        )

    def evaluate_guard(
        self,
        symbol: str,
        snapshot: Optional[OrderBookSnapshot] = None,
        bar: Optional[TradeBar] = None,
        key_levels: Optional[List[KeyLevel]] = None,
    ) -> GuardEvaluation:
        """
        Coordinates full microstructure guard evaluation:
        1. Analyzes order book depth and spread for liquidity holes.
        2. Analyzes price action and volume for stop-hunt liquidity sweeps.
        3. Updates guard state machine and determines recommended actions & slippage buffers.
        """
        sym_state = self._get_symbol_state(symbol)
        now = datetime.now(timezone.utc)

        hole_eval = self.detect_liquidity_hole(symbol, snapshot)
        hunt_eval = self.detect_stop_hunt(symbol, bar, key_levels)

        # State transition logic
        is_hole = hole_eval.is_hole_detected
        is_hunt = hunt_eval.is_hunt_detected

        # Check if in existing cooldown
        is_in_cooldown = sym_state.cooldown_until is not None and now < sym_state.cooldown_until

        if not self.is_enabled:
            target_state = GuardState.NORMAL
            action = GuardAction.PROCEED_NORMAL
            delay_sec = 0
            adverse_buffer_bps = 0.0
        elif is_hole and is_hunt:
            target_state = GuardState.DEFENSIVE_PAUSE
            action = GuardAction.DELAY_EXECUTION
            delay_sec = self.cooldown_seconds
            adverse_buffer_bps = 35.0
            sym_state.cooldown_until = now + timedelta(seconds=delay_sec)
            sym_state.last_trigger_details = f"Compound Shock: {hole_eval.details} | {hunt_eval.details}"
        elif is_hole:
            target_state = GuardState.LIQUIDITY_HOLE
            action = GuardAction.FORCE_PASSIVE_LIMIT
            delay_sec = max(15, self.cooldown_seconds // 2)
            adverse_buffer_bps = 20.0
            sym_state.cooldown_until = now + timedelta(seconds=delay_sec)
            sym_state.last_trigger_details = hole_eval.details
        elif is_hunt:
            target_state = GuardState.HUNT_SWEEP_ALERT
            action = GuardAction.ABORT_BREAKOUT_CHASE
            delay_sec = max(30, int(self.cooldown_seconds * 0.75))
            adverse_buffer_bps = 25.0
            sym_state.cooldown_until = now + timedelta(seconds=delay_sec)
            sym_state.last_trigger_details = hunt_eval.details
        elif is_in_cooldown:
            # Maintain defensive pause or warning until cooldown expires
            target_state = GuardState.DEFENSIVE_PAUSE
            action = GuardAction.DELAY_EXECUTION
            delay_sec = max(0, int((sym_state.cooldown_until - now).total_seconds()))  # type: ignore
            adverse_buffer_bps = 15.0
        else:
            target_state = GuardState.NORMAL
            action = GuardAction.PROCEED_NORMAL
            delay_sec = 0
            adverse_buffer_bps = 0.0
            sym_state.cooldown_until = None

        if target_state != sym_state.current_state:
            logger.info(
                f"[E4 Guard] {symbol.upper()} state transitioned from {sym_state.current_state} -> {target_state}."
            )
            sym_state.current_state = target_state
            sym_state.last_state_change = now

        return GuardEvaluation(
            symbol=symbol.upper().strip(),
            state=target_state,
            action=action,
            liquidity_hole=hole_eval,
            stop_hunt=hunt_eval,
            recommended_delay_seconds=delay_sec,
            adverse_slippage_buffer_bps=round(adverse_buffer_bps, 2),
            evaluated_at=now,
        )

    def get_guard_state(self, symbol: str) -> GuardState:
        """Retrieves the current guard state for a symbol."""
        return self._get_symbol_state(symbol).current_state

    def reset_symbol_state(self, symbol: str) -> None:
        """Resets the symbol cache and restores state to NORMAL."""
        sym_state = self._get_symbol_state(symbol)
        sym_state.current_state = GuardState.NORMAL
        sym_state.cooldown_until = None
        sym_state.last_trigger_details = "State manually reset to NORMAL."
        sym_state.last_state_change = datetime.now(timezone.utc)

    def get_all_guard_states(self) -> Dict[str, Dict[str, Any]]:
        """Returns summary of all tracked symbols and their microstructure states."""
        res: Dict[str, Dict[str, Any]] = {}
        now = datetime.now(timezone.utc)
        for sym, state in self._states.items():
            in_cooldown = state.cooldown_until is not None and now < state.cooldown_until
            remaining_cooldown = (
                max(0, int((state.cooldown_until - now).total_seconds()))
                if in_cooldown else 0
            )
            res[sym] = {
                "symbol": sym,
                "current_state": state.current_state.value,
                "in_cooldown": in_cooldown,
                "remaining_cooldown_seconds": remaining_cooldown,
                "last_state_change": state.last_state_change.isoformat(),
                "last_trigger_details": state.last_trigger_details,
                "snapshot_count": len(state.snapshots),
                "trade_bar_count": len(state.trade_bars),
            }
        return res
