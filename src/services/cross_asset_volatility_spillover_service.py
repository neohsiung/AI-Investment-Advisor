"""
M7: Cross-Asset Volatility Spillover & Contagion Shielder Service
=============================================================================
Monitors intraday liquidity shocks and circuit breaker events across assets.
When a bellwether/leader ticker halts, propagates dynamic volatility spillover
penalties to correlated cluster peers and industry basket holdings:
1. Cross-Asset Volatility Spillover Matrix:
   - Tracks 60-day Pearson/Spearman return correlation matrix (rho_ij)
   - Sector/Industry affiliation co-membership weights (w_sector)
   - Directional spillover propagation factor:
       S_ij = alpha_spill * |rho_ij| + (1 - alpha_spill) * delta_sector(i, j)
2. Dynamic Slippage Multiplier Elevation (P6 Feedback):
   - Injects temporary spillover multiplier M_spill into AdaptiveExecutionSlippageCompensator
   - Increases execution slice count and window to dodge toxic contagion waves
3. Dynamic Cash Buffer Expansion (M1 Feedback):
   - Temporarily expands defensive cash buffer proportional to contagion index
4. Auto-Decay & Manual Reversion:
   - Spillover shocks decay exponentially with a configurable half-life (e.g. 30 mins)
   - Automatically synchronizes with P7 Circuit Breaker state changes (Halt / Resume)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.services.intraday_liquidity_circuit_breaker_service import (
    CircuitBreakerState,
    CircuitBreakerStatus,
    ShockTriggerType,
)

logger = logging.getLogger(__name__)


@dataclass
class ContagionSpilloverImpact:
    """Detailed spillover contagion impact metrics for a single peer ticker."""
    target_ticker: str
    source_ticker: str
    correlation: float
    same_sector: bool
    spillover_intensity: float  # [0.0, 1.0]
    elevated_slippage_multiplier: float  # e.g. 1.50x
    additional_cash_buffer_pct: float  # e.g. 0.05 (+5%)
    cooldown_until: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_ticker": self.target_ticker,
            "source_ticker": self.source_ticker,
            "correlation": round(self.correlation, 4),
            "same_sector": self.same_sector,
            "spillover_intensity": round(self.spillover_intensity, 4),
            "elevated_slippage_multiplier": round(self.elevated_slippage_multiplier, 3),
            "additional_cash_buffer_pct": round(self.additional_cash_buffer_pct, 4),
            "cooldown_until": self.cooldown_until,
            "reason": self.reason,
        }


@dataclass
class SpilloverContagionAssessment:
    """System-level assessment of active volatility contagion."""
    is_active: bool
    active_sources: List[str]
    total_impacted_tickers: int
    aggregate_cash_expansion_pct: float
    max_slippage_multiplier: float
    impacts: Dict[str, ContagionSpilloverImpact] = field(default_factory=dict)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_active": self.is_active,
            "active_sources": self.active_sources,
            "total_impacted_tickers": self.total_impacted_tickers,
            "aggregate_cash_expansion_pct": round(self.aggregate_cash_expansion_pct, 4),
            "max_slippage_multiplier": round(self.max_slippage_multiplier, 3),
            "impacts": {k: v.to_dict() for k, v in self.impacts.items()},
            "evaluated_at": self.evaluated_at,
        }


class CrossAssetVolatilitySpilloverService:
    """
    Cross-Asset Volatility Spillover & Contagion Shielder Orchestrator (M7).
    """

    DEFAULT_SPILLOVER_CORRELATION_WEIGHT = 0.70
    DEFAULT_SPILLOVER_SECTOR_WEIGHT = 0.30
    DEFAULT_SPILLOVER_THRESHOLD = 0.40  # Minimum intensity to trigger contagion protection
    DEFAULT_MAX_SLIPPAGE_ELEVATION = 2.50
    DEFAULT_MAX_CASH_EXPANSION_PCT = 0.15  # Up to +15% extra defensive cash
    DEFAULT_DECAY_HALF_LIFE_MINUTES = 30.0

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        circuit_breaker_service: Optional[Any] = None,
        slippage_compensator: Optional[Any] = None,
        ticker_universe_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self.circuit_breaker_service = circuit_breaker_service
        self.slippage_compensator = slippage_compensator
        self.ticker_universe_service = ticker_universe_service

        # Active contagion shocks: {source_ticker: (triggered_at, cooldown_until, trigger_reason)}
        self._active_shocks: Dict[str, Tuple[datetime, datetime, str]] = {}

        # Static / dynamic correlation matrix cache: {ticker_a: {ticker_b: corr}}
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}
        # Sector metadata cache: {ticker: sector}
        self._sector_map: Dict[str, str] = {}

        # Auto-subscribe to circuit breaker if provided
        if self.circuit_breaker_service is not None and hasattr(self.circuit_breaker_service, "register_listener"):
            self.circuit_breaker_service.register_listener(self)

    def _get_setting(self, key: str, default: Any, val_type: type = float) -> Any:
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
        return self._get_setting("volatility_spillover_enabled", True, bool)

    @property
    def spillover_threshold(self) -> float:
        return float(self._get_setting("volatility_spillover_threshold", self.DEFAULT_SPILLOVER_THRESHOLD, float))

    @property
    def max_slippage_elevation(self) -> float:
        return float(self._get_setting("volatility_spillover_max_slippage_elevation", self.DEFAULT_MAX_SLIPPAGE_ELEVATION, float))

    @property
    def max_cash_expansion_pct(self) -> float:
        return float(self._get_setting("volatility_spillover_max_cash_expansion_pct", self.DEFAULT_MAX_CASH_EXPANSION_PCT, float))

    @property
    def decay_half_life_minutes(self) -> float:
        return float(self._get_setting("volatility_spillover_half_life_minutes", self.DEFAULT_DECAY_HALF_LIFE_MINUTES, float))

    def update_correlations(self, matrix: Dict[str, Dict[str, float]]) -> None:
        """Update or seed correlation matrix."""
        for t1, row in matrix.items():
            sym1 = t1.upper().strip()
            self._correlation_matrix.setdefault(sym1, {})
            for t2, corr in row.items():
                sym2 = t2.upper().strip()
                self._correlation_matrix[sym1][sym2] = float(corr)

    def update_sector_map(self, sectors: Dict[str, str]) -> None:
        """Update or seed ticker-to-sector affiliations."""
        for t, sec in sectors.items():
            self._sector_map[t.upper().strip()] = str(sec).strip()

    def on_circuit_breaker_triggered(self, status: CircuitBreakerStatus) -> None:
        """
        Callback invoked by IntradayLiquidityCircuitBreakerService when a breaker state transitions.
        """
        sym = status.symbol.upper().strip()
        if status.state in (CircuitBreakerState.TRIGGERED, CircuitBreakerState.COOLDOWN):
            now = status.triggered_at or datetime.now(timezone.utc)
            until = status.cooldown_until or (now + timedelta(minutes=15))
            reason = status.reason or "Intraday Liquidity Shock Tripped"
            self.register_shock(source_ticker=sym, triggered_at=now, cooldown_until=until, reason=reason)
        elif status.state == CircuitBreakerState.NORMAL:
            self.remove_shock(source_ticker=sym)

    def register_shock(
        self,
        source_ticker: str,
        triggered_at: Optional[datetime] = None,
        cooldown_until: Optional[datetime] = None,
        reason: str = "Market liquidity shock",
    ) -> SpilloverContagionAssessment:
        """
        Record a liquidity shock from a source ticker and propagate contagion effects.
        """
        sym = source_ticker.upper().strip()
        now = triggered_at or datetime.now(timezone.utc)
        until = cooldown_until or (now + timedelta(minutes=15))

        self._active_shocks[sym] = (now, until, reason)
        logger.warning(
            f"⚡ Volatility Spillover Shielder: Registered shock on source '{sym}' until {until.isoformat()} ({reason})"
        )

        return self.evaluate_contagion()

    def remove_shock(self, source_ticker: str) -> SpilloverContagionAssessment:
        """Remove a shock source (e.g. upon resume) and re-evaluate contagion."""
        sym = source_ticker.upper().strip()
        if sym in self._active_shocks:
            del self._active_shocks[sym]
            logger.info(f"🟢 Volatility Spillover Shielder: Removed shock on source '{sym}'")
        return self.evaluate_contagion()

    def clear_all_shocks(self) -> None:
        """Clear all active shocks."""
        self._active_shocks.clear()
        if self.slippage_compensator is not None and hasattr(self.slippage_compensator, "clear_spillover_multipliers"):
            self.slippage_compensator.clear_spillover_multipliers()

    def _get_correlation(self, sym1: str, sym2: str) -> float:
        """Fetch correlation between two tickers with fallback."""
        if sym1 == sym2:
            return 1.0
        row = self._correlation_matrix.get(sym1, {})
        if sym2 in row:
            return row[sym2]
        row2 = self._correlation_matrix.get(sym2, {})
        if sym1 in row2:
            return row2[sym1]
        # Same sector fallback
        sec1 = self._sector_map.get(sym1)
        sec2 = self._sector_map.get(sym2)
        if sec1 and sec2 and sec1 == sec2:
            return 0.55
        return 0.30

    def _is_same_sector(self, sym1: str, sym2: str) -> bool:
        sec1 = self._sector_map.get(sym1)
        sec2 = self._sector_map.get(sym2)
        return bool(sec1 and sec2 and sec1 == sec2)

    def evaluate_contagion(
        self,
        universe_tickers: Optional[List[str]] = None,
    ) -> SpilloverContagionAssessment:
        """
        Evaluate current cross-asset contagion spread across active universe tickers.
        Calculates spillover intensity, elevated slippage multiplier, and extra cash buffer.
        """
        now = datetime.now(timezone.utc)
        # 1. Clean expired shocks
        expired = [
            src for src, (t_start, t_until, _) in self._active_shocks.items()
            if t_until is not None and now >= t_until
        ]
        for src in expired:
            del self._active_shocks[src]

        if not self.is_enabled or not self._active_shocks:
            # Revert any elevated multipliers in compensator
            if self.slippage_compensator is not None and hasattr(self.slippage_compensator, "clear_spillover_multipliers"):
                self.slippage_compensator.clear_spillover_multipliers()

            return SpilloverContagionAssessment(
                is_active=False,
                active_sources=[],
                total_impacted_tickers=0,
                aggregate_cash_expansion_pct=0.0,
                max_slippage_multiplier=1.0,
                impacts={},
            )

        # 2. Determine target evaluation pool
        all_tickers = set(universe_tickers or [])
        # Include correlation matrix keys and sector map keys
        all_tickers.update(self._correlation_matrix.keys())
        all_tickers.update(self._sector_map.keys())

        if not all_tickers:
            # Default to active sources if universe is empty
            all_tickers = set(self._active_shocks.keys())

        impacts: Dict[str, ContagionSpilloverImpact] = {}
        active_sources = list(self._active_shocks.keys())
        half_life_secs = max(60.0, self.decay_half_life_minutes * 60.0)

        # 3. Propagate spillover per target asset
        for target in sorted(all_tickers):
            target_sym = target.upper().strip()
            # If target itself is a halted source, skip peer elevation (it is directly halted)
            if target_sym in self._active_shocks:
                continue

            max_intensity = 0.0
            best_source = ""
            best_corr = 0.0
            best_same_sec = False
            best_until_str: Optional[str] = None
            best_reason = ""

            for src, (t_start, t_until, reason) in self._active_shocks.items():
                if src == "GLOBAL":
                    # Global halt trips maximum contagion across all assets
                    corr = 1.0
                    same_sec = True
                    raw_intensity = 1.0
                else:
                    corr = self._get_correlation(src, target_sym)
                    same_sec = self._is_same_sector(src, target_sym)
                    sec_bonus = 1.0 if same_sec else 0.0
                    # Composite intensity formula: 70% correlation + 30% sector co-membership
                    raw_intensity = (
                        self.DEFAULT_SPILLOVER_CORRELATION_WEIGHT * abs(corr)
                        + self.DEFAULT_SPILLOVER_SECTOR_WEIGHT * sec_bonus
                    )

                # Time decay since shock inception
                elapsed_secs = max(0.0, (now - t_start).total_seconds())
                decay_factor = math.exp(-math.log(2.0) * (elapsed_secs / half_life_secs))
                decayed_intensity = max(0.0, min(1.0, raw_intensity * decay_factor))

                if decayed_intensity > max_intensity:
                    max_intensity = decayed_intensity
                    best_source = src
                    best_corr = corr
                    best_same_sec = same_sec
                    best_until_str = t_until.isoformat() if t_until else None
                    best_reason = f"Volatility spillover from {src} ({reason})"

            # If intensity passes threshold, assign contagion protection
            if max_intensity >= self.spillover_threshold:
                # Slippage multiplier: scale from 1.0 up to max_slippage_elevation
                # M_spill = 1.0 + (max_elevation - 1.0) * intensity
                elevated_multiplier = 1.0 + (self.max_slippage_elevation - 1.0) * max_intensity
                # Cash expansion: scale up to max_cash_expansion_pct
                extra_cash_pct = self.max_cash_expansion_pct * max_intensity

                impact = ContagionSpilloverImpact(
                    target_ticker=target_sym,
                    source_ticker=best_source,
                    correlation=best_corr,
                    same_sector=best_same_sec,
                    spillover_intensity=max_intensity,
                    elevated_slippage_multiplier=round(elevated_multiplier, 3),
                    additional_cash_buffer_pct=round(extra_cash_pct, 4),
                    cooldown_until=best_until_str,
                    reason=best_reason,
                )
                impacts[target_sym] = impact

                # Synchronize to P6 Slippage Compensator if attached
                if self.slippage_compensator is not None and hasattr(self.slippage_compensator, "set_spillover_multiplier"):
                    self.slippage_compensator.set_spillover_multiplier(target_sym, elevated_multiplier)
            else:
                # Remove spillover multiplier if intensity subsided below threshold
                if self.slippage_compensator is not None and hasattr(self.slippage_compensator, "set_spillover_multiplier"):
                    self.slippage_compensator.set_spillover_multiplier(target_sym, 1.0)

        # Compute aggregate metrics
        agg_cash = max([imp.additional_cash_buffer_pct for imp in impacts.values()] or [0.0])
        max_mult = max([imp.elevated_slippage_multiplier for imp in impacts.values()] or [1.0])

        return SpilloverContagionAssessment(
            is_active=len(impacts) > 0,
            active_sources=active_sources,
            total_impacted_tickers=len(impacts),
            aggregate_cash_expansion_pct=agg_cash,
            max_slippage_multiplier=max_mult,
            impacts=impacts,
        )

    def get_extra_defensive_cash_pct(self) -> float:
        """
        Helper for M1 / D1 Adaptive Intelligence: returns additional cash reserve percentage [0.0, 0.15].
        """
        assessment = self.evaluate_contagion()
        return assessment.aggregate_cash_expansion_pct
