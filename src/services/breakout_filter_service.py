"""
Volume-Price Spread & Breakout Confirmation Filter Service
===========================================================
盤中量價異動動態偵測與假突破過濾服務 (Volume-Price Spread & False Breakout Filter)。

設計原理：
1. **成交量放量倍數 (Volume Expansion Ratio)**：
   - 突破或順勢推進時，當前或即時成交量相對於 20 日日均量 (ADV20) 應具備充足放量比率 (預設 >= 1.2x ~ 1.5x)。
   - 若價格突破或大幅上漲，但成交量顯著萎縮 (< 0.7x ADV20)，判定為量價背離 (Volume-Price Divergence / Exhaustion Breakout)。
2. **VWAP 空間位階過濾 (VWAP Distance & Position)**：
   - 即時或當前價格必須站穩於 VWAP (或 Anchored VWAP) 之上。
   - 若現價大幅偏離 VWAP 過高 (例如偏離 > +5% ~ +8%)，判定為極度乖離與超買延伸 (Overextended / High Risk of Mean Reversion)，暫緩追高加碼。
3. **假突破與上影線抑制 (Upper Shadow / Pin Bar Rejection)**：
   - 當日或近期 K 線若上影線過長 (Upper Shadow Ratio > 0.40)，表示上方高檔解套或獲利拋壓沉重，判定為假突破 (False Breakout)。
4. **即時 WebSocket Tick 級別量價衝擊確認 (Real-time Tick Confirmation)**：
   - 在 Polygon WebSocket 接收到 Trade / Bar Aggregate 時，即時評估交易規模與 VWAP 偏離，提供 `evaluate_tick_anomaly`。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("BreakoutFilterService")


@dataclass
class BreakoutFilterResult:
    """量價突破過濾評估結果。"""
    is_valid_breakout: bool
    rejection_reason: Optional[str]
    volume_ratio: float
    vwap_distance_pct: float
    upper_shadow_ratio: float
    confidence_penalty: float
    metrics: Dict[str, Any]


class BreakoutFilterService:
    """
    盤中量價異動與假突破過濾器。
    """

    def __init__(
        self,
        market_data_service: Any = None,
        settings_service: Any = None,
        user_id: Optional[str] = None,
    ):
        self.market_data_service = market_data_service
        self.settings_service = settings_service
        self.user_id = user_id

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service and hasattr(self.settings_service, "get_setting"):
            try:
                val = self.settings_service.get_setting(key, default, self.user_id)
                return val if val is not None else default
            except Exception:
                return default
        return default

    def evaluate_breakout_quality(
        self,
        ticker: str,
        current_price: float,
        ohlcv_data: Optional[Dict[str, List[Any]]] = None,
        realtime_volume: Optional[float] = None,
        realtime_vwap: Optional[float] = None,
    ) -> BreakoutFilterResult:
        """
        評估特定標的在突破或推進當下的量價結構品質。
        若檢測為假突破、量價背離或過度乖離，返回 is_valid_breakout=False。
        """
        ticker = str(ticker).upper().strip()

        # 0. 功能開關
        enabled = self._get_setting("enable_breakout_volume_filter", True)
        if not str(enabled).lower() in ("true", "1"):
            return BreakoutFilterResult(
                is_valid_breakout=True,
                rejection_reason=None,
                volume_ratio=1.0,
                vwap_distance_pct=0.0,
                upper_shadow_ratio=0.0,
                confidence_penalty=0.0,
                metrics={"filter_disabled": True},
            )

        # 門檻參數
        min_vol_ratio = float(self._get_setting("breakout_min_volume_ratio", 1.2))
        max_vwap_dev_pct = float(self._get_setting("breakout_max_vwap_dev_pct", 6.0))
        max_shadow_ratio = float(self._get_setting("breakout_max_upper_shadow_ratio", 0.40))
        allow_fallback_pass = str(self._get_setting("breakout_filter_fail_open", True)).lower() in ("true", "1")

        # 1. 取得歷史數據
        ohlcv = ohlcv_data
        if not ohlcv and self.market_data_service:
            try:
                ohlcv = self.market_data_service.get_ohlcv(ticker, days=30)
            except Exception as e:
                logger.debug(f"[BreakoutFilter] Could not fetch OHLCV for {ticker}: {e}")

        if not ohlcv or not ohlcv.get("close") or len(ohlcv["close"]) < 5:
            # 數據不足時的安全處理
            return BreakoutFilterResult(
                is_valid_breakout=allow_fallback_pass,
                rejection_reason="Insufficient OHLCV data for breakout verification" if not allow_fallback_pass else None,
                volume_ratio=1.0,
                vwap_distance_pct=0.0,
                upper_shadow_ratio=0.0,
                confidence_penalty=0.0,
                metrics={"insufficient_data": True},
            )

        closes = [float(x) for x in ohlcv.get("close", [])]
        highs = [float(x) for x in ohlcv.get("high", [])]
        lows = [float(x) for x in ohlcv.get("low", [])]
        opens = [float(x) for x in ohlcv.get("open", [])]
        volumes = [float(x) for x in ohlcv.get("volume", [])]

        eff_price = current_price if current_price > 0 else closes[-1]

        # 2. 計算 20 日平均成交量 (ADV20) 與 成交量放量比率 (Volume Expansion Ratio)
        vol_lookback = volumes[-21:-1] if len(volumes) >= 21 else volumes[:-1]
        adv20 = sum(vol_lookback) / len(vol_lookback) if vol_lookback else 1.0
        adv20 = max(1.0, adv20)

        curr_vol = realtime_volume if (realtime_volume is not None and realtime_volume > 0) else volumes[-1]
        volume_ratio = round(curr_vol / adv20, 2)

        # 3. 計算 VWAP 與偏離度 (VWAP Distance %)
        vwap = realtime_vwap
        if vwap is None or vwap <= 0:
            # 由近 5 日 OHLCV 計算典型價格 VWAP 作為短線基準
            pv_sum = 0.0
            v_sum = 0.0
            slice_len = min(5, len(closes))
            for i in range(len(closes) - slice_len, len(closes)):
                typ_p = (highs[i] + lows[i] + closes[i]) / 3.0
                v = max(1.0, volumes[i])
                pv_sum += typ_p * v
                v_sum += v
            vwap = (pv_sum / v_sum) if v_sum > 0 else closes[-1]

        vwap_dist_pct = round(((eff_price - vwap) / vwap) * 100.0, 2) if vwap > 0 else 0.0

        # 4. 計算上影線比例 (Upper Shadow Ratio)
        # 上影線 = High - max(Open, Close)；實體與振幅 = High - Low
        latest_high = max(highs[-1], eff_price)
        latest_low = min(lows[-1], eff_price)
        latest_open = opens[-1] if opens else eff_price
        latest_close = eff_price

        candle_range = max(0.001, latest_high - latest_low)
        upper_shadow = max(0.0, latest_high - max(latest_open, latest_close))
        upper_shadow_ratio = round(upper_shadow / candle_range, 2)

        metrics = {
            "ticker": ticker,
            "current_price": eff_price,
            "vwap": round(vwap, 2),
            "vwap_distance_pct": vwap_dist_pct,
            "volume_ratio": volume_ratio,
            "adv20": round(adv20, 0),
            "current_volume": round(curr_vol, 0),
            "upper_shadow_ratio": upper_shadow_ratio,
        }

        # 5. 檢核過濾條件
        # 檢核 A: 價格跌破 VWAP 且未站穩 (低於 VWAP 1.5% 以上)
        if eff_price < (vwap * 0.985):
            return BreakoutFilterResult(
                is_valid_breakout=False,
                rejection_reason=f"價格 ${eff_price:.2f} 低於短線基準 VWAP ${vwap:.2f} ({vwap_dist_pct:.1f}%)，多頭動能不足",
                volume_ratio=volume_ratio,
                vwap_distance_pct=vwap_dist_pct,
                upper_shadow_ratio=upper_shadow_ratio,
                confidence_penalty=1.5,
                metrics=metrics,
            )

        # 檢核 B: 量價背離／極度縮量突破
        # 若為突破新高或加碼點，但成交量不足 20MA 日均量的 0.7 倍，判定為衰竭性誘多
        if volume_ratio < 0.70:
            return BreakoutFilterResult(
                is_valid_breakout=False,
                rejection_reason=f"成交量萎縮 (量比僅 {volume_ratio:.2f}x ADV20)，呈現量價背離與無量衝高，具誘多假突破風險",
                volume_ratio=volume_ratio,
                vwap_distance_pct=vwap_dist_pct,
                upper_shadow_ratio=upper_shadow_ratio,
                confidence_penalty=1.2,
                metrics=metrics,
            )

        # 檢核 C: 過度偏離 VWAP 超買延伸 (Overextension)
        if vwap_dist_pct > max_vwap_dev_pct:
            return BreakoutFilterResult(
                is_valid_breakout=False,
                rejection_reason=f"現價距 VWAP 正乖離率達 +{vwap_dist_pct:.1f}% (上限 +{max_vwap_dev_pct:.1f}%)，短線過度延伸超買，高檔回落風險高",
                volume_ratio=volume_ratio,
                vwap_distance_pct=vwap_dist_pct,
                upper_shadow_ratio=upper_shadow_ratio,
                confidence_penalty=1.0,
                metrics=metrics,
            )

        # 檢核 D: 上影線過長判定假突破 (Pin Bar Rejection)
        if upper_shadow_ratio > max_shadow_ratio:
            return BreakoutFilterResult(
                is_valid_breakout=False,
                rejection_reason=f"上方遭遇強烈拋壓，上影線佔比達 {upper_shadow_ratio * 100:.0f}% (上限 {max_shadow_ratio * 100:.0f}%)，判定假突破墓碑線",
                volume_ratio=volume_ratio,
                vwap_distance_pct=vwap_dist_pct,
                upper_shadow_ratio=upper_shadow_ratio,
                confidence_penalty=1.5,
                metrics=metrics,
            )

        # 全數通過：有效動能突破
        return BreakoutFilterResult(
            is_valid_breakout=True,
            rejection_reason=None,
            volume_ratio=volume_ratio,
            vwap_distance_pct=vwap_dist_pct,
            upper_shadow_ratio=upper_shadow_ratio,
            confidence_penalty=0.0,
            metrics=metrics,
        )

    def evaluate_tick_anomaly(
        self,
        ticker: str,
        price: float,
        size: Optional[float] = None,
        last_price: Optional[float] = None,
        adv20: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        針對 Polygon WebSocket 的即時 Tick 數據進行微結構異動檢測。
        """
        is_large_block = False
        if size and adv20 and adv20 > 0:
            # 單筆成交量大於日均量的 0.5% 即視為主力量化大單 (Block Trade)
            is_large_block = size >= (adv20 * 0.005)

        move_pct = 0.0
        if last_price and last_price > 0:
            move_pct = ((price - last_price) / last_price) * 100.0

        return {
            "ticker": ticker,
            "price": price,
            "size": size,
            "is_large_block": is_large_block,
            "move_pct": round(move_pct, 2),
            "anomaly_detected": is_large_block or abs(move_pct) >= 1.5,
        }
