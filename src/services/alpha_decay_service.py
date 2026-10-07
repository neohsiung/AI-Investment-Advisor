"""
Holding Alpha Decay Service
持倉 Alpha 鈍化衰減與動能輪動服務
=============================================================================
Manages holding tenure and alpha decay for active portfolio positions:
1. Holding Duration Tracking:
   Measures holding days since position inception.
2. Momentum Stall & Alpha Stagnation Detection:
   Positions held > 20 trading days that underperform the benchmark,
   fall below their 20-day moving average, or show weakening momentum
   are flagged for alpha decay.
3. Exponential Alpha Decay Function:
   DecayFactor = max(Floor, exp(-lambda * (T_hold - T_start)))
4. Compounding Winner Exemption:
   Holdings that maintain strong positive alpha, price > SMA20, and healthy
   momentum receive DecayFactor = 1.0 (100% winner protection for compounding).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


@dataclass
class AlphaDecayAssessment:
    """Assessment of a position's holding duration, alpha health, and decay factor."""
    ticker: str
    holding_days: int
    has_decay: bool
    decay_factor: float
    is_stagnant: bool
    reason: str
    alpha_pct: Optional[float] = None
    is_long_term_winner: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)


class AlphaDecayService:
    """
    Monitors position age and applies dynamic alpha decay to stagnant holdings,
    gently pruning underperforming positions to liberate liquidity for fresh leaders.
    持倉 Alpha 鈍化衰減管理服務。
    """

    DEFAULT_DECAY_START_DAYS = 20     # Grace period before decay kicks in (trading days)
    DEFAULT_DECAY_RATE = 0.035        # Exponential decay rate lambda (halves in ~20 days)
    DEFAULT_DECAY_FLOOR = 0.40        # Minimum decay floor (prevents immediate collapse to 0)

    def __init__(
        self,
        user_id: str,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        if settings_service:
            self.settings_service = settings_service
        else:
            from src.services.settings_service import SettingsService
            self.settings_service = SettingsService(user_id=self.user_id)
        self.market_data_service = market_data_service

    def calculate_holding_days(
        self,
        open_date: Optional[datetime],
        now: Optional[datetime] = None,
    ) -> int:
        """
        Calculate the number of calendar/trading days a position has been held.
        """
        if not open_date:
            return 0

        current_dt = now or datetime.now(timezone.utc)
        if open_date.tzinfo is None:
            # Assume UTC if naive
            open_dt = open_date.replace(tzinfo=timezone.utc)
        else:
            open_dt = open_date

        delta = current_dt - open_dt
        return max(0, delta.days)

    def evaluate_holding_decay(
        self,
        ticker: str,
        holding_days: int,
        current_price: float = 0.0,
        sma_20: float = 0.0,
        rsi: float = 50.0,
        macd_status: str = "neutral",
        holding_return_pct: Optional[float] = None,
        benchmark_return_pct: Optional[float] = None,
        is_long_term_winner: bool = False,
        decay_start_days: Optional[int] = None,
    ) -> AlphaDecayAssessment:
        """
        Evaluate if a holding qualifies for alpha decay or winner compounding protection.
        """
        try:
            if decay_start_days is not None:
                start_days = int(decay_start_days)
            else:
                start_days = int(self.settings_service.get_setting("holding_decay_start_days", self.DEFAULT_DECAY_START_DAYS))
        except Exception:
            start_days = decay_start_days if decay_start_days is not None else self.DEFAULT_DECAY_START_DAYS

        try:
            decay_rate = float(self.settings_service.get_setting("holding_decay_rate", self.DEFAULT_DECAY_RATE))
        except Exception:
            decay_rate = self.DEFAULT_DECAY_RATE

        try:
            decay_floor = float(self.settings_service.get_setting("holding_decay_floor", self.DEFAULT_DECAY_FLOOR))
        except Exception:
            decay_floor = self.DEFAULT_DECAY_FLOOR

        alpha_pct: Optional[float] = None
        if holding_return_pct is not None and benchmark_return_pct is not None:
            alpha_pct = round(float(holding_return_pct) - float(benchmark_return_pct), 4)

        # 1. Grace Period Check
        if holding_days <= start_days:
            return AlphaDecayAssessment(
                ticker=ticker,
                holding_days=holding_days,
                has_decay=False,
                decay_factor=1.0,
                is_stagnant=False,
                alpha_pct=alpha_pct,
                is_long_term_winner=is_long_term_winner,
                reason=f"持倉 {holding_days} 天未達衰減考覈門檻 (<= {start_days} 天)，維持基準置信度",
                metrics={"holding_days": holding_days, "start_days": start_days},
            )

        # 2. Check for Stagnation / Momentum Stall
        is_below_20ma = (sma_20 > 0.0 and current_price > 0.0 and current_price < (sma_20 * 0.99))
        is_weak_rsi = (rsi < 45.0)
        is_bearish_macd = ("bearish" in str(macd_status).lower())
        is_negative_alpha = (alpha_pct is not None and alpha_pct < -0.01)

        # If holding is a certified long-term winner with price above 20MA and healthy RSI, protect it!
        has_healthy_momentum = (not is_below_20ma and not is_weak_rsi and not is_negative_alpha)

        if has_healthy_momentum or (is_long_term_winner and not is_below_20ma and not is_bearish_macd):
            return AlphaDecayAssessment(
                ticker=ticker,
                holding_days=holding_days,
                has_decay=False,
                decay_factor=1.0,
                is_stagnant=False,
                alpha_pct=alpha_pct,
                is_long_term_winner=is_long_term_winner,
                reason=f"持倉 {holding_days} 天動能健康且維持正向 Alpha (價格高於20MA，RSI={rsi:.1f})，全額保護長線複利",
                metrics={
                    "holding_days": holding_days,
                    "alpha_pct": alpha_pct,
                    "is_below_20ma": is_below_20ma,
                    "rsi": rsi,
                },
            )

        # 3. Apply Exponential Alpha Decay
        excess_days = holding_days - start_days
        raw_factor = math.exp(-decay_rate * excess_days)
        decay_factor = round(max(decay_floor, min(1.0, raw_factor)), 4)
        has_decay = decay_factor < 0.999

        stagnation_reasons = []
        if is_negative_alpha and alpha_pct is not None:
            stagnation_reasons.append(f"相對大盤 Alpha 落後 ({alpha_pct:+.1%})")
        if is_below_20ma:
            stagnation_reasons.append(f"跌破 20 日均線 (${sma_20:.2f})")
        if is_weak_rsi:
            stagnation_reasons.append(f"動能冷卻 (RSI={rsi:.1f})")
        if is_bearish_macd:
            stagnation_reasons.append("MACD 偏空死叉")

        reason_str = "; ".join(stagnation_reasons) if stagnation_reasons else "橫盤停滯死資本"
        reason = (
            f"持倉 {holding_days} 天動能鈍化 ({reason_str})，"
            f"啟動 Alpha 衰減機制 (衰減因子 {decay_factor:.2f})，引導資本自然輪動"
        )

        return AlphaDecayAssessment(
            ticker=ticker,
            holding_days=holding_days,
            has_decay=has_decay,
            decay_factor=decay_factor,
            is_stagnant=True,
            alpha_pct=alpha_pct,
            is_long_term_winner=is_long_term_winner,
            reason=reason,
            metrics={
                "holding_days": holding_days,
                "excess_days": excess_days,
                "decay_factor": decay_factor,
                "alpha_pct": alpha_pct,
                "is_below_20ma": is_below_20ma,
                "rsi": rsi,
            },
        )

    def apply_decay_to_confidence(self, base_confidence: float, decay_factor: float) -> float:
        """
        Applies decay factor to a confidence score, ensuring a safe floor.
        """
        norm_conf = base_confidence / 10.0 if base_confidence > 1.0 else base_confidence
        decayed = max(0.10, norm_conf * decay_factor)
        return round(decayed * 10.0 if base_confidence > 1.0 else decayed, 4)
