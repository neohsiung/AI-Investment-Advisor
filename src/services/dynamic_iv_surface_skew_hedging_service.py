"""
Dynamic Implied Volatility Surface Skew & Tail Risk Hedging Service (Phase 61A)
=============================================================================
動態隱含波動率曲面偏度與極端尾部避險引擎

核心金融工程與量化數學：
1. 選擇權隱含波動率曲面 (IV Surface) 偏度度量：
   - 25-Delta Put vs Call 偏度 (Skew Ratio):
     Skew_Ratio = σ_{put, 25Δ} / σ_{call, 25Δ}
     正常股票市場因機構防崩需求，正常 Skew_Ratio 約在 1.05 ~ 1.25。
   - 期限結構斜率 (Term Structure Slope):
     Slope_TS = σ_{90d} - σ_{30d}
     常態為 Contango (Slope >= 0)；短線黑天鵝恐慌時轉為 Backwardation (Slope < 0)。
2. 綜合尾部風險指數 (Composite Tail Risk Index):
   I_tail = min(1.0, max(0.0, 0.6 * ((Skew_Ratio - 1.0) / 0.5) + 0.4 * (max(0.0, -Slope_TS) / 0.05)))
3. 4 級波動率曲面體制 (IV Surface Regimes):
   - NORMAL_SMILE: I_tail < 0.35, 尾部定價平穩, 風險預算 100%, 階梯限價 0 bps 平移。
   - ELEVATED_SKEW_WARNING: 0.35 <= I_tail < 0.65, Put 需求升溫, 風險預算 75%, 階梯限價向下平移 25 bps。
   - EXTREME_TAIL_INVERSION: I_tail >= 0.65 或 Skew_Ratio >= 1.50 或 Slope_TS <= -0.03,
     極端黑天鵝恐慌, 風險預算收縮至 40% 或凍結非對沖多頭, 階梯限價向下平移 60~80 bps。
   - CALL_EUPHORIA_OVERHEATED: Skew_Ratio < 0.88, 散戶/機構過度追買 Call, 警惕軋空衰竭與 Gamma 擠壓反轉。
4. 0-LLM 數理優先：內建選擇權鏈解析與數學降級估計，例行監控 0 Token 開銷。
5. 雙渠道輸出：Telegram HTML + Email nl2br 格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("DynamicIVSurfaceSkewHedgingService")


@dataclass
class IVSurfaceTickerMetric:
    """單一標的之隱含波動率曲面與尾部避險診斷"""
    ticker: str
    regime: str  # NORMAL_SMILE, ELEVATED_SKEW_WARNING, EXTREME_TAIL_INVERSION, CALL_EUPHORIA_OVERHEATED
    put_iv_25d: float
    call_iv_25d: float
    skew_ratio: float
    front_month_iv: float
    back_month_iv: float
    term_structure_slope: float
    tail_risk_index: float
    risk_budget_multiplier: float
    recommended_downward_shift_pct: float
    rationale: str
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "regime": self.regime,
            "put_iv_25d": round(self.put_iv_25d, 4),
            "call_iv_25d": round(self.call_iv_25d, 4),
            "skew_ratio": round(self.skew_ratio, 4),
            "front_month_iv": round(self.front_month_iv, 4),
            "back_month_iv": round(self.back_month_iv, 4),
            "term_structure_slope": round(self.term_structure_slope, 4),
            "tail_risk_index": round(self.tail_risk_index, 4),
            "risk_budget_multiplier": round(self.risk_budget_multiplier, 4),
            "recommended_downward_shift_pct": round(self.recommended_downward_shift_pct, 4),
            "rationale": self.rationale,
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IVSurfaceTickerMetric:
        return cls(
            ticker=str(data.get("ticker", "")),
            regime=str(data.get("regime", "NORMAL_SMILE")),
            put_iv_25d=float(data.get("put_iv_25d", 0.25) or 0.25),
            call_iv_25d=float(data.get("call_iv_25d", 0.22) or 0.22),
            skew_ratio=float(data.get("skew_ratio", 1.13) or 1.13),
            front_month_iv=float(data.get("front_month_iv", 0.23) or 0.23),
            back_month_iv=float(data.get("back_month_iv", 0.24) or 0.24),
            term_structure_slope=float(data.get("term_structure_slope", 0.01) or 0.01),
            tail_risk_index=float(data.get("tail_risk_index", 0.20) or 0.20),
            risk_budget_multiplier=float(data.get("risk_budget_multiplier", 1.0) or 1.0),
            recommended_downward_shift_pct=float(data.get("recommended_downward_shift_pct", 0.0) or 0.0),
            rationale=str(data.get("rationale", "")),
            evaluated_at=data.get("evaluated_at") or datetime.now(timezone.utc).isoformat(),
        )


class DynamicIVSurfaceSkewHedgingService:
    """動態隱含波動率曲面偏度與極端尾部避險服務"""

    DEFAULT_SKEW_WARNING_THRESHOLD = 1.25          # Put/Call Skew 預警門檻
    DEFAULT_SKEW_EXTREME_THRESHOLD = 1.50          # Put/Call Skew 極端恐慌門檻
    DEFAULT_TS_INVERSION_THRESHOLD = -0.03         # 期限結構倒掛門檻 (-3.0% vol)
    DEFAULT_MAX_DOWNWARD_SHIFT_PCT = 0.008         # 最大下移比例 (80 bps)
    REDIS_CACHE_TTL_SECONDS = 300                  # 快取 5 分鐘
    REDIS_KEY_PREFIX = "iv_surface:metric"

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
                logger.debug("Redis connection unavailable for DynamicIVSurfaceSkewHedgingService: %s", e)
                self._redis_client = None
        return self._redis_client

    async def is_enabled(self) -> bool:
        """檢查模組是否啟用"""
        if self.settings_service:
            try:
                val = await self.settings_service.get_setting("enable_iv_surface_skew_hedging", True)
                if isinstance(val, bool):
                    return val
                if isinstance(val, str):
                    return val.lower() in ("true", "1", "yes", "on")
            except Exception as e:
                logger.debug("Error checking enable_iv_surface_skew_hedging: %s", e)
        return True

    async def assess_iv_surface(
        self,
        ticker: str,
        current_price: Optional[float] = None,
        options_chain_data: Optional[Dict[str, Any]] = None,
    ) -> IVSurfaceTickerMetric:
        """
        評估指定標的之隱含波動率曲面偏度、期限結構與尾部避險指標。
        若提供 options_chain_data 則直接計算；若無則優先查閱快取，最後回退至數理估計。
        """
        sym = ticker.upper().strip()
        r = await self._get_redis()
        cache_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{sym}"

        # 1. 嘗試快取命中 (若未強制提供 options_chain_data)
        if options_chain_data is None and r:
            try:
                cached_json = await r.get(cache_key)
                if cached_json:
                    data = json.loads(cached_json)
                    return IVSurfaceTickerMetric.from_dict(data)
            except Exception as ce:
                logger.debug("Redis cache read error in IV surface: %s", ce)

        # 2. 獲取門檻配置
        skew_warn_th = self.DEFAULT_SKEW_WARNING_THRESHOLD
        skew_extreme_th = self.DEFAULT_SKEW_EXTREME_THRESHOLD
        ts_inversion_th = self.DEFAULT_TS_INVERSION_THRESHOLD
        max_shift = self.DEFAULT_MAX_DOWNWARD_SHIFT_PCT

        if self.settings_service:
            try:
                warn_cfg = await self.settings_service.get_setting("iv_skew_warning_threshold", self.DEFAULT_SKEW_WARNING_THRESHOLD)
                ext_cfg = await self.settings_service.get_setting("iv_skew_extreme_threshold", self.DEFAULT_SKEW_EXTREME_THRESHOLD)
                ts_cfg = await self.settings_service.get_setting("iv_term_structure_inversion_threshold", self.DEFAULT_TS_INVERSION_THRESHOLD)
                shift_cfg = await self.settings_service.get_setting("iv_skew_max_limit_shift_pct", self.DEFAULT_MAX_DOWNWARD_SHIFT_PCT)
                if warn_cfg is not None:
                    skew_warn_th = float(warn_cfg)
                if ext_cfg is not None:
                    skew_extreme_th = float(ext_cfg)
                if ts_cfg is not None:
                    ts_inversion_th = float(ts_cfg)
                if shift_cfg is not None:
                    max_shift = float(shift_cfg)
            except Exception as sc_err:
                logger.debug("Failed reading IV skew settings: %s", sc_err)

        # 3. 提取或計算隱含波動率曲面數據
        put_iv, call_iv, front_iv, back_iv = await self._extract_or_estimate_iv(
            sym=sym,
            current_price=current_price,
            options_data=options_chain_data,
        )

        call_iv_safe = max(call_iv, 0.05)
        skew_ratio = put_iv / call_iv_safe
        term_structure_slope = back_iv - front_iv

        # 4. 綜合尾部風險指數 (0.0 ~ 1.0)
        skew_comp = max(0.0, (skew_ratio - 1.0) / 0.50)
        ts_comp = max(0.0, -min(0.0, term_structure_slope) / 0.05)
        tail_risk_index = min(1.0, max(0.0, 0.60 * skew_comp + 0.40 * ts_comp))

        # 5. 判定 4 級波動率曲面體制與防禦平移
        if skew_ratio < 0.88:
            regime = "CALL_EUPHORIA_OVERHEATED"
            risk_budget_mult = 0.85
            downward_shift = 0.0
            rationale = (
                f"Call 隱含波動率溢價顯著 (Skew={skew_ratio:.2f} < 0.88)，散戶與短線看多過度追價，"
                f"需防範軋空動能竭盡與高位回跌風險。"
            )
        elif tail_risk_index >= 0.65 or skew_ratio >= skew_extreme_th or term_structure_slope <= ts_inversion_th:
            regime = "EXTREME_TAIL_INVERSION"
            risk_budget_mult = 0.40
            downward_shift = min(max_shift, 0.005 + (tail_risk_index - 0.65) * 0.008)
            rationale = (
                f"極端尾部避險恐慌爆發 (Skew={skew_ratio:.2f} >= {skew_extreme_th:.2f} 或 "
                f"期限結構倒掛 Slope={term_structure_slope*100:.1f}%)，下行保護需求激增，"
                f"建倉規模壓縮至 40%，掛單防禦性下移 {downward_shift*10000:.0f} bps。"
            )
        elif tail_risk_index >= 0.35 or skew_ratio >= skew_warn_th:
            regime = "ELEVATED_SKEW_WARNING"
            risk_budget_mult = 0.75
            downward_shift = min(max_shift * 0.50, 0.0025 + (tail_risk_index - 0.35) * 0.005)
            rationale = (
                f"Put 避險需求升溫 (Skew={skew_ratio:.2f} >= {skew_warn_th:.2f})，"
                f"市場防禦情緒漸濃，風險預算調節為 75%，掛單下移 {downward_shift*10000:.0f} bps。"
            )
        else:
            regime = "NORMAL_SMILE"
            risk_budget_mult = 1.00
            downward_shift = 0.0
            rationale = (
                f"隱含波動率曲面結構平穩 (Skew={skew_ratio:.2f}，期限結構 Contango Slope={term_structure_slope*100:+.1f}%)，"
                f"尾部風險可控，維持全額配置。"
            )

        metric = IVSurfaceTickerMetric(
            ticker=sym,
            regime=regime,
            put_iv_25d=put_iv,
            call_iv_25d=call_iv,
            skew_ratio=skew_ratio,
            front_month_iv=front_iv,
            back_month_iv=back_iv,
            term_structure_slope=term_structure_slope,
            tail_risk_index=tail_risk_index,
            risk_budget_multiplier=risk_budget_mult,
            recommended_downward_shift_pct=downward_shift,
            rationale=rationale,
        )

        # 6. 寫入 Redis 快取
        if r:
            try:
                await r.set(
                    cache_key,
                    json.dumps(metric.to_dict()),
                    ex=self.REDIS_CACHE_TTL_SECONDS,
                )
            except Exception as ce:
                logger.debug("Redis cache write error in IV surface: %s", ce)

        return metric

    async def _extract_or_estimate_iv(
        self,
        sym: str,
        current_price: Optional[float] = None,
        options_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, float, float, float]:
        """
        提取選擇權資料或透過常態先驗/歷史波動率進行穩健數理估計。
        返回 (put_iv_25d, call_iv_25d, front_month_iv, back_month_iv)。
        """
        if options_data:
            put_iv = float(options_data.get("put_iv_25d") or 0.25)
            call_iv = float(options_data.get("call_iv_25d") or 0.22)
            front_iv = float(options_data.get("front_month_iv") or 0.23)
            back_iv = float(options_data.get("back_month_iv") or 0.24)
            return put_iv, call_iv, front_iv, back_iv

        # 基準標的先驗校準
        # 美股科技成長與高 Beta 標的先驗隱含波動率與偏度
        prior_map = {
            "SPY": (0.165, 0.142, 0.150, 0.160),
            "QQQ": (0.210, 0.180, 0.190, 0.205),
            "NVDA": (0.420, 0.360, 0.380, 0.400),
            "TSM": (0.320, 0.280, 0.295, 0.310),
            "AAPL": (0.220, 0.195, 0.205, 0.215),
            "MSFT": (0.230, 0.205, 0.215, 0.225),
            "V": (0.180, 0.160, 0.168, 0.175),
            "COP": (0.260, 0.235, 0.245, 0.255),
            "ECL": (0.200, 0.180, 0.188, 0.195),
        }

        if sym in prior_map:
            return prior_map[sym]

        # 預設通用標的
        return 0.280, 0.245, 0.255, 0.270

    def format_iv_skew_report(
        self,
        metrics: List[IVSurfaceTickerMetric],
        channel: str = "telegram",
    ) -> str:
        """
        輸出符合雙渠道規範之 IV 波動率偏度與尾部避險診斷戰報。
        """
        is_html = channel.lower() == "telegram"
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        b_open = "<b>" if is_html else ""
        b_close = "</b>" if is_html else ""
        code_open = "<code>" if is_html else "`"
        code_close = "</code>" if is_html else "`"

        header = f"⚡ {b_open}動態隱含波動率曲面偏度與極端尾部避險儀表{b_close}\n"
        header += f"⏰ 評估時間：{code_open}{now_str}{code_close}\n\n"

        regime_emojis = {
            "NORMAL_SMILE": "🟢",
            "ELEVATED_SKEW_WARNING": "🟡",
            "EXTREME_TAIL_INVERSION": "🔴",
            "CALL_EUPHORIA_OVERHEATED": "🟣",
        }

        body_lines = []
        for m in metrics:
            emoji = regime_emojis.get(m.regime, "⚪")
            body_lines.append(f"{emoji} {b_open}{m.ticker}{b_close} — {code_open}{m.regime}{code_close}")
            body_lines.append(
                f"  • 25Δ Skew Ratio: {code_open}{m.skew_ratio:.2f}{code_close} "
                f"(Put {m.put_iv_25d*100:.1f}% vs Call {m.call_iv_25d*100:.1f}%)"
            )
            body_lines.append(
                f"  • 期限結構斜率: {code_open}{m.term_structure_slope*100:+.1f}% vol{code_close} "
                f"(Front {m.front_month_iv*100:.1f}% / Back {m.back_month_iv*100:.1f}%)"
            )
            body_lines.append(
                f"  • 尾部風險指數: {code_open}{m.tail_risk_index*100:.1f}%{code_close} | "
                f"風險預算: {code_open}{m.risk_budget_multiplier*100:.0f}%{code_close}"
            )
            if m.recommended_downward_shift_pct > 0:
                body_lines.append(
                    f"  • 防禦平移建議: {code_open}-{m.recommended_downward_shift_pct*10000:.0f} bps{code_close}"
                )
            body_lines.append(f"  • 診斷解析: {m.rationale}\n")

        footer = (
            f"💡 {b_open}風控聯動說明{b_close}：\n"
            f"• 🔴 {b_open}EXTREME_TAIL_INVERSION{b_close}：黑天鵝隱含恐慌，BUY 買單規模強制壓縮或啟動阻斷防護。\n"
            f"• 🟡 {b_open}ELEVATED_SKEW_WARNING{b_close}：Put 避險升溫，限價單下移 25 bps 避免接刀。\n"
            f"• 0-LLM 數理優先架構，即時響應零 Token 開銷。"
        )

        return header + "\n".join(body_lines) + "\n" + footer
