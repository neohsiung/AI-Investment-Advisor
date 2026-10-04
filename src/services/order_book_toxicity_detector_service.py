"""
Order Book Imbalance & VPIN Toxicity Detector Service (E3 Engine)
訂單簿深度失衡與毒性流偵測器
=============================================================================
Provides microsecond-level forward-looking market toxicity estimation and
order book queue imbalance detection before bid-ask spreads significantly widen.

Key Capabilities:
1. Order Book Imbalance (OBI / OFI):
   - Computes normalized queue depth skew:
     OBI = (V_bid - V_ask) / (V_bid + V_ask) in [-1.0, 1.0]
   - Detects aggressive quote-side leaning and depletion that triggers adverse
     selection for incoming market/limit orders.
2. Volume-Synchronized Probability of Toxicity (VPIN, Easley et al., 2012):
   - Slices continuous trades into equal-volume buckets (Volume Clock).
   - Classifies trade volume into buyer-initiated and seller-initiated flow.
   - Computes rolling VPIN across N recent completed buckets:
     VPIN = sum(|V_tau^B - V_tau^S|) / (N * V_bucket) in [0.0, 1.0]
   - Quantifies the presence of informed traders trading aggressively on private info.
3. Microstructure Predictive Shielding & Closed-Loop Integration:
   - Evaluates composite ToxicityLevel (NORMAL, ELEVATED_TOXICITY, CRITICAL_TOXICITY).
   - Informs P6 Slippage Compensator: dynamically scales up M_slip boost
     to avoid stepping into predatory toxic flow.
   - Informs E1 Smart Order Routing & P7 Circuit Breaker: triggers forward-looking
     execution throttling or halts aggressive sweeps before flash-crash damage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class ToxicityLevel(str, Enum):
    """Classification of order flow toxicity severity."""
    NORMAL = "NORMAL"
    ELEVATED_TOXICITY = "ELEVATED_TOXICITY"
    CRITICAL_TOXICITY = "CRITICAL_TOXICITY"


class TradeDirection(str, Enum):
    """Direction of trade initiation."""
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"


@dataclass
class OrderBookDepthSnapshot:
    """Real-time top-of-book or Level-2 depth observation."""
    symbol: str
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float
    timestamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        self.symbol = self.symbol.upper()

    @property
    def mid_price(self) -> float:
        if self.bid_price > 0 and self.ask_price > 0:
            return (self.bid_price + self.ask_price) / 2.0
        return max(self.bid_price, self.ask_price)

    @property
    def spread_bps(self) -> float:
        mid = self.mid_price
        if mid <= 0:
            return 0.0
        return max(0.0, ((self.ask_price - self.bid_price) / mid) * 10000.0)

    @property
    def obi(self) -> float:
        """Normalized Order Book Imbalance (OBI) in [-1.0, 1.0]."""
        total_depth = self.bid_size + self.ask_size
        if total_depth <= 0:
            return 0.0
        return (self.bid_size - self.ask_size) / total_depth


@dataclass
class TradeTick:
    """Individual trade fill record on the tape."""
    symbol: str
    price: float
    volume: float
    timestamp: Optional[datetime] = None
    direction: Optional[TradeDirection] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        self.symbol = self.symbol.upper()


@dataclass
class VolumeBucket:
    """Discrete volume bucket in the VPIN volume clock."""
    bucket_index: int
    target_volume: float
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    is_complete: bool = False

    @property
    def current_volume(self) -> float:
        return self.buy_volume + self.sell_volume

    @property
    def remaining_capacity(self) -> float:
        return max(0.0, self.target_volume - self.current_volume)

    @property
    def absolute_imbalance(self) -> float:
        return abs(self.buy_volume - self.sell_volume)


@dataclass
class ToxicityAssessment:
    """Comprehensive microstructure toxicity evaluation for a symbol."""
    symbol: str
    vpin: float
    order_book_imbalance: float
    toxicity_level: ToxicityLevel
    is_toxic: bool
    recommended_action: str
    recommended_slippage_boost: float
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "vpin": round(self.vpin, 4),
            "order_book_imbalance": round(self.order_book_imbalance, 4),
            "toxicity_level": self.toxicity_level.value,
            "is_toxic": self.is_toxic,
            "recommended_action": self.recommended_action,
            "recommended_slippage_boost": round(self.recommended_slippage_boost, 4),
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class OrderBookToxicityDetectorService:
    """
    E3 Engine: Order Book Imbalance & VPIN Toxicity Detector.
    Real-time monitoring of informed order flow and queue depth dynamics.
    """

    DEFAULT_BUCKET_SIZE = 1000.0           # Default shares per VPIN bucket
    DEFAULT_WINDOW_BUCKETS = 20            # Number of completed buckets in rolling window
    DEFAULT_ELEVATED_VPIN_THRESHOLD = 0.50 # Moderate informed trading alert
    DEFAULT_CRITICAL_VPIN_THRESHOLD = 0.75 # Severe toxic flow flash-crash danger
    DEFAULT_EXTREME_OBI_THRESHOLD = 0.60   # Extreme book queue skewness
    DEFAULT_MAX_SLIPPAGE_BOOST = 1.0       # Max extra multiplier boost for P6 compensator

    def __init__(
        self,
        user_id: str = "default_user",
        settings_repo: Any = None,
        circuit_breaker_service: Any = None,
        slippage_compensator: Any = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_repo = settings_repo
        self.circuit_breaker_service = circuit_breaker_service
        self.slippage_compensator = slippage_compensator

        # Internal state per symbol
        self._latest_depth: Dict[str, OrderBookDepthSnapshot] = {}
        self._completed_buckets: Dict[str, List[VolumeBucket]] = {}
        self._active_buckets: Dict[str, VolumeBucket] = {}
        self._bucket_counters: Dict[str, int] = {}
        self._last_trade_prices: Dict[str, float] = {}

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
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
        return self._get_setting("toxicity_detector_enabled", True, bool)

    @property
    def bucket_size(self) -> float:
        return float(self._get_setting("vpin_bucket_size", self.DEFAULT_BUCKET_SIZE, float))

    @property
    def window_buckets(self) -> int:
        return int(self._get_setting("vpin_window_buckets", self.DEFAULT_WINDOW_BUCKETS, int))

    @property
    def elevated_vpin_threshold(self) -> float:
        return float(self._get_setting("vpin_elevated_threshold", self.DEFAULT_ELEVATED_VPIN_THRESHOLD, float))

    @property
    def critical_vpin_threshold(self) -> float:
        return float(self._get_setting("vpin_critical_threshold", self.DEFAULT_CRITICAL_VPIN_THRESHOLD, float))

    @property
    def extreme_obi_threshold(self) -> float:
        return float(self._get_setting("obi_extreme_threshold", self.DEFAULT_EXTREME_OBI_THRESHOLD, float))

    @property
    def max_slippage_boost(self) -> float:
        return float(self._get_setting("toxicity_slippage_boost_max", self.DEFAULT_MAX_SLIPPAGE_BOOST, float))

    def record_quote(self, snapshot: OrderBookDepthSnapshot) -> None:
        """Ingest real-time top-of-book depth update."""
        sym = snapshot.symbol.upper()
        self._latest_depth[sym] = snapshot

    def record_trade(self, tick: TradeTick) -> None:
        """
        Ingest a trade fill into the VPIN volume clock buckets.
        Classifies buyer-initiated vs seller-initiated volume using tick rule or direction.
        """
        sym = tick.symbol.upper()
        volume = max(0.0, float(tick.volume))
        if volume <= 0:
            return

        # 1. Classify Direction
        direction = tick.direction
        if direction is None or direction == TradeDirection.UNKNOWN:
            # Tick rule fallback: compare against last trade price or quote mid
            last_px = self._last_trade_prices.get(sym)
            if last_px is not None:
                if tick.price > last_px:
                    direction = TradeDirection.BUY
                elif tick.price < last_px:
                    direction = TradeDirection.SELL
                else:
                    direction = TradeDirection.BUY  # Zero-tick continuation default
            else:
                # Compare against mid price if available
                depth = self._latest_depth.get(sym)
                if depth and depth.mid_price > 0:
                    direction = TradeDirection.BUY if tick.price >= depth.mid_price else TradeDirection.SELL
                else:
                    direction = TradeDirection.BUY

        self._last_trade_prices[sym] = tick.price

        # 2. Allocate to volume buckets
        target_bucket_size = max(1.0, self.bucket_size)
        rem_vol = volume

        while rem_vol > 0:
            active = self._get_or_create_active_bucket(sym, target_bucket_size)
            space = active.remaining_capacity

            fill_in_this_bucket = min(rem_vol, space)
            if direction == TradeDirection.BUY:
                active.buy_volume += fill_in_this_bucket
            else:
                active.sell_volume += fill_in_this_bucket

            rem_vol -= fill_in_this_bucket

            if active.remaining_capacity <= 1e-6:
                # Bucket is complete, move to completed list
                active.is_complete = True
                completed = self._completed_buckets.setdefault(sym, [])
                completed.append(active)

                # Keep only rolling window of buckets
                max_history = self.window_buckets * 2
                if len(completed) > max_history:
                    self._completed_buckets[sym] = completed[-max_history:]

                # Reset active bucket
                self._bucket_counters[sym] = self._bucket_counters.get(sym, 0) + 1
                self._active_buckets[sym] = VolumeBucket(
                    bucket_index=self._bucket_counters[sym],
                    target_volume=target_bucket_size,
                )

    def _get_or_create_active_bucket(self, symbol: str, target_size: float) -> VolumeBucket:
        if symbol not in self._active_buckets:
            counter = self._bucket_counters.get(symbol, 0) + 1
            self._bucket_counters[symbol] = counter
            self._active_buckets[symbol] = VolumeBucket(
                bucket_index=counter,
                target_volume=target_size,
            )
        return self._active_buckets[symbol]

    def calculate_obi(self, symbol: str) -> float:
        """Calculate Order Book Imbalance (OBI) from latest snapshot."""
        sym = symbol.upper()
        depth = self._latest_depth.get(sym)
        if not depth:
            return 0.0
        return depth.obi

    def calculate_vpin(self, symbol: str) -> float:
        """
        Calculate rolling VPIN over N recent completed buckets.
        Formula: sum(|V_tau^B - V_tau^S|) / (N * V_bucket)
        """
        sym = symbol.upper()
        completed = self._completed_buckets.get(sym, [])
        window_n = max(1, self.window_buckets)

        if not completed:
            # Fall back to active bucket imbalance ratio if no completed buckets yet
            active = self._active_buckets.get(sym)
            if active and active.current_volume > 0:
                return active.absolute_imbalance / active.current_volume
            return 0.0

        sample_buckets = completed[-window_n:]
        total_imbalance = sum(b.absolute_imbalance for b in sample_buckets)
        total_volume = sum(b.current_volume for b in sample_buckets)

        if total_volume <= 0:
            return 0.0

        vpin = total_imbalance / total_volume
        return max(0.0, min(1.0, vpin))

    def evaluate_toxicity(
        self,
        symbol: str,
        proposed_action: Optional[str] = None,
    ) -> ToxicityAssessment:
        """
        Comprehensive toxicity assessment combining VPIN and OBI skew.
        Optionally evaluates adverse selection risk relative to proposed trade direction (BUY/SELL).
        """
        sym = symbol.upper()

        if not self.is_enabled:
            return ToxicityAssessment(
                symbol=sym,
                vpin=0.0,
                order_book_imbalance=0.0,
                toxicity_level=ToxicityLevel.NORMAL,
                is_toxic=False,
                recommended_action="PROCEED",
                recommended_slippage_boost=0.0,
                details={"reason": "Toxicity detector disabled via configuration"},
            )

        vpin = self.calculate_vpin(sym)
        obi = self.calculate_obi(sym)
        depth = self._latest_depth.get(sym)

        crit_vpin = self.critical_vpin_threshold
        elev_vpin = self.elevated_vpin_threshold
        ext_obi = self.extreme_obi_threshold

        # Directional adverse selection check if proposed action is given
        is_adverse_skew = False
        if proposed_action:
            act_str = str(proposed_action).upper()
            # If buying when book is overwhelmingly seller-depleted or huge selling pressure
            if "BUY" in act_str and obi < -ext_obi:
                is_adverse_skew = True
            elif "SELL" in act_str and obi > ext_obi:
                is_adverse_skew = True

        # Level Decision Logic
        if vpin >= crit_vpin or (vpin >= elev_vpin and is_adverse_skew) or (vpin >= elev_vpin and abs(obi) >= 0.85):
            level = ToxicityLevel.CRITICAL_TOXICITY
            is_toxic = True
            action = "HALT_AGGRESSIVE_FLOW"
            # Full slippage boost
            slippage_boost = self.max_slippage_boost
        elif vpin >= elev_vpin or abs(obi) >= ext_obi or is_adverse_skew:
            level = ToxicityLevel.ELEVATED_TOXICITY
            is_toxic = True
            action = "THROTTLE_SLICES"
            # Scaled slippage boost based on VPIN excess
            vpin_scale = max(0.0, (vpin - elev_vpin) / max(0.01, (crit_vpin - elev_vpin)))
            slippage_boost = min(self.max_slippage_boost, 0.3 + 0.7 * vpin_scale)
        else:
            level = ToxicityLevel.NORMAL
            is_toxic = False
            action = "PROCEED"
            slippage_boost = 0.0

        details = {
            "vpin_value": round(vpin, 4),
            "obi_value": round(obi, 4),
            "completed_buckets_count": len(self._completed_buckets.get(sym, [])),
            "is_adverse_skew": is_adverse_skew,
            "top_spread_bps": round(depth.spread_bps, 2) if depth else None,
            "bid_size": depth.bid_size if depth else None,
            "ask_size": depth.ask_size if depth else None,
        }

        assessment = ToxicityAssessment(
            symbol=sym,
            vpin=vpin,
            order_book_imbalance=obi,
            toxicity_level=level,
            is_toxic=is_toxic,
            recommended_action=action,
            recommended_slippage_boost=slippage_boost,
            details=details,
        )

        # Closed-loop notification to P6 Slippage Compensator if attached
        if self.slippage_compensator is not None and slippage_boost > 0:
            try:
                # Add extra safety multiplier on top of existing baseline
                curr_mult = self.slippage_compensator.get_spillover_multiplier(sym)
                self.slippage_compensator.set_spillover_multiplier(sym, max(curr_mult, 1.0 + slippage_boost))
            except Exception as e:
                logger.warning(f"Failed to propagate slippage boost to P6 for {sym}: {e}")

        return assessment

    def is_execution_halted(self, symbol: str) -> bool:
        """
        Check whether microstructure toxicity indicates an urgent execution halt.
        Triggered when ToxicityLevel is CRITICAL_TOXICITY.
        """
        assessment = self.evaluate_toxicity(symbol)
        return assessment.toxicity_level == ToxicityLevel.CRITICAL_TOXICITY

    def get_slippage_boost(self, symbol: str) -> float:
        """Retrieve recommended slippage multiplier boost for the symbol."""
        assessment = self.evaluate_toxicity(symbol)
        return assessment.recommended_slippage_boost

    def clear_symbol_state(self, symbol: str) -> None:
        """Reset depth and bucket state for a symbol."""
        sym = symbol.upper()
        self._latest_depth.pop(sym, None)
        self._completed_buckets.pop(sym, None)
        self._active_buckets.pop(sym, None)
        self._bucket_counters.pop(sym, None)
        self._last_trade_prices.pop(sym, None)
