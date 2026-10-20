"""
Kalman Filter Dynamic Cointegration & Statistical Arbitrage Pairs Service (Phase 62B)
=====================================================================================
卡爾曼濾波動態協整與統計套利配對引擎

核心金融工程與量化數學：
1. 線上遞迴狀態空間估計 (State-Space Model):
   - 觀測方程式 (Measurement Equation):
     y_t = α_t + β_t * x_t + v_t,   v_t ~ N(0, R_t)
   - 狀態方程式 (State Equation):
     θ_t = [α_t, β_t]^T = θ_{t-1} + w_t,   w_t ~ N(0, Q_t)
   - 動態避險比率 (Dynamic Hedge Ratio β_t) 隨市場體制線上即時收斂，
     相較於傳統 OLS 靜態回歸更具自適應性，消除結構突變滯後效應。
2. 殘差價差 (Residual Spread e_t) 與 Ornstein-Uhlenbeck (OU) 均值回歸半衰期:
   - e_t = y_t - (α_t + β_t * x_t)
   - 離散 AR(1) 均值回歸估計：
     Δe_t = a + b * e_{t-1} + ε_t
     半衰期 t_{1/2} = -ln(2) / ln(1 + b) ≈ -ln(2) / b (當 b < 0)
   - 若 b >= 0 則為發散非平穩序列 (Structural Break)。
3. 動態滾動 Z-Score 統計套利訊號:
   - Z_t = (e_t - μ_e) / σ_e
4. 4 級配對體制 (Pairs Trading Regimes):
   - EQUILIBRIUM_COINTEGRATED: |Z_t| <= 1.0，價差處於常態震盪平衡區。
   - DIVERGENCE_ARBITRAGE_ENTRY: 1.5 <= |Z_t| <= 2.5 且 t_{1/2} <= 15 天，具備強均值回歸引力，觸發無 Beta 統計套利進場信號。
   - MEAN_REVERSION_EXIT: |Z_t| <= 0.5，價差收斂至平衡點，獲利平倉離場。
   - STRUCTURAL_BREAK_STOP_LOSS: |Z_t| > 3.0 或價差發散 (b >= 0)，協整關係破裂停損。
5. 0-LLM 數理優先：矩陣遞迴演算法與最小平方法回歸，例行監控 0 Token 開銷。
6. 雙渠道輸出：Telegram HTML + Email nl2br 格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import math
import random
import zlib
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("KalmanPairsCointegrationService")


@dataclass
class KalmanPairsMetric:
    """配對標的卡爾曼濾波動態協整度量結果"""
    ticker_y: str
    ticker_x: str
    price_y: float
    price_x: float
    dynamic_beta: float                # Kalman β_t (對沖比率)
    dynamic_alpha: float               # Kalman α_t (截距)
    residual_spread: float             # e_t = y - (α + β*x)
    spread_zscore: float               # Z_t = (e - μ) / σ
    ou_half_life_days: float           # Ornstein-Uhlenbeck 半衰期 (天)
    regime: str                        # EQUILIBRIUM_COINTEGRATED, DIVERGENCE_ARBITRAGE_ENTRY, MEAN_REVERSION_EXIT, STRUCTURAL_BREAK_STOP_LOSS
    arbitrage_action: str              # PAIR_LONG_Y_SHORT_X, PAIR_SHORT_Y_LONG_X, CLOSE_PAIR_POSITIONS, HOLD_EQUILIBRIUM, EMERGENCY_PAIR_STOP_LOSS
    target_hedge_ratio_x_per_y: float  # 每 1 單位 Y 需配置的 X 股數比例 (無 Beta 對沖)
    requires_circuit_breaker: bool     # 是否觸發結構性破裂熔斷
    rationale: str
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Set when the series was synthetic (no real price history): the numbers are NOT a measurement
    # and must never drive a decision. 序列為合成（無真實歷史價）時必填，數值不得作為決策輸入。
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker_y": self.ticker_y,
            "ticker_x": self.ticker_x,
            "price_y": round(self.price_y, 2),
            "price_x": round(self.price_x, 2),
            "dynamic_beta": round(self.dynamic_beta, 4),
            "dynamic_alpha": round(self.dynamic_alpha, 4),
            "residual_spread": round(self.residual_spread, 4),
            "spread_zscore": round(self.spread_zscore, 2),
            "ou_half_life_days": round(self.ou_half_life_days, 1),
            "regime": self.regime,
            "arbitrage_action": self.arbitrage_action,
            "target_hedge_ratio_x_per_y": round(self.target_hedge_ratio_x_per_y, 4),
            "requires_circuit_breaker": self.requires_circuit_breaker,
            "rationale": self.rationale,
            "evaluated_at": self.evaluated_at,
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KalmanPairsMetric:
        return cls(
            ticker_y=str(data.get("ticker_y", "")),
            ticker_x=str(data.get("ticker_x", "")),
            price_y=float(data.get("price_y", 100.0) or 100.0),
            price_x=float(data.get("price_x", 100.0) or 100.0),
            dynamic_beta=float(data.get("dynamic_beta", 1.0) or 1.0),
            dynamic_alpha=float(data.get("dynamic_alpha", 0.0) or 0.0),
            residual_spread=float(data.get("residual_spread", 0.0) or 0.0),
            spread_zscore=float(data.get("spread_zscore", 0.0) or 0.0),
            ou_half_life_days=float(data.get("ou_half_life_days", 10.0) or 10.0),
            regime=str(data.get("regime", "EQUILIBRIUM_COINTEGRATED")),
            arbitrage_action=str(data.get("arbitrage_action", "HOLD_EQUILIBRIUM")),
            target_hedge_ratio_x_per_y=float(data.get("target_hedge_ratio_x_per_y", 1.0) or 1.0),
            requires_circuit_breaker=bool(data.get("requires_circuit_breaker", False)),
            rationale=str(data.get("rationale", "")),
            evaluated_at=data.get("evaluated_at") or datetime.now(timezone.utc).isoformat(),
            fallback_reason=data.get("fallback_reason"),
        )


class KalmanPairsCointegrationService:
    """卡爾曼濾波動態協整與統計套利配對服務"""

    REGIME_EQUILIBRIUM = "EQUILIBRIUM_COINTEGRATED"
    REGIME_DIVERGENCE = "DIVERGENCE_ARBITRAGE_ENTRY"
    REGIME_REVERSION = "MEAN_REVERSION_EXIT"
    REGIME_STRUCTURAL_BREAK = "STRUCTURAL_BREAK_STOP_LOSS"

    ACTION_LONG_Y_SHORT_X = "PAIR_LONG_Y_SHORT_X"
    ACTION_SHORT_Y_LONG_X = "PAIR_SHORT_Y_LONG_X"
    ACTION_CLOSE = "CLOSE_PAIR_POSITIONS"
    ACTION_HOLD = "HOLD_EQUILIBRIUM"
    ACTION_STOP_LOSS = "EMERGENCY_PAIR_STOP_LOSS"

    FALLBACK_SYNTHETIC = "synthetic_series"

    REDIS_CACHE_TTL_SECONDS = 300
    REDIS_KEY_PREFIX = "kalman_pairs:metric"

    # Default Kalman hyperparameters
    DELTA = 1e-4  # Transition covariance multiplier
    V_TRANS = 1e-3  # Observation noise variance

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
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

        if market_data_service is not None:
            self.market_data_service = market_data_service
        else:
            try:
                from src.services.market_data_service import MarketDataService
                self.market_data_service = MarketDataService(settings_service=self.settings_service)
            except Exception:
                self.market_data_service = None

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service and hasattr(self.settings_service, "get_setting"):
            try:
                val = self.settings_service.get_setting(key, default)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to read setting {key}: {e}")
        return default

    async def is_enabled(self) -> bool:
        """檢查是否啟用卡爾曼濾波動態協整與統計套利"""
        val = self._get_setting("enable_kalman_pairs_cointegration", True)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return True

    # -------------------------------------------------------------
    # 核心數學演算法 1：線上卡爾曼濾波遞迴更新
    # -------------------------------------------------------------
    @classmethod
    def run_kalman_filter_series(
        cls,
        series_y: List[float],
        series_x: List[float],
        delta: float = 1e-4,
        v_noise: float = 1e-3,
    ) -> Tuple[List[float], List[float], List[float]]:
        """
        對歷史價格序列線上遞迴執行 2D 卡爾曼濾波。
        狀態向量 θ_t = [α_t, β_t]^T
        返回 (alphas, betas, spreads)。
        """
        n = min(len(series_y), len(series_x))
        if n == 0:
            return [], [], []

        # 初始狀態與共變異矩陣
        # θ_0 = [0.0, 1.0]^T
        theta = [0.0, series_y[0] / series_x[0] if series_x[0] > 0 else 1.0]
        # P_0 = [[1, 0], [0, 1]]
        P = [[1.0, 0.0], [0.0, 1.0]]
        # 過程雜訊 Q = (delta / (1 - delta)) * I
        q_val = delta / (1.0 - delta) if delta < 1.0 else 1e-4
        Q = [[q_val, 0.0], [0.0, q_val]]

        alphas: List[float] = []
        betas: List[float] = []
        spreads: List[float] = []

        for t in range(n):
            y_t = series_y[t]
            x_t = series_x[t]

            # 1. 預測步 (Prediction)
            # θ_{t|t-1} = θ_{t-1}
            # P_{t|t-1} = P_{t-1} + Q
            P_pred = [
                [P[0][0] + Q[0][0], P[0][1] + Q[0][1]],
                [P[1][0] + Q[1][0], P[1][1] + Q[1][1]],
            ]

            # 2. 觀測矩陣 H_t = [1.0, x_t]
            # 殘差 e_t = y_t - H_t * θ_{t|t-1} = y_t - (α + β * x_t)
            y_hat = theta[0] + theta[1] * x_t
            e_t = y_t - y_hat

            # 3. 創新共變異 S_t = H * P_pred * H^T + R
            # H * P_pred = [P00 + x*P10, P01 + x*P11]
            hp0 = P_pred[0][0] + x_t * P_pred[1][0]
            hp1 = P_pred[0][1] + x_t * P_pred[1][1]
            s_t = hp0 * 1.0 + hp1 * x_t + v_noise

            if abs(s_t) < 1e-12:
                s_t = 1e-12

            # 4. 卡爾曼增益 K_t = P_pred * H^T / S_t
            k0 = (P_pred[0][0] + P_pred[0][1] * x_t) / s_t
            k1 = (P_pred[1][0] + P_pred[1][1] * x_t) / s_t

            # 5. 更新步 (Update)
            theta[0] += k0 * e_t
            theta[1] += k1 * e_t

            # P_t = P_pred - K * H * P_pred
            # K * (H * P_pred) = [[k0*hp0, k0*hp1], [k1*hp0, k1*hp1]]
            P[0][0] = P_pred[0][0] - k0 * hp0
            P[0][1] = P_pred[0][1] - k0 * hp1
            P[1][0] = P_pred[1][0] - k1 * hp0
            P[1][1] = P_pred[1][1] - k1 * hp1

            alphas.append(theta[0])
            betas.append(theta[1])
            spreads.append(e_t)

        return alphas, betas, spreads

    # -------------------------------------------------------------
    # 核心數學演算法 2：Ornstein-Uhlenbeck 均值回歸半衰期精算
    # -------------------------------------------------------------
    @staticmethod
    def calculate_ou_half_life(spreads: List[float]) -> float:
        """
        透過一階自回歸 AR(1) 估計 Ornstein-Uhlenbeck 均值回歸速度與半衰期：
        Δe_t = a + b * e_{t-1} + ε_t
        t_{1/2} = -ln(2) / b
        若 b >= 0 則代表無均值回歸 (非協整或發散)，返回 999.0。
        """
        if len(spreads) < 10:
            return 10.0

        n = len(spreads)
        # y = Δe_t, x = e_{t-1}
        deltas = [spreads[i] - spreads[i - 1] for i in range(1, n)]
        lags = [spreads[i - 1] for i in range(1, n)]
        m = len(deltas)

        sum_x = sum(lags)
        sum_y = sum(deltas)
        sum_xx = sum(x * x for x in lags)
        sum_xy = sum(x * y for x, y in zip(lags, deltas))

        denom = m * sum_xx - sum_x * sum_x
        if abs(denom) < 1e-12:
            return 999.0

        b = (m * sum_xy - sum_x * sum_y) / denom

        if b >= 0.0:
            return 999.0  # Diverging / Non-stationary

        # Half-life = -ln(2) / ln(1 + b); b < 0 here and 1 + b > 0.0001 is checked first, so log is safe.
        if 1.0 + b <= 0.0001:
            return 1.0  # Extreme mean reversion within 1 day
        half_life = -math.log(2.0) / math.log(1.0 + b)
        return max(0.5, min(999.0, half_life))

    # -------------------------------------------------------------
    # 核心數學演算法 3：滾動價差 Z-Score
    # -------------------------------------------------------------
    @staticmethod
    def calculate_spread_zscore(spreads: List[float], lookback: int = 20) -> float:
        """
        計算殘差價差之動態滾動 Z-Score:
        Z = (e_t - μ_e) / σ_e
        """
        if not spreads:
            return 0.0
        window = spreads[-lookback:] if len(spreads) >= lookback else spreads
        if len(window) < 2:
            return 0.0

        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / (len(window) - 1)
        std = math.sqrt(variance) if variance > 1e-12 else 1e-6
        current_spread = spreads[-1]
        z = (current_spread - mean) / std
        return max(-5.0, min(5.0, z))

    # -------------------------------------------------------------
    # 歷史數據獲取或數理降級生成
    # -------------------------------------------------------------
    async def get_price_series_pair(
        self,
        ticker_y: str,
        ticker_x: str,
        periods: int = 60,
    ) -> Tuple[List[float], List[float], bool]:
        """
        獲取配對資產的收盤價格序列 (Y 與 X)，並回報是否為合成序列 (is_synthetic)。
        Returns (series_y, series_x, is_synthetic); a synthetic series is deterministic per pair.
        """
        sy = ticker_y.upper().strip()
        sx = ticker_x.upper().strip()

        # 嘗試從 MarketDataService 獲取真實 OHLCV 歷史價格
        if self.market_data_service and hasattr(self.market_data_service, "get_historical_prices"):
            try:
                hist_y = await self.market_data_service.get_historical_prices(sy, days=periods)
                hist_x = await self.market_data_service.get_historical_prices(sx, days=periods)
                if hist_y and hist_x and len(hist_y) >= 15 and len(hist_x) >= 15:
                    n = min(len(hist_y), len(hist_x))
                    return hist_y[-n:], hist_x[-n:], False
            except Exception as e:
                logger.debug(f"Direct history fetch failed for pair ({sy}, {sx}): {e}")

        # 數理第一原則降級：獲取即時價格並基於板塊相關性生成微觀高頻序列
        prior_price_map = {
            "SPY": 580.0, "QQQ": 490.0, "NVDA": 135.0, "AAPL": 230.0,
            "MSFT": 420.0, "TSM": 190.0, "META": 580.0, "AMD": 160.0,
            "AMZN": 190.0, "GOOGL": 170.0, "TSLA": 220.0,
        }
        py = prior_price_map.get(sy, 100.0)
        px = prior_price_map.get(sx, 100.0)
        try:
            r = await self._get_redis()
            if r:
                cp_y = await r.get(f"market:price:{sy}")
                cp_x = await r.get(f"market:price:{sx}")
                if cp_y:
                    py = float(cp_y)
                if cp_x:
                    px = float(cp_x)
        except Exception:
            pass

        # 依據標的特性設定預期動態對沖比例
        expected_ratio = py / px if px > 0 else 1.0
        series_x = []
        series_y = []
        # Generate synthetic co-integrated random walk
        # Stable seed: builtin hash() of str varies per process (PYTHONHASHSEED); crc32 does not.
        rnd = random.Random(zlib.crc32((sy + sx).encode("utf-8")) & 0xFFFF)
        curr_x = px * 0.95
        spread = 0.0

        for i in range(periods):
            # Market common factor shock
            mkt_shock = rnd.gauss(0.0005, 0.012)
            curr_x *= (1.0 + mkt_shock)
            # Mean-reverting spread shock (OU process)
            spread_shock = -0.15 * spread + rnd.gauss(0.0, py * 0.008)
            spread += spread_shock
            curr_y = expected_ratio * curr_x + spread

            series_x.append(max(1.0, curr_x))
            series_y.append(max(1.0, curr_y))

        # Adjust the very last prices to match live prices
        series_x[-1] = px
        series_y[-1] = py

        return series_y, series_x, True

    # -------------------------------------------------------------
    # 診斷與配對體制判定 (Regime Evaluation)
    # -------------------------------------------------------------
    async def evaluate_pairs_cointegration(
        self,
        ticker_y: str,
        ticker_x: str,
    ) -> KalmanPairsMetric:
        """
        評估兩檔標的之卡爾曼濾波動態協整性、均值回歸半衰期與統計套利操作信號。
        """
        sy = ticker_y.upper().strip()
        sx = ticker_x.upper().strip()

        # 1. 取得配對價格序列
        series_y, series_x, is_synthetic = await self.get_price_series_pair(sy, sx, periods=60)
        py = series_y[-1] if series_y else 100.0
        px = series_x[-1] if series_x else 100.0

        # 2. 執行卡爾曼濾波
        alphas, betas, spreads = self.run_kalman_filter_series(
            series_y, series_x, delta=self.DELTA, v_noise=self.V_TRANS
        )

        dyn_beta = betas[-1] if betas else 1.0
        dyn_alpha = alphas[-1] if alphas else 0.0
        residual_spread = spreads[-1] if spreads else 0.0

        # 3. 計算 OU 半衰期與 Z-Score
        half_life = self.calculate_ou_half_life(spreads)
        z_score = self.calculate_spread_zscore(spreads, lookback=20)

        # 4. 計算無 Beta 對沖之股份配置比率
        # 每 1 股 Y 需放空/做多多少股 X，使得組合 Beta = 0:
        # Hedge Ratio (shares of X per share of Y) = β_t
        target_hedge_ratio = max(0.01, min(50.0, dyn_beta))

        # 5. 判定 4 級配對體制與套利行動
        regime = self.REGIME_EQUILIBRIUM
        action = self.ACTION_HOLD
        requires_circuit_breaker = False
        rationale = ""

        # 結構性破裂門檻：|Z| > 3.0 或半衰期極度發散 (> 35 天)
        if abs(z_score) >= 3.0 or half_life >= 35.0:
            regime = self.REGIME_STRUCTURAL_BREAK
            action = self.ACTION_STOP_LOSS
            requires_circuit_breaker = True
            rationale = (
                f"結構性破裂熔斷體制：價差 Z-Score 達到極端異常值 ({z_score:+.2f}σ) 或 "
                f"OU 均值回歸半衰期發散 ({half_life:.1f} 天)，"
                f"兩者基本面相關結構可能已被打破，嚴格觸發停損保護，禁止逆勢加碼套利。"
            )
        # 套利進場門檻：1.5 <= |Z| < 3.0 且半衰期收斂 <= 18 天
        elif abs(z_score) >= 1.5 and half_life <= 18.0:
            regime = self.REGIME_DIVERGENCE
            if z_score >= 1.5:
                # e_t = Y - (α + β*X) 過高 -> Y 高估，X 低估 -> 做空 Y，做多 X
                action = self.ACTION_SHORT_Y_LONG_X
                rationale = (
                    f"價差正向發散套利機會：Z-Score 為 {z_score:+.2f}σ (Y 溢價 / X 折價)，"
                    f"OU 均值回歸半衰期僅 {half_life:.1f} 天具備強回歸動力。"
                    f"建議【做空 {sy} (1 單位) / 做多 {sx} ({target_hedge_ratio:.2f} 單位)】收割均值回歸利差。"
                )
            else:
                # e_t 過低 -> Y 低估，X 高估 -> 做多 Y，做空 X
                action = self.ACTION_LONG_Y_SHORT_X
                rationale = (
                    f"價差負向發散套利機會：Z-Score 為 {z_score:+.2f}σ (Y 折價 / X 溢價)，"
                    f"OU 均值回歸半衰期僅 {half_life:.1f} 天具備強回歸動力。"
                    f"建議【做多 {sy} (1 單位) / 做空 {sx} ({target_hedge_ratio:.2f} 單位)】進行無 Beta 利差套利。"
                )
        # 獲利平倉門檻：|Z| <= 0.5 且先前已有收斂趨勢
        elif abs(z_score) <= 0.5:
            regime = self.REGIME_REVERSION
            action = self.ACTION_CLOSE
            rationale = (
                f"價差均值回歸平倉體制：殘差 Z-Score 已收斂至平衡中樞 ({z_score:+.2f}σ)，"
                f"統計套利利差已完成回歸，建議全數平倉鎖定無風險利潤。"
            )
        # 常態震盪
        else:
            regime = self.REGIME_EQUILIBRIUM
            action = self.ACTION_HOLD
            rationale = (
                f"常態協整均衡體制：殘差 Z-Score ({z_score:+.2f}σ) 與半衰期 ({half_life:.1f} 天) 處於常態波動區間，"
                f"暫無統計套利進場優勢，維持長線均衡觀望。"
            )

        fallback_reason: Optional[str] = None
        if is_synthetic:
            # Synthetic series is not evidence of a structural break: never trip the breaker on it.
            # 合成序列不構成結構性破裂證據：不得據此熔斷。
            fallback_reason = self.FALLBACK_SYNTHETIC
            requires_circuit_breaker = False
            logger.warning(
                f"Kalman pairs {sy}/{sx}: no real price history, result marked {fallback_reason}"
            )

        metric = KalmanPairsMetric(
            ticker_y=sy,
            ticker_x=sx,
            price_y=py,
            price_x=px,
            dynamic_beta=dyn_beta,
            dynamic_alpha=dyn_alpha,
            residual_spread=residual_spread,
            spread_zscore=z_score,
            ou_half_life_days=half_life,
            regime=regime,
            arbitrage_action=action,
            target_hedge_ratio_x_per_y=target_hedge_ratio,
            requires_circuit_breaker=requires_circuit_breaker,
            rationale=rationale,
            fallback_reason=fallback_reason,
        )

        return metric

    # -------------------------------------------------------------
    # 雙渠道輸出格式化 (Telegram HTML + Email nl2br)
    # -------------------------------------------------------------
    def format_pairs_report(self, metric: KalmanPairsMetric) -> str:
        """
        格式化卡爾曼協整與統計套利戰報，恪守 Telegram HTML 與 Email nl2br 規範。
        """
        if metric.fallback_reason:
            return (
                f"<b>📈 卡爾曼配對協整</b>\n\n"
                f"🎯 <b>配對</b>：<code>{metric.ticker_y}/{metric.ticker_x}</code>\n"
                f"⚪ <b>不適用</b>：無真實歷史價格，序列為合成，未提供體制或信號 "
                f"(<code>{metric.fallback_reason}</code>)"
            )
        regime_badges = {
            self.REGIME_EQUILIBRIUM: "🟢 常態協整均衡 (Equilibrium Normal)",
            self.REGIME_DIVERGENCE: "🟠 價差發散套利機會 (Stat-Arb Opportunity)",
            self.REGIME_REVERSION: "🟣 均值回歸收斂平倉 (Reversion Exit)",
            self.REGIME_STRUCTURAL_BREAK: "🔴 結構破裂停損熔斷 (Structural Break)",
        }
        badge = regime_badges.get(metric.regime, metric.regime)

        action_labels = {
            self.ACTION_LONG_Y_SHORT_X: f"📈 做多 {metric.ticker_y} ＋ 📉 做空 {metric.ticker_x}",
            self.ACTION_SHORT_Y_LONG_X: f"📉 做空 {metric.ticker_y} ＋ 📈 做多 {metric.ticker_x}",
            self.ACTION_CLOSE: "🎯 獲利了結平倉 (Close Positions)",
            self.ACTION_HOLD: "⏸️ 觀望常態持倉 (Hold Equilibrium)",
            self.ACTION_STOP_LOSS: "🚨 結構破裂停損出場 (Emergency Stop-Loss)",
        }
        action_text = action_labels.get(metric.arbitrage_action, metric.arbitrage_action)

        report = (
            f"<b>📈 卡爾曼濾波動態協整與統計套利診斷戰報</b>\n\n"
            f"🎯 <b>配對標的</b>：<code>{metric.ticker_y}</code> (${metric.price_y:.2f}) vs <code>{metric.ticker_x}</code> (${metric.price_x:.2f})\n"
            f"⚡ <b>協整體制</b>：{badge}\n"
            f"🕒 <b>診斷時間</b>：{metric.evaluated_at[:19].replace('T', ' ')} UTC\n\n"
            f"<b>【動態狀態空間參數 (Kalman State-Space)】</b>\n"
            f"• <b>線上動態對沖比率 (β_t)</b>：<code>{metric.dynamic_beta:.4f}</code>\n"
            f"• <b>線上動態截距 (α_t)</b>：<code>${metric.dynamic_alpha:.4f}</code>\n"
            f"• <b>即時殘差價差 (e_t)</b>：<code>${metric.residual_spread:+.4f}</code>\n"
            f"• <b>標準化動態 Z-Score</b>：<code>{metric.spread_zscore:+.2f}σ</code>\n\n"
            f"<b>【均值回歸速度與對沖配置】</b>\n"
            f"• <b>Ornstein-Uhlenbeck 半衰期</b>：<code>{metric.ou_half_life_days:.1f} 天</code>\n"
            f"• <b>無 Beta 目標配比</b>：<code>1 股 {metric.ticker_y} : {metric.target_hedge_ratio_x_per_y:.2f} 股 {metric.ticker_x}</code>\n"
            f"• <b>推薦套利行動</b>：<b>{action_text}</b>\n\n"
            f"<b>💡 【量化策略處置指引】</b>\n"
            f"{metric.rationale}\n\n"
            f"🛡️ <b>單一真理閘門狀態</b>："
            f"{'🚨 觸發協整破裂熔斷，禁止逆勢加倉' if metric.requires_circuit_breaker else '✅ 無 Beta 市場中性風控通過'}"
        )
        return report
