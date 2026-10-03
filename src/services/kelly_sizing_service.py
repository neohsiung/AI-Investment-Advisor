"""
Dynamic Fractional Kelly Sizing Service
動態分數凱利部位定價服務
=============================================================================
Computes mathematically sound position sizing based on rolling realized performance:
1. Historical Win Rate (p) and Payoff Ratio (b = AvgWin / AvgLoss).
2. Full Kelly Criterion:
   f* = (p * b - (1 - p)) / b
3. Fractional Kelly Damping:
   f_fractional = multiplier * f* (default 0.25 = Quarter-Kelly)
4. Rigid Boundary Constraints:
   f_min (default 2%) <= recommended_size <= f_max (default 20%)
5. Sample Size Safeguard:
   Smooth fallback to prior default sizing if realized sample trades < min_trades (default 10).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


@dataclass
class KellyAssessment:
    """Quantitative assessment of trading edge and fractional Kelly position size."""
    win_rate: float
    win_loss_ratio: float
    full_kelly: float
    fractional_kelly: float
    recommended_size: float
    sample_count: int
    is_statistically_valid: bool
    expected_edge: float
    reason: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "win_rate": round(self.win_rate, 4),
            "win_loss_ratio": round(self.win_loss_ratio, 4),
            "full_kelly": round(self.full_kelly, 4),
            "fractional_kelly": round(self.fractional_kelly, 4),
            "recommended_size": round(self.recommended_size, 4),
            "sample_count": self.sample_count,
            "is_statistically_valid": self.is_statistically_valid,
            "expected_edge": round(self.expected_edge, 4),
            "reason": self.reason,
            "details": self.details,
        }


class KellySizingService:
    """
    Calculates dynamic fractional Kelly sizing for trading candidates and portfolio assets.
    動態分數凱利注碼精算服務。
    """

    DEFAULT_FRACTION_MULTIPLIER = 0.25   # Quarter-Kelly
    DEFAULT_MIN_TRADES = 10              # Minimum sample size before activating Kelly
    DEFAULT_MIN_POSITION = 0.02          # 2.0% floor for positive edge trades
    DEFAULT_MAX_POSITION = 0.20          # 20.0% hard cap
    DEFAULT_LOOKBACK_DAYS = 90           # 90-day evaluation window

    def __init__(
        self,
        user_id: str = "default_user",
        settings_service: Any | None = None,
        outcome_repo: Any | None = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.settings_service = settings_service
        self.outcome_repo = outcome_repo

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service is not None:
            try:
                val = self.settings_service.get_setting(key)
                if val is not None:
                    return type(default)(val)
            except Exception as e:  # noqa: BLE001
                logger.debug("Failed to read setting %s: %s", key, e)
        return default

    @property
    def fraction_multiplier(self) -> float:
        return float(self._get_setting("kelly_fraction_multiplier", self.DEFAULT_FRACTION_MULTIPLIER))

    @property
    def min_trades(self) -> int:
        return int(self._get_setting("kelly_min_trades", self.DEFAULT_MIN_TRADES))

    @property
    def min_position_pct(self) -> float:
        return float(self._get_setting("kelly_min_position_pct", self.DEFAULT_MIN_POSITION))

    @property
    def max_position_pct(self) -> float:
        return float(self._get_setting("kelly_max_position_pct", self.DEFAULT_MAX_POSITION))

    @property
    def lookback_days(self) -> int:
        return int(self._get_setting("kelly_lookback_days", self.DEFAULT_LOOKBACK_DAYS))

    def calculate_from_metrics(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        sample_count: int = 10,
        default_prior_size: float = 0.10,
    ) -> KellyAssessment:
        """
        Calculate Kelly assessment from summary statistics:
        p: win rate (0.0 to 1.0)
        avg_win: average profit amount or percentage (>= 0)
        avg_loss: average loss amount or percentage (> 0)
        sample_count: total closed trades
        """
        p = max(0.0, min(1.0, float(win_rate)))
        w = max(0.0, float(avg_win))
        loss = abs(float(avg_loss))

        # Handle payoff ratio b = avg_win / avg_loss
        if loss > 1e-7:
            b = w / loss
        elif w > 0:
            b = 2.0  # Favorable default if zero losses recorded
        else:
            b = 1.0

        multiplier = self.fraction_multiplier
        min_pos = self.min_position_pct
        max_pos = self.max_position_pct
        min_tr = self.min_trades

        expected_edge = p * b - (1.0 - p)

        # Full Kelly formula: f* = (p * b - (1 - p)) / b = p - (1 - p) / b
        if b > 1e-7 and expected_edge > 0:
            full_kelly = expected_edge / b
            fractional_kelly = full_kelly * multiplier
        else:
            full_kelly = 0.0
            fractional_kelly = 0.0

        details = {
            "p": round(p, 4),
            "b": round(b, 4),
            "avg_win": round(w, 4),
            "avg_loss": round(loss, 4),
            "expected_edge": round(expected_edge, 4),
            "multiplier": multiplier,
            "min_trades_threshold": min_tr,
        }

        # Check sample size validity
        if sample_count < min_tr:
            fallback_size = max(min_pos, min(max_pos, default_prior_size))
            return KellyAssessment(
                win_rate=p,
                win_loss_ratio=b,
                full_kelly=full_kelly,
                fractional_kelly=fractional_kelly,
                recommended_size=round(fallback_size, 4),
                sample_count=sample_count,
                is_statistically_valid=False,
                expected_edge=expected_edge,
                reason=(
                    f"樣本數不足 ({sample_count} < {min_tr})，"
                    f"平滑回退至先驗預設基準 ({fallback_size:.1%})"
                ),
                details=details,
            )

        # Check edge
        if expected_edge <= 0 or full_kelly <= 0:
            return KellyAssessment(
                win_rate=p,
                win_loss_ratio=b,
                full_kelly=0.0,
                fractional_kelly=0.0,
                recommended_size=0.0,
                sample_count=sample_count,
                is_statistically_valid=True,
                expected_edge=expected_edge,
                reason=(
                    f"歷史交易無統計優勢 (勝率 {p:.1%}, 賠率 {b:.2f}, "
                    f"Edge {expected_edge:.3f} <= 0)，凱利建議部位為 0%"
                ),
                details=details,
            )

        # Positive edge with sufficient sample size: apply fractional Kelly and clamp boundaries
        recommended = max(min_pos, min(max_pos, fractional_kelly))
        return KellyAssessment(
            win_rate=p,
            win_loss_ratio=b,
            full_kelly=round(full_kelly, 4),
            fractional_kelly=round(fractional_kelly, 4),
            recommended_size=round(recommended, 4),
            sample_count=sample_count,
            is_statistically_valid=True,
            expected_edge=round(expected_edge, 4),
            reason=(
                f"動態凱利定價放行：勝率 {p:.1%}, 賠率 {b:.2f}, "
                f"全額凱利 {full_kelly:.1%}, 分數凱利 ({multiplier:.2f}x) -> {recommended:.1%}"
            ),
            details=details,
        )

    def calculate_from_trades(
        self,
        trades: list[dict[str, Any]],
        default_prior_size: float = 0.10,
    ) -> KellyAssessment:
        """
        Extract win rate and payoff ratio from a list of closed trades.
        Each trade dict may contain 'pnl' or 'pnl_pct' or 'net_return'.
        """
        closed_trades = []
        for t in trades:
            val = t.get("pnl")
            if val is None:
                val = t.get("pnl_pct")
            if val is None:
                val = t.get("net_return")
            if val is not None:
                try:
                    closed_trades.append(float(val))
                except (ValueError, TypeError):
                    continue

        n = len(closed_trades)
        if n == 0:
            return self.calculate_from_metrics(
                win_rate=0.50,
                avg_win=0.05,
                avg_loss=0.03,
                sample_count=0,
                default_prior_size=default_prior_size,
            )

        wins = [x for x in closed_trades if x > 0]
        losses = [abs(x) for x in closed_trades if x < 0]

        win_rate = len(wins) / n
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0

        return self.calculate_from_metrics(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sample_count=n,
            default_prior_size=default_prior_size,
        )

    def evaluate_from_decision_outcomes(
        self,
        ticker: str | None = None,
        lookback_days: int | None = None,
        default_prior_size: float = 0.10,
    ) -> KellyAssessment:
        """
        Query realized decision outcomes from database/repo and compute Kelly sizing.
        """
        days = lookback_days or self.lookback_days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        trades: list[dict[str, Any]] = []
        if self.outcome_repo is not None:
            try:
                records = self.outcome_repo.get_outcomes(
                    user_id=self.user_id,
                    ticker=ticker,
                    since=cutoff_date,
                )
                for r in records:
                    pnl = getattr(r, "pnl", None) or (r.get("pnl") if isinstance(r, dict) else None)
                    pnl_pct = getattr(r, "pnl_pct", None) or (r.get("pnl_pct") if isinstance(r, dict) else None)
                    trades.append({"pnl": pnl, "pnl_pct": pnl_pct})
            except Exception as e:  # noqa: BLE001
                logger.warning("Error fetching decision outcomes for Kelly sizing: %s", e)

        return self.calculate_from_trades(trades, default_prior_size=default_prior_size)

    def scale_target_allocations(
        self,
        base_weights: dict[str, float],
        ticker_assessments: dict[str, KellyAssessment],
        max_total_weight: float = 0.95,
    ) -> dict[str, float]:
        """
        Adjust unconstrained allocation weights based on individual Kelly sizing constraints.
        If a ticker has negative edge (recommended_size == 0), it is removed from allocation.
        Each remaining ticker's weight is capped by its recommended_size, then normalized.
        """
        if not base_weights:
            return {}

        adjusted = {}
        for ticker, weight in base_weights.items():
            if weight <= 0:
                continue
            assessment = ticker_assessments.get(ticker)
            if assessment is not None:
                if assessment.recommended_size <= 0:
                    logger.info("Ticker %s excluded from allocation: Kelly edge <= 0", ticker)
                    continue
                # Cap individual target weight by recommended Kelly limit
                adjusted[ticker] = min(weight, assessment.recommended_size)
            else:
                adjusted[ticker] = weight

        total = sum(adjusted.values())
        if total <= 0:
            return {}

        # Scale to max_total_weight if sum exceeds it
        if total > max_total_weight:
            scale = max_total_weight / total
            adjusted = {t: round(w * scale, 4) for t, w in adjusted.items()}
        else:
            adjusted = {t: round(w, 4) for t, w in adjusted.items()}

        return adjusted
