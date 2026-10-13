"""
Cross-Market Dark Pool Block-Trade Pricing & Calibration Service (Phase 60A)
=============================================================================
跨市場暗池大宗換手與隔夜掛單動態校準引擎

核心架構：
1. 追蹤美股盤前 (04:00~09:30 EST) 與盤後 (16:00~20:00 EST) 暗池/FINRA ADF 大宗交易 (Dark Pool Prints / Block Trades)。
2. 度量大宗成交集中價位 (Block VWAP)、暗池買賣失衡比率 (Dark Pool Buy Ratio) 與機構溢折價偏離度 (Discount %)。
3. 4 級暗池體制 (Dark Pool Regimes):
   - INSTITUTIONAL_ACCUMULATION: 暗池大單集中於折價區且買方佔優 (Buy Ratio >= 65%)
     -> 將 Tier 1 限價校準錨定至 Block VWAP，提高撮合成交率，捕獲主力建倉底價。
   - BLOCK_DISTRIBUTION_FLUSH: 暗池大單折價出貨拋售 (Sell Ratio >= 65%)
     -> 將所有 Tier 限價向下平移 50 ~ 80 bps，防範承接機構拋售潮。
   - BALANCED_DARK_LIQUIDITY: 暗池換手均衡 (Buy Ratio 35% ~ 65%)
     -> 維持常規籌碼結構錨點 (0 bps 平移)。
   - INSUFFICIENT_DARK_PRINTS: 缺乏暗池大宗資料
     -> 安全回退為常規基準，不盲目校準。
4. 整合 StaggeredDipBuyingService:
   - 於開盤前精算階梯吸籌目標價時，自適應注入暗池底價校準 (Calibrated Anchor Price)。
5. 0-LLM 數理優先，輸出符合 Telegram HTML + Email nl2br 雙渠道格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("CrossMarketDarkPoolPricingService")


@dataclass
class DarkPoolTickerSummary:
    """單一標的之暗池大宗換手與校準指標"""
    ticker: str
    regime: str  # INSTITUTIONAL_ACCUMULATION, BLOCK_DISTRIBUTION_FLUSH, BALANCED_DARK_LIQUIDITY, INSUFFICIENT_DARK_PRINTS
    block_vwap: float
    reference_price: float
    total_dark_volume: float
    total_dark_notional_usd: float
    dark_pool_buy_ratio: float
    dark_pool_discount_pct: float
    recommended_limit_shift_pct: float
    calibrated_anchor_price: float
    rationale: str
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "regime": self.regime,
            "block_vwap": round(self.block_vwap, 2),
            "reference_price": round(self.reference_price, 2),
            "total_dark_volume": round(self.total_dark_volume, 2),
            "total_dark_notional_usd": round(self.total_dark_notional_usd, 2),
            "dark_pool_buy_ratio": round(self.dark_pool_buy_ratio, 4),
            "dark_pool_discount_pct": round(self.dark_pool_discount_pct, 4),
            "recommended_limit_shift_pct": round(self.recommended_limit_shift_pct, 4),
            "calibrated_anchor_price": round(self.calibrated_anchor_price, 2),
            "rationale": self.rationale,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DarkPoolTickerSummary:
        return cls(
            ticker=str(data.get("ticker", "")),
            regime=str(data.get("regime", "BALANCED_DARK_LIQUIDITY")),
            block_vwap=float(data.get("block_vwap", 0.0) or 0.0),
            reference_price=float(data.get("reference_price", 0.0) or 0.0),
            total_dark_volume=float(data.get("total_dark_volume", 0.0) or 0.0),
            total_dark_notional_usd=float(data.get("total_dark_notional_usd", 0.0) or 0.0),
            dark_pool_buy_ratio=float(data.get("dark_pool_buy_ratio", 0.50) or 0.50),
            dark_pool_discount_pct=float(data.get("dark_pool_discount_pct", 0.0) or 0.0),
            recommended_limit_shift_pct=float(data.get("recommended_limit_shift_pct", 0.0) or 0.0),
            calibrated_anchor_price=float(data.get("calibrated_anchor_price", 0.0) or 0.0),
            rationale=str(data.get("rationale", "")),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


class CrossMarketDarkPoolPricingService:
    """跨市場暗池大宗換手與隔夜掛單動態校準服務"""

    DEFAULT_ACCUMULATION_BUY_RATIO = 0.65       # 機構吸籌買方佔比門檻 (>= 65%)
    DEFAULT_DISTRIBUTION_SELL_RATIO = 0.65      # 機構出貨拋售佔比門檻 (>= 65%)
    DEFAULT_MAX_LIMIT_SHIFT_PCT = 0.008         # 最大允許價格校準平移比例 (0.80% = 80 bps)
    REDIS_CACHE_TTL_SECONDS = 300               # 快取 5 分鐘
    REDIS_KEY_PREFIX = "darkpool:summary"

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        self.market_data_service = market_data_service

    def _get_setting(self, key: str, default: Any) -> Any:
        try:
            return self.settings_service.get_setting(key, default)
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("enable_dark_pool_pricing", True))

    @property
    def accumulation_threshold(self) -> float:
        return float(self._get_setting("dark_pool_accumulation_threshold", self.DEFAULT_ACCUMULATION_BUY_RATIO))

    @property
    def distribution_threshold(self) -> float:
        return float(self._get_setting("dark_pool_distribution_threshold", self.DEFAULT_DISTRIBUTION_SELL_RATIO))

    @property
    def max_limit_shift_pct(self) -> float:
        return float(self._get_setting("dark_pool_max_limit_shift_pct", self.DEFAULT_MAX_LIMIT_SHIFT_PCT))

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 暗池大宗換手評估 (evaluate_dark_pool_activity)
    # ═══════════════════════════════════════════════════════════════════════

    async def evaluate_dark_pool_activity(
        self,
        ticker: str,
        reference_price: float,
        dark_prints: Optional[List[Dict[str, Any]]] = None,
        force_refresh: bool = False,
    ) -> DarkPoolTickerSummary:
        """
        評估標的盤前盤後暗池大宗換手與價格偏離度，給出階梯吸籌校準底價。
        """
        clean_ticker = (ticker or "").upper().strip()
        ref_p = round(max(0.01, reference_price), 2)

        if not self.is_enabled:
            return DarkPoolTickerSummary(
                ticker=clean_ticker,
                regime="BALANCED_DARK_LIQUIDITY",
                block_vwap=ref_p,
                reference_price=ref_p,
                total_dark_volume=0.0,
                total_dark_notional_usd=0.0,
                dark_pool_buy_ratio=0.50,
                dark_pool_discount_pct=0.0,
                recommended_limit_shift_pct=0.0,
                calibrated_anchor_price=ref_p,
                rationale="暗池大宗定價校準已停用",
            )

        # 1. 檢查 Redis 快取
        if not force_refresh:
            try:
                from src.infrastructure.cache.redis_client import get_redis
                r = await get_redis(decode_responses=True)
                cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{clean_ticker}"
                cached = await r.get(cache_key)
                if cached:
                    summary = DarkPoolTickerSummary.from_dict(json.loads(cached))
                    summary.reference_price = ref_p
                    if summary.regime == "INSTITUTIONAL_ACCUMULATION" and summary.block_vwap > 0:
                        summary.calibrated_anchor_price = summary.block_vwap
                    else:
                        summary.calibrated_anchor_price = round(ref_p * (1.0 + summary.recommended_limit_shift_pct), 2)
                    return summary
            except Exception as ce:
                logger.debug("Redis lookup error in dark pool pricing: %s", ce)

        # 2. 統計暗池成交量、Notional、Block VWAP 與 Buy Ratio
        total_vol = 0.0
        total_notional = 0.0
        buy_vol = 0.0
        sell_vol = 0.0

        if dark_prints:
            for p in dark_prints:
                vol = float(p.get("size", 0.0) or (p.get("volume", 0.0) or 0.0))
                pr = float(p.get("price", 0.0) or 0.0)
                side = str(p.get("side", "UNKNOWN")).upper()
                if vol <= 0 or pr <= 0:
                    continue
                total_vol += vol
                notional = vol * pr
                total_notional += notional
                if side in ("BUY", "BID"):
                    buy_vol += vol
                elif side in ("SELL", "ASK"):
                    sell_vol += vol
                else:
                    # 未標明方向依相對 reference_price 判定
                    if pr >= ref_p:
                        buy_vol += vol
                    else:
                        sell_vol += vol

            block_vwap = round(total_notional / total_vol, 2) if total_vol > 0 else ref_p
            classified_vol = buy_vol + sell_vol
            buy_ratio = round(buy_vol / classified_vol, 4) if classified_vol > 0 else 0.50
        else:
            # 若無明細，以即時買賣報價與近期成交特徵進行穩健合成
            block_vwap = ref_p
            buy_ratio = 0.50
            total_vol = 0.0
            total_notional = 0.0

            try:
                if self.market_data_service:
                    quote_call = self.market_data_service.get_quote(clean_ticker)
                    import inspect
                    quote = await quote_call if inspect.isawaitable(quote_call) else quote_call
                    if quote:
                        bid = float(quote.get("bid", 0.0) or 0.0)
                        ask = float(quote.get("ask", 0.0) or 0.0)
                        last_p = float(quote.get("last", 0.0) or quote.get("close", 0.0) or ref_p)
                        if bid > 0 and ask > 0:
                            mid = (bid + ask) / 2.0
                            # 若最新成交顯著偏向 Bid (主動折價) 或 Ask (主動溢價)
                            if last_p < mid:
                                buy_ratio = 0.38  # 略偏空
                            elif last_p > mid:
                                buy_ratio = 0.62  # 略偏多
                            block_vwap = round(last_p, 2)
            except Exception as me:
                logger.debug("Failed synthesizing dark pool proxy for %s: %s", clean_ticker, me)

        discount_pct = round((block_vwap - ref_p) / ref_p, 4) if ref_p > 0 else 0.0

        # 3. 狀態機判定
        accum_thresh = self.accumulation_threshold
        distrib_thresh = self.distribution_threshold
        max_shift = self.max_limit_shift_pct

        if total_vol <= 0 and buy_ratio == 0.50:
            regime = "INSUFFICIENT_DARK_PRINTS"
            shift_pct = 0.0
            calibrated_anchor = ref_p
            rationale = "盤前盤後暫無顯著暗池大宗換手；維持常規籌碼結構錨點"
        elif buy_ratio >= accum_thresh:
            regime = "INSTITUTIONAL_ACCUMULATION"
            # 若機構在折價處大舉吸籌，將錨點直接校準至 Block VWAP
            shift_pct = max(-max_shift, min(max_shift, discount_pct))
            calibrated_anchor = block_vwap if block_vwap > 0 else ref_p
            rationale = (
                f"偵測到機構暗池大宗吸籌 (買方佔比: {buy_ratio:.1%} >= {accum_thresh:.1%})；"
                f"將第一檔吸籌錨點校準至機構大宗均價 ${calibrated_anchor:.2f} (偏離: {discount_pct:+.2%})，搶先截擊真實主力底價"
            )
        elif (1.0 - buy_ratio) >= distrib_thresh:
            regime = "BLOCK_DISTRIBUTION_FLUSH"
            # 機構折價拋售出貨，防禦性向下平移
            shift_pct = -max(0.005, max_shift * 0.75)
            calibrated_anchor = round(ref_p * (1.0 + shift_pct), 2)
            rationale = (
                f"偵測到機構暗池大宗出貨拋售 (賣方佔比: {(1.0-buy_ratio):.1%} >= {distrib_thresh:.1%})；"
                f"階梯限價向下平移 {abs(shift_pct)*100:.2f}% (${ref_p:.2f} ➔ ${calibrated_anchor:.2f})，規避承接拋售潮"
            )
        else:
            regime = "BALANCED_DARK_LIQUIDITY"
            shift_pct = 0.0
            calibrated_anchor = ref_p
            rationale = (
                f"暗池換手處於中性平衡 (買方: {buy_ratio:.1%}, Block VWAP: ${block_vwap:.2f})；"
                f"維持標準階梯目標點位"
            )

        summary = DarkPoolTickerSummary(
            ticker=clean_ticker,
            regime=regime,
            block_vwap=block_vwap,
            reference_price=ref_p,
            total_dark_volume=total_vol,
            total_dark_notional_usd=total_notional,
            dark_pool_buy_ratio=buy_ratio,
            dark_pool_discount_pct=discount_pct,
            recommended_limit_shift_pct=shift_pct,
            calibrated_anchor_price=calibrated_anchor,
            rationale=rationale,
        )

        # 4. 寫入 Redis 快取
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{clean_ticker}"
            await r.setex(cache_key, self.REDIS_CACHE_TTL_SECONDS, json.dumps(summary.to_dict()))
        except Exception as we:
            logger.debug("Failed saving dark pool summary to Redis: %s", we)

        return summary

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 0-LLM 雙渠道戰報生成
    # ═══════════════════════════════════════════════════════════════════════

    def format_dark_pool_report(
        self,
        summaries: List[DarkPoolTickerSummary],
        channel: str = "telegram",
    ) -> str:
        """
        產出符合 Telegram HTML 與 Email nl2br 雙渠道標準之暗池大宗換手戰報。
        """
        if not summaries:
            return (
                "🌌 <b>【跨市場暗池大宗換手與隔夜掛單校準儀表】</b>\n"
                "• <i>目前暫無暗池大宗換手監控數據。</i>\n"
                "💡 <i>輸入 <code>/dipbuy plan</code> 檢視限價計畫，輸入 <code>/spoof</code> 檢視微觀防欺詐。</i>"
            )

        lines = [
            "🌌 <b>【跨市場暗池大宗換手與隔夜掛單校準儀表】</b>",
            "━━━━━━━━━━━━━━━━━━",
        ]

        for s in summaries:
            if s.regime == "INSTITUTIONAL_ACCUMULATION":
                badge = "🟢 <b>機構吸籌換手 (INSTITUTIONAL_ACCUMULATION)</b>"
            elif s.regime == "BLOCK_DISTRIBUTION_FLUSH":
                badge = "🔴 <b>大宗出貨拋售 (BLOCK_DISTRIBUTION_FLUSH)</b>"
            elif s.regime == "BALANCED_DARK_LIQUIDITY":
                badge = "🟡 <b>暗池換手中性 (BALANCED_LIQUIDITY)</b>"
            else:
                badge = "⚪ <b>常規微幅流動 (INSUFFICIENT_DATA)</b>"

            lines.append(f"• 標的：<b>{s.ticker}</b> ➔ {badge}")
            lines.append(
                f"  ├ 基準價: <code>${s.reference_price:.2f}</code> | "
                f"大宗均價 (VWAP): <code>${s.block_vwap:.2f}</code>"
            )
            lines.append(
                f"  ├ 暗池買方比: <code>{s.dark_pool_buy_ratio:.1%}</code> | "
                f"大宗總額: <code>${s.total_dark_notional_usd:,.0f} USD</code>"
            )
            if s.recommended_limit_shift_pct != 0.0 or s.calibrated_anchor_price != s.reference_price:
                lines.append(
                    f"  ├ <b>吸籌點位校準</b>：<code>${s.reference_price:.2f}</code> ➔ "
                    f"<code><b>${s.calibrated_anchor_price:.2f}</b></code> "
                    f"({s.recommended_limit_shift_pct*100:+.2f}%)"
                )
            lines.append(f"  └ <i>校準解析</i>：{s.rationale}")
            lines.append("──────────────────")

        lines.append("💡 <b>定價聯動</b>：開盤 3-Tier 限價單自動依機構暗池底價校準，防止盲目追價並鎖定機構換手底部。")
        lines.append("💡 <b>快捷指令</b>：輸入 <code>/dipbuy plan</code> 檢視階梯限價，輸入 <code>/convex</code> 檢視夏普邊界配置。")

        return "\n".join(lines)
