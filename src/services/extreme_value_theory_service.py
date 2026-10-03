"""
Extreme Value Theory (EVT) & Peaks-Over-Threshold (POT) Tail Risk Engine
黑天鵝極值理論尾部風險外推與超額峰值引擎
=============================================================================
Provides mathematically rigorous tail risk estimation beyond Gaussian/empirical boundaries:
1. Peaks-Over-Threshold (POT) approach via Pickands-Balkema-de Haan Theorem.
2. Generalized Pareto Distribution (GPD) parameter estimation (Probability-Weighted Moments & MLE).
3. Closed-form high-quantile extrapolation for VaR (99.0%, 99.5%, 99.9%) and Expected Shortfall (CVaR).
4. Tail Fatness Ratio (EVT VaR vs Gaussian VaR) & Black Swan Warning Classification.
5. Component Asset Tail Index Profiling & Extreme Drawdown Buffer Synthesis.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class TailDomain(str, Enum):
    """Domain of attraction for the generalized Pareto distribution."""
    FRECHET_HEAVY = "FRECHET_HEAVY"      # xi > 0: Heavy/fat-tailed (polynomial decay, standard for finance)
    GUMBEL_EXPONENTIAL = "GUMBEL_EXPONENTIAL"  # xi == 0: Light-tailed (exponential decay, e.g. Gaussian)
    WEIBULL_SHORT = "WEIBULL_SHORT"      # xi < 0: Short-tailed (bounded upper endpoint)


class BlackSwanAlertLevel(str, Enum):
    """Tail risk and black swan warning severity levels."""
    NORMAL = "NORMAL"                    # Tail fatness ratio < 1.30, xi < 0.25
    ELEVATED = "ELEVATED"                # Tail fatness ratio 1.30 ~ 1.79, or xi 0.25 ~ 0.35
    HIGH = "HIGH"                        # Tail fatness ratio 1.80 ~ 2.49, or xi 0.35 ~ 0.50
    EXTREME_BLACK_SWAN = "EXTREME_BLACK_SWAN"  # Tail fatness ratio >= 2.50 or xi >= 0.50


@dataclass
class GPDParameters:
    """Fitted Generalized Pareto Distribution parameters."""
    xi: float                            # Shape parameter / tail index (fatness)
    sigma: float                         # Scale parameter
    threshold_u: float                   # Exceedance threshold u
    exceedances_count: int               # Number of exceedances (N_u)
    total_count: int                     # Total sample size (N)
    tail_domain: TailDomain              # Tail classification
    estimation_method: str               # "PWM" or "MLE"
    standard_error_xi: float = 0.0       # Asymptotic standard error of shape parameter

    @property
    def exceedance_ratio(self) -> float:
        """Ratio of exceedances N_u / N."""
        return self.exceedances_count / max(1, self.total_count)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xi": round(self.xi, 4),
            "sigma": round(self.sigma, 6),
            "threshold_u": round(self.threshold_u, 6),
            "exceedances_count": self.exceedances_count,
            "total_count": self.total_count,
            "exceedance_ratio": round(self.exceedance_ratio, 4),
            "tail_domain": self.tail_domain.value,
            "estimation_method": self.estimation_method,
            "standard_error_xi": round(self.standard_error_xi, 4),
        }


@dataclass
class EVTTailRiskMetrics:
    """Comprehensive EVT-based tail risk indicators."""
    var_95: float
    var_99: float
    var_995: float
    var_999: float
    es_95: float
    es_99: float
    es_995: float
    es_999: float
    gaussian_var_999: float
    tail_fatness_ratio_999: float        # EVT VaR_99.9% / Gaussian VaR_99.9%
    tail_index_alpha: float              # alpha = 1 / xi (Pareto alpha)
    tail_domain: TailDomain
    alert_level: BlackSwanAlertLevel
    threshold_u: float
    xi: float
    sigma: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "var_95": round(self.var_95, 4),
            "var_99": round(self.var_99, 4),
            "var_995": round(self.var_995, 4),
            "var_999": round(self.var_999, 4),
            "es_95": round(self.es_95, 4),
            "es_99": round(self.es_99, 4),
            "es_995": round(self.es_995, 4),
            "es_999": round(self.es_999, 4),
            "gaussian_var_999": round(self.gaussian_var_999, 4),
            "tail_fatness_ratio_999": round(self.tail_fatness_ratio_999, 3),
            "tail_index_alpha": round(self.tail_index_alpha, 3),
            "tail_domain": self.tail_domain.value,
            "alert_level": self.alert_level.value,
            "threshold_u": round(self.threshold_u, 4),
            "xi": round(self.xi, 4),
            "sigma": round(self.sigma, 6),
        }


@dataclass
class AssetTailContribution:
    """Individual asset tail risk profile."""
    symbol: str
    weight: float
    xi: float
    var_999: float
    es_999: float
    tail_fatness_ratio: float
    alert_level: BlackSwanAlertLevel

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "weight": round(self.weight, 4),
            "xi": round(self.xi, 4),
            "var_999": round(self.var_999, 4),
            "es_999": round(self.es_999, 4),
            "tail_fatness_ratio": round(self.tail_fatness_ratio, 3),
            "alert_level": self.alert_level.value,
        }


@dataclass
class PortfolioEVTAssessment:
    """Top-level assessment combining portfolio and cross-sectional tail profiles."""
    portfolio_metrics: EVTTailRiskMetrics
    asset_contributions: List[AssetTailContribution]
    recommended_tail_buffer: float       # Additional cash/defense buffer (0.0 to 0.30)
    is_black_swan_triggered: bool
    diagnostic_summary: str
    gpd_parameters: GPDParameters

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portfolio_metrics": self.portfolio_metrics.to_dict(),
            "asset_contributions": [a.to_dict() for a in self.asset_contributions],
            "recommended_tail_buffer": round(self.recommended_tail_buffer, 4),
            "is_black_swan_triggered": self.is_black_swan_triggered,
            "diagnostic_summary": self.diagnostic_summary,
            "gpd_parameters": self.gpd_parameters.to_dict(),
        }


class ExtremeValueTheoryService:
    """
    Extreme Value Theory & Peaks-Over-Threshold Tail Risk Engine.
    極值理論與超額峰值黑天鵝尾部風險外推服務。
    """

    DEFAULT_THRESHOLD_QUANTILE = 0.90
    DEFAULT_TAIL_FATNESS_ALERT_THRESHOLD = 1.80
    DEFAULT_MAX_SHAPE_XI = 0.80

    def __init__(self, settings_repo: Any = None):
        self.settings_repo = settings_repo

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_repo is not None:
            try:
                user_id = resolve_user_id()
                val = self.settings_repo.get(key, user_id=user_id)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to fetch setting '{key}': {e}")
        return default

    # =========================================================================
    # 1. GPD Parameter Fitting (POT)
    # =========================================================================

    def fit_gpd(
        self,
        losses: Union[np.ndarray, List[float]],
        threshold_quantile: Optional[float] = None,
        method: str = "pwm",
    ) -> GPDParameters:
        """
        Fit Generalized Pareto Distribution (GPD) on exceedances over threshold u.
        
        Args:
            losses: 1D array of portfolio positive loss values (Loss = -Return).
            threshold_quantile: Quantile for threshold selection u (default 0.90).
            method: 'pwm' (Probability-Weighted Moments) or 'mle' (Maximum Likelihood).
            
        Returns:
            GPDParameters dataclass containing xi, sigma, threshold, and diagnostic stats.
        """
        loss_arr = np.asarray(losses, dtype=float)
        loss_arr = loss_arr[~np.isnan(loss_arr)]
        n_total = len(loss_arr)

        q = threshold_quantile or float(
            self._get_setting("evt_threshold_quantile", self.DEFAULT_THRESHOLD_QUANTILE)
        )
        q = max(0.70, min(0.98, q))

        # Safe fallback for tiny sample size
        if n_total < 15:
            logger.warning(f"Sample size {n_total} too small for robust EVT POT; using parametric proxy.")
            mu = float(np.mean(loss_arr)) if n_total > 0 else 0.0
            std = float(np.std(loss_arr)) if n_total > 1 else 0.02
            u = max(0.001, mu + 1.28 * std)
            return GPDParameters(
                xi=0.15,
                sigma=max(0.005, std * 0.7),
                threshold_u=u,
                exceedances_count=max(1, int(n_total * (1.0 - q))),
                total_count=max(1, n_total),
                tail_domain=TailDomain.FRECHET_HEAVY,
                estimation_method="FALLBACK_PARAMETRIC",
                standard_error_xi=0.10,
            )

        u = float(np.quantile(loss_arr, q))
        exceedances = loss_arr[loss_arr > u] - u
        n_u = len(exceedances)

        # If too few exceedances, adapt threshold downwards
        if n_u < 8 and q > 0.75:
            q_adapted = max(0.70, q - 0.10)
            u = float(np.quantile(loss_arr, q_adapted))
            exceedances = loss_arr[loss_arr > u] - u
            n_u = len(exceedances)

        if n_u < 4:
            # Fallback to exponential approximation
            sample_std = float(np.std(loss_arr))
            return GPDParameters(
                xi=0.05,
                sigma=max(0.005, sample_std * 0.6),
                threshold_u=u,
                exceedances_count=n_u,
                total_count=n_total,
                tail_domain=TailDomain.GUMBEL_EXPONENTIAL,
                estimation_method="FALLBACK_EXPONENTIAL",
                standard_error_xi=0.15,
            )

        # Perform parameter estimation
        if method.lower() == "mle":
            xi, sigma = self._fit_gpd_mle(exceedances)
            est_method = "MLE"
        else:
            xi, sigma = self._fit_gpd_pwm(exceedances)
            est_method = "PWM"

        # Boundary sanity clamps
        max_xi = float(self._get_setting("evt_max_shape_xi", self.DEFAULT_MAX_SHAPE_XI))
        xi = max(-0.45, min(max_xi, xi))
        sigma = max(1e-5, sigma)

        # Standard error of xi (robust general approximation)
        se_xi = float(np.sqrt((1.0 + abs(xi)) ** 2 / max(1, n_u)))

        if abs(xi) < 1e-4:
            domain = TailDomain.GUMBEL_EXPONENTIAL
        elif xi > 0:
            domain = TailDomain.FRECHET_HEAVY
        else:
            domain = TailDomain.WEIBULL_SHORT

        return GPDParameters(
            xi=xi,
            sigma=sigma,
            threshold_u=u,
            exceedances_count=n_u,
            total_count=n_total,
            tail_domain=domain,
            estimation_method=est_method,
            standard_error_xi=se_xi,
        )

    def _fit_gpd_pwm(self, exceedances: np.ndarray) -> Tuple[float, float]:
        """
        Probability-Weighted Moments (PWM) estimation of GPD parameters (Hosking & Wallis 1987).
        Closed-form, highly stable, non-iterative.
        """
        y = np.sort(exceedances)
        k = len(y)
        y_bar = float(np.mean(y))

        # First probability-weighted moment a1 = (1/k) * sum_{i=1}^k ((k - i)/(k - 1)) * y_(i)
        weights = (k - np.arange(1, k + 1)) / max(1.0, float(k - 1))
        a1 = float(np.sum(weights * y) / k)

        denom = y_bar - 2.0 * a1
        if abs(denom) < 1e-7 or y_bar <= 0:
            # Fallback to exponential (xi = 0, sigma = y_bar)
            return 0.0, max(1e-5, y_bar)

        xi = 2.0 - (y_bar / denom)
        sigma = (2.0 * y_bar * a1) / denom

        if sigma <= 0 or np.isnan(xi) or np.isnan(sigma):
            # Numerical fallback
            return 0.10, max(1e-5, y_bar)

        return float(xi), float(sigma)

    def _fit_gpd_mle(self, exceedances: np.ndarray) -> Tuple[float, float]:
        """
        Maximum Likelihood Estimation (MLE) of GPD with PWM seed fallback.
        """
        # Start with PWM seed
        xi_seed, sigma_seed = self._fit_gpd_pwm(exceedances)

        try:
            from scipy.optimize import minimize

            def neg_log_likelihood(params: np.ndarray) -> float:
                xi_val, sigma_val = params[0], params[1]
                if sigma_val <= 1e-6:
                    return 1e10
                z = 1.0 + (xi_val * exceedances) / sigma_val
                if np.any(z <= 0):
                    return 1e10
                if abs(xi_val) < 1e-6:
                    nll = len(exceedances) * np.log(sigma_val) + np.sum(exceedances) / sigma_val
                else:
                    nll = len(exceedances) * np.log(sigma_val) + (1.0 + 1.0 / xi_val) * np.sum(np.log(z))
                return float(nll) if np.isfinite(nll) else 1e10

            res = minimize(
                neg_log_likelihood,
                x0=np.array([xi_seed, sigma_seed]),
                bounds=[(-0.45, 1.2), (1e-5, None)],
                method="L-BFGS-B",
            )
            if res.success and np.isfinite(res.x[0]) and np.isfinite(res.x[1]) and res.x[1] > 0:
                return float(res.x[0]), float(res.x[1])
        except Exception as e:
            logger.debug(f"MLE optimization failed, using PWM: {e}")

        return xi_seed, sigma_seed

    # =========================================================================
    # 2. EVT VaR & Expected Shortfall (ES / CVaR) Extrapolation
    # =========================================================================

    def calculate_evt_var(self, params: GPDParameters, alpha: float) -> float:
        """
        Extrapolate Value-at-Risk at confidence level alpha using the fitted GPD.
        
        Formula:
            VaR_alpha = u + (sigma / xi) * [ ((N / N_u) * (1 - alpha))^(-xi) - 1 ]  (if xi != 0)
            VaR_alpha = u + sigma * ln( (N / N_u) / (1 - alpha) )                   (if xi == 0)
        """
        if alpha >= 1.0 or alpha <= 0.0:
            raise ValueError(f"Confidence level alpha must be strictly between 0 and 1, got {alpha}")

        u = params.threshold_u
        xi = params.xi
        sigma = params.sigma
        ratio = params.exceedance_ratio  # N_u / N

        if ratio <= 0:
            return u

        # Probability scaling factor
        factor = (1.0 - alpha) / ratio

        if factor <= 0:
            return u

        if abs(xi) < 1e-5:
            # Gumbel / Exponential tail
            var = u - sigma * math.log(factor)
        else:
            var = u + (sigma / xi) * (math.pow(factor, -xi) - 1.0)

        return float(max(u, var))

    def calculate_evt_es(self, params: GPDParameters, alpha: float) -> float:
        """
        Calculate Expected Shortfall (ES / Conditional VaR) at confidence level alpha.
        
        Formula:
            ES_alpha = (VaR_alpha + sigma - xi * u) / (1 - xi)   (for xi < 1)
        """
        var_alpha = self.calculate_evt_var(params, alpha)
        u = params.threshold_u
        xi = params.xi
        sigma = params.sigma

        # When xi >= 1.0, theoretical mean is infinite; use asymptotic safety multiplier
        if xi >= 0.98:
            logger.warning(f"Shape parameter xi={xi:.3f} >= 0.98 approaches infinite-mean regime.")
            # Safety approximation: upper quantile proxy
            alpha_upper = 1.0 - (1.0 - alpha) * 0.35
            return float(self.calculate_evt_var(params, alpha_upper))

        es = (var_alpha + sigma - xi * u) / (1.0 - xi)
        return float(max(var_alpha, es))

    # =========================================================================
    # 3. Comprehensive Tail Risk & Black Swan Assessment
    # =========================================================================

    def assess_tail_risk(
        self,
        returns: Union[np.ndarray, List[float]],
        weights: Optional[Dict[str, float]] = None,
        asset_returns: Optional[Dict[str, Union[np.ndarray, List[float]]]] = None,
        threshold_quantile: Optional[float] = None,
    ) -> PortfolioEVTAssessment:
        """
        Full-spectrum extreme tail risk assessment for portfolio and component assets.
        
        Args:
            returns: Daily return series of the portfolio (or simulated historical returns).
            weights: Optional current portfolio asset weights dict.
            asset_returns: Optional historical daily return series per ticker.
            threshold_quantile: High quantile for POT thresholding.
            
        Returns:
            PortfolioEVTAssessment with VaR/ES at 95%, 99%, 99.5%, 99.9%, Tail Fatness Ratio,
            and Black Swan Warning Level.
        """
        ret_arr = np.asarray(returns, dtype=float)
        losses = -ret_arr  # Positive losses

        gpd_params = self.fit_gpd(losses, threshold_quantile=threshold_quantile)

        # Standard Gaussian benchmark for 99.9% VaR
        mu_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
        std_loss = float(np.std(losses)) if len(losses) > 1 else 0.02
        z_999 = 3.0902  # Standard normal 99.9% quantile
        gaussian_var_999 = max(0.001, mu_loss + z_999 * std_loss)

        # EVT metrics
        var_95 = self.calculate_evt_var(gpd_params, 0.95)
        var_99 = self.calculate_evt_var(gpd_params, 0.99)
        var_995 = self.calculate_evt_var(gpd_params, 0.995)
        var_999 = self.calculate_evt_var(gpd_params, 0.999)

        es_95 = self.calculate_evt_es(gpd_params, 0.95)
        es_99 = self.calculate_evt_es(gpd_params, 0.99)
        es_995 = self.calculate_evt_es(gpd_params, 0.995)
        es_999 = self.calculate_evt_es(gpd_params, 0.999)

        # Tail Fatness Ratio
        tail_fatness = var_999 / gaussian_var_999
        tail_index = 1.0 / max(1e-4, gpd_params.xi) if gpd_params.xi > 0 else 999.0

        # Black swan alert categorization
        alert_thresh = float(
            self._get_setting(
                "evt_tail_fatness_alert_threshold", self.DEFAULT_TAIL_FATNESS_ALERT_THRESHOLD
            )
        )
        if tail_fatness >= max(2.5, alert_thresh * 1.35) or gpd_params.xi >= 0.50:
            alert = BlackSwanAlertLevel.EXTREME_BLACK_SWAN
        elif tail_fatness >= alert_thresh or gpd_params.xi >= 0.35:
            alert = BlackSwanAlertLevel.HIGH
        elif tail_fatness >= 1.30 or gpd_params.xi >= 0.25:
            alert = BlackSwanAlertLevel.ELEVATED
        else:
            alert = BlackSwanAlertLevel.NORMAL

        metrics = EVTTailRiskMetrics(
            var_95=var_95,
            var_99=var_99,
            var_995=var_995,
            var_999=var_999,
            es_95=es_95,
            es_99=es_99,
            es_995=es_995,
            es_999=es_999,
            gaussian_var_999=gaussian_var_999,
            tail_fatness_ratio_999=tail_fatness,
            tail_index_alpha=tail_index,
            tail_domain=gpd_params.tail_domain,
            alert_level=alert,
            threshold_u=gpd_params.threshold_u,
            xi=gpd_params.xi,
            sigma=gpd_params.sigma,
        )

        # Asset-level tail profiling
        asset_contribs: List[AssetTailContribution] = []
        if asset_returns and weights:
            asset_contribs = self._profile_asset_tails(weights, asset_returns)

        # Tail defense buffer recommendation (0% ~ 25% cash buffer)
        recommended_buffer = 0.0
        if alert == BlackSwanAlertLevel.EXTREME_BLACK_SWAN:
            recommended_buffer = 0.25
        elif alert == BlackSwanAlertLevel.HIGH:
            recommended_buffer = 0.15
        elif alert == BlackSwanAlertLevel.ELEVATED:
            recommended_buffer = 0.08

        # Summary text
        summary = (
            f"EVT Tail Risk Diagnosis: Alert Level [{alert.value}]. "
            f"Tail Index xi={gpd_params.xi:.3f} ({gpd_params.tail_domain.value}), "
            f"99.9% VaR={var_999 * 100:.2f}%, 99.9% Expected Shortfall={es_999 * 100:.2f}%. "
            f"Tail Fatness Ratio={tail_fatness:.2f}x vs Gaussian benchmark."
        )

        return PortfolioEVTAssessment(
            portfolio_metrics=metrics,
            asset_contributions=asset_contribs,
            recommended_tail_buffer=recommended_buffer,
            is_black_swan_triggered=(alert in (BlackSwanAlertLevel.HIGH, BlackSwanAlertLevel.EXTREME_BLACK_SWAN)),
            diagnostic_summary=summary,
            gpd_parameters=gpd_params,
        )

    def _profile_asset_tails(
        self,
        weights: Dict[str, float],
        asset_returns: Dict[str, Union[np.ndarray, List[float]]],
    ) -> List[AssetTailContribution]:
        """Profile component asset tail risk and identify fattest-tail contributors."""
        results = []
        for symbol, w in weights.items():
            if w <= 0 or symbol.upper() in {"CASH", "USD"}:
                continue
            rets = asset_returns.get(symbol)
            if rets is None or len(rets) < 15:
                continue

            arr = np.asarray(rets, dtype=float)
            arr = arr[~np.isnan(arr)]
            losses = -arr

            gpd = self.fit_gpd(losses)
            var_999 = self.calculate_evt_var(gpd, 0.999)
            es_999 = self.calculate_evt_es(gpd, 0.999)

            mu = float(np.mean(losses))
            std = float(np.std(losses))
            gauss_999 = max(0.001, mu + 3.0902 * std)
            fatness = var_999 / gauss_999

            if fatness >= 2.5 or gpd.xi >= 0.50:
                asset_alert = BlackSwanAlertLevel.EXTREME_BLACK_SWAN
            elif fatness >= 1.80 or gpd.xi >= 0.35:
                asset_alert = BlackSwanAlertLevel.HIGH
            elif fatness >= 1.30 or gpd.xi >= 0.25:
                asset_alert = BlackSwanAlertLevel.ELEVATED
            else:
                asset_alert = BlackSwanAlertLevel.NORMAL

            results.append(
                AssetTailContribution(
                    symbol=symbol,
                    weight=w,
                    xi=gpd.xi,
                    var_999=var_999,
                    es_999=es_999,
                    tail_fatness_ratio=fatness,
                    alert_level=asset_alert,
                )
            )

        # Sort by tail fatness ratio descending
        results.sort(key=lambda x: x.tail_fatness_ratio, reverse=True)
        return results

    # =========================================================================
    # 4. Multi-Distribution Comparison Matrix
    # =========================================================================

    def compare_distributions(
        self,
        losses: Union[np.ndarray, List[float]],
        alphas: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Compare empirical, Gaussian, and EVT GPD tail estimates across quantiles.
        """
        if alphas is None:
            alphas = [0.95, 0.99, 0.995, 0.999]

        loss_arr = np.asarray(losses, dtype=float)
        loss_arr = loss_arr[~np.isnan(loss_arr)]

        mu = float(np.mean(loss_arr)) if len(loss_arr) > 0 else 0.0
        std = float(np.std(loss_arr)) if len(loss_arr) > 1 else 0.02

        gpd = self.fit_gpd(loss_arr)

        from scipy.stats import norm

        comparison = []
        for a in alphas:
            # Empirical
            emp_var = float(np.quantile(loss_arr, a)) if len(loss_arr) > 0 else 0.0

            # Gaussian
            z = norm.ppf(a)
            gauss_var = mu + z * std

            # EVT
            evt_var = self.calculate_evt_var(gpd, a)
            evt_es = self.calculate_evt_es(gpd, a)

            ratio = evt_var / max(1e-5, gauss_var)

            comparison.append({
                "alpha": a,
                "empirical_var": round(emp_var, 4),
                "gaussian_var": round(gauss_var, 4),
                "evt_gpd_var": round(evt_var, 4),
                "evt_gpd_es": round(evt_es, 4),
                "tail_fatness_multiplier": round(ratio, 3),
            })

        return {
            "gpd_parameters": gpd.to_dict(),
            "sample_moments": {
                "mean": round(mu, 4),
                "std": round(std, 4),
                "sample_size": len(loss_arr),
            },
            "comparison": comparison,
        }
