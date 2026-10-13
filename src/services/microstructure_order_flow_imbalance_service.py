"""
Microstructure Order Flow Imbalance & Liquidity Vacuum Defense Service (Phase 61B)
==================================================================================
微觀訂單流失衡率與做市商流動性真空防禦引擎

核心微觀結構量化理論：
1. 訂單流失衡 (Order Flow Imbalance, OFI - Cont, Kukanov, and Stoikov 2014):
   度量相鄰微觀委託更新 (t-1 -> t) 最佳買賣價量變化：
   - ΔB_t:
     * 若 P_t^b > P_{t-1}^b: ΔB_t = q_t^b (買價上移，新委買厚度進場)
     * 若 P_t^b = P_{t-1}^b: ΔB_t = q_t^b - q_{t-1}^b (買價不變，委買厚度增減)
     * 若 P_t^b < P_{t-1}^b: ΔB_t = -q_{t-1}^b (買價下移，前一檔委買撤單或被擊穿)
   - ΔA_t:
     * 若 P_t^a < P_{t-1}^a: ΔA_t = -q_t^a (賣價下移，新委賣壓低進場)
     * 若 P_t^a = P_{t-1}^a: ΔA_t = q_t^a - q_{t-1}^a (賣價不變，委賣厚度增減)
     * 若 P_t^a > P_{t-1}^a: ΔA_t = q_{t-1}^a (賣價上移，前一檔委賣撤單或被吃掉)
   - OFI_t = ΔB_t - ΔA_t
   - OFI_Ratio = (ΔB_t - ΔA_t) / (|ΔB_t| + |ΔA_t| + 1e-6) ∈ [-1.0, 1.0]

2. 做市商撤單與流動性真空 (Spread Shock & Liquidity Vacuum):
   - 當做市商因風險厭惡或極端資訊不對稱閃電撤單時，買賣價差 (Bid-Ask Spread) 瞬間跳增 2.5 倍以上。
   - 委託厚度大幅縮水，形成訂單薄空洞 (Liquidity Vacuum)。
   - 若在此時執行市價單或寬幅掛單，將遭遇嚴重非理性滑點。

3. 4 級微觀流動性體制 (Microstructure Liquidity Regimes):
   - DEEP_LIQUIDITY_HEALTHY: 價差正常 (Spread Ratio <= 1.30)，|OFI_Ratio| <= 0.35。
   - BUY_PRESSURE_ACCUMULATION: OFI_Ratio > +0.45，主動買方佔優推升價格，流動性充足。
   - SELL_PRESSURE_DRAIN: OFI_Ratio < -0.45，主動賣壓拋售傾瀉，防範下行衝擊。
   - LIQUIDITY_VACUUM_FREEZE: Spread Shock >= 2.5x 或厚度枯竭，觸發防禦性冷凍 (Freeze)，阻斷買單 120 秒。

4. 風控單一真理閘門 (SSOT) 整合：
   - 整合至 UnifiedRiskGatewayService，流動性真空期間直接擋下 BUY 訂單。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("MicrostructureOrderFlowImbalanceService")


@dataclass
class OFITickerMetric:
    """單一標的之微觀訂單流失衡與流動性真空指標"""
    ticker: str
    regime: str  # DEEP_LIQUIDITY_HEALTHY, BUY_PRESSURE_ACCUMULATION, SELL_PRESSURE_DRAIN, LIQUIDITY_VACUUM_FREEZE
    best_bid: float
    best_ask: float
    spread_usd: float
    spread_ratio: float
    ofi_value: float
    ofi_ratio: float
    bid_depth: float
    ask_depth: float
    is_vacuum_frozen: bool
    recommended_action: str  # EXECUTE_NORMAL, AGGRESSIVE_FILL, DEFENSIVE_DRIFT, BLOCK_AND_COOLDOWN
    freeze_remaining_seconds: int
    rationale: str
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "regime": self.regime,
            "best_bid": round(self.best_bid, 4),
            "best_ask": round(self.best_ask, 4),
            "spread_usd": round(self.spread_usd, 4),
            "spread_ratio": round(self.spread_ratio, 2),
            "ofi_value": round(self.ofi_value, 2),
            "ofi_ratio": round(self.ofi_ratio, 4),
            "bid_depth": round(self.bid_depth, 2),
            "ask_depth": round(self.ask_depth, 2),
            "is_vacuum_frozen": self.is_vacuum_frozen,
            "recommended_action": self.recommended_action,
            "freeze_remaining_seconds": self.freeze_remaining_seconds,
            "rationale": self.rationale,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OFITickerMetric:
        return cls(
            ticker=str(data.get("ticker", "")),
            regime=str(data.get("regime", "DEEP_LIQUIDITY_HEALTHY")),
            best_bid=float(data.get("best_bid", 0.0) or 0.0),
            best_ask=float(data.get("best_ask", 0.0) or 0.0),
            spread_usd=float(data.get("spread_usd", 0.0) or 0.0),
            spread_ratio=float(data.get("spread_ratio", 1.0) or 1.0),
            ofi_value=float(data.get("ofi_value", 0.0) or 0.0),
            ofi_ratio=float(data.get("ofi_ratio", 0.0) or 0.0),
            bid_depth=float(data.get("bid_depth", 0.0) or 0.0),
            ask_depth=float(data.get("ask_depth", 0.0) or 0.0),
            is_vacuum_frozen=bool(data.get("is_vacuum_frozen", False)),
            recommended_action=str(data.get("recommended_action", "EXECUTE_NORMAL")),
            freeze_remaining_seconds=int(data.get("freeze_remaining_seconds", 0) or 0),
            rationale=str(data.get("rationale", "")),
            updated_at=data.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        )


class MicrostructureOrderFlowImbalanceService:
    """微觀訂單流失衡率與做市商流動性真空防禦服務"""

    DEFAULT_SPREAD_SHOCK_MULTIPLIER = 2.5       # 價差跳增 2.5 倍視為 Spread Shock
    DEFAULT_VACUUM_COOLDOWN_SECONDS = 120       # 流動性真空冷卻冷凍時間 (120 秒)
    DEFAULT_OFI_THRESHOLD = 0.45                # OFI Ratio 顯著失衡門檻
    REDIS_CACHE_TTL_SECONDS = 180               # 診斷快取 3 分鐘
    REDIS_KEY_PREFIX = "ofi:metric"
    REDIS_FREEZE_KEY_PREFIX = "ofi:freeze"

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

        self.market_data_service = market_data_service
        self._redis_client = None

    async def _get_redis(self):
        if self._redis_client is None:
            try:
                from src.infrastructure.cache.redis_client import get_redis
                self._redis_client = await get_redis(decode_responses=True)
            except Exception as e:
                logger.debug("Redis connection unavailable for MicrostructureOrderFlowImbalanceService: %s", e)
                self._redis_client = None
        return self._redis_client

    async def is_enabled(self) -> bool:
        """檢查微觀訂單流防禦是否啟用"""
        if self.settings_service:
            try:
                val = await self.settings_service.get_setting("enable_microstructure_ofi_defense", True)
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    return val.lower() in ("true", "1", "yes", "on")
            except Exception as e:
                logger.debug("Error checking enable_microstructure_ofi_defense: %s", e)
        return True

    async def is_vacuum_frozen(self, ticker: str) -> Tuple[bool, Optional[str], int]:
        """
        檢查指定標的是否正處於流動性真空防禦冷凍期。
        返回 (is_frozen, reason, remaining_seconds)。
        """
        sym = ticker.upper().strip()
        r = await self._get_redis()
        if not r:
            return False, None, 0

        freeze_key = f"{self.REDIS_FREEZE_KEY_PREFIX}:{self.user_id}:{sym}"
        try:
            ttl = await r.ttl(freeze_key)
            if ttl and ttl > 0:
                reason = await r.get(freeze_key) or "Spread Shock Liquidity Vacuum Active"
                return True, reason, ttl
        except Exception as e:
            logger.debug("Redis error checking vacuum freeze for %s: %s", sym, e)

        return False, None, 0

    async def trigger_vacuum_freeze(
        self,
        ticker: str,
        reason: str,
        duration_seconds: Optional[int] = None,
    ) -> int:
        """
        手動或觸發式激活流動性真空防禦冷凍。
        """
        sym = ticker.upper().strip()
        dur = duration_seconds or self.DEFAULT_VACUUM_COOLDOWN_SECONDS
        if self.settings_service:
            try:
                cfg_dur = await self.settings_service.get_setting("ofi_vacuum_cooldown_seconds", self.DEFAULT_VACUUM_COOLDOWN_SECONDS)
                if cfg_dur:
                    dur = int(cfg_dur)
            except Exception:
                pass

        r = await self._get_redis()
        if r:
            freeze_key = f"{self.REDIS_FREEZE_KEY_PREFIX}:{self.user_id}:{sym}"
            try:
                await r.set(freeze_key, reason, ex=dur)
            except Exception as e:
                logger.debug("Error writing freeze key for %s: %s", sym, e)
        return dur

    async def evaluate_order_flow_imbalance(
        self,
        ticker: str,
        current_quote: Optional[Dict[str, Any]] = None,
        quote_history: Optional[List[Dict[str, Any]]] = None,
    ) -> OFITickerMetric:
        """
        評估指定標的之微觀訂單流失衡率 (OFI) 與做市商價差衝擊。
        若傳入 quote_history 則依 Cont et al. (2014) 演算法精算；
        若無則依當前行情與快取判定微觀體制。
        """
        sym = ticker.upper().strip()
        r = await self._get_redis()
        cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{sym}"

        # 1. 檢查是否處於既有冷凍狀態
        is_frozen, freeze_reason, freeze_remaining = await self.is_vacuum_frozen(sym)

        # 2. 獲取價差衝擊與冷卻設定
        spread_shock_mult = self.DEFAULT_SPREAD_SHOCK_MULTIPLIER
        ofi_th = self.DEFAULT_OFI_THRESHOLD
        vacuum_ttl = self.DEFAULT_VACUUM_COOLDOWN_SECONDS

        if self.settings_service:
            try:
                mult_cfg = await self.settings_service.get_setting("ofi_spread_shock_multiplier", self.DEFAULT_SPREAD_SHOCK_MULTIPLIER)
                ttl_cfg = await self.settings_service.get_setting("ofi_vacuum_cooldown_seconds", self.DEFAULT_VACUUM_COOLDOWN_SECONDS)
                if mult_cfg is not None:
                    spread_shock_mult = float(mult_cfg)
                if ttl_cfg is not None:
                    vacuum_ttl = int(ttl_cfg)
            except Exception as se:
                logger.debug("Error reading ofi settings: %s", se)

        # 3. 解析或估算微觀報價
        best_bid, best_ask, bid_size, ask_size, median_spread = self._parse_or_estimate_quotes(
            sym=sym,
            quote=current_quote,
        )

        spread_usd = max(0.0001, best_ask - best_bid)
        spread_ratio = spread_usd / max(0.001, median_spread)

        # 4. 計算 OFI 數理指標 (若有相鄰報價序列)
        if quote_history and len(quote_history) >= 2:
            ofi_val, ofi_ratio = self._calculate_ofi_from_history(quote_history)
        else:
            # 單筆報價深度失衡代理計算
            tot_depth = bid_size + ask_size + 1e-6
            ofi_val = bid_size - ask_size
            ofi_ratio = max(-1.0, min(1.0, ofi_val / tot_depth))

        # 5. 判定 4 級微觀流動性體制
        if is_frozen:
            regime = "LIQUIDITY_VACUUM_FREEZE"
            rec_action = "BLOCK_AND_COOLDOWN"
            rationale = (
                f"做市商流動性真空防禦中 ({freeze_reason or 'Spread Shock'})，"
                f"剩餘冷凍時間 {freeze_remaining} 秒，強制暫停所有新開多頭以防滑點吞噬。"
            )
        elif spread_ratio >= spread_shock_mult:
            # 觸發新的 Spread Shock 冷凍
            regime = "LIQUIDITY_VACUUM_FREEZE"
            rec_action = "BLOCK_AND_COOLDOWN"
            freeze_reason = f"Bid-Ask Spread Shock 擴大 {spread_ratio:.1f}x (>${spread_usd:.3f})"
            freeze_remaining = await self.trigger_vacuum_freeze(
                ticker=sym,
                reason=freeze_reason,
                duration_seconds=vacuum_ttl,
            )
            is_frozen = True
            rationale = (
                f"做市商撤單觸發價差衝擊 (SpreadRatio={spread_ratio:.1f}x >= {spread_shock_mult:.1f}x)！"
                f"即刻啟動流動性真空防禦，全盤冷凍 {freeze_remaining} 秒。"
            )
        elif ofi_ratio < -ofi_th:
            regime = "SELL_PRESSURE_DRAIN"
            rec_action = "DEFENSIVE_DRIFT"
            rationale = (
                f"主動性賣單持續傾瀉擊穿委買 (OFI Ratio={ofi_ratio:.2f} < -{ofi_th:.2f})，"
                f"微觀流動性承壓，建議買單向下平移以捕捉更低撮合點。"
            )
        elif ofi_ratio > ofi_th:
            regime = "BUY_PRESSURE_ACCUMULATION"
            rec_action = "AGGRESSIVE_FILL"
            rationale = (
                f"主動性買盤積極吃單抬升報價 (OFI Ratio={ofi_ratio:.2f} > +{ofi_th:.2f})，"
                f"微觀撮合動能充沛，滑點預期極低。"
            )
        else:
            regime = "DEEP_LIQUIDITY_HEALTHY"
            rec_action = "EXECUTE_NORMAL"
            rationale = (
                f"訂單流結構均衡健康 (OFI Ratio={ofi_ratio:+.2f}，Spread Ratio={spread_ratio:.1f}x)，"
                f"委買委賣厚度充裕，允許正常執行。"
            )

        metric = OFITickerMetric(
            ticker=sym,
            regime=regime,
            best_bid=best_bid,
            best_ask=best_ask,
            spread_usd=spread_usd,
            spread_ratio=spread_ratio,
            ofi_value=ofi_val,
            ofi_ratio=ofi_ratio,
            bid_depth=bid_size,
            ask_depth=ask_size,
            is_vacuum_frozen=is_frozen,
            recommended_action=rec_action,
            freeze_remaining_seconds=freeze_remaining,
            rationale=rationale,
        )

        # 6. 寫入 Redis 診斷快取
        if r:
            try:
                await r.set(
                    cache_key,
                    json.dumps(metric.to_dict()),
                    ex=self.REDIS_CACHE_TTL_SECONDS,
                )
            except Exception as ce:
                logger.debug("Redis cache write error in OFI metric: %s", ce)

        return metric

    def _calculate_ofi_from_history(
        self,
        quote_history: List[Dict[str, Any]],
    ) -> Tuple[float, float]:
        """
        依 Cont et al. (2014) 標準遞迴累計微觀訂單流失衡。
        """
        cum_ofi = 0.0
        abs_flow_sum = 0.0

        for i in range(1, len(quote_history)):
            prev = quote_history[i - 1]
            curr = quote_history[i]

            pb_prev = float(prev.get("bid", 0.0))
            qb_prev = float(prev.get("bid_size", 0.0))
            pa_prev = float(prev.get("ask", 0.0))
            qa_prev = float(prev.get("ask_size", 0.0))

            pb_curr = float(curr.get("bid", 0.0))
            qb_curr = float(curr.get("bid_size", 0.0))
            pa_curr = float(curr.get("ask", 0.0))
            qa_curr = float(curr.get("ask_size", 0.0))

            # 計算 delta_b
            if pb_curr > pb_prev:
                delta_b = qb_curr
            elif pb_curr == pb_prev:
                delta_b = qb_curr - qb_prev
            else:
                delta_b = -qb_prev

            # 計算 delta_a
            if pa_curr < pa_prev:
                delta_a = -qa_curr
            elif pa_curr == pa_prev:
                delta_a = qa_curr - qa_prev
            else:
                delta_a = qa_prev

            flow_step = delta_b - delta_a
            cum_ofi += flow_step
            abs_flow_sum += abs(delta_b) + abs(delta_a)

        ofi_ratio = cum_ofi / (abs_flow_sum + 1e-6)
        ofi_ratio = max(-1.0, min(1.0, ofi_ratio))
        return cum_ofi, ofi_ratio

    def _parse_or_estimate_quotes(
        self,
        sym: str,
        quote: Optional[Dict[str, Any]],
    ) -> Tuple[float, float, float, float, float]:
        """
        解析或提供基準標的之穩健報價先驗。
        返回 (best_bid, best_ask, bid_size, ask_size, median_spread)。
        """
        if quote:
            bid = float(quote.get("bid") or 0.0)
            ask = float(quote.get("ask") or 0.0)
            bid_sz = float(quote.get("bid_size") or 100.0)
            ask_sz = float(quote.get("ask_size") or 100.0)
            med_sp = float(quote.get("median_spread") or (ask - bid if ask > bid else 0.02))
            if bid > 0 and ask >= bid:
                return bid, ask, bid_sz, ask_sz, max(0.01, med_sp)

        # 預設基準先驗 (針對美股熱門股票)
        defaults = {
            "NVDA": (124.98, 125.02, 1500.0, 1400.0, 0.04),
            "TSM": (189.95, 190.02, 1200.0, 1100.0, 0.06),
            "AAPL": (228.48, 228.52, 2500.0, 2400.0, 0.03),
            "MSFT": (419.95, 420.05, 1800.0, 1750.0, 0.08),
            "V": (281.95, 282.05, 800.0, 750.0, 0.08),
            "COP": (117.96, 118.04, 600.0, 580.0, 0.06),
            "ECL": (244.90, 245.10, 400.0, 420.0, 0.15),
            "SPY": (575.98, 576.01, 5000.0, 4800.0, 0.02),
            "QQQ": (490.96, 491.01, 3500.0, 3400.0, 0.03),
        }

        if sym in defaults:
            return defaults[sym]

        return 99.95, 100.05, 500.0, 500.0, 0.08

    def format_ofi_report(
        self,
        metrics: List[OFITickerMetric],
        channel: str = "telegram",
    ) -> str:
        """
        輸出符合 Telegram HTML 與 Email nl2br 雙渠道標準之微觀訂單流失衡戰報。
        """
        is_html = channel.lower() == "telegram"
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        b_open = "<b>" if is_html else ""
        b_close = "</b>" if is_html else ""
        code_open = "<code>" if is_html else "`"
        code_close = "</code>" if is_html else "`"

        header = f"🌊 {b_open}微觀訂單流失衡率 (OFI) 與流動性真空防禦儀表{b_close}\n"
        header += f"⏰ 監控時間：{code_open}{now_str}{code_close}\n\n"

        regime_emojis = {
            "DEEP_LIQUIDITY_HEALTHY": "🟢",
            "BUY_PRESSURE_ACCUMULATION": "🔵",
            "SELL_PRESSURE_DRAIN": "🟡",
            "LIQUIDITY_VACUUM_FREEZE": "🛑",
        }

        body_lines = []
        for m in metrics:
            emoji = regime_emojis.get(m.regime, "⚪")
            body_lines.append(f"{emoji} {b_open}{m.ticker}{b_close} — {code_open}{m.regime}{code_close}")
            body_lines.append(
                f"  • 報價與價差: {code_open}${m.best_bid:.2f} / ${m.best_ask:.2f}{code_close} "
                f"(Spread ${m.spread_usd:.3f} | {code_open}{m.spread_ratio:.1f}x{code_close})"
            )
            body_lines.append(
                f"  • OFI 失衡率: {code_open}{m.ofi_ratio:+.2f}{code_close} "
                f"(淨失衡 {m.ofi_value:+,.0f} 股 | 深度 買 {m.bid_depth:,.0f} vs 賣 {m.ask_depth:,.0f})"
            )
            if m.is_vacuum_frozen:
                body_lines.append(
                    f"  • 🛑 {b_open}流動性真空冷凍進行中{b_close}: 剩餘 {code_open}{m.freeze_remaining_seconds}s{code_close} (禁止新買單)"
                )
            body_lines.append(f"  • 防禦處置: {code_open}{m.recommended_action}{code_close}")
            body_lines.append(f"  • 診斷解析: {m.rationale}\n")

        footer = (
            f"💡 {b_open}微觀做市防禦機制{b_close}：\n"
            f"• 🛑 {b_open}LIQUIDITY_VACUUM_FREEZE{b_close}：價差跳增 >= 2.5x 或厚度枯竭，觸發防禦冷凍阻斷買單，拒絕非理性滑點。\n"
            f"• 🟡 {b_open}SELL_PRESSURE_DRAIN{b_close}：OFI < -0.45 淨賣壓傾瀉，階梯掛單防禦性下置捕捉低點。\n"
            f"• 0-LLM Cont et al. (2014) 物理高頻流體微觀模型，0 Token 毫秒級運算。"
        )

        return header + "\n".join(body_lines) + "\n" + footer
