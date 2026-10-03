"""
Smart Money Institutional Cost & Support Service
================================================
計算主力機構建倉平均成本（Smart Money Institutional Cost Basis）、成交量分佈控制點 (POC)、
錨定成交量加權平均價 (Anchored VWAP) 及關鍵支撐價格（Key Support Price）。

核心設計原理：
1. Anchored VWAP (AVWAP): 從波段結構起漲點（例如 60~90 日最低點）錨定，精確計算累積成交量加權平均價。
2. Volume Profile & POC: 統計歷史成交量在各價格區間的分佈，找出籌碼最密集之控制點 (POC) 與次級高量節點 (HVN)。
3. Composite Key Support:
   - 當現價高於 POC 與 AVWAP 時，關鍵支撐取 max(POC, AVWAP)。
   - 停損點設於支撐價下方緩衝區 (預設 0.8%~1.2%)，防範洗盤與破底翻。
   - 確保滿足 eToro min-pip 撮合門檻與最大風控幅度。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("SmartMoneySupportService")


@dataclass
class SmartMoneySupportResult:
    """主力籌碼成本與關鍵支撐計算結果。"""
    ticker: str
    current_price: float
    anchored_vwap: float
    point_of_control: float
    value_area_high: float
    value_area_low: float
    high_volume_nodes: List[float]
    key_support_price: float
    recommended_stop_loss: float
    stop_loss_distance_pct: float
    support_type: str                   # "POC_SUPPORT" | "AVWAP_SUPPORT" | "HVN_SUPPORT" | "SWING_LOW_FALLBACK" | "FALLBACK_PERCENTAGE"
    anchor_date: Optional[str]
    rationale: str


class SmartMoneySupportService:
    """
    Service for calculating institutional cost basis and structural support levels.
    主力籌碼成本與結構支撐計算服務。
    """

    DEFAULT_LOOKBACK_DAYS = 90
    DEFAULT_BUFFER_PCT = 0.008          # 0.8% 緩衝，防範主力洗盤與假跌破
    MIN_DISTANCE_PCT = 0.015            # 距現價至少 1.5%，滿足 eToro min-pip 撮合檢核
    MAX_DISTANCE_PCT = 0.10             # 最大停損距離 10%，防範極端過度承擔風險

    def __init__(self, market_data_service: Any = None):
        self._market_data_service = market_data_service

    def _get_market_data_service(self):
        if self._market_data_service is None:
            try:
                from src.services.market_data_service import MarketDataService
                self._market_data_service = MarketDataService()
            except Exception as e:
                logger.warning(f"Could not initialize MarketDataService: {e}")
        return self._market_data_service

    def calculate_anchored_vwap(
        self,
        dates: List[str],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        volumes: List[float],
        anchor_idx: Optional[int] = None,
    ) -> Tuple[float, int, str]:
        """
        計算自錨點開始的 Anchored VWAP。
        若未指定 anchor_idx，預設以觀察區間內的波段最低點 (Swing Low) 作為吸籌起點。
        """
        n = len(closes)
        if n == 0:
            return 0.0, 0, ""

        if anchor_idx is None or anchor_idx < 0 or anchor_idx >= n:
            # 尋找波段最低價對應的索引
            min_low = float("inf")
            best_idx = 0
            for i in range(n):
                if lows[i] < min_low:
                    min_low = lows[i]
                    best_idx = i
            anchor_idx = best_idx

        anchor_date = dates[anchor_idx] if anchor_idx < len(dates) else ""
        cum_volume = 0.0
        cum_pv = 0.0

        for i in range(anchor_idx, n):
            # Typical Price = (High + Low + Close) / 3
            typical_price = (highs[i] + lows[i] + closes[i]) / 3.0
            vol = max(0.0, float(volumes[i]))
            cum_pv += typical_price * vol
            cum_volume += vol

        if cum_volume > 0:
            avwap = cum_pv / cum_volume
        else:
            # 無成交量數據時回退為收盤價平均
            sub_closes = closes[anchor_idx:]
            avwap = sum(sub_closes) / len(sub_closes) if sub_closes else closes[-1]

        return round(avwap, 4), anchor_idx, anchor_date

    def calculate_volume_profile(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        volumes: List[float],
        bins: int = 50,
    ) -> Dict[str, Any]:
        """
        計算成交量分佈 (Volume Profile) 與控制點 (POC, Point of Control)。
        """
        n = len(closes)
        if n == 0:
            return {
                "poc": 0.0,
                "val": 0.0,
                "vah": 0.0,
                "hvns": [],
                "bins": [],
            }

        min_p = min(lows)
        max_p = max(highs)

        if max_p <= min_p:
            return {
                "poc": round(closes[-1], 4),
                "val": round(closes[-1], 4),
                "vah": round(closes[-1], 4),
                "hvns": [round(closes[-1], 4)],
                "bins": [],
            }

        bin_width = (max_p - min_p) / bins
        bin_volumes = [0.0] * bins
        bin_prices = [min_p + (i + 0.5) * bin_width for i in range(bins)]

        for i in range(n):
            h = highs[i]
            l = lows[i]
            v = max(0.0, float(volumes[i]))
            if v <= 0:
                continue

            # 計算此 K 線覆蓋的 bin 範圍，依覆蓋比例分配成交量
            start_bin = int(max(0, min(bins - 1, (l - min_p) // bin_width)))
            end_bin = int(max(0, min(bins - 1, (h - min_p) // bin_width)))

            span = end_bin - start_bin + 1
            allocated_vol = v / span
            for b in range(start_bin, end_bin + 1):
                bin_volumes[b] += allocated_vol

        # 找出成交量最高之 bin 作為 POC (Point of Control)
        max_vol = -1.0
        poc_idx = 0
        for b in range(bins):
            if bin_volumes[b] > max_vol:
                max_vol = bin_volumes[b]
                poc_idx = b

        poc_price = bin_prices[poc_idx]

        # 計算 Value Area (包含 70% 成交量的價格區間: VAH, VAL)
        total_vol = sum(bin_volumes)
        target_vol = total_vol * 0.70
        accum_vol = bin_volumes[poc_idx]
        val_idx = poc_idx
        vah_idx = poc_idx

        while accum_vol < target_vol and (val_idx > 0 or vah_idx < bins - 1):
            next_down_vol = bin_volumes[val_idx - 1] if val_idx > 0 else -1.0
            next_up_vol = bin_volumes[vah_idx + 1] if vah_idx < bins - 1 else -1.0

            if next_down_vol >= next_up_vol and next_down_vol >= 0:
                val_idx -= 1
                accum_vol += next_down_vol
            elif next_up_vol >= 0:
                vah_idx += 1
                accum_vol += next_up_vol
            else:
                break

        val = bin_prices[val_idx]
        vah = bin_prices[vah_idx]

        # 識別局部次級高量節點 (HVN - High Volume Nodes)
        hvns: List[float] = []
        for b in range(1, bins - 1):
            if bin_volumes[b] > bin_volumes[b - 1] and bin_volumes[b] > bin_volumes[b + 1]:
                # 成交量顯著大於平均水平
                if bin_volumes[b] >= (total_vol / bins) * 1.2:
                    hvns.append(round(bin_prices[b], 4))

        if not hvns:
            hvns.append(round(poc_price, 4))

        return {
            "poc": round(poc_price, 4),
            "val": round(val, 4),
            "vah": round(vah, 4),
            "hvns": sorted(hvns),
        }

    def calculate_institutional_support(
        self,
        ticker: str,
        current_price: Optional[float] = None,
        days: int = DEFAULT_LOOKBACK_DAYS,
        ohlcv_data: Optional[Dict[str, List[Any]]] = None,
    ) -> SmartMoneySupportResult:
        """
        計算標的之主力平均成本、結構支撐位及建議移動停損點。
        """
        # 1. 取得歷史數據
        ohlcv = ohlcv_data
        if not ohlcv:
            mds = self._get_market_data_service()
            if mds:
                try:
                    ohlcv = mds.get_ohlcv(ticker, days=days)
                except Exception as e:
                    logger.warning(f"Failed to fetch OHLCV for {ticker}: {e}")

        # 數據不足時的安全回退處理
        dates = ohlcv.get("date", []) if ohlcv else []
        closes = [float(x) for x in ohlcv.get("close", [])] if ohlcv else []
        highs = [float(x) for x in ohlcv.get("high", [])] if ohlcv else []
        lows = [float(x) for x in ohlcv.get("low", [])] if ohlcv else []
        volumes = [float(x) for x in ohlcv.get("volume", [])] if ohlcv else []

        # 解析有效現價
        eff_price = current_price if (current_price and current_price > 0) else (closes[-1] if closes else 100.0)

        if len(closes) < 5:
            # 歷史數據過短，使用安全百分比作為停損點
            fallback_stop = round(eff_price * (1.0 - 0.06), 4)
            return SmartMoneySupportResult(
                ticker=ticker,
                current_price=eff_price,
                anchored_vwap=eff_price,
                point_of_control=eff_price,
                value_area_high=eff_price,
                value_area_low=eff_price,
                high_volume_nodes=[eff_price],
                key_support_price=eff_price,
                recommended_stop_loss=fallback_stop,
                stop_loss_distance_pct=6.0,
                support_type="FALLBACK_PERCENTAGE",
                anchor_date=None,
                rationale="OHLCV 數據不足，採用預設 6.0% 停損防護線。",
            )

        # 2. 計算 Anchored VWAP (以波段最低點為錨)
        avwap, anchor_idx, anchor_date = self.calculate_anchored_vwap(
            dates=dates, highs=highs, lows=lows, closes=closes, volumes=volumes
        )

        # 3. 計算 Volume Profile 與 POC
        vp = self.calculate_volume_profile(
            highs=highs, lows=lows, closes=closes, volumes=volumes
        )
        poc = vp["poc"]
        val = vp["val"]
        vah = vp["vah"]
        hvns = vp["hvns"]

        # 4. 判定關鍵主力支撐價位 (Key Support)
        # 情況 A：現價高於 POC 與 AVWAP（主力籌碼全面處於獲利中，最理想的結構支撐）
        if eff_price >= poc and eff_price >= avwap:
            key_support = max(poc, avwap)
            support_type = "POC_SUPPORT" if poc >= avwap else "AVWAP_SUPPORT"
        # 情況 B：現價介於兩者之間
        elif eff_price >= min(poc, avwap):
            key_support = min(poc, avwap)
            support_type = "AVWAP_SUPPORT" if key_support == avwap else "POC_SUPPORT"
        # 情況 C：現價低於 POC 與 AVWAP（短線回檔或空頭走勢，尋找下方次級籌碼峰 HVN）
        else:
            lower_hvns = [h for h in hvns if h < eff_price]
            if lower_hvns:
                key_support = max(lower_hvns)
                support_type = "HVN_SUPPORT"
            else:
                key_support = min(lows)
                support_type = "SWING_LOW_FALLBACK"

        # 5. 計算建議移動停損點（保留安全緩衝區，並施加邊界保護）
        raw_stop = key_support * (1.0 - self.DEFAULT_BUFFER_PCT)

        # 門檻保護 1：停損價必須低於現價至少 1.5%，滿足 eToro min-pip 撮合規則
        max_allowed_stop = eff_price * (1.0 - self.MIN_DISTANCE_PCT)
        if raw_stop > max_allowed_stop:
            raw_stop = max_allowed_stop

        # 門檻保護 2：停損幅度至多 10.0%，避免過度承擔下檔風險
        min_allowed_stop = eff_price * (1.0 - self.MAX_DISTANCE_PCT)
        if raw_stop < min_allowed_stop:
            raw_stop = min_allowed_stop

        recommended_stop = round(raw_stop, 4)
        dist_pct = round(((eff_price - recommended_stop) / eff_price) * 100.0, 2)

        rationale = (
            f"主力建倉密集區 POC=${poc:.2f}, 波段錨定均價 AVWAP=${avwap:.2f} (自 {anchor_date} 起算)。"
            f"關鍵支撐 ${key_support:.2f} ({support_type})，在支撐下方設置緩衝移動停損價 ${recommended_stop:.2f} "
            f"(距現價 -{dist_pct:.2f}%)，結合 eToro TSL 功能鎖定獲利。"
        )

        return SmartMoneySupportResult(
            ticker=ticker,
            current_price=eff_price,
            anchored_vwap=avwap,
            point_of_control=poc,
            value_area_high=vah,
            value_area_low=val,
            high_volume_nodes=hvns,
            key_support_price=key_support,
            recommended_stop_loss=recommended_stop,
            stop_loss_distance_pct=dist_pct,
            support_type=support_type,
            anchor_date=anchor_date,
            rationale=rationale,
        )
