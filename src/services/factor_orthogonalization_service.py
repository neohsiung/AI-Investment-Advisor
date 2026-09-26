"""
Factor Orthogonalization & Multi-Collinearity Gate Service.
自研量化因子正交性檢定與多重共線性防護閘門服務。

Ensures that new candidate alpha factors promote to live ACTIVE status
only if their correlation with existing active factors is below the configured
threshold (default 0.65). Prevents duplicate momentum or valuation variants
from fragmenting capital allocation.
"""

import math
from typing import List, Dict, Any, Optional, Tuple
from src.utils.logger import setup_logger

logger = setup_logger("FactorOrthogonalizationService")

DEFAULT_MAX_CORRELATION = 0.65


class FactorOrthogonalizationService:
    """
    Checks cross-sectional and time-series orthogonality of factor candidates.
    檢定因子候選者與在線活躍因子之相關性與正交性。
    """

    def __init__(self, max_correlation: float = DEFAULT_MAX_CORRELATION) -> None:
        self.max_correlation = max_correlation

    @staticmethod
    def _extract_returns_series(record: Any) -> Dict[str, float]:
        """
        Extract date -> daily return map from an artifact record.
        Prioritizes shadow_tracking_log, then backtest_metrics.
        """
        returns_map: Dict[str, float] = {}

        # 1. Shadow tracking log
        shadow_log = getattr(record, "shadow_tracking_log", None) or []
        for entry in shadow_log:
            dt = entry.get("date") or entry.get("timestamp")
            if dt and "daily_pnl_pct" in entry:
                try:
                    returns_map[str(dt)[:10]] = float(entry["daily_pnl_pct"])
                except (ValueError, TypeError):
                    continue

        if returns_map:
            return returns_map

        # 2. Backtest returns if available
        metrics = getattr(record, "backtest_metrics", None) or {}
        daily_returns = metrics.get("daily_returns") or metrics.get("returns")
        if isinstance(daily_returns, dict):
            for dt, val in daily_returns.items():
                try:
                    returns_map[str(dt)[:10]] = float(val)
                except (ValueError, TypeError):
                    continue
        elif isinstance(daily_returns, list):
            for i, val in enumerate(daily_returns):
                try:
                    returns_map[f"idx_{i}"] = float(val)
                except (ValueError, TypeError):
                    continue

        return returns_map

    @staticmethod
    def compute_pearson_correlation(x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient between two series."""
        n = len(x)
        if n < 3:
            return 0.0

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if den_x == 0 or den_y == 0:
            return 0.0

        return num / (den_x * den_y)

    @staticmethod
    def compute_spearman_correlation(x: List[float], y: List[float]) -> float:
        """Calculate Spearman rank correlation coefficient between two series."""
        n = len(x)
        if n < 3:
            return 0.0

        def _get_ranks(seq: List[float]) -> List[float]:
            sorted_indices = sorted(range(len(seq)), key=lambda i: seq[i])
            ranks = [0.0] * len(seq)
            for rank, idx in enumerate(sorted_indices):
                ranks[idx] = float(rank + 1)
            return ranks

        rank_x = _get_ranks(x)
        rank_y = _get_ranks(y)
        return FactorOrthogonalizationService.compute_pearson_correlation(rank_x, rank_y)

    @staticmethod
    def compute_code_token_similarity(code_a: str, code_b: str) -> float:
        """Compute token-level Jaccard similarity between two source codes."""
        if not code_a or not code_b:
            return 0.0
        tokens_a = set(code_a.replace("\n", " ").split())
        tokens_b = set(code_b.replace("\n", " ").split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        return len(intersection) / len(union) if union else 0.0

    def calculate_correlation(
        self, candidate: Any, active_factor: Any
    ) -> Tuple[float, str]:
        """
        Calculate maximum correlation between candidate and an active factor.
        Returns: (correlation_score, method_used)
        """
        cand_returns = self._extract_returns_series(candidate)
        active_returns = self._extract_returns_series(active_factor)

        # Find matching timestamps
        overlap_dates = sorted(set(cand_returns.keys()) & set(active_returns.keys()))
        if len(overlap_dates) >= 3:
            x = [cand_returns[d] for d in overlap_dates]
            y = [active_returns[d] for d in overlap_dates]
            pearson = abs(self.compute_pearson_correlation(x, y))
            spearman = abs(self.compute_spearman_correlation(x, y))
            corr = max(pearson, spearman)
            return corr, f"return_series({len(overlap_dates)}_points)"

        # Fallback to code token similarity if returns are insufficient
        cand_code = getattr(candidate, "source_code", "")
        active_code = getattr(active_factor, "source_code", "")
        sim = self.compute_code_token_similarity(cand_code, active_code)
        return sim, "code_token_jaccard"

    def check_orthogonality(
        self,
        candidate: Any,
        active_factors: List[Any],
        max_correlation: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Verify if candidate is orthogonal to all existing active factors.
        檢定候選因子與既有在線因子是否滿足正交條件。
        """
        threshold = max_correlation if max_correlation is not None else self.max_correlation
        cand_name = getattr(candidate, "name", getattr(candidate, "id", "Unknown"))

        if not active_factors:
            return {
                "orthogonal": True,
                "max_correlation": 0.0,
                "correlated_with": None,
                "reason": "Passed: No active factors to compare against",
                "details": [],
            }

        max_corr = 0.0
        conflicting_factor = None
        details = []

        for active in active_factors:
            active_id = getattr(active, "id", "")
            cand_id = getattr(candidate, "id", "")
            # Skip comparing factor to itself
            if active_id and cand_id and active_id == cand_id:
                continue

            active_name = getattr(active, "name", active_id)
            corr, method = self.calculate_correlation(candidate, active)
            details.append({
                "factor_name": active_name,
                "correlation": round(corr, 4),
                "method": method,
            })

            if corr > max_corr:
                max_corr = corr
                conflicting_factor = active_name

        if max_corr > threshold:
            msg = (
                f"Factor collinearity check failed: Correlation with '{conflicting_factor}' "
                f"is {max_corr:.2f}, exceeding max threshold {threshold:.2f}."
            )
            logger.warning(f"Orthogonality gate blocked '{cand_name}': {msg}")
            return {
                "orthogonal": False,
                "max_correlation": max_corr,
                "correlated_with": conflicting_factor,
                "reason": msg,
                "details": details,
            }

        return {
            "orthogonal": True,
            "max_correlation": max_corr,
            "correlated_with": conflicting_factor if max_corr > 0.0 else None,
            "reason": f"Passed: Max correlation {max_corr:.2f} is within limit {threshold:.2f}",
            "details": details,
        }
