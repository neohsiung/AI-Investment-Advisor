"""
Microstructure Quote Spoofing & Depth-Imbalance Shielder (Phase 59B)
====================================================================
盤中流動性微觀獵殺與自適應點差訂單簿反欺詐嗅探器

核心架構：
1. 針對 3-Tier 限價吸籌掛單，實施盤中微觀反欺詐嗅探：
   - 掛單撤單比率 (Cancel-to-Fill Ratio, CFR): 衡量盤口短時掛單頻繁撤單率 (CFR >= 3.0 代表虛假流動性誘導)。
   - 流動性存續半衰期 (Depth Persistence Half-Life, DPH): 假單通常存續時間極短 (< 2.0s)。
   - 盤口深度失衡跳水衝擊 (Depth-Imbalance Flush Risk)。
2. 4 級反欺詐嗅探體制 (Spoofing Regimes):
   - SPOOF_HUNT_DETECTED (偵測到獵殺假單): CFR >= 3.0 或 DPH < 2.0s -> 階梯限價向下平移 0.40% ~ 0.60%，規避誘多誘空，捕獲做市商砸出的真實低點。
   - PHANTOM_LIQUIDITY_WARNING (虛假深度預警): 2.0 <= CFR < 3.0 -> 階梯限價向下微調 0.20%。
   - CLEAN_ORDER_FLOW (健康真實訂單流): CFR < 2.0 -> 維持原始階梯限價目標 (0.0% 平移)。
   - INSUFFICIENT_TICK_DATA (缺乏微觀高頻資料): 安全回退為 CLEAN_ORDER_FLOW，不盲目調整。
3. 整合 StaggeredDipBuyingService:
   - 於計算階梯目標價與盤中追單改價時自動套用反獵殺平移 (Anti-Hunt Downward Offset)。
4. 0-LLM 數理優先，輸出符合 Telegram HTML + Email nl2br 雙渠道格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("MicrostructureSpoofingDetectorService")


@dataclass
class SpoofingMetric:
    """單一標的之微觀反欺詐與假突破獵殺嗅探指標"""
    ticker: str
    regime: str  # SPOOF_HUNT_DETECTED, PHANTOM_LIQUIDITY_WARNING, CLEAN_ORDER_FLOW, INSUFFICIENT_TICK_DATA
    cancel_to_fill_ratio: float
    depth_persistence_seconds: float
    anti_hunt_downward_offset_pct: float
    original_target_price: float
    adjusted_target_price: float
    rationale: str
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "regime": self.regime,
            "cancel_to_fill_ratio": round(self.cancel_to_fill_ratio, 2),
            "depth_persistence_seconds": round(self.depth_persistence_seconds, 2),
            "anti_hunt_downward_offset_pct": round(self.anti_hunt_downward_offset_pct, 4),
            "original_target_price": round(self.original_target_price, 2),
            "adjusted_target_price": round(self.adjusted_target_price, 2),
            "rationale": self.rationale,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SpoofingMetric:
        return cls(
            ticker=str(data.get("ticker", "")),
            regime=str(data.get("regime", "CLEAN_ORDER_FLOW")),
            cancel_to_fill_ratio=float(data.get("cancel_to_fill_ratio", 1.0) or 1.0),
            depth_persistence_seconds=float(data.get("depth_persistence_seconds", 5.0) or 5.0),
            anti_hunt_downward_offset_pct=float(data.get("anti_hunt_downward_offset_pct", 0.0) or 0.0),
            original_target_price=float(data.get("original_target_price", 0.0) or 0.0),
            adjusted_target_price=float(data.get("adjusted_target_price", 0.0) or 0.0),
            rationale=str(data.get("rationale", "")),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


class MicrostructureSpoofingDetectorService:
    """盤中流動性微觀獵殺與自適應點差訂單簿反欺詐嗅探服務"""

    DEFAULT_CFR_THRESHOLD = 3.0                    # 假單撤單比率門檻 (>= 3.0)
    DEFAULT_PERSISTENCE_THRESHOLD_SEC = 2.0        # 深度存續半衰期警示門檻 (< 2.0s)
    DEFAULT_ANTI_HUNT_OFFSET_PCT = 0.004           # 偵測到獵殺時向下平移幅度 (-0.4% = 40 bps)

    REDIS_CACHE_TTL_SECONDS = 180                  # 快取 3 分鐘
    REDIS_KEY_PREFIX = "microstructure:spoof_shield"

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
        return bool(self._get_setting("enable_microstructure_spoofing_shield", True))

    @property
    def cfr_threshold(self) -> float:
        return float(self._get_setting("spoofing_cancel_to_fill_ratio_threshold", self.DEFAULT_CFR_THRESHOLD))

    @property
    def anti_hunt_offset_pct(self) -> float:
        return float(self._get_setting("spoofing_anti_hunt_downward_offset_pct", self.DEFAULT_ANTI_HUNT_OFFSET_PCT))

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 微觀反欺詐嗅探 (evaluate_spoofing_risk)
    # ═══════════════════════════════════════════════════════════════════════

    async def evaluate_spoofing_risk(
        self,
        ticker: str,
        current_price: float,
        target_price: float,
        tick_data: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False,
    ) -> SpoofingMetric:
        """
        評估標的盤口是否存在假單撤單誘多與停損獵殺風險。
        """
        clean_ticker = (ticker or "").upper().strip()
        orig_price = round(max(0.01, target_price), 2)

        if not self.is_enabled:
            return SpoofingMetric(
                ticker=clean_ticker,
                regime="CLEAN_ORDER_FLOW",
                cancel_to_fill_ratio=1.0,
                depth_persistence_seconds=10.0,
                anti_hunt_downward_offset_pct=0.0,
                original_target_price=orig_price,
                adjusted_target_price=orig_price,
                rationale="微觀反欺詐嗅探已停用",
            )

        # 1. 檢查 Redis 快取
        if not force_refresh:
            try:
                from src.infrastructure.cache.redis_client import get_redis
                r = await get_redis(decode_responses=True)
                cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{clean_ticker}"
                cached = await r.get(cache_key)
                if cached:
                    metric = SpoofingMetric.from_dict(json.loads(cached))
                    # 重新根據傳入的 target_price 動態映射 adjusted_price
                    adj = round(orig_price * (1.0 - metric.anti_hunt_downward_offset_pct), 2)
                    metric.original_target_price = orig_price
                    metric.adjusted_target_price = adj
                    return metric
            except Exception as ce:
                logger.debug("Redis lookup error in spoofing detector: %s", ce)

        # 2. 提取或推導微觀訂單流特徵
        cfr = 1.0
        persistence_sec = 5.0

        if tick_data:
            cfr = float(tick_data.get("cancel_to_fill_ratio", 1.0) or 1.0)
            persistence_sec = float(tick_data.get("depth_persistence_seconds", 5.0) or 5.0)
        else:
            # 依據買賣價差與近期成交量特徵估算
            try:
                if self.market_data_service:
                    quote_call = self.market_data_service.get_quote(clean_ticker)
                    import inspect
                    quote = await quote_call if inspect.isawaitable(quote_call) else quote_call
                    if quote:
                        sp_pct = float(quote.get("spread_pct", 0.001) or 0.001)
                        # 若點差異常擴大 (> 0.25%)，微觀盤口撤單與空洞風險攀升
                        if sp_pct >= 0.0025:
                            cfr = 3.2
                            persistence_sec = 1.2
                        elif sp_pct >= 0.0015:
                            cfr = 2.2
                            persistence_sec = 2.8
            except Exception as me:
                logger.debug("Failed deriving micro features for %s: %s", clean_ticker, me)

        # 3. 狀態機判定
        cfr_thresh = self.cfr_threshold
        persist_thresh = self.DEFAULT_PERSISTENCE_THRESHOLD_SEC

        if cfr >= cfr_thresh or persistence_sec < persist_thresh:
            regime = "SPOOF_HUNT_DETECTED"
            offset_pct = self.anti_hunt_offset_pct
            rationale = (
                f"偵測到做市商假單撤單誘多與停損獵殺風險 (CFR: {cfr:.1f} >= {cfr_thresh:.1f}, "
                f"深度半衰期: {persistence_sec:.1f}s < {persist_thresh:.1f}s)；"
                f"自動將階梯目標價向下平移 {offset_pct*100:.2f}% 防誘單並鎖定真實清洗低點"
            )
        elif cfr >= 2.0:
            regime = "PHANTOM_LIQUIDITY_WARNING"
            offset_pct = round(self.anti_hunt_offset_pct * 0.50, 4)
            rationale = (
                f"盤口深度閃爍 (CFR: {cfr:.1f})，虛假流動性升溫；"
                f"自適應向下微調 {offset_pct*100:.2f}% 擴大安全邊際"
            )
        else:
            regime = "CLEAN_ORDER_FLOW"
            offset_pct = 0.0
            rationale = f"盤口訂單流健康 (CFR: {cfr:.1f}, 存續: {persistence_sec:.1f}s)；維持標準階梯目標"

        adjusted_target = round(orig_price * (1.0 - offset_pct), 2)

        metric = SpoofingMetric(
            ticker=clean_ticker,
            regime=regime,
            cancel_to_fill_ratio=cfr,
            depth_persistence_seconds=persistence_sec,
            anti_hunt_downward_offset_pct=offset_pct,
            original_target_price=orig_price,
            adjusted_target_price=adjusted_target,
            rationale=rationale,
        )

        # 4. 寫入 Redis 快取
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{clean_ticker}"
            await r.setex(cache_key, self.REDIS_CACHE_TTL_SECONDS, json.dumps(metric.to_dict()))
        except Exception as we:
            logger.debug("Failed saving spoofing metric to Redis: %s", we)

        return metric

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 0-LLM 雙渠道戰報生成
    # ═══════════════════════════════════════════════════════════════════════

    def format_spoofing_report(
        self,
        metrics: List[SpoofingMetric],
        channel: str = "telegram",
    ) -> str:
        """
        產出符合 Telegram HTML 與 Email nl2br 雙渠道標準之反欺詐嗅探儀表戰報。
        """
        if not metrics:
            return (
                "🛡️ <b>【盤中微觀獵殺與反欺詐訂單簿嗅探儀表】</b>\n"
                "• <i>目前暫無待嗅探之階梯限價標的。</i>\n"
                "💡 <i>輸入 <code>/dipbuy plan</code> 檢視限價計畫，輸入 <code>/guard</code> 檢視風控守衛。</i>"
            )

        lines = [
            "🛡️ <b>【盤中微觀獵殺與反欺詐訂單簿嗅探儀表】</b>",
            "━━━━━━━━━━━━━━━━━━",
        ]

        for m in metrics:
            if m.regime == "SPOOF_HUNT_DETECTED":
                badge = "🔴 <b>獵殺假單警戒 (SPOOF_HUNT_DETECTED)</b>"
            elif m.regime == "PHANTOM_LIQUIDITY_WARNING":
                badge = "🟡 <b>虛假深度預警 (PHANTOM_LIQUIDITY)</b>"
            else:
                badge = "🟢 <b>真實健康訂單流 (CLEAN_ORDER_FLOW)</b>"

            lines.append(f"• 標的：<b>{m.ticker}</b> ➔ {badge}")
            lines.append(
                f"• 微觀指標：撤單比率 (CFR) <code>{m.cancel_to_fill_ratio:.1f}</code> | "
                f"深度半衰期 <code>{m.depth_persistence_seconds:.1f}s</code>"
            )
            if m.anti_hunt_downward_offset_pct > 0:
                lines.append(
                    f"• <b>防獵殺平移</b>：向下安全平移 <code><b>-{m.anti_hunt_downward_offset_pct*100:.2f}%</b></code> "
                    f"(${m.original_target_price:.2f} ➔ <code><b>${m.adjusted_target_price:.2f}</b></code>)"
                )
            else:
                lines.append(f"• <b>階梯目標價</b>：<code>${m.adjusted_target_price:.2f}</code> (維持基準)")
            lines.append(f"• <i>嗅探處置說明</i>：{m.rationale}")
            lines.append("──────────────────")

        lines.append("💡 <b>守衛聯動</b>：階梯限價吸籌自動下移目標價，防止散戶停損點被獵殺時過早進場接飛刀。")
        lines.append("💡 <b>快捷指令</b>：輸入 <code>/dipbuy plan</code> 檢視最新點位，輸入 <code>/betadamp</code> 檢視貝塔阻尼。")

        return "\n".join(lines)
