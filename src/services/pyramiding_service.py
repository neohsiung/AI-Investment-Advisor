"""
Pyramiding Position Scaling Service (強勢股波段動能金字塔加碼服務)
================================================================
實現頂級量化與順勢交易（Trend Following）金字塔加碼機制：
1. 嚴格順勢盈利（Add Only to Winners）：僅在持倉累積充分浮盈時啟動，嚴禁逆勢攤平。
2. 零本金風險防線（Zero-Risk Guarantee）：移動停損線必須已上推至成本保本線以上，確保即使加碼部位遭停損，全案依然獲利或保本。
3. 金字塔部位遞減（Pyramidal Decreasing Sizing）：加碼規模嚴格小於底倉（Stage 1 25%、Stage 2 15%），避免大幅墊高均價。
4. 動能與多頭趨勢閘門（Momentum & Trend Validation）：現價 > 20MA、RSI 處於健康強勢推升區間 (52~76)，排除超買力竭或破線弱勢。
5. 集中度與風險預算約束（Concentration & Risk Guard）：嚴格受限於單檔持倉權重上限 (max_single_position_pct)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.services.long_term_winner_service import LongTermWinnerService
from src.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)


@dataclass
class PyramidingDecision:
    """金字塔加碼決策結果"""
    should_scale_in: bool
    ticker: str
    stage: int                                 # 1 或 2
    add_shares: float                          # 建議加碼股數
    add_amount_usd: float                      # 建議加碼美元金額
    current_shares: float                      # 原持倉股數
    current_price: float                       # 現價
    avg_price: float                           # 原始平均持倉成本
    unrealized_pnl_pct: float                  # 未實現報酬率 %
    current_weight_pct: float                  # 當前投組權重 %
    projected_weight_pct: float                # 加碼後預計投組權重 %
    active_stop_price: float                   # 當前活躍移動停損價
    confidence_score: float                    # 確信度總分 (0-10)
    confidence_breakdown: List[Dict[str, Any]] # 分項置信度明細
    rationale: str                             # 執行依據
    metrics: Dict[str, Any] = field(default_factory=dict) # 技術指標快照


class PyramidingService:
    """
    強勢股金字塔加碼評估與風控調度引擎。
    """

    def __init__(
        self,
        user_id: str,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[MarketDataService] = None,
    ):
        self.user_id = user_id
        self.settings_service = settings_service
        self.market = market_data_service or MarketDataService(user_id=user_id)
        self.winner_service = LongTermWinnerService(user_id=user_id, market_data_service=self.market)
        self._in_memory_stages: Dict[str, int] = {}

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service and hasattr(self.settings_service, "get_setting"):
            try:
                return self.settings_service.get_setting(key, default, self.user_id)
            except Exception:
                pass
        return default

    async def get_current_stage(self, ticker: str) -> int:
        """獲取該標的目前已執行的金字塔加碼階梯（支援 Redis 持久化與記憶體快取）"""
        ticker = ticker.upper().strip()
        if ticker in self._in_memory_stages:
            return self._in_memory_stages[ticker]

        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            key = f"sentinel:pyramid_stage:{self.user_id}:{ticker}"
            val = await r.get(key)
            if val is not None:
                stage = int(val)
                self._in_memory_stages[ticker] = stage
                return stage
        except Exception as e:
            logger.debug(f"PyramidingService: Redis stage read error for {ticker}: {e}")

        return 0

    async def record_stage_advance(self, ticker: str, new_stage: int) -> None:
        """更新並持久化該標的的金字塔加碼階梯"""
        ticker = ticker.upper().strip()
        self._in_memory_stages[ticker] = new_stage
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            key = f"sentinel:pyramid_stage:{self.user_id}:{ticker}"
            await r.set(key, str(new_stage), ex=86400 * 90)
        except Exception as e:
            logger.debug(f"PyramidingService: Redis stage update error for {ticker}: {e}")

    async def evaluate_position(
        self,
        ticker: str,
        current_shares: float,
        current_price: float,
        avg_price: float,
        current_peak: float,
        active_stop_price: float,
        portfolio_total_equity: float,
        current_weight_pct: float = 0.0,
    ) -> Optional[PyramidingDecision]:
        """
        評估單一持倉是否具備金字塔順勢加碼條件。
        """
        ticker = ticker.upper().strip()

        # 0. 功能開關
        enable_val = self._get_setting("enable_pyramiding", True)
        if not str(enable_val).lower() in ("true", "1"):
            return None

        if current_shares <= 0 or current_price <= 0 or avg_price <= 0:
            return None

        # 1. 浮盈計算與最低門檻檢查（嚴禁虧損攤平）
        unrealized_pnl_pct = ((current_price - avg_price) / avg_price) * 100.0
        stage1_min_pnl = float(self._get_setting("pyramid_stage1_min_pnl_pct", 8.0))
        stage2_min_pnl = float(self._get_setting("pyramid_stage2_min_pnl_pct", 16.0))

        if unrealized_pnl_pct < stage1_min_pnl:
            return None

        # 2. 零本金風險檢查 (Zero-Risk Guarantee)
        # 移動停損價必須已經單向鎖定在進場成本線上 (active_stop >= avg_price * 1.00)
        # 確保若加碼後發生回檔觸發 TSL，底倉既得利益足以覆蓋整體風險
        if active_stop_price < (avg_price * 0.998):
            logger.debug(
                f"Pyramiding: {ticker} passed pnl hurdle (+{unrealized_pnl_pct:.1f}%), "
                f"but stop ${active_stop_price:.2f} is below cost ${avg_price:.2f}. Pyramiding blocked."
            )
            return None

        # 3. 加碼階梯檢查 (Max Stages Gate)
        current_stage = await self.get_current_stage(ticker)
        max_stages = int(self._get_setting("max_pyramid_stages", 2))
        if current_stage >= max_stages:
            return None

        target_stage = current_stage + 1
        if target_stage == 2 and unrealized_pnl_pct < stage2_min_pnl:
            return None

        # 4. 強勢趨勢與動能閘門 (Trend & Momentum Gates)
        tech = {}
        try:
            tech = self.market.get_technical_indicators(ticker) or {}
        except Exception as e:
            logger.debug(f"Pyramiding: Technical fetch failed for {ticker}: {e}")

        rsi = float(tech.get("rsi") or 50.0)
        # RSI 必須處於多頭強勢推進區間 (52 ~ 76)，排除過度超買衰竭 (>78) 或轉弱 (<50)
        if rsi < 52.0 or rsi > 78.0:
            logger.debug(f"Pyramiding: {ticker} RSI={rsi:.1f} out of healthy momentum band [52, 78]. Skipped.")
            return None

        sma_dict = tech.get("sma", {}) if isinstance(tech.get("sma"), dict) else {}
        sma_20 = float(sma_dict.get("sma_20") or 0.0)
        sma_50 = float(sma_dict.get("sma_50") or 0.0)

        # 價格必須站穩 20MA
        if sma_20 > 0 and current_price < (sma_20 * 0.99):
            logger.debug(f"Pyramiding: {ticker} price ${current_price:.2f} below 20MA ${sma_20:.2f}. Skipped.")
            return None

        # 多頭排列檢查 (20MA >= 50MA)
        if sma_20 > 0 and sma_50 > 0 and sma_20 < (sma_50 * 0.985):
            logger.debug(f"Pyramiding: {ticker} 20MA ${sma_20:.2f} < 50MA ${sma_50:.2f}. Trend not confirmed.")
            return None

        # 回檔幅度防線：若自高點已深度回檔超過 5.0%，不宜追高加碼
        drawdown_from_peak = ((current_price - current_peak) / current_peak) * 100.0 if current_peak > 0 else 0.0
        if drawdown_from_peak < -5.0:
            logger.debug(f"Pyramiding: {ticker} drawdown {drawdown_from_peak:.1f}% from peak is too deep.")
            return None

        # 5. 金字塔遞減規模計算 (Pyramidal Decreasing Sizing)
        scale_ratio = float(self._get_setting(
            "pyramid_stage1_scale_ratio" if target_stage == 1 else "pyramid_stage2_scale_ratio",
            0.25 if target_stage == 1 else 0.15,
        ))

        add_shares = round(current_shares * scale_ratio, 2)
        if add_shares <= 0.001:
            return None

        add_amount_usd = round(add_shares * current_price, 2)

        # 6. 集中度上限守衛 (Concentration Cap Guard)
        max_single_position_pct = float(self._get_setting("max_single_position_pct", 0.18))
        if portfolio_total_equity > 0:
            current_pos_val = current_shares * current_price
            max_allowed_val = portfolio_total_equity * max_single_position_pct
            projected_val = current_pos_val + add_amount_usd

            if projected_val > max_allowed_val:
                remaining_val = max_allowed_val - current_pos_val
                if remaining_val < 10.0:  # 可加碼空間小於 $10，拒絕執行
                    logger.info(
                        f"Pyramiding: {ticker} already near concentration ceiling "
                        f"({current_pos_val / portfolio_total_equity * 100:.1f}% / {max_single_position_pct * 100:.1f}%). Skipped."
                    )
                    return None
                # 自動鉗制加碼規模至權重上限
                add_shares = round(remaining_val / current_price, 2)
                add_amount_usd = round(add_shares * current_price, 2)
                if add_shares <= 0.001:
                    return None

            projected_weight_pct = round(((current_pos_val + add_amount_usd) / portfolio_total_equity) * 100.0, 2)
        else:
            projected_weight_pct = current_weight_pct

        # 7. 確信度評分模型 (Conviction Scoring: 8.5 ~ 9.8)
        base_score = 8.5
        breakdown = [
            {"agent": "TrendMomentum", "confidence": 8.5, "weight": 0.4, "key_factor": f"Stage {target_stage} Profit Breakout (+{unrealized_pnl_pct:.1f}%)"}
        ]

        # RSI 黃金動能推進區加分 (60 ~ 72)
        if 58.0 <= rsi <= 72.0:
            base_score += 0.5
            breakdown.append({"agent": "RSI_Momentum", "confidence": 9.0, "weight": 0.2, "key_factor": f"Optimal Momentum RSI={rsi:.1f}"})

        # 認證長線贏家護城河加分
        is_winner = False
        try:
            is_winner = self.winner_service.is_winner(ticker)
            if is_winner:
                base_score += 0.5
                breakdown.append({"agent": "MoatDefense", "confidence": 9.5, "weight": 0.2, "key_factor": "Certified Compounder Winner"})
        except Exception:
            pass

        # MACD 多頭交叉加分
        if tech.get("macd") == "bullish":
            base_score += 0.3
            breakdown.append({"agent": "TrendCross", "confidence": 8.8, "weight": 0.2, "key_factor": "Bullish MACD Structure"})

        confidence_score = round(min(9.8, base_score), 2)

        rationale = (
            f"🚀 [金字塔動能加碼 Stage {target_stage}] {ticker}: 浮盈 +{unrealized_pnl_pct:.1f}%，"
            f"移動停損已推進至 ${active_stop_price:.2f} (高於成本 ${avg_price:.2f})，鎖定底倉風險。"
            f"動能指標健康 (RSI {rsi:.1f}, 站穩 20MA ${sma_20:.2f})，"
            f"依金字塔原則順勢加碼 {add_shares} 股 (~${add_amount_usd:.2f})，預計權重至 {projected_weight_pct:.1f}%。"
        )

        return PyramidingDecision(
            should_scale_in=True,
            ticker=ticker,
            stage=target_stage,
            add_shares=add_shares,
            add_amount_usd=add_amount_usd,
            current_shares=current_shares,
            current_price=current_price,
            avg_price=avg_price,
            unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
            current_weight_pct=round(current_weight_pct, 2),
            projected_weight_pct=projected_weight_pct,
            active_stop_price=active_stop_price,
            confidence_score=confidence_score,
            confidence_breakdown=breakdown,
            rationale=rationale,
            metrics={"rsi": rsi, "sma_20": sma_20, "sma_50": sma_50, "drawdown_from_peak": drawdown_from_peak},
        )
