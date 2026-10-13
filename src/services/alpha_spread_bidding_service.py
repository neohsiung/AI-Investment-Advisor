"""
Alpha Spread Bidding & Friction Offset Service
=============================================
開盤建倉前動態利差競標與自適應摩擦抵消引擎 (Phase 57)

核心架構：
1. 物理摩擦精算 (Estimated Total Friction, in bps)：
   - 買賣價差半幅 (Half-Spread bps = (Ask - Bid) / (2 * Mid) * 10,000)
   - 訂單流毒性與滑點懲罰 (VPIN Toxicity & Realized Slippage EWMA Multiplier)
2. 預期毛超額精算 (Expected Gross Alpha, in bps)：
   - 綜合多因子確信度 (Multi-Factor Conviction)
   - 跨板塊多角化溢價 (Diversification Alpha Premium, +12.0 bps)
3. 淨利差競標指標 (Net Alpha Spread, in bps)：
   - Net Alpha Spread = Gross Alpha - Total Friction
4. 動態配額競標決策 (Bidding Allocation & Friction Offset)：
   - 若 Net Alpha Spread >= 1.5x Hurdle (>= 22.5 bps)：AGGRESSIVE_EXPAND，跨板塊配額自動上浮至 45.0%
   - 若 Net Alpha Spread >= 1.0x Hurdle (>= 15.0 bps)：EXPAND，配額上浮至 40.0%
   - 若 5.0 bps <= Net Alpha Spread < Hurdle：NEUTRAL_PROCEED，維持標準 35.0%
   - 若 0.0 bps <= Net Alpha Spread < 5.0 bps：DEFENSIVE_CONTRACT，縮減至 25.0%
   - 若 Net Alpha Spread < 0.0 bps：FRICTION_BLOCKED，降至保底 20.0%
5. 嚴格 0-LLM 數理優先，輸出符合 Telegram HTML + Email nl2br 雙渠道格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("AlphaSpreadBiddingService")


@dataclass
class BiddingCandidateMetric:
    """單一標的之利差競標與摩擦指標"""
    ticker: str
    current_price: float
    confidence_score: float
    gross_alpha_bps: float
    half_spread_bps: float
    toxicity_bps: float
    total_friction_bps: float
    net_alpha_spread_bps: float
    is_cross_sector_injected: bool = False
    injected_sector: Optional[str] = None
    bidding_status: str = "NEUTRAL_PROCEED"  # AGGRESSIVE_EXPAND, EXPAND, NEUTRAL_PROCEED, DEFENSIVE_CONTRACT, FRICTION_BLOCKED
    allocated_quota_pct: float = 0.35
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "current_price": round(self.current_price, 2),
            "confidence_score": round(self.confidence_score, 2),
            "gross_alpha_bps": round(self.gross_alpha_bps, 2),
            "half_spread_bps": round(self.half_spread_bps, 2),
            "toxicity_bps": round(self.toxicity_bps, 2),
            "total_friction_bps": round(self.total_friction_bps, 2),
            "net_alpha_spread_bps": round(self.net_alpha_spread_bps, 2),
            "is_cross_sector_injected": self.is_cross_sector_injected,
            "injected_sector": self.injected_sector,
            "bidding_status": self.bidding_status,
            "allocated_quota_pct": round(self.allocated_quota_pct, 4),
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BiddingCandidateMetric:
        return cls(
            ticker=str(data.get("ticker", "")),
            current_price=float(data.get("current_price", 0.0) or 0.0),
            confidence_score=float(data.get("confidence_score", 6.5) or 6.5),
            gross_alpha_bps=float(data.get("gross_alpha_bps", 0.0) or 0.0),
            half_spread_bps=float(data.get("half_spread_bps", 0.0) or 0.0),
            toxicity_bps=float(data.get("toxicity_bps", 0.0) or 0.0),
            total_friction_bps=float(data.get("total_friction_bps", 0.0) or 0.0),
            net_alpha_spread_bps=float(data.get("net_alpha_spread_bps", 0.0) or 0.0),
            is_cross_sector_injected=bool(data.get("is_cross_sector_injected", False)),
            injected_sector=data.get("injected_sector"),
            bidding_status=str(data.get("bidding_status", "NEUTRAL_PROCEED")),
            allocated_quota_pct=float(data.get("allocated_quota_pct", 0.35) or 0.35),
            rationale=str(data.get("rationale", "")),
        )


@dataclass
class BiddingAssessmentResult:
    """全批次建倉動態利差競標評估成果"""
    hurdle_bps: float
    base_quota_pct: float
    cross_sector_adjusted_quota_pct: float
    bidding_status: str
    candidates: Dict[str, BiddingCandidateMetric]
    average_friction_bps: float
    portfolio_net_spread_bps: float
    injected_ticker: Optional[str] = None
    injected_sector: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hurdle_bps": round(self.hurdle_bps, 2),
            "base_quota_pct": round(self.base_quota_pct, 4),
            "cross_sector_adjusted_quota_pct": round(self.cross_sector_adjusted_quota_pct, 4),
            "bidding_status": self.bidding_status,
            "average_friction_bps": round(self.average_friction_bps, 2),
            "portfolio_net_spread_bps": round(self.portfolio_net_spread_bps, 2),
            "injected_ticker": self.injected_ticker,
            "injected_sector": self.injected_sector,
            "created_at": self.created_at,
            "candidates": {k: v.to_dict() for k, v in self.candidates.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BiddingAssessmentResult:
        cand_map = {}
        for k, v in data.get("candidates", {}).items():
            if isinstance(v, dict):
                cand_map[k] = BiddingCandidateMetric.from_dict(v)
            elif isinstance(v, BiddingCandidateMetric):
                cand_map[k] = v
        return cls(
            hurdle_bps=float(data.get("hurdle_bps", 15.0) or 15.0),
            base_quota_pct=float(data.get("base_quota_pct", 0.35) or 0.35),
            cross_sector_adjusted_quota_pct=float(data.get("cross_sector_adjusted_quota_pct", 0.35) or 0.35),
            bidding_status=str(data.get("bidding_status", "NEUTRAL_PROCEED")),
            candidates=cand_map,
            average_friction_bps=float(data.get("average_friction_bps", 0.0) or 0.0),
            portfolio_net_spread_bps=float(data.get("portfolio_net_spread_bps", 0.0) or 0.0),
            injected_ticker=data.get("injected_ticker"),
            injected_sector=data.get("injected_sector"),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


class AlphaSpreadBiddingService:
    """開盤建倉前動態利差競標與自適應摩擦抵消服務"""

    DEFAULT_HURDLE_BPS = 15.0               # 基準利差門檻 15 bps (0.15%)
    DEFAULT_BASE_QUOTA_PCT = 0.35           # 跨板塊基準配額 35%
    DEFAULT_MAX_QUOTA_PCT = 0.45            # 跨板塊激進上浮配額 45%
    DEFAULT_MIN_QUOTA_PCT = 0.20            # 跨板塊保底防守配額 20%
    DIVERSIFICATION_PREMIUM_BPS = 12.0      # 跨板塊分散 HHI 多角化溢價 +12 bps

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
        slippage_guard: Optional[Any] = None,
        vpin_guard: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        self.market_data_service = market_data_service
        self.slippage_guard = slippage_guard
        self.vpin_guard = vpin_guard

    def _get_setting(self, key: str, default: Any) -> Any:
        try:
            return self.settings_service.get_setting(key, default)
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("enable_alpha_spread_bidding", True))

    @property
    def hurdle_bps(self) -> float:
        return float(self._get_setting("alpha_bidding_hurdle_bps", self.DEFAULT_HURDLE_BPS))

    @property
    def max_quota_pct(self) -> float:
        return float(self._get_setting("cross_sector_max_bidding_quota_pct", self.DEFAULT_MAX_QUOTA_PCT))

    @property
    def min_quota_pct(self) -> float:
        return float(self._get_setting("cross_sector_min_bidding_quota_pct", self.DEFAULT_MIN_QUOTA_PCT))

    @property
    def diversification_premium_bps(self) -> float:
        return float(self._get_setting("alpha_bidding_diversification_premium_bps", self.DIVERSIFICATION_PREMIUM_BPS))

    async def _get_market_data_service(self) -> Any:
        if self.market_data_service:
            return self.market_data_service
        try:
            from src.services.market_data_service import MarketDataService
            self.market_data_service = MarketDataService(user_id=self.user_id)
            return self.market_data_service
        except Exception as me:
            logger.debug("Could not resolve MarketDataService: %s", me)
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 單一標的物理摩擦精算 (Estimated Total Friction)
    # ═══════════════════════════════════════════════════════════════════════

    async def calculate_candidate_friction(
        self,
        ticker: str,
        current_price: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        """
        計算標的物理交易摩擦 (bps)：
        1. Half-Spread bps：買賣價差半幅 (若缺失則依大盤權值預設 3.5 bps)。
        2. Toxicity & Slippage bps：訂單流微觀毒性與實現滑點 EWMA 補償。
        3. Total Friction bps = Half-Spread + Toxicity Friction。
        回傳 (half_spread_bps, toxicity_bps, total_friction_bps)。
        """
        clean_ticker = (ticker or "").upper().strip()
        half_spread_bps = 3.5  # 預設大盤大型龍頭標的半價差
        toxicity_bps = 0.0

        mkt_svc = await self._get_market_data_service()
        if mkt_svc:
            try:
                quote = await mkt_svc.get_quote(clean_ticker)
                if quote:
                    bid = float(quote.get("bid", 0.0) or 0.0)
                    ask = float(quote.get("ask", 0.0) or 0.0)
                    mid = float(quote.get("mid", 0.0) or quote.get("last", 0.0) or 0.0)
                    if bid > 0 and ask > 0 and mid > 0 and ask >= bid:
                        # Half spread in bps
                        half_spread_bps = max(0.5, ((ask - bid) / (2.0 * mid)) * 10000.0)
                    elif quote.get("spread_pct") is not None:
                        sp_pct = float(quote["spread_pct"])
                        if sp_pct > 0:
                            half_spread_bps = max(0.5, (sp_pct / 2.0) * 10000.0)
            except Exception as qe:
                logger.debug("Friction quote check fallback for %s: %s", clean_ticker, qe)

        # 檢驗滑點補償器 (AdaptiveExecutionSlippageCompensator)
        try:
            if self.slippage_guard and hasattr(self.slippage_guard, "compensator") and self.slippage_guard.compensator:
                c_metrics = self.slippage_guard.compensator.get_metrics(clean_ticker)
                if c_metrics:
                    # 每 1.0x 補償乘數增加 5 bps 摩擦
                    if c_metrics.slippage_multiplier > 1.0:
                        toxicity_bps += (c_metrics.slippage_multiplier - 1.0) * 8.0
                    if c_metrics.adverse_selection_count > 0:
                        toxicity_bps += min(15.0, c_metrics.adverse_selection_count * 3.0)
        except Exception as se:
            logger.debug("Slippage compensator lookup error for %s: %s", clean_ticker, se)

        # 檢驗 VPIN 訂單流毒性守衛
        try:
            if self.vpin_guard and hasattr(self.vpin_guard, "evaluate_ticker"):
                v_eval = await self.vpin_guard.evaluate_ticker(clean_ticker)
                if v_eval and hasattr(v_eval, "vpin"):
                    v_val = float(v_eval.vpin or 0.0)
                    if v_val > 0.20:
                        # 超過 0.20 正常水準，每 0.10 VPIN 增加 5 bps 摩擦
                        toxicity_bps += (v_val - 0.20) * 50.0
        except Exception as ve:
            logger.debug("VPIN guard lookup error for %s: %s", clean_ticker, ve)

        total_friction_bps = round(half_spread_bps + toxicity_bps, 2)
        return (round(half_spread_bps, 2), round(toxicity_bps, 2), total_friction_bps)

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 標的預期毛超額精算 (Expected Gross Alpha)
    # ═══════════════════════════════════════════════════════════════════════

    def calculate_candidate_gross_alpha(
        self,
        ticker: str,
        confidence_score: float = 6.5,
        is_cross_sector_injected: bool = False,
    ) -> float:
        """
        精算標的預期毛超額 (bps)：
        1. 信心分數 (0~10 分)：以基準 5.0 分為中心，每高出 1 分帶來約 +5.0 bps 預期超額。
        2. 若為跨板塊注入標的 (is_cross_sector_injected=True)：
           額外享有分散 HHI 與降低未涵蓋板塊波動之多角化溢價 (+12.0 bps)。
        """
        conf = max(1.0, min(10.0, float(confidence_score or 6.0)))
        # 基準 Alpha: 5.0 分為 15 bps, 7.0 分為 25 bps, 9.0 分為 35 bps
        base_alpha_bps = 15.0 + (conf - 5.0) * 5.0

        if is_cross_sector_injected:
            base_alpha_bps += self.diversification_premium_bps

        return round(max(5.0, base_alpha_bps), 2)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. 全批次動態利差競標與自適應配額評估
    # ═══════════════════════════════════════════════════════════════════════

    async def evaluate_bidding_for_batch(
        self,
        batch_items: List[Dict[str, Any]],
        contender: Optional[Dict[str, Any]] = None,
        base_quota_pct: Optional[float] = None,
    ) -> BiddingAssessmentResult:
        """
        評估批次清單中各候選標的之利差與摩擦，並對跨板塊注入標的進行自適應競標定價：
        - 決定 contender 的調整配額 (adjusted_quota_pct)，支援自適應上浮至 45% 或下調至 20%。
        - 輸出詳細的 BiddingAssessmentResult 供建倉服務調度。
        """
        base_quota = float(base_quota_pct or self.DEFAULT_BASE_QUOTA_PCT)
        hurdle = self.hurdle_bps
        candidates: Dict[str, BiddingCandidateMetric] = {}

        # 1. 評估現有批次標的
        for it in batch_items:
            sym = it.get("ticker", "")
            if not sym:
                continue
            conf = float(it.get("confidence", 6.5) or 6.5)
            p = float(it.get("current_price", 100.0) or 100.0)
            is_inj = bool(it.get("is_cross_sector_injected", False))
            inj_sec = it.get("injected_sector")

            half_sp, tox, friction = await self.calculate_candidate_friction(sym, p)
            gross_alpha = self.calculate_candidate_gross_alpha(sym, conf, is_inj)
            net_spread = round(gross_alpha - friction, 2)

            candidates[sym] = BiddingCandidateMetric(
                ticker=sym,
                current_price=p,
                confidence_score=conf,
                gross_alpha_bps=gross_alpha,
                half_spread_bps=half_sp,
                toxicity_bps=tox,
                total_friction_bps=friction,
                net_alpha_spread_bps=net_spread,
                is_cross_sector_injected=is_inj,
                injected_sector=inj_sec,
                allocated_quota_pct=0.0,
                rationale=f"常規候選: 毛 Alpha {gross_alpha:+.1f} bps, 摩擦 {friction:.1f} bps, 淨利差 {net_spread:+.1f} bps",
            )

        # 2. 若有跨板塊 Contender，進行重點利差競標精算
        adjusted_quota = base_quota
        bidding_status = "NEUTRAL_PROCEED"
        injected_sym = None
        injected_sec = None

        if contender:
            c_sym = contender.get("ticker", "")
            c_sec = contender.get("sector")
            c_conf = float(contender.get("confidence", 6.8) or 6.8)
            c_price = float(contender.get("current_price", 100.0) or 100.0)

            c_half, c_tox, c_friction = await self.calculate_candidate_friction(c_sym, c_price)
            c_gross = self.calculate_candidate_gross_alpha(c_sym, c_conf, is_cross_sector_injected=True)
            c_net = round(c_gross - c_friction, 2)

            # 動態配額競標階梯判斷
            if c_net >= hurdle * 1.5:  # >= 22.5 bps
                # 利差極佳且流動性充裕，最大化分散 HHI 權重至 45%
                adjusted_quota = self.max_quota_pct
                bidding_status = "AGGRESSIVE_EXPAND"
                c_rationale = (
                    f"強勁淨利差 ({c_net:+.1f} bps >= 1.5x Hurdle)，摩擦低 ({c_friction:.1f} bps)；"
                    f"激進上浮注入配額至 {adjusted_quota:.1%} 加速持倉分散"
                )
            elif c_net >= hurdle:      # >= 15.0 bps
                adjusted_quota = round(min(self.max_quota_pct, base_quota + 0.05), 4)  # 40%
                bidding_status = "EXPAND"
                c_rationale = (
                    f"淨利差覆蓋門檻 ({c_net:+.1f} bps >= Hurdle {hurdle:.1f} bps)；"
                    f"上浮注入配額至 {adjusted_quota:.1%}"
                )
            elif c_net >= 5.0:         # 5.0 ~ 14.9 bps
                adjusted_quota = base_quota  # 35%
                bidding_status = "NEUTRAL_PROCEED"
                c_rationale = (
                    f"淨利差中等 ({c_net:+.1f} bps)；維持標準注入配額 {adjusted_quota:.1%}"
                )
            elif c_net >= 0.0:         # 0.0 ~ 4.9 bps
                adjusted_quota = round(max(self.min_quota_pct, base_quota - 0.10), 4)  # 25%
                bidding_status = "DEFENSIVE_CONTRACT"
                c_rationale = (
                    f"淨利差微弱 ({c_net:+.1f} bps < 5 bps)；防守性縮減配額至 {adjusted_quota:.1%} 降低摩擦磨損"
                )
            else:                      # < 0.0 bps
                adjusted_quota = self.min_quota_pct  # 20%
                bidding_status = "FRICTION_BLOCKED"
                c_rationale = (
                    f"摩擦成本 ({c_friction:.1f} bps) 超過毛 Alpha ({c_gross:+.1f} bps)；"
                    f"降至保底配額 {adjusted_quota:.1%}"
                )

            injected_sym = c_sym
            injected_sec = c_sec
            candidates[c_sym] = BiddingCandidateMetric(
                ticker=c_sym,
                current_price=c_price,
                confidence_score=c_conf,
                gross_alpha_bps=c_gross,
                half_spread_bps=c_half,
                toxicity_bps=c_tox,
                total_friction_bps=c_friction,
                net_alpha_spread_bps=c_net,
                is_cross_sector_injected=True,
                injected_sector=c_sec,
                bidding_status=bidding_status,
                allocated_quota_pct=adjusted_quota,
                rationale=c_rationale,
            )

        avg_friction = (
            sum(m.total_friction_bps for m in candidates.values()) / len(candidates)
            if candidates else 0.0
        )
        portfolio_net = (
            sum(m.net_alpha_spread_bps for m in candidates.values()) / len(candidates)
            if candidates else 0.0
        )

        return BiddingAssessmentResult(
            hurdle_bps=hurdle,
            base_quota_pct=base_quota,
            cross_sector_adjusted_quota_pct=adjusted_quota,
            bidding_status=bidding_status,
            candidates=candidates,
            average_friction_bps=round(avg_friction, 2),
            portfolio_net_spread_bps=round(portfolio_net, 2),
            injected_ticker=injected_sym,
            injected_sector=injected_sec,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 4. 0-LLM 快速診斷戰報生成 (/spread 指令)
    # ═══════════════════════════════════════════════════════════════════════

    def format_spread_bidding_report(
        self,
        assessment: BiddingAssessmentResult,
        channel: str = "telegram",
    ) -> str:
        """
        產出符合 Telegram HTML 與 Email nl2br 雙渠道標準之利差競標診斷戰報。
        """
        status = assessment.bidding_status
        if status in ("AGGRESSIVE_EXPAND", "EXPAND"):
            badge = "🟢 <b>利差充裕 (ALPHA_SURPLUS)</b>"
        elif status == "NEUTRAL_PROCEED":
            badge = "🟡 <b>利差中性 (MODERATE_SPREAD)</b>"
        else:
            badge = "🔴 <b>摩擦偏高 (HIGH_FRICTION_DRAG)</b>"

        lines = [
            f"🎯 <b>【開盤建倉前動態利差競標與摩擦抵消儀表】</b>",
            f"• <b>當前利差狀態</b>：{badge}",
            f"• <b>基準利差門檻</b>：<code>{assessment.hurdle_bps:.1f} bps</code> (0.15%)",
            f"• <b>平均交易摩擦</b>：<code>{assessment.average_friction_bps:.1f} bps</code>",
            f"• <b>投組平均淨利差</b>：<code>{assessment.portfolio_net_spread_bps:+.1f} bps</code>\n",
            "<b>【候選標的利差與摩擦明細】</b>",
            "━━━━━━━━━━━━━━━━━━",
        ]

        for sym, m in assessment.candidates.items():
            inj_tag = f" <i>[跨板塊: {m.injected_sector}]</i>" if m.is_cross_sector_injected else ""
            status_icon = "🟢" if m.net_alpha_spread_bps >= assessment.hurdle_bps else ("🟡" if m.net_alpha_spread_bps >= 0 else "🔴")

            lines.append(f"{status_icon} <b>{sym}</b>{inj_tag}：")
            lines.append(f"  • 預期毛 Alpha：<code>{m.gross_alpha_bps:+.1f} bps</code> | 信心：<code>{m.confidence_score:.1f}</code>")
            lines.append(f"  • 預估總摩擦：<code>{m.total_friction_bps:.1f} bps</code> (半價差: {m.half_spread_bps:.1f} + 毒性: {m.toxicity_bps:.1f})")
            lines.append(f"  • <b>淨確信利差</b>：<code><b>{m.net_alpha_spread_bps:+.1f} bps</b></code>")
            if m.is_cross_sector_injected:
                lines.append(f"  • <b>競標配額決策</b>：<code><b>{m.allocated_quota_pct * 100:.1f}%</b></code> ({m.bidding_status})")
                lines.append(f"  • <i>評定說明</i>：{m.rationale}")
            lines.append("──────────────────")

        if assessment.injected_ticker:
            lines.append(
                f"\n💡 <b>自適應競標結論</b>：跨板塊龍頭 <code>{assessment.injected_ticker}</code> "
                f"淨利差為 <code>{assessment.candidates[assessment.injected_ticker].net_alpha_spread_bps:+.1f} bps</code>，"
                f"配額調整為 <b>{assessment.cross_sector_adjusted_quota_pct * 100:.1f}%</b> "
                f"(基準: {assessment.base_quota_pct * 100:.1f}%)。"
            )

        lines.append("\n💡 <b>快捷指令</b>：輸入 <code>/batch</code> 檢視建倉計畫，輸入 <code>/sector</code> 檢視板塊 HHI，輸入 <code>/dipbuy plan</code> 檢視階梯限價。")

        return "\n".join(lines)
