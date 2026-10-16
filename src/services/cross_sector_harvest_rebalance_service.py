"""
Cross-Sector Harvest & Rebalance Profit Recirculation Service (Phase 59A)
========================================================================
跨板塊注入標的動態出清與再平衡利差回流引擎

核心架構：
1. 監控板塊集中度與 HHI 自癒狀態 (HHI <= 0.18 且科技股佔淨值比率 <= 28%)。
2. 評估持倉中跨板塊防守標的 (如 V, COP, ECL) 之未實現盈虧與波段超額收益率：
   - HARVEST_ELIGIBLE: HHI 自癒完成且獲利 >= 10% (或動能高位鈍化) -> 啟動 2-Tier 分批減碼 50% 鎖利，釋放資本。
   - RUNNER_PRESERVE: 獲利 > 15% 且動能持續強勁 -> 保留部分倉位掛載移動停利 (TSL)，追求極致盈虧比。
   - HOLDING_STABILIZING: HHI 仍高於門檻 (> 0.22) 或未達利潤門檻 -> 繼續持有維持投組多角化防禦。
   - NORMAL: 常規非注入標的。
3. 利差回流閉環 (Profit Recirculation):
   - 將收割釋放之資金與獲利記為 `recirculated_cash` 並持久化至 Redis。
   - 下一輪批次建倉 (`BatchCashDeploymentService`) 可無縫調用回流資金，重新注回高 Alpha 核心資產。
4. 風控單一真理閘門：所有出場與減碼交易強制調用 UnifiedRiskGatewayService (SELL 為 Fail-Open)。
5. 0-LLM 數理優先，輸出符合 Telegram HTML + Email nl2br 雙渠道格式標準。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("CrossSectorHarvestRebalanceService")


@dataclass
class HarvestCandidateMetric:
    """單一標的之動態收割與利差回流指標"""
    ticker: str
    sector: str
    shares: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pnl_usd: float
    unrealized_pnl_pct: float
    status: str  # HARVEST_ELIGIBLE, RUNNER_PRESERVE, HOLDING_STABILIZING, NORMAL
    recommended_harvest_shares: float
    recirculated_usd: float
    rationale: str
    is_cross_sector_contender: bool = True
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "sector": self.sector,
            "shares": round(self.shares, 4),
            "current_price": round(self.current_price, 2),
            "market_value": round(self.market_value, 2),
            "cost_basis": round(self.cost_basis, 2),
            "unrealized_pnl_usd": round(self.unrealized_pnl_usd, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 4),
            "status": self.status,
            "recommended_harvest_shares": round(self.recommended_harvest_shares, 4),
            "recirculated_usd": round(self.recirculated_usd, 2),
            "rationale": self.rationale,
            "is_cross_sector_contender": self.is_cross_sector_contender,
            "evaluated_at": self.evaluated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HarvestCandidateMetric:
        return cls(
            ticker=str(data.get("ticker", "")),
            sector=str(data.get("sector", "Unknown")),
            shares=float(data.get("shares", 0.0) or 0.0),
            current_price=float(data.get("current_price", 0.0) or 0.0),
            market_value=float(data.get("market_value", 0.0) or 0.0),
            cost_basis=float(data.get("cost_basis", 0.0) or 0.0),
            unrealized_pnl_usd=float(data.get("unrealized_pnl_usd", 0.0) or 0.0),
            unrealized_pnl_pct=float(data.get("unrealized_pnl_pct", 0.0) or 0.0),
            status=str(data.get("status", "NORMAL")),
            recommended_harvest_shares=float(data.get("recommended_harvest_shares", 0.0) or 0.0),
            recirculated_usd=float(data.get("recirculated_usd", 0.0) or 0.0),
            rationale=str(data.get("rationale", "")),
            is_cross_sector_contender=bool(data.get("is_cross_sector_contender", True)),
            evaluated_at=data.get("evaluated_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class HarvestAssessmentResult:
    """投組動態收割與利差回流綜合診斷成果"""
    portfolio_hhi: float
    is_hhi_healthy: bool
    total_recirculated_cash_usd: float
    candidates: List[HarvestCandidateMetric]
    can_execute_harvest: bool
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portfolio_hhi": round(self.portfolio_hhi, 4),
            "is_hhi_healthy": self.is_hhi_healthy,
            "total_recirculated_cash_usd": round(self.total_recirculated_cash_usd, 2),
            "candidate_count": len(self.candidates),
            "can_execute_harvest": self.can_execute_harvest,
            "evaluated_at": self.evaluated_at,
            "candidates": [c.to_dict() for c in self.candidates],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HarvestAssessmentResult:
        candidates_raw = data.get("candidates", [])
        candidates = [HarvestCandidateMetric.from_dict(c) for c in candidates_raw]
        return cls(
            portfolio_hhi=float(data.get("portfolio_hhi", 0.25) or 0.25),
            is_hhi_healthy=bool(data.get("is_hhi_healthy", False)),
            total_recirculated_cash_usd=float(data.get("total_recirculated_cash_usd", 0.0) or 0.0),
            candidates=candidates,
            can_execute_harvest=bool(data.get("can_execute_harvest", False)),
            evaluated_at=data.get("evaluated_at") or datetime.now(timezone.utc).isoformat(),
        )


class CrossSectorHarvestRebalanceService:
    """跨板塊注入標的動態出清與再平衡利差回流服務"""

    DEFAULT_SAFE_HHI_THRESHOLD = 0.18               # 投組安全分散 HHI 水準 (<= 0.18)
    DEFAULT_MIN_PROFIT_PCT = 10.0                   # 觸發分批收割之最低未實現獲利 (10.0%)
    DEFAULT_RUNNER_PROFIT_PCT = 15.0                # 觸發強者恆強保留之利潤門檻 (15.0%)
    DEFAULT_TECH_CAP_PCT = 0.28                     # 科技板塊安全上限比率 (<= 28%)
    REDIS_KEY_RECIRCULATED_CASH = "portfolio:recirculated_cash"

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        sector_drift_guard: Optional[Any] = None,
        risk_gateway: Optional[Any] = None,
        broker: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        self.sector_drift_guard = sector_drift_guard
        self.risk_gateway = risk_gateway
        self.broker = broker

    def _get_setting(self, key: str, default: Any) -> Any:
        try:
            return self.settings_service.get_setting(key, default)
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("enable_cross_sector_harvest_rebalance", True))

    @property
    def safe_hhi_threshold(self) -> float:
        return float(self._get_setting("cross_sector_harvest_safe_hhi_threshold", self.DEFAULT_SAFE_HHI_THRESHOLD))

    @property
    def min_profit_pct(self) -> float:
        return float(self._get_setting("cross_sector_harvest_min_profit_pct", self.DEFAULT_MIN_PROFIT_PCT))

    async def _get_sector_drift_guard(self) -> Any:
        if self.sector_drift_guard:
            return self.sector_drift_guard
        try:
            from src.services.sector_drift_guard_service import SectorDriftGuardService
            self.sector_drift_guard = SectorDriftGuardService(user_id=self.user_id)
            return self.sector_drift_guard
        except Exception as sde:
            logger.debug("Could not resolve SectorDriftGuardService: %s", sde)
            return None

    async def _get_risk_gateway(self) -> Any:
        if self.risk_gateway:
            return self.risk_gateway
        try:
            from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService
            self.risk_gateway = UnifiedRiskGatewayService(user_id=self.user_id)
            return self.risk_gateway
        except Exception as rge:
            logger.debug("Could not resolve UnifiedRiskGatewayService: %s", rge)
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 動態收割評估 (evaluate_portfolio_harvest)
    # ═══════════════════════════════════════════════════════════════════════

    async def evaluate_portfolio_harvest(
        self,
        positions: Optional[List[Any]] = None,
        total_equity: float = 1685.0,
    ) -> HarvestAssessmentResult:
        """
        評估投組中跨板塊防守標的之收割機會與回流金額。
        1. 計算投組當前 HHI 與板塊分佈。
        2. 檢查各非科技標的之收益率與防守必要性。
        3. 產出 2-Tier 收割建議 (50% 鎖利 / 保留 Runner)。
        """
        if not self.is_enabled:
            return HarvestAssessmentResult(
                portfolio_hhi=0.25,
                is_hhi_healthy=False,
                total_recirculated_cash_usd=0.0,
                candidates=[],
                can_execute_harvest=False,
            )

        drift_guard = await self._get_sector_drift_guard()
        report = None
        current_hhi = 0.25
        tech_ratio = 0.35

        if drift_guard and positions is not None:
            try:
                report = drift_guard.analyze_portfolio_holdings(positions, total_equity=total_equity)
                current_hhi = report.hhi_index
                tech_ratio = report.nlv_sector_weights.get("Technology", 0.0)
            except Exception as e:
                logger.debug("Drift guard analysis error in harvest: %s", e)

        is_hhi_healthy = (current_hhi <= self.safe_hhi_threshold) and (tech_ratio <= self.DEFAULT_TECH_CAP_PCT)

        candidates: List[HarvestCandidateMetric] = []
        total_recirculated = 0.0

        if positions:
            for p in positions:
                sym = getattr(p, "symbol", "") or (p.get("symbol") if isinstance(p, dict) else "")
                sym = str(sym).upper().strip()
                if not sym:
                    continue

                # 判斷所屬板塊
                sector = "Unknown"
                if drift_guard and hasattr(drift_guard, "get_stock_sector"):
                    sector = drift_guard.get_stock_sector(sym)

                is_tech = sector in ("Technology", "科技/半導體")
                is_cross_sector = not is_tech  # 非科技部位即為多角化注入/防守 Contender

                shares = float(getattr(p, "quantity", 0.0) or (p.get("quantity") if isinstance(p, dict) else 0.0) or 0.0)
                cur_price = float(getattr(p, "current_price", 0.0) or (p.get("current_price") if isinstance(p, dict) else 0.0) or 0.0)
                cost = float(getattr(p, "average_entry_price", 0.0) or (p.get("average_entry_price") if isinstance(p, dict) else 0.0) or cur_price)

                if shares <= 0 or cur_price <= 0:
                    continue

                mkt_val = shares * cur_price
                cost_basis = shares * cost
                pnl_usd = mkt_val - cost_basis
                pnl_pct = (pnl_usd / cost_basis * 100.0) if cost_basis > 0 else 0.0

                status = "NORMAL"
                rec_shares = 0.0
                recirc_usd = 0.0
                rationale = "一般持倉，未達收割標準"

                if is_cross_sector:
                    if is_hhi_healthy and pnl_pct >= self.DEFAULT_RUNNER_PROFIT_PCT:
                        # 投組健康且大賺 -> 保留 50% Runner，收割 50% 鎖利回流
                        status = "RUNNER_PRESERVE"
                        rec_shares = round(shares * 0.50, 4)
                        recirc_usd = round(rec_shares * cur_price, 2)
                        rationale = (
                            f"投組 HHI 集中度健康 ({current_hhi:.4f} <= {self.safe_hhi_threshold:.4f})，"
                            f"且獲利卓越 ({pnl_pct:+.1f}%)；收割 50% 倉位鎖利回流，剩餘部位掛載移動停利放飛"
                        )
                    elif is_hhi_healthy and pnl_pct >= self.min_profit_pct:
                        # 投組健康且獲利達標 -> 分批減碼 50%
                        status = "HARVEST_ELIGIBLE"
                        rec_shares = round(shares * 0.50, 4)
                        recirc_usd = round(rec_shares * cur_price, 2)
                        rationale = (
                            f"投組 HHI 自癒完成 ({current_hhi:.4f}) 且波段利潤達標 ({pnl_pct:+.1f}%)；"
                            f"執行 50% 分批收割，將資金回流至高 Alpha 核心資產"
                        )
                    elif not is_hhi_healthy and pnl_pct >= 20.0:
                        # 即使 HHI 仍偏高，若個股利潤達到極端暴利 (+20%)，亦進行 30% 止盈
                        status = "HARVEST_ELIGIBLE"
                        rec_shares = round(shares * 0.30, 4)
                        recirc_usd = round(rec_shares * cur_price, 2)
                        rationale = f"個股獲利豐厚 ({pnl_pct:+.1f}%)，適度減碼 30% 平抑波動並保留防禦底倉"
                    else:
                        status = "HOLDING_STABILIZING"
                        rationale = (
                            f"維持持倉防守 (HHI: {current_hhi:.4f}, 獲利: {pnl_pct:+.1f}%)；"
                            f"繼續平抑科技板塊波動風險"
                        )

                metric = HarvestCandidateMetric(
                    ticker=sym,
                    sector=sector,
                    shares=shares,
                    current_price=cur_price,
                    market_value=mkt_val,
                    cost_basis=cost_basis,
                    unrealized_pnl_usd=pnl_usd,
                    unrealized_pnl_pct=pnl_pct,
                    status=status,
                    recommended_harvest_shares=rec_shares,
                    recirculated_usd=recirc_usd,
                    rationale=rationale,
                    is_cross_sector_contender=is_cross_sector,
                )
                candidates.append(metric)
                if status in ("HARVEST_ELIGIBLE", "RUNNER_PRESERVE"):
                    total_recirculated += recirc_usd

        can_execute = total_recirculated >= 10.0

        result = HarvestAssessmentResult(
            portfolio_hhi=round(current_hhi, 4),
            is_hhi_healthy=is_hhi_healthy,
            total_recirculated_cash_usd=round(total_recirculated, 2),
            candidates=candidates,
            can_execute_harvest=can_execute,
        )

        # 寫入 Redis 供建倉服務調度
        if can_execute:
            try:
                from src.infrastructure.cache.redis_client import get_redis
                r = await get_redis(decode_responses=True)
                cache_key = f"{self.REDIS_KEY_RECIRCULATED_CASH}:{self.user_id}"
                await r.setex(cache_key, 86400, json.dumps(result.to_dict()))
            except Exception as re_err:
                logger.debug("Failed saving recirculated cash to Redis: %s", re_err)

        return result

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 執行收割訂單 (execute_harvest_orders)
    # ═══════════════════════════════════════════════════════════════════════

    async def execute_harvest_orders(
        self,
        assessment: HarvestAssessmentResult,
        broker: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        執行收割賣單，並經過 UnifiedRiskGatewayService 審核 (Fail-Open)。
        """
        exec_broker = broker or self.broker
        if not exec_broker:
            try:
                from src.services.broker_factory import BrokerFactory
                exec_broker = BrokerFactory.get_broker(user_id=self.user_id)
            except Exception as be:
                logger.warning("Could not resolve Broker for harvest: %s", be)

        risk_gateway = await self._get_risk_gateway()
        executed_orders: List[Dict[str, Any]] = []
        skipped_orders: List[Dict[str, Any]] = []

        for c in assessment.candidates:
            if c.status not in ("HARVEST_ELIGIBLE", "RUNNER_PRESERVE") or c.recommended_harvest_shares <= 0:
                continue

            sym = c.ticker
            shares = c.recommended_harvest_shares

            # 風控檢查 (SELL 是 Fail-Open，但在極端條件下需留痕)
            if risk_gateway:
                try:
                    risk_res = await risk_gateway.evaluate_trade_risk(
                        ticker=sym,
                        action="SELL",
                        shares=shares,
                        price=c.current_price,
                        order_type="MARKET",
                    )
                    if not getattr(risk_res, "is_allowed", getattr(risk_res, "allowed", False)):
                        logger.warning("Harvest sell risk blocked for %s: %s", sym, risk_res.reasons)
                        skipped_orders.append({"ticker": sym, "reason": "risk_blocked"})
                        continue
                except Exception as re:
                    # A risk check that cannot run is not a pass: skip the order (fail closed) and say so.
                    # 無法執行的風控檢查不等於通過：略過該筆委託（fail-closed）並明確記錄。
                    logger.warning("Risk gateway error in harvest sell for %s — order skipped: %s", sym, re)
                    skipped_orders.append({"ticker": sym, "reason": f"risk_check_error: {re}"})
                    continue

            # 券商委託 — only a broker that can really place orders may execute; never record a simulated
            # fill as executed (same bug as the staggered-order service).
            # 只有真的能下單的券商才可執行；絕不把模擬成交記為已執行（與階梯單服務同一類錯誤）。
            if not (exec_broker and hasattr(exec_broker, "place_order")):
                logger.warning("Harvest sell for %s NOT executed: no execution broker with place_order", sym)
                skipped_orders.append({"ticker": sym, "reason": "no_execution_broker"})
                continue
            try:
                place_res = await exec_broker.place_order(
                    symbol=sym,
                    action="SELL",
                    shares=shares,
                    order_type="MARKET",
                )
                order_id = str(place_res.get("order_id"))
            except Exception as oe:
                logger.error("Failed executing harvest sell for %s: %s", sym, oe)
                skipped_orders.append({"ticker": sym, "reason": f"order_error: {oe}"})
                continue

            executed_orders.append({
                "ticker": sym,
                "shares": shares,
                "price": c.current_price,
                "recirculated_usd": c.recirculated_usd,
                "order_id": order_id,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            })

        return {
            "status": "success",
            "executed_count": len(executed_orders),
            "orders": executed_orders,
            "skipped_orders": skipped_orders,
            "total_recirculated_usd": round(sum(o["recirculated_usd"] for o in executed_orders), 2),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 3. 0-LLM 雙渠道戰報生成
    # ═══════════════════════════════════════════════════════════════════════

    def format_harvest_report(
        self,
        assessment: HarvestAssessmentResult,
        channel: str = "telegram",
    ) -> str:
        """
        產出符合 Telegram HTML 與 Email nl2br 雙渠道標準之收割與利差回流戰報。
        """
        hhi_badge = "🟢 健康低集中" if assessment.is_hhi_healthy else "🟡 集中度修復中"

        lines = [
            "🌾 <b>【跨板塊注入標的動態收割與利差回流儀表】</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"• <b>投組 HHI 指數</b>：<code>{assessment.portfolio_hhi:.4f}</code> ({hhi_badge})",
            f"• <b>可回流現金總額</b>：<code>${assessment.total_recirculated_cash_usd:,.2f} USD</code>",
            f"• <b>執行許可狀態</b>：{'🟢 具備收割機會' if assessment.can_execute_harvest else '⚪ 持倉穩定無需減碼'}",
            "━━━━━━━━━━━━━━━━━━",
        ]

        cross_candidates = [c for c in assessment.candidates if c.is_cross_sector_contender]
        if not cross_candidates:
            lines.append("• <i>目前持倉中無跨板塊自癒標的。</i>")
        else:
            lines.append("🎯 <b>【跨板塊自癒標的診斷清單】</b>")
            for c in cross_candidates:
                if c.status == "RUNNER_PRESERVE":
                    status_badge = "💎 <b>獲利放飛 (RUNNER_PRESERVE)</b>"
                elif c.status == "HARVEST_ELIGIBLE":
                    status_badge = "💰 <b>分批收割 (HARVEST_ELIGIBLE)</b>"
                else:
                    status_badge = "🛡️ <b>持倉防守 (HOLDING_STABILIZING)</b>"

                pnl_color = "🟢" if c.unrealized_pnl_usd >= 0 else "🔴"
                lines.append(f"• <b>{c.ticker}</b> <i>[{c.sector}]</i>：{status_badge}")
                lines.append(
                    f"  ├ 現價: <code>${c.current_price:.2f}</code> | "
                    f"成本: <code>${c.cost_basis / max(0.0001, c.shares):.2f}</code> | "
                    f"損益: {pnl_color} <code>{c.unrealized_pnl_pct:+.2f}%</code> (${c.unrealized_pnl_usd:+,.2f})"
                )
                if c.recommended_harvest_shares > 0:
                    lines.append(
                        f"  ├ 建議減碼: <code>{c.recommended_harvest_shares:.4f} 股</code> "
                        f"(回流資金: <code><b>${c.recirculated_usd:,.2f}</b></code>)"
                    )
                lines.append(f"  └ <i>評估說明</i>：{c.rationale}")
                lines.append("──────────────────")

        lines.append("💡 <b>再平衡閉環</b>：收割資金自動劃撥為可支配現金，供下一批次建倉注入高 Alpha 核心股票。")
        lines.append("💡 <b>快捷指令</b>：輸入 <code>/sector</code> 檢視板塊分佈，輸入 <code>/batch</code> 檢視建倉計畫。")

        return "\n".join(lines)
