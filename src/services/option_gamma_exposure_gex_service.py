"""
Option Gamma Exposure (GEX) & Volatility Pinning Forecasting Service (Phase 62A)
================================================================================
做市商淨伽馬暴露與波動率釘盤預測引擎

核心金融工程與量化數學：
1. 做市商 Delta-Hedging 動態與伽馬暴露 (Dollar GEX):
   - Black-Scholes-Merton 選擇權伽馬:
     d_1 = (ln(S/K) + (r + 0.5 * σ^2) * T) / (σ * sqrt(T))
     Γ = exp(-0.5 * d_1^2) / (S * σ * sqrt(2π * T))
   - Call GEX ($) = OI * 100 * S * Γ * S
   - Put GEX ($)  = -OI * 100 * S * Γ * S
   - Net GEX ($)  = Σ Call_GEX + Σ Put_GEX
2. 零伽馬翻轉點 (Zero-Gamma Flip Point, S*):
   - 做市商淨伽馬暴露由正轉負的臨界股價。
   - 股價高於 S*：做市商低買高賣抑制波動 (Sticky Mean-Reverting)。
   - 股價低於 S*：做市商追漲殺跌被動放大波動 (Volatility Accelerator)。
3. 期權到期日 (OpEx) 釘盤引力 (Pinning Gravity):
   - 尋找最大未平倉量合約 (Max OI Strike, K_pin)。
   - 當距到期日 <= 3 天且股價接近 K_pin 時，做市商避險平倉形成磁吸釘盤效應。
4. 4 級 GEX 波動率體制 (GEX Regimes):
   - POSITIVE_GAMMA_STICKY: Net GEX > 0 且 S > S*，做市商抑制波動，適合均值回歸與階梯吸籌。
   - NEGATIVE_GAMMA_VOLATILITY_ACCELERATOR: Net GEX < 0 且 S < S*，流動性外擴與波動放大，嚴格限制市價買單與槓桿。
   - ZERO_GAMMA_FLIP_WARNING: 股價位於 S* ±1.2% 區間，處於體制切換劇烈臨界點。
   - OPEX_PIN_CONVERGENCE: 到期日 <= 3 天且接近 K_pin，做市商釘盤引力主導。
5. 0-LLM 數理優先：內建 BSM 解析幾何與二分根搜尋，例行監控 0 Token 開銷。
6. 雙渠道輸出：Telegram HTML + Email nl2br 格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("OptionGammaExposureGEXService")


@dataclass
class GEXExposureMetric:
    """單一標的做市商淨伽馬暴露與波動率釘盤度量結果"""
    ticker: str
    spot_price: float
    net_gex: float                     # Dollar GEX (USD)
    call_gex: float                    # Total Call GEX (USD)
    put_gex: float                     # Total Put GEX (USD)
    zero_gamma_flip_point: float       # Flip Point S* (USD)
    distance_to_flip_pct: float        # (S - S*) / S
    max_oi_pin_strike: float           # OpEx Pin Strike (USD)
    pinning_gravity_score: float       # 0.0 ~ 1.0
    days_to_opex: int
    regime: str                        # POSITIVE_GAMMA_STICKY, NEGATIVE_GAMMA_VOLATILITY_ACCELERATOR, ZERO_GAMMA_FLIP_WARNING, OPEX_PIN_CONVERGENCE
    volatility_damping_multiplier: float # < 1.0: dampening, > 1.0: accelerating
    requires_protection: bool
    rationale: str
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Set when the metric is NOT a real measurement (e.g. no option chain provider).
    # Callers must treat a metric with a fallback_reason as "not applicable", never as a pass.
    # 非真實量測時必填（例如無選擇權鏈來源）；呼叫端須視為「不適用」，不得當作通過。
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "spot_price": round(self.spot_price, 2),
            "net_gex": round(self.net_gex, 2),
            "call_gex": round(self.call_gex, 2),
            "put_gex": round(self.put_gex, 2),
            "zero_gamma_flip_point": round(self.zero_gamma_flip_point, 2),
            "distance_to_flip_pct": round(self.distance_to_flip_pct, 4),
            "max_oi_pin_strike": round(self.max_oi_pin_strike, 2),
            "pinning_gravity_score": round(self.pinning_gravity_score, 4),
            "days_to_opex": self.days_to_opex,
            "regime": self.regime,
            "volatility_damping_multiplier": round(self.volatility_damping_multiplier, 4),
            "requires_protection": self.requires_protection,
            "rationale": self.rationale,
            "evaluated_at": self.evaluated_at,
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GEXExposureMetric:
        return cls(
            ticker=str(data.get("ticker", "")),
            spot_price=float(data.get("spot_price", 100.0) or 100.0),
            net_gex=float(data.get("net_gex", 0.0) or 0.0),
            call_gex=float(data.get("call_gex", 0.0) or 0.0),
            put_gex=float(data.get("put_gex", 0.0) or 0.0),
            zero_gamma_flip_point=float(data.get("zero_gamma_flip_point", 100.0) or 100.0),
            distance_to_flip_pct=float(data.get("distance_to_flip_pct", 0.0) or 0.0),
            max_oi_pin_strike=float(data.get("max_oi_pin_strike", 100.0) or 100.0),
            pinning_gravity_score=float(data.get("pinning_gravity_score", 0.0) or 0.0),
            days_to_opex=int(data.get("days_to_opex", 7) or 7),
            regime=str(data.get("regime", "POSITIVE_GAMMA_STICKY")),
            volatility_damping_multiplier=float(data.get("volatility_damping_multiplier", 1.0) or 1.0),
            requires_protection=bool(data.get("requires_protection", False)),
            rationale=str(data.get("rationale", "")),
            evaluated_at=data.get("evaluated_at") or datetime.now(timezone.utc).isoformat(),
            fallback_reason=data.get("fallback_reason"),
        )


class OptionGammaExposureGEXService:
    """做市商淨伽馬暴露與波動率釘盤預測服務"""

    REGIME_POSITIVE_GAMMA = "POSITIVE_GAMMA_STICKY"
    REGIME_NEGATIVE_GAMMA = "NEGATIVE_GAMMA_VOLATILITY_ACCELERATOR"
    REGIME_FLIP_WARNING = "ZERO_GAMMA_FLIP_WARNING"
    REGIME_OPEX_PIN = "OPEX_PIN_CONVERGENCE"
    REGIME_UNAVAILABLE = "UNAVAILABLE_NO_OPTIONS_CHAIN"
    FALLBACK_NO_CHAIN = "no_options_chain_provider"

    REDIS_CACHE_TTL_SECONDS = 300
    REDIS_KEY_PREFIX = "gex_service:metric"

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
        """檢查是否啟用做市商淨伽馬暴露與釘盤預測"""
        val = self._get_setting("enable_option_gamma_exposure_gex", False)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return False

    # -------------------------------------------------------------
    # 核心數學演算法：Black-Scholes-Merton 伽馬與 Dollar GEX 精算
    # -------------------------------------------------------------
    @staticmethod
    def calculate_bsm_gamma(
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        iv: float,
        risk_free_rate: float = 0.045,
    ) -> float:
        """
        計算 Black-Scholes-Merton 選擇權伽馬 (Γ):
        Γ = exp(-0.5 * d_1^2) / (S * σ * sqrt(2π * T))
        """
        if spot <= 0 or strike <= 0 or iv <= 0.001 or time_to_expiry_years <= 0.0001:
            return 0.0

        try:
            sqrt_t = math.sqrt(time_to_expiry_years)
            d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv * iv) * time_to_expiry_years) / (iv * sqrt_t)
            pdf_d1 = math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)
            gamma = pdf_d1 / (spot * iv * sqrt_t)
            return max(0.0, gamma)
        except Exception:
            return 0.0

    @classmethod
    def calculate_dollar_gex_for_contract(
        cls,
        option_type: str,
        spot: float,
        strike: float,
        open_interest: float,
        time_to_expiry_years: float,
        iv: float,
        risk_free_rate: float = 0.045,
    ) -> float:
        """
        計算單一選擇權合約對做市商產生的 Dollar GEX (USD):
        Call GEX = +OI * 100 * S * Γ * S
        Put GEX  = -OI * 100 * S * Γ * S
        """
        gamma = cls.calculate_bsm_gamma(spot, strike, time_to_expiry_years, iv, risk_free_rate)
        # Dollar Gamma per 1 share = S * Γ * S
        contract_dollar_gamma = open_interest * 100.0 * spot * gamma * spot
        opt = str(option_type).upper().strip()
        if opt in ("CALL", "C"):
            return contract_dollar_gamma
        elif opt in ("PUT", "P"):
            return -contract_dollar_gamma
        return 0.0

    @classmethod
    def compute_aggregate_gex_profile(
        cls,
        spot: float,
        options_chain: List[Dict[str, Any]],
        risk_free_rate: float = 0.045,
    ) -> Dict[str, Any]:
        """
        遍歷選擇權鏈，計算全盤 Call GEX, Put GEX, Net GEX 與 Max OI Pin Strike。
        """
        total_call_gex = 0.0
        total_put_gex = 0.0
        strike_oi_map: Dict[float, float] = {}
        min_days_to_expiry = 30

        for opt in options_chain:
            otype = str(opt.get("type") or opt.get("option_type") or "CALL").upper()
            strike = float(opt.get("strike", spot) or spot)
            oi = float(opt.get("open_interest", 0.0) or 0.0)
            iv = float(opt.get("implied_volatility", 0.25) or 0.25)
            dte = int(opt.get("days_to_expiry", 14) or 14)
            if dte < min_days_to_expiry:
                min_days_to_expiry = dte

            t_years = max(1.0 / 365.0, dte / 365.0)
            gex = cls.calculate_dollar_gex_for_contract(
                option_type=otype,
                spot=spot,
                strike=strike,
                open_interest=oi,
                time_to_expiry_years=t_years,
                iv=iv,
                risk_free_rate=risk_free_rate,
            )

            if gex >= 0:
                total_call_gex += gex
            else:
                total_put_gex += gex

            strike_oi_map[strike] = strike_oi_map.get(strike, 0.0) + oi

        net_gex = total_call_gex + total_put_gex

        # Find Max OI Strike (Pinning Candidate)
        max_oi_strike = spot
        max_oi = 0.0
        total_chain_oi = sum(strike_oi_map.values())
        for stk, val in strike_oi_map.items():
            if val > max_oi:
                max_oi = val
                max_oi_strike = stk

        # OpEx Pinning Gravity Score
        pinning_gravity = 0.0
        if total_chain_oi > 0:
            dist_ratio = abs(spot - max_oi_strike) / max_oi_strike if max_oi_strike > 0 else 0.0
            oi_weight = max_oi / total_chain_oi
            pinning_gravity = max(0.0, 1.0 - min(1.0, dist_ratio * 15.0)) * min(1.0, oi_weight * 3.0)

        return {
            "net_gex": net_gex,
            "call_gex": total_call_gex,
            "put_gex": total_put_gex,
            "max_oi_pin_strike": max_oi_strike,
            "pinning_gravity_score": pinning_gravity,
            "days_to_opex": min_days_to_expiry,
        }

    @classmethod
    def estimate_zero_gamma_flip_point(
        cls,
        spot: float,
        options_chain: List[Dict[str, Any]],
        risk_free_rate: float = 0.045,
    ) -> float:
        """
        數理二分/網格搜尋估計零伽馬翻轉點 (Zero-Gamma Flip Point, S*):
        評估股價在 [0.75 * S, 1.25 * S] 區間內的淨伽馬零交點。
        """
        if not options_chain or spot <= 0:
            return spot

        grid_points = 51
        low_p = spot * 0.75
        high_p = spot * 1.25
        step = (high_p - low_p) / (grid_points - 1)

        prev_p = low_p
        prev_gex: Optional[float] = None

        for i in range(grid_points):
            test_p = low_p + i * step
            # Calculate net GEX at test_p
            curr_gex = 0.0
            for opt in options_chain:
                otype = str(opt.get("type") or opt.get("option_type") or "CALL").upper()
                strike = float(opt.get("strike", spot) or spot)
                oi = float(opt.get("open_interest", 0.0) or 0.0)
                iv = float(opt.get("implied_volatility", 0.25) or 0.25)
                dte = int(opt.get("days_to_expiry", 14) or 14)
                t_years = max(1.0 / 365.0, dte / 365.0)

                g = cls.calculate_dollar_gex_for_contract(
                    option_type=otype,
                    spot=test_p,
                    strike=strike,
                    open_interest=oi,
                    time_to_expiry_years=t_years,
                    iv=iv,
                    risk_free_rate=risk_free_rate,
                )
                curr_gex += g

            if prev_gex is not None:
                # Zero crossing detected
                if (prev_gex <= 0 and curr_gex >= 0) or (prev_gex >= 0 and curr_gex <= 0):
                    # Linear interpolation for zero crossing
                    denom = (curr_gex - prev_gex)
                    if abs(denom) > 1e-9:
                        zero_cross = prev_p + (0.0 - prev_gex) * (test_p - prev_p) / denom
                        return round(zero_cross, 2)
                    return round((prev_p + test_p) / 2.0, 2)

            prev_p = test_p
            prev_gex = curr_gex

        # If monotonic across range, return boundary or default to spot
        if prev_gex is not None and prev_gex > 0:
            return round(spot * 0.85, 2)
        return round(spot * 1.15, 2)

    # -------------------------------------------------------------
    # 選擇權鏈獲取（僅真實來源；無來源回 None，絕不合成）
    # -------------------------------------------------------------
    async def get_options_chain(
        self,
        ticker: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Return a real option chain from the market-data provider, or None when no provider
        can supply one. Never fabricates a chain.
        回傳真實選擇權鏈；無來源時回 None，絕不合成。
        """
        provider = self.market_data_service
        if provider is None or not hasattr(provider, "get_options_chain"):
            return None
        try:
            raw_chain = await provider.get_options_chain(ticker)
        except Exception as e:
            logger.warning(f"Options chain fetch failed for {ticker}: {e}")
            return None
        if raw_chain and isinstance(raw_chain, list) and len(raw_chain) >= 4:
            return raw_chain
        return None

    # -------------------------------------------------------------
    # 診斷與體制判定 (Regime Evaluation)
    # -------------------------------------------------------------
    async def evaluate_ticker_gex(
        self,
        ticker: str,
        spot_price: Optional[float] = None,
    ) -> GEXExposureMetric:
        """
        評估標的做市商淨伽馬暴露、零伽馬翻轉點與釘盤引力。
        """
        sym = ticker.upper().strip()

        # 1. 取得真實選擇權鏈；無來源 → 標記不適用，不產生體制與數字
        chain = await self.get_options_chain(sym)
        if chain is None:
            logger.warning(
                f"GEX for {sym}: no options chain provider, result marked "
                f"{self.FALLBACK_NO_CHAIN} (guard not applicable)"
            )
            return GEXExposureMetric(
                ticker=sym,
                spot_price=float(spot_price or 0.0),
                net_gex=0.0,
                call_gex=0.0,
                put_gex=0.0,
                zero_gamma_flip_point=0.0,
                distance_to_flip_pct=0.0,
                max_oi_pin_strike=0.0,
                pinning_gravity_score=0.0,
                days_to_opex=0,
                regime=self.REGIME_UNAVAILABLE,
                volatility_damping_multiplier=1.0,
                requires_protection=False,
                rationale="No real option chain available; GEX not measured.",
                fallback_reason=self.FALLBACK_NO_CHAIN,
            )

        # 2. 取得現貨市價（鏈為真實時才需要）
        spot = spot_price or 0.0
        if spot <= 0:
            try:
                r = await self._get_redis()
                if r:
                    cached_p = await r.get(f"market:price:{sym}")
                    if cached_p:
                        spot = float(cached_p)
            except Exception as e:
                logger.warning(f"GEX spot price cache read failed for {sym}: {e}")
        if spot <= 0:
            logger.warning(f"GEX for {sym}: no spot price, result marked no_spot_price")
            return GEXExposureMetric(
                ticker=sym, spot_price=0.0, net_gex=0.0, call_gex=0.0, put_gex=0.0,
                zero_gamma_flip_point=0.0, distance_to_flip_pct=0.0, max_oi_pin_strike=0.0,
                pinning_gravity_score=0.0, days_to_opex=0,
                regime=self.REGIME_UNAVAILABLE, volatility_damping_multiplier=1.0,
                requires_protection=False,
                rationale="No spot price available; GEX not measured.",
                fallback_reason="no_spot_price",
            )

        # 3. 精算 GEX Profile
        profile = self.compute_aggregate_gex_profile(spot, chain)
        net_gex = profile["net_gex"]
        call_gex = profile["call_gex"]
        put_gex = profile["put_gex"]
        max_oi_strike = profile["max_oi_pin_strike"]
        pin_gravity = profile["pinning_gravity_score"]
        days_to_opex = profile["days_to_opex"]

        # 4. 精算翻轉點 S*
        flip_point = self.estimate_zero_gamma_flip_point(spot, chain)
        dist_to_flip = (spot - flip_point) / spot if spot > 0 else 0.0

        # 5. 判定 4 級體制
        regime = self.REGIME_POSITIVE_GAMMA
        damping_mult = 0.85
        requires_protection = False
        rationale = ""

        # OpEx Pinning check: D <= 3 days, distance <= 2%
        is_opex_window = days_to_opex <= 3
        dist_to_pin_pct = abs(spot - max_oi_strike) / max_oi_strike if max_oi_strike > 0 else 1.0

        if is_opex_window and dist_to_pin_pct <= 0.02 and pin_gravity >= 0.35:
            regime = self.REGIME_OPEX_PIN
            damping_mult = 0.70
            requires_protection = False
            rationale = (
                f"OpEx 到期日釘盤體制：距離結算剩餘 {days_to_opex} 天，"
                f"市價 (${spot:.2f}) 逼近最大未平倉量履約價 (${max_oi_strike:.2f})，"
                f"做市商 Delta 避險平倉引力評分 {pin_gravity:.2f}，價格將高度錨定於履約價附近收斂。"
            )
        elif abs(dist_to_flip) <= 0.012:
            regime = self.REGIME_FLIP_WARNING
            damping_mult = 1.15
            requires_protection = False
            rationale = (
                f"零伽馬翻轉警戒體制：市價 (${spot:.2f}) 緊貼零伽馬邊界 S* (${flip_point:.2f}) "
                f"(差距 {dist_to_flip:+.2%})，體制處於正負 Gamma 切換之極度脆弱邊緣，"
                f"一旦向下跌破將激發做市商被動拋售，波動率將迅速放大。"
            )
        elif net_gex < 0 or spot < flip_point:
            regime = self.REGIME_NEGATIVE_GAMMA
            damping_mult = 1.45
            requires_protection = True
            rationale = (
                f"負伽馬波動率加速體制：Net GEX 處於負值 (${net_gex/1e6:.2f}M) 且跌破翻轉點 S* (${flip_point:.2f})，"
                f"做市商被迫追漲殺跌（低賣高買避險），市場波動度被動擴張，"
                f"嚴禁市價追單，限價買單向下平移以防範滑點踩踏。"
            )
        else:
            regime = self.REGIME_POSITIVE_GAMMA
            damping_mult = 0.85
            requires_protection = False
            rationale = (
                f"正伽馬黏性穩定體制：Net GEX 為正 (${net_gex/1e6:.2f}M) 且高於翻轉點 S* (${flip_point:.2f})，"
                f"做市商低買高賣抑制市場波動，具備均值回歸黏性，"
                f"適合階梯分批吸籌 (Staggered Dip Buying) 與網格佈局。"
            )

        metric = GEXExposureMetric(
            ticker=sym,
            spot_price=spot,
            net_gex=net_gex,
            call_gex=call_gex,
            put_gex=put_gex,
            zero_gamma_flip_point=flip_point,
            distance_to_flip_pct=dist_to_flip,
            max_oi_pin_strike=max_oi_strike,
            pinning_gravity_score=pin_gravity,
            days_to_opex=days_to_opex,
            regime=regime,
            volatility_damping_multiplier=damping_mult,
            requires_protection=requires_protection,
            rationale=rationale,
        )

        return metric

    # -------------------------------------------------------------
    # 雙渠道輸出格式化 (Telegram HTML + Email nl2br)
    # -------------------------------------------------------------
    def format_gex_report(self, metric: GEXExposureMetric) -> str:
        """
        格式化做市商淨伽馬暴露戰報，恪守 Telegram HTML 與 Email nl2br 規範。
        """
        if metric.fallback_reason:
            return (
                f"<b>📊 做市商淨伽馬暴露 (GEX)</b>\n\n"
                f"🎯 <b>標的代號</b>：<code>{metric.ticker}</code>\n"
                f"⚪ <b>不適用</b>：無真實選擇權鏈來源，未產生體制或數值 "
                f"(<code>{metric.fallback_reason}</code>)"
            )
        regime_badges = {
            self.REGIME_POSITIVE_GAMMA: "🟢 正伽馬黏性穩定 (Sticky Damping)",
            self.REGIME_NEGATIVE_GAMMA: "🔴 負伽馬波動加速 (Volatility Accelerator)",
            self.REGIME_FLIP_WARNING: "🟠 零伽馬翻轉警戒 (Flip Point Warning)",
            self.REGIME_OPEX_PIN: "🟣 到期日釘盤收斂 (OpEx Pinning Gravity)",
        }
        badge = regime_badges.get(metric.regime, metric.regime)
        net_m = metric.net_gex / 1e6
        call_m = metric.call_gex / 1e6
        put_m = metric.put_gex / 1e6

        report = (
            f"<b>📊 做市商淨伽馬暴露 (GEX) 診斷戰報</b>\n\n"
            f"🎯 <b>標的代號</b>：<code>{metric.ticker}</code> | <b>現價</b>：${metric.spot_price:.2f}\n"
            f"⚡ <b>市場體制</b>：{badge}\n"
            f"🕒 <b>診斷時間</b>：{metric.evaluated_at[:19].replace('T', ' ')} UTC\n\n"
            f"<b>【做市商伽馬暴露剖面 (GEX Profile)】</b>\n"
            f"• <b>Net GEX 淨曝險</b>：<code>${net_m:+.2f}M</code> (做市商{'抑制' if net_m >= 0 else '放大'}波動)\n"
            f"• <b>Call GEX</b>：<code>${call_m:+.2f}M</code> | <b>Put GEX</b>：<code>${put_m:+.2f}M</code>\n"
            f"• <b>零伽馬翻轉點 (S*)</b>：<code>${metric.zero_gamma_flip_point:.2f}</code> (距現價 {metric.distance_to_flip_pct:+.2%})\n\n"
            f"<b>【期權結算與釘盤引力 (Pinning)】</b>\n"
            f"• <b>最大未平倉釘盤價 (Pin Strike)</b>：<code>${metric.max_oi_pin_strike:.2f}</code>\n"
            f"• <b>距離到期日 (OpEx)</b>：<code>{metric.days_to_opex} 天</code>\n"
            f"• <b>結算釘盤引力指數</b>：<code>{metric.pinning_gravity_score:.2f} / 1.00</code>\n"
            f"• <b>波動率乘數因子</b>：<code>{metric.volatility_damping_multiplier:.2f}x</code>\n\n"
            f"<b>💡 【量化風控與交易處置方針】</b>\n"
            f"{metric.rationale}\n\n"
            f"🛡️ <b>單一真理閘門處置</b>："
            f"{'⚠️ 已啟動負伽馬防禦，限制市價追單' if metric.requires_protection else '✅ 體制安全，常態限價吸籌放行'}"
        )
        return report
