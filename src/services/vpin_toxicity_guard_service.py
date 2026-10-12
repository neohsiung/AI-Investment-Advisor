"""
VPIN & Kyle's Lambda Microstructure Toxicity Guard Service
=========================================================
微觀結構訂單流毒性與知情交易者檢定守衛 (Kyle's Lambda & VPIN Microstructure Guard)

職責：
1. 成交量同步機率毒性 (VPIN, Volume-Synchronized Probability of Toxicity; Easley et al., 2012)：
   - 將連續成交量切分為等量桶 (Volume Buckets, V_B = ADV * ratio)。
   - 透過 Bulk Volume Classification (BVC) 或 Tick Rule 估算每筆/每 Bar 之主買量 V^B 與主賣量 V^S。
   - 滾動計算過去 N 個已完成桶之累積絕對失衡比率：
     VPIN = sum(|V_tau^B - V_tau^S|) / (N * V_B) in [0.0, 1.0]
   - 判定毒性體制：
     - NORMAL: VPIN < 0.25 (流動性健康，正常執行)
     - ELEVATED: 0.25 <= VPIN < 0.40 (中度失衡，拆單降速並適度調升滑點補償)
     - TOXIC: VPIN >= 0.40 (知情交易者聚集，觸發防守熔斷暫緩下單 3~5 分鐘)
2. Kyle's Lambda (λ) 價格衝擊模型 (Kyle, 1985)：
   - 建立價格變動 ΔP 與淨訂單流 Q = V^B - V^S 之 OLS 回歸：
     ΔP_tau = μ + λ * Q_tau + ε_tau
     λ = Cov(ΔP, Q) / Var(Q)
   - 量化每 1,000 股訂單失衡所造成的價格衝擊與知情交易者比率 α = VPIN / (1 + VPIN)。
3. 交易執行前置防護與開盤建倉守衛整合 (Closed-Loop Guard Integration)：
   - 在 SlippageGuardService.evaluate_trade 前置檢定：若標的 VPIN >= 0.40，主動阻斷市價或激進下單。
   - 在 BatchCashDeploymentService 標記毒性標的並暫緩執行，保留當前批次指針不跳號。
   - 具備 Fail-Open 與合成流退化機制，保證離線/數據缺失時系統永不崩潰。
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

logger = setup_logger("VPINToxicityGuardService")


class VPINToxicityRegime(str, Enum):
    """訂單流毒性體制分類"""
    NORMAL = "NORMAL"        # VPIN < 0.25: 流動性健康
    ELEVATED = "ELEVATED"    # 0.25 <= VPIN < 0.40: 中度知情交易滲透
    TOXIC = "TOXIC"          # VPIN >= 0.40: 重度毒性訂單流，暫緩下單


@dataclass
class VolumeBucketState:
    """單一成交量時鐘桶 (Volume Clock Bucket)"""
    bucket_index: int
    target_volume: float
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    start_price: float = 0.0
    end_price: float = 0.0
    is_complete: bool = False

    @property
    def total_volume(self) -> float:
        return self.buy_volume + self.sell_volume

    @property
    def remaining_capacity(self) -> float:
        return max(0.0, self.target_volume - self.total_volume)

    @property
    def imbalance(self) -> float:
        """淨訂單流 Q = V_B - V_S"""
        return self.buy_volume - self.sell_volume

    @property
    def abs_imbalance(self) -> float:
        """訂單絕對失衡 |V_B - V_S|"""
        return abs(self.buy_volume - self.sell_volume)

    @property
    def price_change(self) -> float:
        """桶內價格變動 ΔP = P_end - P_start"""
        return self.end_price - self.start_price


@dataclass
class KylesLambdaMetrics:
    """Kyle's Lambda (λ) 價格衝擊度量指標"""
    lambda_coeff: float                  # λ 斜率 (每 1,000 股訂單失衡造成的美元價格衝擊)
    r_squared: float                     # 回歸 R^2 擬合優度
    informed_trader_ratio: float         # 估計知情交易者比率 α
    sample_buckets_count: int            # 回歸樣本桶數
    cov_delta_p_q: float                 # Cov(ΔP, Q)
    var_q: float                         # Var(Q)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lambda_coeff": round(self.lambda_coeff, 6),
            "r_squared": round(self.r_squared, 4),
            "informed_trader_ratio": round(self.informed_trader_ratio, 4),
            "sample_buckets_count": self.sample_buckets_count,
            "cov_delta_p_q": round(self.cov_delta_p_q, 6),
            "var_q": round(self.var_q, 4),
        }


@dataclass
class TickerVPINAssessment:
    """單一標的微觀結構毒性檢定報告"""
    symbol: str
    vpin: float
    regime: VPINToxicityRegime
    kyle_lambda: float
    kyle_metrics: KylesLambdaMetrics
    adv: float
    bucket_size: float
    completed_buckets: int
    is_toxic: bool
    recommended_action: str              # "PROCEED", "THROTTLE", "DEFER"
    execution_pace_minutes: int          # 暫緩冷卻或拆單延遲分鐘數 (0, 3, 5)
    slippage_boost: float                # 建議滑點乘數增量 (0.0 ~ 1.0)
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "vpin": round(self.vpin, 4),
            "regime": self.regime.value,
            "kyle_lambda": round(self.kyle_lambda, 6),
            "kyle_metrics": self.kyle_metrics.to_dict(),
            "adv": round(self.adv, 0),
            "bucket_size": round(self.bucket_size, 0),
            "completed_buckets": self.completed_buckets,
            "is_toxic": self.is_toxic,
            "recommended_action": self.recommended_action,
            "execution_pace_minutes": self.execution_pace_minutes,
            "slippage_boost": round(self.slippage_boost, 4),
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PortfolioVPINSummary:
    """全投資組合微觀結構毒性監控摘要"""
    assessments: Dict[str, TickerVPINAssessment]
    toxic_symbols: List[str]
    elevated_symbols: List[str]
    normal_symbols: List[str]
    overall_market_toxicity: str         # "BENIGN", "MODERATE", "ACUTE_TOXICITY"
    mean_vpin: float
    mean_kyle_lambda: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessments": {k: v.to_dict() for k, v in self.assessments.items()},
            "toxic_symbols": self.toxic_symbols,
            "elevated_symbols": self.elevated_symbols,
            "normal_symbols": self.normal_symbols,
            "overall_market_toxicity": self.overall_market_toxicity,
            "mean_vpin": round(self.mean_vpin, 4),
            "mean_kyle_lambda": round(self.mean_kyle_lambda, 6),
            "timestamp": self.timestamp,
        }


class VPINToxicityGuardService:
    """微觀結構訂單流毒性與 Kyle's Lambda 守衛服務"""

    # 預設參數常數
    DEFAULT_BUCKET_SIZE_ADV_RATIO = 0.02   # 預設單桶成交量為 ADV 的 2% (即 1 天約 50 桶)
    DEFAULT_ALERT_THRESHOLD = 0.40         # VPIN 毒性熔斷警戒門檻 (>= 0.40)
    DEFAULT_ELEVATED_THRESHOLD = 0.25      # VPIN 中度升溫門檻 (>= 0.25)
    DEFAULT_WINDOW_BUCKETS = 50            # 滾動計算 VPIN 與 Kyle's Lambda 之桶數
    DEFAULT_PACE_MINUTES = 5               # 遭遇 TOXIC 時建議暫緩等待冷卻分鐘數
    MIN_BUCKET_SIZE = 1000.0               # 最低單桶股數下限

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

        # 行程內最新狀態快取 (Symbol -> TickerVPINAssessment)
        self._memory_cache: Dict[str, TickerVPINAssessment] = {}
        # 標的實時桶流狀態存儲 (Symbol -> List[VolumeBucketState])
        self._completed_buckets_map: Dict[str, List[VolumeBucketState]] = {}
        self._active_bucket_map: Dict[str, VolumeBucketState] = {}
        self._bucket_counter_map: Dict[str, int] = {}

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
        return self._get_setting_bool("enable_vpin_toxicity_guard", True)

    @property
    def bucket_size_adv_ratio(self) -> float:
        return self._get_setting_float("vpin_bucket_size_adv_ratio", self.DEFAULT_BUCKET_SIZE_ADV_RATIO)

    @property
    def alert_threshold(self) -> float:
        return self._get_setting_float("vpin_alert_threshold", self.DEFAULT_ALERT_THRESHOLD)

    @property
    def elevated_threshold(self) -> float:
        return self.DEFAULT_ELEVATED_THRESHOLD

    @property
    def window_buckets(self) -> int:
        return self._get_setting_int("vpin_window_buckets", self.DEFAULT_WINDOW_BUCKETS)

    @property
    def execution_pace_minutes(self) -> int:
        return self._get_setting_int("vpin_execution_pace_minutes", self.DEFAULT_PACE_MINUTES)

    # ── 核心微觀結構演算法 ───────────────────────────────────────────

    @staticmethod
    def classify_bvc(
        price_changes: List[float],
        volumes: List[float],
    ) -> Tuple[List[float], List[float]]:
        """
        大量成交量分類法 (Bulk Volume Classification, BVC - Easley et al., 2012)。
        使用價格變動除以其標準差之標準常態分佈累積機率 Φ(ΔP / σ_ΔP) 估算買方發起成交量比例：
        V_B = V * Φ(ΔP / σ)
        V_S = V * (1 - Φ(ΔP / σ))
        """
        n = len(volumes)
        if n == 0 or len(price_changes) != n:
            return [], []

        # 計算價格變動之標準差 (若均為 0 則預設微小值防除以零)
        mean_dp = sum(price_changes) / max(1, n)
        var_dp = sum((dp - mean_dp) ** 2 for dp in price_changes) / max(1, n)
        sigma = math.sqrt(var_dp) if var_dp > 1e-12 else 1e-6

        buy_vols: List[float] = []
        sell_vols: List[float] = []

        sqrt_2 = math.sqrt(2.0)
        for dp, vol in zip(price_changes, volumes):
            v = max(0.0, float(vol))
            z = dp / sigma
            # 標準常態 CDF: 0.5 * (1 + erf(z / sqrt(2)))
            phi = 0.5 * (1.0 + math.erf(z / sqrt_2))
            phi = max(0.0, min(1.0, phi))

            vb = v * phi
            vs = v * (1.0 - phi)
            buy_vols.append(vb)
            sell_vols.append(vs)

        return buy_vols, sell_vols

    @staticmethod
    def slice_into_buckets(
        buy_volumes: List[float],
        sell_volumes: List[float],
        prices: List[float],
        bucket_size: float,
    ) -> List[VolumeBucketState]:
        """
        將連續買賣單成交量切分為等量成交量時鐘桶 (Volume Clock Slicing)。
        """
        target_size = max(100.0, float(bucket_size))
        buckets: List[VolumeBucketState] = []
        bucket_idx = 1

        active = VolumeBucketState(
            bucket_index=bucket_idx,
            target_volume=target_size,
            start_price=prices[0] if prices else 100.0,
            end_price=prices[0] if prices else 100.0,
        )

        for i, (vb, vs) in enumerate(zip(buy_volumes, sell_volumes)):
            curr_px = prices[i] if i < len(prices) else (prices[-1] if prices else 100.0)
            tot_flow = vb + vs
            if tot_flow <= 0:
                continue

            buy_ratio = vb / tot_flow
            rem_flow = tot_flow

            while rem_flow > 1e-6:
                space = active.remaining_capacity
                fill = min(rem_flow, space)

                b_fill = fill * buy_ratio
                s_fill = fill * (1.0 - buy_ratio)

                active.buy_volume += b_fill
                active.sell_volume += s_fill
                active.end_price = curr_px
                rem_flow -= fill

                if active.remaining_capacity <= 1e-6:
                    active.is_complete = True
                    buckets.append(active)
                    bucket_idx += 1
                    active = VolumeBucketState(
                        bucket_index=bucket_idx,
                        target_volume=target_size,
                        start_price=curr_px,
                        end_price=curr_px,
                    )

        # 若最後一桶尚未填滿但已有成交，保留其作為未完成桶（若需要）
        if active.total_volume > 0:
            buckets.append(active)

        return buckets

    @classmethod
    def compute_vpin(
        cls,
        buckets: List[VolumeBucketState],
        window_n: Optional[int] = None,
    ) -> float:
        """
        計算滾動 VPIN (Volume-Synchronized Probability of Toxicity)。
        VPIN = sum(|V_tau^B - V_tau^S|) / (N * V_B)
        """
        if not buckets:
            return 0.0

        completed = [b for b in buckets if b.is_complete]
        if not completed:
            # 若無完整桶，退化計算現有未完成桶之失衡比例
            tot_v = sum(b.total_volume for b in buckets)
            tot_imb = sum(b.abs_imbalance for b in buckets)
            return (tot_imb / tot_v) if tot_v > 0 else 0.0

        n = window_n or len(completed)
        sample = completed[-n:]
        tot_v = sum(b.total_volume for b in sample)
        tot_imb = sum(b.abs_imbalance for b in sample)

        if tot_v <= 0:
            return 0.0

        vpin = tot_imb / tot_v
        return max(0.0, min(1.0, vpin))

    @classmethod
    def compute_kyles_lambda(
        cls,
        buckets: List[VolumeBucketState],
        window_n: Optional[int] = None,
    ) -> KylesLambdaMetrics:
        """
        估算 Kyle's Lambda (λ) 價格衝擊模型：
        ΔP_tau = μ + λ * Q_tau + ε_tau
        λ = Cov(ΔP, Q) / Var(Q)
        度量每 1,000 股訂單失衡造成的價格變動衝擊。
        """
        completed = [b for b in buckets if b.is_complete]
        if not completed:
            completed = buckets  # 降級使用所有可用桶

        n_window = window_n or len(completed)
        sample = completed[-n_window:]
        m = len(sample)

        if m < 2:
            return KylesLambdaMetrics(
                lambda_coeff=0.0,
                r_squared=0.0,
                informed_trader_ratio=0.0,
                sample_buckets_count=m,
                cov_delta_p_q=0.0,
                var_q=0.0,
            )

        q_list = [b.imbalance for b in sample]
        dp_list = [b.price_change for b in sample]

        mean_q = sum(q_list) / m
        mean_dp = sum(dp_list) / m

        cov_dp_q = sum((dp - mean_dp) * (q - mean_q) for dp, q in zip(dp_list, q_list)) / (m - 1)
        var_q = sum((q - mean_q) ** 2 for q in q_list) / (m - 1)
        var_dp = sum((dp - mean_dp) ** 2 for dp in dp_list) / (m - 1)

        if var_q > 1e-12:
            # 換算為每 1,000 股失衡之美元價格衝擊
            lambda_coeff = (cov_dp_q / var_q) * 1000.0
            r_sq = (cov_dp_q ** 2) / (var_dp * var_q) if var_dp > 1e-12 else 0.0
            r_sq = max(0.0, min(1.0, r_sq))
        else:
            lambda_coeff = 0.0
            r_sq = 0.0

        # 計算 VPIN 並推導知情交易者比率 α = VPIN / (1 + VPIN)
        tot_v = sum(b.total_volume for b in sample)
        tot_imb = sum(b.abs_imbalance for b in sample)
        vpin_est = (tot_imb / tot_v) if tot_v > 0 else 0.0
        alpha = vpin_est / (1.0 + vpin_est) if vpin_est > 0 else 0.0

        return KylesLambdaMetrics(
            lambda_coeff=lambda_coeff,
            r_squared=r_sq,
            informed_trader_ratio=alpha,
            sample_buckets_count=m,
            cov_delta_p_q=cov_dp_q,
            var_q=var_q,
        )

    # ── 即時數據與行情流攝取 ──────────────────────────────────────────

    def ingest_trade_tick(
        self,
        symbol: str,
        price: float,
        volume: float,
        direction: Optional[str] = None,
    ) -> None:
        """
        攝取單筆成交 Tick 進入標的成交量時鐘。
        """
        sym = symbol.strip().upper()
        vol = max(0.0, float(volume))
        px = float(price)
        if vol <= 0 or px <= 0:
            return

        # 估算 ADV 與單桶目標容量
        adv = 1000000.0
        bucket_size = max(self.MIN_BUCKET_SIZE, adv * self.bucket_size_adv_ratio)

        active = self._active_bucket_map.get(sym)
        if active is None:
            c = self._bucket_counter_map.get(sym, 0) + 1
            self._bucket_counter_map[sym] = c
            active = VolumeBucketState(
                bucket_index=c,
                target_volume=bucket_size,
                start_price=px,
                end_price=px,
            )
            self._active_bucket_map[sym] = active

        # 判定買賣方向
        dir_upper = str(direction).upper() if direction else ""
        if dir_upper == "BUY":
            is_buy = True
        elif dir_upper == "SELL":
            is_buy = False
        else:
            # Tick rule
            is_buy = px >= active.end_price

        rem_vol = vol
        while rem_vol > 0:
            space = active.remaining_capacity
            fill = min(rem_vol, space)

            if is_buy:
                active.buy_volume += fill
            else:
                active.sell_volume += fill

            active.end_price = px
            rem_vol -= fill

            if active.remaining_capacity <= 1e-6:
                active.is_complete = True
                completed_list = self._completed_buckets_map.setdefault(sym, [])
                completed_list.append(active)
                if len(completed_list) > self.window_buckets * 2:
                    self._completed_buckets_map[sym] = completed_list[-self.window_buckets * 2:]

                c = self._bucket_counter_map.get(sym, 0) + 1
                self._bucket_counter_map[sym] = c
                active = VolumeBucketState(
                    bucket_index=c,
                    target_volume=bucket_size,
                    start_price=px,
                    end_price=px,
                )
                self._active_bucket_map[sym] = active

    def ingest_bars(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        adv: Optional[float] = None,
    ) -> TickerVPINAssessment:
        """
        批次攝取 1 分鐘或 5 分鐘 Bar 數據，使用 BVC 分類並切分為 Volume Buckets。
        """
        sym = symbol.strip().upper()
        if not bars:
            return self._synthesize_baseline_assessment(sym)

        prices: List[float] = []
        volumes: List[float] = []
        price_changes: List[float] = []

        last_p = None
        total_vol = 0.0
        for b in bars:
            c = float(b.get("close") or b.get("c") or b.get("price") or 0.0)
            v = float(b.get("volume") or b.get("v") or 0.0)
            o = float(b.get("open") or b.get("o") or c)
            if c <= 0:
                continue

            prices.append(c)
            volumes.append(v)
            total_vol += v

            # 價格變動使用 Close - Open 或 Close - PrevClose
            dp = (c - last_p) if last_p is not None else (c - o)
            price_changes.append(dp)
            last_p = c

        effective_adv = adv or max(total_vol * 1.5, 1000000.0)
        bucket_size = max(self.MIN_BUCKET_SIZE, effective_adv * self.bucket_size_adv_ratio)

        # 1. BVC 流量分類
        b_flows, s_flows = self.classify_bvc(price_changes, volumes)

        # 2. 切分為 Volume Buckets
        buckets = self.slice_into_buckets(b_flows, s_flows, prices, bucket_size)

        # 3. 保存至內部狀態
        completed = [b for b in buckets if b.is_complete]
        self._completed_buckets_map[sym] = completed[-self.window_buckets * 2:]
        if buckets and not buckets[-1].is_complete:
            self._active_bucket_map[sym] = buckets[-1]

        # 4. 計算 VPIN 與 Kyle's Lambda
        vpin = self.compute_vpin(buckets, window_n=self.window_buckets)
        kyle = self.compute_kyles_lambda(buckets, window_n=self.window_buckets)

        assessment = self._build_assessment(
            symbol=sym,
            vpin=vpin,
            kyle_metrics=kyle,
            adv=effective_adv,
            bucket_size=bucket_size,
            completed_count=len(completed),
            last_price=prices[-1] if prices else 100.0,
        )
        self._memory_cache[sym] = assessment
        return assessment

    # ── 評估與檢定決策 ───────────────────────────────────────────────

    def _build_assessment(
        self,
        symbol: str,
        vpin: float,
        kyle_metrics: KylesLambdaMetrics,
        adv: float,
        bucket_size: float,
        completed_count: int,
        last_price: float,
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> TickerVPINAssessment:
        """根據 VPIN 與 Kyle's Lambda 判定體制與處置建議"""
        alert_th = self.alert_threshold
        elev_th = self.elevated_threshold

        if vpin >= alert_th:
            regime = VPINToxicityRegime.TOXIC
            is_toxic = True
            action = "DEFER"
            pace_min = self.execution_pace_minutes
            slippage_boost = 1.0  # 最大加成防禦
        elif vpin >= elev_th:
            regime = VPINToxicityRegime.ELEVATED
            is_toxic = False
            action = "THROTTLE"
            pace_min = 3
            # 線性縮放 0.3x ~ 0.7x
            scale = (vpin - elev_th) / max(0.01, alert_th - elev_th)
            slippage_boost = min(0.7, 0.3 + 0.4 * scale)
        else:
            regime = VPINToxicityRegime.NORMAL
            is_toxic = False
            action = "PROCEED"
            pace_min = 0
            slippage_boost = 0.0

        details = {
            "vpin_value": round(vpin, 4),
            "alert_threshold": round(alert_th, 4),
            "elevated_threshold": round(elev_th, 4),
            "kyle_lambda_impact_per_1k": round(kyle_metrics.lambda_coeff, 6),
            "kyle_r_squared": round(kyle_metrics.r_squared, 4),
            "informed_trader_ratio": round(kyle_metrics.informed_trader_ratio, 4),
            "last_price": round(last_price, 2),
            "completed_buckets": completed_count,
        }
        if extra_details:
            details.update(extra_details)

        return TickerVPINAssessment(
            symbol=symbol.upper(),
            vpin=vpin,
            regime=regime,
            kyle_lambda=kyle_metrics.lambda_coeff,
            kyle_metrics=kyle_metrics,
            adv=adv,
            bucket_size=bucket_size,
            completed_buckets=completed_count,
            is_toxic=is_toxic,
            recommended_action=action,
            execution_pace_minutes=pace_min,
            slippage_boost=slippage_boost,
            details=details,
        )

    def _synthesize_baseline_assessment(
        self,
        symbol: str,
        adv: float = 2500000.0,
        current_price: float = 150.0,
    ) -> TickerVPINAssessment:
        """
        Fail-Open 合成基準評估（當外部即時數據完全中斷時的優雅降級）。
        預設回傳健康常態 (NORMAL regime, VPIN ~ 0.18)，保證系統不因數據缺失中斷交易。
        """
        sym = symbol.strip().upper()
        # 基於 ticker 字母雜湊提供穩定平滑的正常值
        hash_seed = sum(ord(c) for c in sym) % 7
        baseline_vpin = 0.16 + (hash_seed * 0.01)  # 0.16 ~ 0.22
        bucket_size = max(self.MIN_BUCKET_SIZE, adv * self.bucket_size_adv_ratio)

        kyle = KylesLambdaMetrics(
            lambda_coeff=0.00015 * (1 + hash_seed * 0.1),
            r_squared=0.12,
            informed_trader_ratio=baseline_vpin / (1.0 + baseline_vpin),
            sample_buckets_count=self.window_buckets,
            cov_delta_p_q=0.005,
            var_q=10000.0,
        )

        return self._build_assessment(
            symbol=sym,
            vpin=baseline_vpin,
            kyle_metrics=kyle,
            adv=adv,
            bucket_size=bucket_size,
            completed_count=self.window_buckets,
            last_price=current_price,
            extra_details={"source": "fail_open_synthetic_baseline"},
        )

    # ── 對外公開主介面 ───────────────────────────────────────────────

    async def evaluate_ticker(
        self,
        symbol: str,
        action: Optional[str] = None,
        force_refresh: bool = False,
    ) -> TickerVPINAssessment:
        """
        對單一標的執行即時微觀結構訂單流毒性檢定。
        1. 檢查服務開關 (若關閉則返回 NORMAL 放行)
        2. 讀取快取 (Redis 或 Memory)
        3. 嘗試從 Polygon / MarketDataService 抓取最新分時 bars 進行 BVC 估算
        4. 降級使用行程內現有桶或合成基準，並寫入快取
        """
        sym = symbol.strip().upper()

        if not self.is_enabled:
            kyle_dummy = KylesLambdaMetrics(
                lambda_coeff=0.0, r_squared=0.0, informed_trader_ratio=0.0,
                sample_buckets_count=0, cov_delta_p_q=0.0, var_q=0.0
            )
            return TickerVPINAssessment(
                symbol=sym,
                vpin=0.0,
                regime=VPINToxicityRegime.NORMAL,
                kyle_lambda=0.0,
                kyle_metrics=kyle_dummy,
                adv=0.0,
                bucket_size=0.0,
                completed_buckets=0,
                is_toxic=False,
                recommended_action="PROCEED",
                execution_pace_minutes=0,
                slippage_boost=0.0,
                details={"reason": "VPIN toxicity guard disabled via configuration"},
            )

        # 讀取快取 (若不強制刷新)
        if not force_refresh:
            cached = await self._get_cached_ticker(sym)
            if cached:
                return cached

        # 檢視行程內已攝取之 completed buckets
        completed = self._completed_buckets_map.get(sym, [])
        if len(completed) >= 5:
            adv = 2000000.0
            bucket_size = max(self.MIN_BUCKET_SIZE, adv * self.bucket_size_adv_ratio)
            vpin = self.compute_vpin(completed, window_n=self.window_buckets)
            kyle = self.compute_kyles_lambda(completed, window_n=self.window_buckets)
            last_p = completed[-1].end_price if completed else 100.0
            assessment = self._build_assessment(
                symbol=sym,
                vpin=vpin,
                kyle_metrics=kyle,
                adv=adv,
                bucket_size=bucket_size,
                completed_count=len(completed),
                last_price=last_p,
                extra_details={"source": "realtime_ingested_buckets"},
            )
            await self._set_cached_ticker(sym, assessment)
            return assessment

        # 嘗試從市場數據源提取近期 Bars 進行 BVC 計算
        try:
            bars = await self._fetch_recent_bars(sym)
            if bars and len(bars) >= 5:
                assessment = self.ingest_bars(sym, bars)
                await self._set_cached_ticker(sym, assessment)
                return assessment
        except Exception as e:
            logger.debug(f"Failed to fetch market bars for VPIN on {sym}: {e}")

        # Fail-Open 合成基準
        baseline = self._synthesize_baseline_assessment(sym)
        await self._set_cached_ticker(sym, baseline)
        return baseline

    async def get_portfolio_vpin_assessment(
        self,
        symbols: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> PortfolioVPINSummary:
        """
        對指定標的清單或核心候選池生成全方位毒性體制報告。
        """
        target_symbols = symbols or ["NVDA", "TSM", "AAPL", "MSFT", "MU", "AMD", "SPCX"]
        clean_symbols = [s.strip().upper() for s in target_symbols if s]

        assessments: Dict[str, TickerVPINAssessment] = {}
        toxic_syms: List[str] = []
        elev_syms: List[str] = []
        norm_syms: List[str] = []

        # 並行評估所有標的
        tasks = [self.evaluate_ticker(sym, force_refresh=force_refresh) for sym in clean_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, res in zip(clean_symbols, results):
            if isinstance(res, Exception):
                logger.warning(f"Error evaluating VPIN for {sym}: {res}")
                ass = self._synthesize_baseline_assessment(sym)
            else:
                ass = res

            assessments[sym] = ass
            if ass.regime == VPINToxicityRegime.TOXIC:
                toxic_syms.append(sym)
            elif ass.regime == VPINToxicityRegime.ELEVATED:
                elev_syms.append(sym)
            else:
                norm_syms.append(sym)

        # 全體市場微觀結構狀態判定
        if toxic_syms:
            overall_market = "ACUTE_TOXICITY" if len(toxic_syms) >= 2 else "MODERATE"
        elif elev_syms:
            overall_market = "MODERATE"
        else:
            overall_market = "BENIGN"

        mean_vpin = sum(a.vpin for a in assessments.values()) / max(1, len(assessments))
        mean_kyle = sum(a.kyle_lambda for a in assessments.values()) / max(1, len(assessments))

        summary = PortfolioVPINSummary(
            assessments=assessments,
            toxic_symbols=toxic_syms,
            elevated_symbols=elev_syms,
            normal_symbols=norm_syms,
            overall_market_toxicity=overall_market,
            mean_vpin=mean_vpin,
            mean_kyle_lambda=mean_kyle,
        )

        # 寫入 Redis 快取供對話指令快速讀取
        await self._cache_portfolio_summary(summary)
        return summary

    # ── 快取與輔助數據源 ───────────────────────────────────────────────

    async def _get_cached_ticker(self, symbol: str) -> Optional[TickerVPINAssessment]:
        sym = symbol.upper()
        # 1. Memory 快取
        mem = self._memory_cache.get(sym)
        if mem is not None:
            # 5 分鐘內有效
            elapsed = (datetime.now(timezone.utc) - mem.timestamp).total_seconds()
            if elapsed < 300:
                return mem

        # 2. Redis 快取
        try:
            r = await self._get_redis()
            if r:
                data = await r.get(f"vpin:latest:{sym}")
                if data:
                    raw = json.loads(data)
                    k_raw = raw.get("kyle_metrics", {})
                    kyle_obj = KylesLambdaMetrics(
                        lambda_coeff=k_raw.get("lambda_coeff", 0.0),
                        r_squared=k_raw.get("r_squared", 0.0),
                        informed_trader_ratio=k_raw.get("informed_trader_ratio", 0.0),
                        sample_buckets_count=k_raw.get("sample_buckets_count", 0),
                        cov_delta_p_q=k_raw.get("cov_delta_p_q", 0.0),
                        var_q=k_raw.get("var_q", 0.0),
                    )
                    ass = TickerVPINAssessment(
                        symbol=raw["symbol"],
                        vpin=raw["vpin"],
                        regime=VPINToxicityRegime(raw["regime"]),
                        kyle_lambda=raw["kyle_lambda"],
                        kyle_metrics=kyle_obj,
                        adv=raw.get("adv", 1000000.0),
                        bucket_size=raw.get("bucket_size", 20000.0),
                        completed_buckets=raw.get("completed_buckets", 0),
                        is_toxic=raw.get("is_toxic", False),
                        recommended_action=raw.get("recommended_action", "PROCEED"),
                        execution_pace_minutes=raw.get("execution_pace_minutes", 0),
                        slippage_boost=raw.get("slippage_boost", 0.0),
                        details=raw.get("details", {}),
                    )
                    self._memory_cache[sym] = ass
                    return ass
        except Exception as e:
            logger.debug(f"Error fetching VPIN cache for {sym}: {e}")
        return None

    async def _set_cached_ticker(self, symbol: str, assessment: TickerVPINAssessment) -> None:
        sym = symbol.upper()
        self._memory_cache[sym] = assessment
        try:
            r = await self._get_redis()
            if r:
                payload = json.dumps(assessment.to_dict())
                await r.set(f"vpin:latest:{sym}", payload, ex=300)
        except Exception as e:
            logger.debug(f"Error saving VPIN cache for {sym}: {e}")

    async def _cache_portfolio_summary(self, summary: PortfolioVPINSummary) -> None:
        try:
            r = await self._get_redis()
            if r:
                payload = json.dumps(summary.to_dict())
                await r.set(f"vpin:portfolio:summary:{self.user_id}", payload, ex=300)
        except Exception as e:
            logger.debug(f"Error caching portfolio VPIN summary: {e}")

    def get_latest_cached_assessment(self, symbol: str) -> Optional[Dict[str, Any]]:
        """同步讀取標的記憶體快取（供 router 與快速檢查使用）"""
        sym = symbol.upper()
        mem = self._memory_cache.get(sym)
        if mem:
            return mem.to_dict()
        return None

    async def get_latest_portfolio_summary(self) -> Optional[Dict[str, Any]]:
        """讀取全體組合最新快取摘要"""
        try:
            r = await self._get_redis()
            if r:
                data = await r.get(f"vpin:portfolio:summary:{self.user_id}")
                if data:
                    return json.loads(data)
        except Exception as e:
            logger.debug(f"Error reading portfolio summary cache: {e}")
        return None

    async def _get_redis(self) -> Any:
        if self.redis_client is not None:
            return self.redis_client
        try:
            from src.infrastructure.cache.redis_client import get_redis
            return await get_redis(decode_responses=True)
        except Exception:
            return None

    async def _fetch_recent_bars(self, symbol: str) -> List[Dict[str, Any]]:
        """從 Polygon 或 MarketDataService 獲取分時 bars"""
        # 1. 嘗試透過 Polygon 快照/歷史
        try:
            poly_key = None
            if self.settings_service:
                poly_key = self.settings_service.get_setting("source_polygon_api_key")
            if poly_key:
                import httpx
                # 抓取最近 1 天之 1-minute bars
                today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{today_str}/{today_str}"
                params = {"apiKey": poly_key, "limit": 120}
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        if results:
                            return [
                                {
                                    "open": float(r.get("o", 0.0)),
                                    "high": float(r.get("h", 0.0)),
                                    "low": float(r.get("l", 0.0)),
                                    "close": float(r.get("c", 0.0)),
                                    "volume": float(r.get("v", 0.0)),
                                }
                                for r in results
                            ]
        except Exception as poly_err:
            logger.debug(f"Polygon bars fetch error for {symbol}: {poly_err}")

        # 2. 嘗試透過 MarketDataService.get_history_df
        if self.market_data_service and hasattr(self.market_data_service, "get_history_df"):
            try:
                loop = asyncio.get_running_loop()
                df = await loop.run_in_executor(None, self.market_data_service.get_history_df, symbol, 10)
                if df is not None and not df.empty:
                    bars = []
                    for _, row in df.iterrows():
                        bars.append({
                            "open": float(row.get("Open", row.get("close", 0.0))),
                            "high": float(row.get("High", row.get("close", 0.0))),
                            "low": float(row.get("Low", row.get("close", 0.0))),
                            "close": float(row.get("Close", 0.0)),
                            "volume": float(row.get("Volume", 0.0)),
                        })
                    return bars
            except Exception as mds_err:
                logger.debug(f"MarketDataService history df error for {symbol}: {mds_err}")

        return []
