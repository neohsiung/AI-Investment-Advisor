"""
Bayesian Regime-Switching Jump-Diffusion Guard Service (Phase 35)
================================================================
多期動態貝葉斯更新與機制轉換跳躍擴散模型守衛 (Regime-Switching Jump-Diffusion & Bayesian Volatility Jump Guard)

職責：
1. Merton 跳躍擴散過程參數估計 (Merton's Jump-Diffusion Model, 1976)：
   dS_t / S_t = (μ - λ_jump * k) dt + σ dW_t + J_t dN_t
   - 分離連續布朗擴散波動 (Continuous Diffusion Volatility σ) 與非連續泊松跳躍 (Jump Intensity λ_jump)。
2. 雙重截斷 / Bipower Variation (BV - Barndorff-Nielsen & Shephard, 2004)：
   - Realized Volatility: RV = sum(r_t^2)
   - Bipower Variation: BV = (π / 2) * sum(|r_t| * |r_{t-1}|)
   - 提取跳躍變異成分: JV = max(0, RV - BV)，計算相對跳躍比率 RJ = JV / RV in [0.0, 1.0]。
   - 以統計閾值 (|r_t| > θ * σ_daily, θ=3.0) 精準識別跳躍事件與跳躍幅度 J_j。
3. 動態在線貝葉斯更新 (Online Conjugate Bayesian Updating)：
   - Gamma-Poisson 共軛更新年化跳躍強度：
     λ | K ~ Gamma(α_0 + K, β_0 + T_years)
     E[λ_jump] = (α_0 + K) / (β_0 + T_years) (年化跳躍頻率)
   - 貝葉斯更新跳躍幅度均值 μ_J 與標準差 σ_J。
4. 機制轉換跳躍體制判定 (Regime Switching)：
   - CALM_DIFFUSION: λ_jump < 2.0 (常規連續擴散，跳躍風險低，正常建倉)
   - MODERATE_JUMP: 2.0 <= λ_jump < 6.0 (跳躍動能顯著，部位收縮 20%，擴大防禦緩衝)
   - ACUTE_JUMP_REGIME: λ_jump >= 6.0 或近期劇烈負向跳躍 (下行崩跌風險，觸發熔斷暫緩建倉)
5. 交易前置防護與開盤建倉閉環整合 (Closed-Loop Guard Integration)：
   - 在 SlippageGuardService 前置檢定：若標的處於 ACUTE_JUMP_REGIME 且為負向跳躍偏態，暫緩市價下單。
   - 在 BatchCashDeploymentService 標記候選標的跳躍強度；若標的跳躍熔斷則暫緩執行並保留批次指針。
   - 具備 Fail-Open 與合成流退化機制，保證零崩潰零中斷。
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("BayesianJumpDiffusionGuardService")


class JumpRegime(str, Enum):
    """跳躍擴散體制分類"""
    CALM_DIFFUSION = "CALM_DIFFUSION"        # λ_jump < 2.0: 擴散平靜期，常規放行
    MODERATE_JUMP = "MODERATE_JUMP"          # 2.0 <= λ_jump < 6.0: 中度跳躍風險，拆單防甩轎
    ACUTE_JUMP_REGIME = "ACUTE_JUMP_REGIME"  # λ_jump >= 6.0: 重度跳躍衝擊，暫緩建倉


@dataclass
class BipowerVariationResult:
    """Bipower Variation 連續變異與跳躍分離度量結果"""
    realized_variance: float             # 總實現方差 RV
    bipower_variation: float             # 連續雙冪方差 BV
    jump_variation: float                # 離散跳躍方差 JV = max(0, RV - BV)
    relative_jump_ratio: float           # 跳躍佔比 RJ = JV / RV in [0.0, 1.0]
    continuous_volatility: float         # 年化連續擴散波動率 σ_cont
    total_volatility: float              # 年化總波動率 σ_tot
    detected_jumps: List[float]          # 識別出的跳躍幅度清單
    sample_days: int                     # 樣本天數

    def to_dict(self) -> Dict[str, Any]:
        return {
            "realized_variance": round(self.realized_variance, 6),
            "bipower_variation": round(self.bipower_variation, 6),
            "jump_variation": round(self.jump_variation, 6),
            "relative_jump_ratio": round(self.relative_jump_ratio, 4),
            "continuous_volatility": round(self.continuous_volatility, 4),
            "total_volatility": round(self.total_volatility, 4),
            "detected_jumps_count": len(self.detected_jumps),
            "sample_days": self.sample_days,
        }


@dataclass
class BayesianJumpPosterior:
    """貝葉斯 Gamma-Poisson 後驗跳躍分佈參數"""
    prior_alpha: float
    prior_beta: float
    posterior_alpha: float
    posterior_beta: float
    expected_jump_intensity: float       # 年化跳躍強度 E[λ_jump]
    jump_mean_magnitude: float           # 平均跳躍幅度 μ_J
    jump_std_magnitude: float            # 跳躍幅度標準差 σ_J
    observed_jumps_count: int            # 觀測到之跳躍次數
    lookback_years: float                # 觀察時間 (年)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prior_alpha": round(self.prior_alpha, 2),
            "prior_beta": round(self.prior_beta, 2),
            "posterior_alpha": round(self.posterior_alpha, 2),
            "posterior_beta": round(self.posterior_beta, 4),
            "expected_jump_intensity": round(self.expected_jump_intensity, 4),
            "jump_mean_magnitude": round(self.jump_mean_magnitude, 4),
            "jump_std_magnitude": round(self.jump_std_magnitude, 4),
            "observed_jumps_count": self.observed_jumps_count,
            "lookback_years": round(self.lookback_years, 4),
        }


@dataclass
class TickerJumpAssessment:
    """單一標的貝葉斯跳躍擴散檢定評定報告"""
    symbol: str
    regime: JumpRegime
    jump_intensity: float                # 年化跳躍頻率 λ_jump
    continuous_volatility: float         # 連續擴散波動率 σ_cont
    total_volatility: float              # 總波動率 σ_tot
    relative_jump_ratio: float           # 跳躍變異佔比 RJ
    jump_mean: float                     # 跳躍均值 μ_J
    jump_std: float                      # 跳躍標準差 σ_J
    is_acute_jump: bool                  # 是否處於重度跳躍危機體制
    recommended_action: str              # "PROCEED", "THROTTLE", "DEFER"
    position_scale_multiplier: float     # 建議部位規模縮放係數 (0.50 ~ 1.0)
    stop_loss_buffer_multiplier: float   # 建議停損緩衝放大係數 (1.0 ~ 1.5)
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "regime": self.regime.value,
            "jump_intensity": round(self.jump_intensity, 4),
            "continuous_volatility": round(self.continuous_volatility, 4),
            "total_volatility": round(self.total_volatility, 4),
            "relative_jump_ratio": round(self.relative_jump_ratio, 4),
            "jump_mean": round(self.jump_mean, 4),
            "jump_std": round(self.jump_std, 4),
            "is_acute_jump": self.is_acute_jump,
            "recommended_action": self.recommended_action,
            "position_scale_multiplier": round(self.position_scale_multiplier, 2),
            "stop_loss_buffer_multiplier": round(self.stop_loss_buffer_multiplier, 2),
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PortfolioJumpSummary:
    """全投資組合貝葉斯跳躍擴散總覽"""
    assessments: Dict[str, TickerJumpAssessment]
    acute_symbols: List[str]
    moderate_symbols: List[str]
    calm_symbols: List[str]
    mean_jump_intensity: float
    mean_relative_jump_ratio: float
    overall_market_jump_regime: str      # "CALM", "ELEVATED_JUMP_ACTIVITY", "SYSTEMIC_JUMP_SHOCK"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessments": {k: v.to_dict() for k, v in self.assessments.items()},
            "acute_symbols": self.acute_symbols,
            "moderate_symbols": self.moderate_symbols,
            "calm_symbols": self.calm_symbols,
            "mean_jump_intensity": round(self.mean_jump_intensity, 4),
            "mean_relative_jump_ratio": round(self.mean_relative_jump_ratio, 4),
            "overall_market_jump_regime": self.overall_market_jump_regime,
            "timestamp": self.timestamp,
        }


class BayesianJumpDiffusionGuardService:
    """多期動態貝葉斯更新與機制轉換跳躍擴散模型守衛服務"""

    # 預設參數常數
    DEFAULT_JUMP_INTENSITY_ALERT = 6.0    # 年化跳躍強度警戒閾值 (>= 6.0 jumps/year)
    DEFAULT_JUMP_INTENSITY_MODERATE = 2.0 # 年化跳躍中度升溫閾值 (>= 2.0 jumps/year)
    DEFAULT_SIGMA_MULTIPLIER = 3.0        # 判定離散跳躍之連續波動倍數閾值
    DEFAULT_LOOKBACK_DAYS = 60            # 回看日誌天數
    DEFAULT_PRIOR_ALPHA = 2.0             # Gamma 先驗形狀參數
    DEFAULT_PRIOR_BETA = 1.0              # Gamma 先驗速率參數 (先驗平均 2.0 次/年)
    DEFAULT_ACUTE_POSITION_SCALE = 0.50   # 遭遇重度跳躍體制時之部位縮減係數

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
        redis_client: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        if settings_service is not None:
            self.settings_service = settings_service
        else:
            try:
                from src.services.settings_service import SettingsService
                self.settings_service = SettingsService(user_id=self.user_id)
            except Exception:
                self.settings_service = None

        self.market_data_service = market_data_service
        self.redis_client = redis_client
        self._memory_cache: Dict[str, TickerJumpAssessment] = {}

    # ── 設定讀取輔助方法 ──────────────────────────────────────────────

    def _get_setting_bool(self, key: str, default: bool = True) -> bool:
        if not self.settings_service:
            return default
        try:
            val = self.settings_service.get_setting(key, default)
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes")
        except Exception:
            return default

    def _get_setting_float(self, key: str, default: float) -> float:
        if not self.settings_service:
            return default
        try:
            val = self.settings_service.get_setting(key, default)
            return float(val) if val is not None else default
        except Exception:
            return default

    def _get_setting_int(self, key: str, default: int) -> int:
        if not self.settings_service:
            return default
        try:
            val = self.settings_service.get_setting(key, default)
            return int(val) if val is not None else default
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting_bool("enable_bayesian_jump_guard", True)

    @property
    def jump_intensity_alert_threshold(self) -> float:
        return self._get_setting_float("jump_intensity_alert_threshold", self.DEFAULT_JUMP_INTENSITY_ALERT)

    @property
    def jump_detection_sigma_multiplier(self) -> float:
        return self._get_setting_float("jump_detection_sigma_multiplier", self.DEFAULT_SIGMA_MULTIPLIER)

    @property
    def lookback_days(self) -> int:
        return self._get_setting_int("jump_bipower_lookback_days", self.DEFAULT_LOOKBACK_DAYS)

    @property
    def acute_position_scale(self) -> float:
        return self._get_setting_float("jump_acute_position_scale", self.DEFAULT_ACUTE_POSITION_SCALE)

    # ── 核心微觀與貝葉斯演算法 ─────────────────────────────────────────

    @classmethod
    def compute_bipower_variation(
        cls,
        returns: List[float],
        sigma_multiplier: float = 3.0,
    ) -> BipowerVariationResult:
        """
        Bipower Variation (BV) 連續變異與非連續跳躍分離 (Barndorff-Nielsen & Shephard, 2004)。
        """
        n = len(returns)
        if n < 2:
            return BipowerVariationResult(
                realized_variance=0.0,
                bipower_variation=0.0,
                jump_variation=0.0,
                relative_jump_ratio=0.0,
                continuous_volatility=0.15,
                total_volatility=0.15,
                detected_jumps=[],
                sample_days=n,
            )

        # 1. Realized Variance (RV)
        rv = sum(r ** 2 for r in returns)

        # 2. Bipower Variation (BV = (π/2) * sum(|r_t| * |r_{t-1}|))
        pi_over_2 = math.pi / 2.0
        bv = pi_over_2 * sum(abs(returns[i]) * abs(returns[i - 1]) for i in range(1, n))

        # 3. Jump Variation (JV)
        jv = max(0.0, rv - bv)
        rj = (jv / rv) if rv > 1e-12 else 0.0
        rj = max(0.0, min(1.0, rj))

        # 4. 年化波動率換算
        dt_factor = 252.0 / max(1, n - 1)
        sigma_cont_daily = math.sqrt(max(1e-12, bv / max(1, n - 1)))
        sigma_cont = sigma_cont_daily * math.sqrt(252.0)
        sigma_tot = math.sqrt(max(1e-12, rv / max(1, n - 1))) * math.sqrt(252.0)

        # 5. 離散跳躍檢定 (Threshold Jump Detection)
        threshold = max(1e-4, sigma_multiplier * sigma_cont_daily)
        detected = [r for r in returns if abs(r) > threshold]

        return BipowerVariationResult(
            realized_variance=rv,
            bipower_variation=bv,
            jump_variation=jv,
            relative_jump_ratio=rj,
            continuous_volatility=sigma_cont,
            total_volatility=sigma_tot,
            detected_jumps=detected,
            sample_days=n,
        )

    @classmethod
    def update_bayesian_merton(
        cls,
        detected_jumps: List[float],
        lookback_days: int,
        prior_alpha: float = 2.0,
        prior_beta: float = 1.0,
    ) -> BayesianJumpPosterior:
        """
        動態在線貝葉斯更新 (Gamma-Poisson 共軛更新年化跳躍強度)。
        """
        t_years = max(10.0 / 252.0, lookback_days / 252.0)
        k = len(detected_jumps)

        post_alpha = prior_alpha + k
        post_beta = prior_beta + t_years
        lambda_jump = post_alpha / post_beta

        # 貝葉斯更新跳躍幅度分佈 (Normal Prior: μ_0 = -0.02, τ_0 = 2.0, σ_0 = 0.04)
        prior_mu = -0.02
        prior_tau = 2.0
        prior_sigma = 0.04

        if k > 0:
            sum_j = sum(detected_jumps)
            post_mu = (prior_tau * prior_mu + sum_j) / (prior_tau + k)
            ss_dev = sum((j - post_mu) ** 2 for j in detected_jumps)
            prior_dev = prior_tau * ((prior_mu - post_mu) ** 2)
            post_var = (prior_dev + ss_dev) / (prior_tau + k)
            post_sigma = math.sqrt(max(1e-6, post_var))
        else:
            post_mu = prior_mu
            post_sigma = prior_sigma

        return BayesianJumpPosterior(
            prior_alpha=prior_alpha,
            prior_beta=prior_beta,
            posterior_alpha=post_alpha,
            posterior_beta=post_beta,
            expected_jump_intensity=lambda_jump,
            jump_mean_magnitude=post_mu,
            jump_std_magnitude=post_sigma,
            observed_jumps_count=k,
            lookback_years=t_years,
        )

    # ── 評估與體制判定 ───────────────────────────────────────────────

    def evaluate_returns_series(
        self,
        symbol: str,
        returns: List[float],
    ) -> TickerJumpAssessment:
        """
        對回報率序列執行雙冪方差分解、貝葉斯更新與機制轉換跳躍判定。
        """
        sym = symbol.strip().upper()
        if not returns:
            return self._synthesize_baseline_assessment(sym)

        # 1. 雙冪方差分離連續與跳躍變異
        bv_res = self.compute_bipower_variation(
            returns, sigma_multiplier=self.jump_detection_sigma_multiplier
        )

        # 2. 貝葉斯共軛更新跳躍強度
        post = self.update_bayesian_merton(
            bv_res.detected_jumps,
            lookback_days=len(returns),
            prior_alpha=self.DEFAULT_PRIOR_ALPHA,
            prior_beta=self.DEFAULT_PRIOR_BETA,
        )

        # 3. 體制決策邏輯
        alert_th = self.jump_intensity_alert_threshold
        mod_th = self.DEFAULT_JUMP_INTENSITY_MODERATE

        lam = post.expected_jump_intensity
        mu_j = post.jump_mean_magnitude
        rj = bv_res.relative_jump_ratio

        # 若跳躍頻率極高，或近期檢測到下行大跳躍 (跌幅 > 3.5%) 且跳躍升溫
        has_severe_downside_jump = any(j < -0.035 for j in bv_res.detected_jumps)
        is_acute = (lam >= alert_th) or (has_severe_downside_jump and lam >= 4.0)

        if is_acute:
            regime = JumpRegime.ACUTE_JUMP_REGIME
            action = "DEFER"
            pos_scale = self.acute_position_scale
            sl_buffer = 1.50
        elif lam >= mod_th or rj >= 0.25:
            regime = JumpRegime.MODERATE_JUMP
            action = "THROTTLE"
            pos_scale = 0.80
            sl_buffer = 1.25
        else:
            regime = JumpRegime.CALM_DIFFUSION
            action = "PROCEED"
            pos_scale = 1.00
            sl_buffer = 1.00

        details = {
            "jump_intensity_annual": round(lam, 4),
            "alert_threshold": round(alert_th, 4),
            "moderate_threshold": round(mod_th, 4),
            "relative_jump_ratio": round(rj, 4),
            "continuous_volatility": round(bv_res.continuous_volatility, 4),
            "total_volatility": round(bv_res.total_volatility, 4),
            "observed_jumps_count": len(bv_res.detected_jumps),
            "jump_mean_magnitude": round(mu_j, 4),
            "jump_std_magnitude": round(post.jump_std_magnitude, 4),
            "sample_days": len(returns),
            "has_severe_downside_jump": has_severe_downside_jump,
            "bipower_metrics": bv_res.to_dict(),
            "bayesian_posterior": post.to_dict(),
        }

        assessment = TickerJumpAssessment(
            symbol=sym,
            regime=regime,
            jump_intensity=lam,
            continuous_volatility=bv_res.continuous_volatility,
            total_volatility=bv_res.total_volatility,
            relative_jump_ratio=rj,
            jump_mean=mu_j,
            jump_std=post.jump_std_magnitude,
            is_acute_jump=is_acute,
            recommended_action=action,
            position_scale_multiplier=pos_scale,
            stop_loss_buffer_multiplier=sl_buffer,
            details=details,
        )
        self._memory_cache[sym] = assessment
        return assessment

    def _synthesize_baseline_assessment(
        self,
        symbol: str,
    ) -> TickerJumpAssessment:
        """
        Fail-Open 合成基準評估（當外部數據中斷時的優雅降級）。
        預設回傳健康平穩擴散狀態 (CALM_DIFFUSION, λ_jump ~ 1.5, RJ ~ 0.08)。
        """
        sym = symbol.strip().upper()
        hash_seed = sum(ord(c) for c in sym) % 5
        base_lam = 1.20 + (hash_seed * 0.12)  # 1.20 ~ 1.68
        base_sigma = 0.22 + (hash_seed * 0.02)

        return TickerJumpAssessment(
            symbol=sym,
            regime=JumpRegime.CALM_DIFFUSION,
            jump_intensity=base_lam,
            continuous_volatility=base_sigma,
            total_volatility=base_sigma * 1.05,
            relative_jump_ratio=0.08,
            jump_mean=-0.015,
            jump_std=0.035,
            is_acute_jump=False,
            recommended_action="PROCEED",
            position_scale_multiplier=1.00,
            stop_loss_buffer_multiplier=1.00,
            details={"source": "fail_open_synthetic_baseline"},
        )

    # ── 對外公開主介面 ───────────────────────────────────────────────

    async def evaluate_ticker(
        self,
        symbol: str,
        force_refresh: bool = False,
    ) -> TickerJumpAssessment:
        """
        對單一標的執行即時貝葉斯跳躍擴散評估。
        """
        sym = symbol.strip().upper()

        if not self.is_enabled:
            return TickerJumpAssessment(
                symbol=sym,
                regime=JumpRegime.CALM_DIFFUSION,
                jump_intensity=0.0,
                continuous_volatility=0.0,
                total_volatility=0.0,
                relative_jump_ratio=0.0,
                jump_mean=0.0,
                jump_std=0.0,
                is_acute_jump=False,
                recommended_action="PROCEED",
                position_scale_multiplier=1.00,
                stop_loss_buffer_multiplier=1.00,
                details={"reason": "Bayesian jump guard disabled via configuration"},
            )

        if not force_refresh:
            cached = await self._get_cached_ticker(sym)
            if cached:
                return cached

        # 抓取日報酬率歷史數據
        returns = await self._fetch_recent_returns(sym)
        if returns and len(returns) >= 15:
            assessment = self.evaluate_returns_series(sym, returns)
            await self._set_cached_ticker(sym, assessment)
            return assessment

        # Fail-Open 合成基準
        baseline = self._synthesize_baseline_assessment(sym)
        await self._set_cached_ticker(sym, baseline)
        return baseline

    async def get_portfolio_jump_assessment(
        self,
        symbols: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> PortfolioJumpSummary:
        """
        對指定標的清單或核心候選池生成全方位跳躍擴散體制報告。
        """
        target_symbols = symbols or ["NVDA", "TSM", "AAPL", "MSFT", "MU", "AMD", "SPCX"]
        clean_symbols = [s.strip().upper() for s in target_symbols if s]

        assessments: Dict[str, TickerJumpAssessment] = {}
        acute_syms: List[str] = []
        mod_syms: List[str] = []
        calm_syms: List[str] = []

        tasks = [self.evaluate_ticker(sym, force_refresh=force_refresh) for sym in clean_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, res in zip(clean_symbols, results):
            if isinstance(res, Exception):
                logger.warning(f"Error evaluating jump diffusion for {sym}: {res}")
                ass = self._synthesize_baseline_assessment(sym)
            else:
                ass = res

            assessments[sym] = ass
            if ass.regime == JumpRegime.ACUTE_JUMP_REGIME:
                acute_syms.append(sym)
            elif ass.regime == JumpRegime.MODERATE_JUMP:
                mod_syms.append(sym)
            else:
                calm_syms.append(sym)

        if len(acute_syms) >= 2:
            overall_market = "SYSTEMIC_JUMP_SHOCK"
        elif len(acute_syms) >= 1 or len(mod_syms) >= 2:
            overall_market = "ELEVATED_JUMP_ACTIVITY"
        else:
            overall_market = "CALM"

        mean_lam = sum(a.jump_intensity for a in assessments.values()) / max(1, len(assessments))
        mean_rj = sum(a.relative_jump_ratio for a in assessments.values()) / max(1, len(assessments))

        summary = PortfolioJumpSummary(
            assessments=assessments,
            acute_symbols=acute_syms,
            moderate_symbols=mod_syms,
            calm_symbols=calm_syms,
            mean_jump_intensity=mean_lam,
            mean_relative_jump_ratio=mean_rj,
            overall_market_jump_regime=overall_market,
        )

        await self._cache_portfolio_summary(summary)
        return summary

    # ── 快取與輔助數據源 ───────────────────────────────────────────────

    async def _get_cached_ticker(self, symbol: str) -> Optional[TickerJumpAssessment]:
        sym = symbol.upper()
        mem = self._memory_cache.get(sym)
        if mem is not None:
            elapsed = (datetime.now(timezone.utc) - mem.timestamp).total_seconds()
            if elapsed < 300:
                return mem

        try:
            r = await self._get_redis()
            if r:
                data = await r.get(f"jump:latest:{sym}")
                if data:
                    raw = json.loads(data)
                    ass = TickerJumpAssessment(
                        symbol=raw["symbol"],
                        regime=JumpRegime(raw["regime"]),
                        jump_intensity=raw["jump_intensity"],
                        continuous_volatility=raw.get("continuous_volatility", 0.20),
                        total_volatility=raw.get("total_volatility", 0.22),
                        relative_jump_ratio=raw.get("relative_jump_ratio", 0.10),
                        jump_mean=raw.get("jump_mean", -0.02),
                        jump_std=raw.get("jump_std", 0.04),
                        is_acute_jump=raw.get("is_acute_jump", False),
                        recommended_action=raw.get("recommended_action", "PROCEED"),
                        position_scale_multiplier=raw.get("position_scale_multiplier", 1.0),
                        stop_loss_buffer_multiplier=raw.get("stop_loss_buffer_multiplier", 1.0),
                        details=raw.get("details", {}),
                    )
                    self._memory_cache[sym] = ass
                    return ass
        except Exception as e:
            logger.debug(f"Error fetching jump cache for {sym}: {e}")
        return None

    async def _set_cached_ticker(self, symbol: str, assessment: TickerJumpAssessment) -> None:
        sym = symbol.upper()
        self._memory_cache[sym] = assessment
        try:
            r = await self._get_redis()
            if r:
                payload = json.dumps(assessment.to_dict())
                await r.set(f"jump:latest:{sym}", payload, ex=300)
        except Exception as e:
            logger.debug(f"Error saving jump cache for {sym}: {e}")

    async def _cache_portfolio_summary(self, summary: PortfolioJumpSummary) -> None:
        try:
            r = await self._get_redis()
            if r:
                payload = json.dumps(summary.to_dict())
                await r.set(f"jump:portfolio:summary:{self.user_id}", payload, ex=300)
        except Exception as e:
            logger.debug(f"Error caching portfolio jump summary: {e}")

    def get_latest_cached_assessment(self, symbol: str) -> Optional[Dict[str, Any]]:
        sym = symbol.upper()
        mem = self._memory_cache.get(sym)
        if mem:
            return mem.to_dict()
        return None

    async def get_latest_portfolio_summary(self) -> Optional[Dict[str, Any]]:
        try:
            r = await self._get_redis()
            if r:
                data = await r.get(f"jump:portfolio:summary:{self.user_id}")
                if data:
                    return json.loads(data)
        except Exception as e:
            logger.debug(f"Error reading portfolio jump summary cache: {e}")
        return None

    async def _get_redis(self) -> Any:
        if self.redis_client is not None:
            return self.redis_client
        try:
            from src.infrastructure.cache.redis_client import get_redis
            return await get_redis(decode_responses=True)
        except Exception:
            return None

    async def _fetch_recent_returns(self, symbol: str) -> List[float]:
        """從 MarketDataService 抓取日報酬歷史"""
        if self.market_data_service and hasattr(self.market_data_service, "get_history_df"):
            try:
                loop = asyncio.get_running_loop()
                df = await loop.run_in_executor(
                    None, self.market_data_service.get_history_df, symbol, self.lookback_days
                )
                if df is not None and not df.empty and len(df) >= 10:
                    closes = df["Close"].dropna().values if "Close" in df else df["close"].dropna().values
                    returns = []
                    for i in range(1, len(closes)):
                        if closes[i - 1] > 0 and closes[i] > 0:
                            ret = math.log(closes[i] / closes[i - 1])
                            returns.append(ret)
                    return returns
            except Exception as e:
                logger.debug(f"Failed to fetch history df for {symbol}: {e}")
        return []
