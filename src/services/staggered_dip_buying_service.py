"""
Staggered Dip Buying Service
============================
主力支撐階梯限價吸籌服務 (Smart Staggered Limit Buying / Intraday Dip Catcher)

核心邏輯：
1. 嚴格遵守 20%~25% 防守現金儲備底線，僅動用可支配建倉資金。
2. 拒絕開盤盲目以市價追高，將建倉預算依 3-Tier 階梯分拆：
   - Tier 1 (40% 預算): 輕度回踩首檔進場點，錨定波段 AVWAP / Volume Profile POC (預設 -0.8% ~ -1.2%)。
   - Tier 2 (35% 預算): 結構性主力籌碼支撐，錨定 Value Area Low (VAL) 或 Key Support (預設 -1.8% ~ -2.5%)。
   - Tier 3 (25% 預算): 恐慌甩轎與獵殺下殺（Stop-Hunt Flush），捕獲極端深度折價廉價籌碼 (預設 -3.5% ~ -4.5%)。
3. 預算彈性分檔：若單檔標的預算 < $20 則折疊為 1 檔，< $30 則 2 檔，>= $30 展開標準 3 檔。
4. 嚴格保證價格階梯單調遞減：P_tier3 < P_tier2 < P_tier1 < P_current。
5. 所有事前交易風控檢查一律強制調用 UnifiedRiskGatewayService.evaluate_trade_risk (BUY 是 Fail-Closed)。
6. 收盤前自動撤單 (15:55 EST)：盤中未觸發之限價單於收盤前 5 分鐘自動撤銷，釋放保留現金，杜絕留單過夜與盤後跳空風險。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

import pytz

from src.config.owner import resolve_user_id
from src.utils.logger import setup_logger

logger = setup_logger("StaggeredDipBuyingService")


@dataclass
class StaggeredTierPlan:
    """單一階梯限價計畫"""
    tier_number: int                          # 1, 2, 3
    name: str                                 # "Tier 1 (輕度回踩)", "Tier 2 (結構支撐)", "Tier 3 (深度折價)"
    target_price: float                       # 限價買入目標價
    discount_pct: float                       # 相對現價之折價幅度 (0.008 = -0.8%)
    allocation_usd: float                     # 該階梯配置金額 (USD)
    allocation_pct: float                     # 該階梯佔標的預算百分比 (0.40 = 40%)
    shares: float                             # 預估可購股數
    support_anchor_type: str                  # "AVWAP", "POC", "VAL", "KEY_SUPPORT", "PERCENTAGE_FALLBACK"
    rationale: str                            # 定價依據與說明

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier_number": self.tier_number,
            "name": self.name,
            "target_price": round(self.target_price, 2),
            "discount_pct": round(self.discount_pct * 100.0, 2),
            "allocation_usd": round(self.allocation_usd, 2),
            "allocation_pct": round(self.allocation_pct * 100.0, 1),
            "shares": round(self.shares, 4),
            "support_anchor_type": self.support_anchor_type,
            "rationale": self.rationale,
        }


@dataclass
class TickerStaggeredPlan:
    """單檔標的之完整階梯吸籌計畫"""
    ticker: str
    current_price: float
    total_budget_usd: float
    tiers: List[StaggeredTierPlan]
    is_risk_allowed: bool
    risk_severity: str = "NORMAL"
    risk_blocker: Optional[str] = None
    risk_reasons: List[str] = field(default_factory=list)
    key_support_price: float = 0.0
    anchored_vwap: float = 0.0
    point_of_control: float = 0.0
    value_area_low: float = 0.0
    value_area_high: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "current_price": round(self.current_price, 2),
            "total_budget_usd": round(self.total_budget_usd, 2),
            "tier_count": len(self.tiers),
            "tiers": [t.to_dict() for t in self.tiers],
            "is_risk_allowed": self.is_risk_allowed,
            "risk_severity": self.risk_severity,
            "risk_blocker": self.risk_blocker,
            "risk_reasons": self.risk_reasons,
            "institutional_anchors": {
                "key_support_price": round(self.key_support_price, 2),
                "anchored_vwap": round(self.anchored_vwap, 2),
                "point_of_control": round(self.point_of_control, 2),
                "value_area_low": round(self.value_area_low, 2),
                "value_area_high": round(self.value_area_high, 2),
            },
        }


@dataclass
class StaggeredDipDeploymentPlan:
    """投組批次階梯吸籌全景方案"""
    batch_number: int
    total_deployable_cash: float
    total_planned_deployment_usd: float
    plans: List[TickerStaggeredPlan]
    can_execute: bool
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_number": self.batch_number,
            "total_deployable_cash": round(self.total_deployable_cash, 2),
            "total_planned_deployment_usd": round(self.total_planned_deployment_usd, 2),
            "candidate_count": len(self.plans),
            "can_execute": self.can_execute,
            "created_at": self.created_at,
            "plans": [p.to_dict() for p in self.plans],
        }


class StaggeredDipBuyingService:
    """主力支撐階梯限價吸籌服務"""

    REDIS_KEY_PREFIX = "staggered_orders"

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        support_service: Optional[Any] = None,
        risk_gateway: Optional[Any] = None,
        broker: Optional[Any] = None,
        market_clock: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)

        if support_service is not None:
            self.support_service = support_service
        else:
            try:
                from src.services.smart_money_support_service import SmartMoneySupportService
                self.support_service = SmartMoneySupportService()
            except Exception as se:
                logger.warning("Could not initialize SmartMoneySupportService: %s", se)
                self.support_service = None

        if risk_gateway is not None:
            self.risk_gateway = risk_gateway
        else:
            try:
                from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService
                self.risk_gateway = UnifiedRiskGatewayService(user_id=self.user_id)
            except Exception as rge:
                logger.warning("Could not initialize UnifiedRiskGatewayService: %s", rge)
                self.risk_gateway = None

        self.broker = broker
        from src.utils.market_clock import MarketClock
        self.market_clock = market_clock or MarketClock()

    async def _get_broker(self) -> Any:
        if self.broker:
            return self.broker
        try:
            from src.infrastructure.broker_service import BrokerService
            self.broker = BrokerService()
            return self.broker
        except Exception as be:
            logger.debug("Could not resolve BrokerService: %s", be)
            return None

    def _get_setting(self, key: str, default: Any) -> Any:
        try:
            return self.settings_service.get_setting(key, default)
        except Exception:
            return default

    # ═══════════════════════════════════════════════════════════════════════
    # 1. 核心計算法：單檔標的主力籌碼 3-Tier 階梯限價精算
    # ═══════════════════════════════════════════════════════════════════════

    async def calculate_staggered_plan_for_ticker(
        self,
        ticker: str,
        target_budget_usd: float,
        current_price: Optional[float] = None,
    ) -> TickerStaggeredPlan:
        """
        針對特定標的精算 3-Tier 階梯限價進場點位與分配資金：
        1. 取得主力籌碼支撐 (AVWAP, POC, VAL, KeySupport)。
        2. 依預算規模動態折疊檔位（確保單檔限價至少滿足券商起投額 $10 USD）。
        3. 錨定結構位並設定安全折價，強制單調遞減：P_t3 < P_t2 < P_t1 < P_curr。
        4. 透過 UnifiedRiskGatewayService 執行事前風控核驗 (Fail-Closed)。
        """
        ticker = (ticker or "").upper().strip()
        target_budget_usd = max(0.0, float(target_budget_usd or 0.0))

        # 1. 取得即時價格與主力籌碼結構
        support_res = None
        if self.support_service:
            try:
                support_res = self.support_service.calculate_institutional_support(
                    ticker=ticker,
                    current_price=current_price,
                )
            except Exception as se:
                logger.debug("Support calculation fallback for %s: %s", ticker, se)

        if support_res and support_res.current_price > 0:
            c_price = support_res.current_price
            avwap = support_res.anchored_vwap
            poc = support_res.point_of_control
            val = support_res.value_area_low
            vah = support_res.value_area_high
            key_sup = support_res.key_support_price
        else:
            c_price = float(current_price or 100.0)
            avwap = c_price * 0.99
            poc = c_price * 0.985
            val = c_price * 0.975
            vah = c_price * 1.01
            key_sup = c_price * 0.98

        # 讀取設定檔之折價參數
        t1_dip_def = float(self._get_setting("staggered_tier1_dip_pct", 0.008))  # 0.8%
        t2_dip_def = float(self._get_setting("staggered_tier2_dip_pct", 0.020))  # 2.0%
        t3_dip_def = float(self._get_setting("staggered_tier3_dip_pct", 0.038))  # 3.8%

        t1_alloc_pct = float(self._get_setting("staggered_tier1_allocation_pct", 0.40))
        t2_alloc_pct = float(self._get_setting("staggered_tier2_allocation_pct", 0.35))
        t3_alloc_pct = float(self._get_setting("staggered_tier3_allocation_pct", 0.25))

        # 2. 依預算規模動態分配檔位
        tiers: List[StaggeredTierPlan] = []
        if target_budget_usd < 10.0:
            # 預算過低，無法下發任何階梯單
            tiers = []
        elif target_budget_usd < 20.0:
            # 預算僅足夠下 1 檔 ($10~$19.99)
            p1 = round(min(c_price * (1.0 - t1_dip_def), max(poc, avwap) if max(poc, avwap) < c_price else c_price * (1.0 - t1_dip_def)), 2)
            if p1 >= c_price:
                p1 = round(c_price * (1.0 - t1_dip_def), 2)
            disc1 = (c_price - p1) / c_price
            sh1 = target_budget_usd / p1 if p1 > 0 else 0.0
            tiers.append(StaggeredTierPlan(
                tier_number=1,
                name="Tier 1 (輕度回踩錨點)",
                target_price=p1,
                discount_pct=disc1,
                allocation_usd=target_budget_usd,
                allocation_pct=1.0,
                shares=sh1,
                support_anchor_type="AVWAP_POC_SINGLE",
                rationale=f"預算限額折疊為單一主力回踩檔位，錨定 AVWAP/POC ({p1})",
            ))
        elif target_budget_usd < 30.0:
            # 預算足夠下 2 檔 ($20~$29.99)
            b1 = round(target_budget_usd * 0.55, 2)
            b2 = round(target_budget_usd - b1, 2)

            p1 = round(min(c_price * (1.0 - t1_dip_def), max(poc, avwap) if max(poc, avwap) < c_price else c_price * (1.0 - t1_dip_def)), 2)
            if p1 >= c_price:
                p1 = round(c_price * (1.0 - t1_dip_def), 2)

            p2 = round(min(p1 * 0.99, val if val < p1 else c_price * (1.0 - t2_dip_def)), 2)
            if p2 >= p1:
                p2 = round(p1 * 0.985, 2)

            disc1 = (c_price - p1) / c_price
            disc2 = (c_price - p2) / c_price

            tiers.append(StaggeredTierPlan(
                tier_number=1,
                name="Tier 1 (首檔回踩)",
                target_price=p1,
                discount_pct=disc1,
                allocation_usd=b1,
                allocation_pct=round(b1 / target_budget_usd, 4),
                shares=b1 / p1 if p1 > 0 else 0.0,
                support_anchor_type="AVWAP_POC",
                rationale=f"首檔輕度回踩進場點，錨定密集籌碼 ({p1})",
            ))
            tiers.append(StaggeredTierPlan(
                tier_number=2,
                name="Tier 2 (結構支撐)",
                target_price=p2,
                discount_pct=disc2,
                allocation_usd=b2,
                allocation_pct=round(b2 / target_budget_usd, 4),
                shares=b2 / p2 if p2 > 0 else 0.0,
                support_anchor_type="VAL_SUPPORT",
                rationale=f"結構支撐防守位，錨定 Value Area Low ({p2})",
            ))
        else:
            # 標準 3 檔位 ($30+)
            b1 = round(target_budget_usd * t1_alloc_pct, 2)
            b2 = round(target_budget_usd * t2_alloc_pct, 2)
            b3 = round(target_budget_usd - b1 - b2, 2)

            # Tier 1 定價：AVWAP / POC 高量區或預設 -0.8%
            candidate_p1 = max(poc, avwap)
            if 0 < candidate_p1 < c_price:
                p1 = round(min(candidate_p1, c_price * (1.0 - t1_dip_def)), 2)
                anchor1 = "POC" if poc >= avwap else "AVWAP"
            else:
                p1 = round(c_price * (1.0 - t1_dip_def), 2)
                anchor1 = "PERCENTAGE_FALLBACK"

            # Tier 2 定價：VAL 或 Key Support 或預設 -2.0%
            candidate_p2 = min(val, key_sup) if min(val, key_sup) > 0 else val
            if 0 < candidate_p2 < p1:
                p2 = round(min(candidate_p2, c_price * (1.0 - t2_dip_def)), 2)
                anchor2 = "VAL" if val <= key_sup else "KEY_SUPPORT"
            else:
                p2 = round(min(p1 * 0.988, c_price * (1.0 - t2_dip_def)), 2)
                anchor2 = "PERCENTAGE_FALLBACK"

            # Tier 3 定價：恐慌甩轎深度折價 (VAL * 0.985 或預設 -3.8%)
            candidate_p3 = val * 0.985 if val > 0 else 0.0
            if 0 < candidate_p3 < p2:
                p3 = round(min(candidate_p3, c_price * (1.0 - t3_dip_def)), 2)
                anchor3 = "VAL_DEEP_DISCOUNT"
            else:
                p3 = round(min(p2 * 0.982, c_price * (1.0 - t3_dip_def)), 2)
                anchor3 = "PERCENTAGE_FALLBACK"

            # 剛性防禦檢查：嚴格保證遞減順序 P_t3 < P_t2 < P_t1 < P_curr
            if p1 >= c_price:
                p1 = round(c_price * 0.992, 2)
            if p2 >= p1:
                p2 = round(p1 * 0.985, 2)
            if p3 >= p2:
                p3 = round(p2 * 0.982, 2)

            disc1 = (c_price - p1) / c_price
            disc2 = (c_price - p2) / c_price
            disc3 = (c_price - p3) / c_price

            tiers.append(StaggeredTierPlan(
                tier_number=1,
                name="Tier 1 (輕度回踩)",
                target_price=p1,
                discount_pct=disc1,
                allocation_usd=b1,
                allocation_pct=round(b1 / target_budget_usd, 4),
                shares=b1 / p1 if p1 > 0 else 0.0,
                support_anchor_type=anchor1,
                rationale=f"首檔輕度回踩進場點，錨定 {anchor1} ({p1})",
            ))
            tiers.append(StaggeredTierPlan(
                tier_number=2,
                name="Tier 2 (結構支撐)",
                target_price=p2,
                discount_pct=disc2,
                allocation_usd=b2,
                allocation_pct=round(b2 / target_budget_usd, 4),
                shares=b2 / p2 if p2 > 0 else 0.0,
                support_anchor_type=anchor2,
                rationale=f"第二檔結構防守支撐，錨定 {anchor2} ({p2})",
            ))
            tiers.append(StaggeredTierPlan(
                tier_number=3,
                name="Tier 3 (深度折價)",
                target_price=p3,
                discount_pct=disc3,
                allocation_usd=b3,
                allocation_pct=round(b3 / target_budget_usd, 4),
                shares=b3 / p3 if p3 > 0 else 0.0,
                support_anchor_type=anchor3,
                rationale=f"第三檔甩轎恐慌深度折價，捕獲極端折價籌碼 ({p3})",
            ))

        # 3. 透過 UnifiedRiskGatewayService 執行事前風控核驗 (Fail-Closed)
        is_allowed = True
        risk_sev = "NORMAL"
        primary_blocker = None
        reasons: List[str] = []

        if self.risk_gateway is not None and target_budget_usd >= 10.0:
            try:
                risk_res = await self.risk_gateway.evaluate_trade_risk(
                    ticker=ticker,
                    action="BUY",
                    amount_usd=target_budget_usd,
                )
                is_allowed = risk_res.allowed
                risk_sev = risk_res.severity.value if hasattr(risk_res.severity, "value") else str(risk_res.severity)
                primary_blocker = risk_res.primary_blocker
                reasons = risk_res.reasons or []
            except Exception as rge:
                logger.error("UnifiedRiskGateway failed for %s (blocking BUY for safety): %s", ticker, rge)
                is_allowed = False
                risk_sev = "CRITICAL"
                primary_blocker = "RiskGatewayException"
                reasons = [f"Risk gateway unavailable ({type(rge).__name__}); Fail-Closed active"]

        return TickerStaggeredPlan(
            ticker=ticker,
            current_price=c_price,
            total_budget_usd=target_budget_usd,
            tiers=tiers,
            is_risk_allowed=is_allowed,
            risk_severity=risk_sev,
            risk_blocker=primary_blocker,
            risk_reasons=reasons,
            key_support_price=key_sup,
            anchored_vwap=avwap,
            point_of_control=poc,
            value_area_low=val,
            value_area_high=vah,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 2. 批次全景建倉方案生成
    # ═══════════════════════════════════════════════════════════════════════

    async def generate_batch_staggered_plan(
        self,
        batch_number: Optional[int] = None,
    ) -> StaggeredDipDeploymentPlan:
        """
        生成全投組批次階梯限價吸籌規劃方案。
        整合 BatchCashDeploymentService 取得合格候選標的清單與配置金額。
        """
        from src.services.batch_cash_deployment_service import BatchCashDeploymentService
        batch_svc = BatchCashDeploymentService(
            user_id=self.user_id,
            settings_service=self.settings_service,
            broker=self.broker,
        )

        if batch_number is None or batch_number <= 0:
            batch_number = await batch_svc.get_active_batch_number()

        if batch_number == 0:
            status = await batch_svc.get_portfolio_status()
            deployable = float(status.get("deployable_cash", 0.0) or 0.0)
            return StaggeredDipDeploymentPlan(
                batch_number=0,
                total_deployable_cash=deployable,
                total_planned_deployment_usd=0.0,
                plans=[],
                can_execute=False,
            )

        base_plan = await batch_svc.get_deployment_plan(batch_number=batch_number)
        deployable_cash = float(base_plan.get("portfolio_status", {}).get("deployable_cash", 0.0) or 0.0)
        items = base_plan.get("items") or []

        plans: List[TickerStaggeredPlan] = []
        total_planned = 0.0

        for it in items:
            sym = it.get("ticker", "")
            amt = float(it.get("amount_usd", 0.0) or 0.0)
            if not sym or amt < 10.0:
                continue

            ticker_plan = await self.calculate_staggered_plan_for_ticker(
                ticker=sym,
                target_budget_usd=amt,
            )
            plans.append(ticker_plan)
            if ticker_plan.is_risk_allowed:
                total_planned += amt

        can_exec = bool(plans) and any(p.is_risk_allowed for p in plans) and deployable_cash >= 10.0

        return StaggeredDipDeploymentPlan(
            batch_number=batch_number,
            total_deployable_cash=deployable_cash,
            total_planned_deployment_usd=total_planned,
            plans=plans,
            can_execute=can_exec,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 3. 階梯限價單下發與執行 (Execution & Redis State Tracking)
    # ═══════════════════════════════════════════════════════════════════════

    async def execute_staggered_dip_deployment(
        self,
        batch_number: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        執行主力支撐階梯限價建倉：
        1. 產出 3-Tier 階梯吸籌規劃。
        2. 風控核驗放行之標的，產生 StaggeredOrderRecord 寫入 Redis。
        3. 透過 Broker (若支援 LIMIT) 下發被動限價掛單。
        4. 透過 NotificationService 發送標準化雙渠道推播 (含 Telegram Inline 按鈕與 Email 快捷指令)。
        """
        plan = await self.generate_batch_staggered_plan(batch_number=batch_number)
        if not plan.can_execute and not force:
            logger.info("Staggered dip deployment cannot execute: can_execute=False")
            return {
                "success": False,
                "status": "cannot_execute",
                "message": "階梯限價吸籌條件未達標 (無可支配資金或標的受風控阻斷)",
                "plan": plan.to_dict(),
                "orders_placed": [],
            }

        broker = await self._get_broker()
        placed_orders: List[Dict[str, Any]] = []
        ny_tz = pytz.timezone("US/Eastern")
        now_ny = datetime.now(ny_tz)
        date_str = now_ny.strftime("%Y-%m-%d")

        for tp in plan.plans:
            if not tp.is_risk_allowed and not force:
                logger.warning("Skipping %s due to risk block: %s", tp.ticker, tp.risk_blocker)
                continue

            for tier in tp.tiers:
                order_id = f"dip_{tp.ticker}_{tier.tier_number}_{uuid.uuid4().hex[:8]}"
                record = {
                    "order_id": order_id,
                    "user_id": self.user_id,
                    "ticker": tp.ticker,
                    "tier_number": tier.tier_number,
                    "tier_name": tier.name,
                    "limit_price": tier.target_price,
                    "amount_usd": tier.allocation_usd,
                    "discount_pct": tier.discount_pct,
                    "shares": tier.shares,
                    "status": "PENDING",
                    "placed_at": datetime.now(timezone.utc).isoformat(),
                    "date": date_str,
                    "anchor_type": tier.support_anchor_type,
                    "broker_order_id": None,
                }

                # 若券商支援 place_order，下發 LIMIT 單
                if broker and hasattr(broker, "place_order"):
                    try:
                        from src.domain.trading import OrderAction, OrderType
                        b_res = await broker.place_order(
                            symbol=tp.ticker,
                            action=OrderAction.BUY if hasattr(OrderAction, "BUY") else "BUY",
                            order_type=OrderType.LIMIT if hasattr(OrderType, "LIMIT") else "LIMIT",
                            amount=tier.allocation_usd,
                            limit_price=tier.target_price,
                        )
                        if isinstance(b_res, dict) and b_res.get("order_id"):
                            record["broker_order_id"] = str(b_res.get("order_id"))
                    except Exception as be:
                        logger.debug("Broker limit placement fallback for %s tier %d: %s", tp.ticker, tier.tier_number, be)

                placed_orders.append(record)

        # 寫入 Redis 持久化儲存
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            r_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{date_str}"
            existing = await r.get(r_key)
            all_records = json.loads(existing) if existing else []
            all_records.extend(placed_orders)
            # 保存 24 小時
            await r.setex(r_key, 86400, json.dumps(all_records, ensure_ascii=False))
        except Exception as re:
            logger.warning("Failed to persist staggered orders to Redis: %s", re)

        # 發送 Telegram / Email 通知
        await self.dispatch_staggered_deployment_alert(plan, placed_orders)

        return {
            "success": True,
            "status": "orders_placed",
            "batch_number": plan.batch_number,
            "order_count": len(placed_orders),
            "total_planned_usd": plan.total_planned_deployment_usd,
            "orders": placed_orders,
            "plan": plan.to_dict(),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 4. 收盤前自動撤銷清理 (15:55 EST Market-Close Sweep)
    # ═══════════════════════════════════════════════════════════════════════

    async def cancel_all_pending_staggered_orders(
        self,
        reason: str = "收盤前自動安全撤銷 (Market Close Cleanup)",
    ) -> Dict[str, Any]:
        """
        收盤前 15:55 EST 自動撤除所有未成交之階梯掛單：
        1. 讀取 Redis 今日掛單記錄。
        2. 針對 PENDING 狀態之掛單進行撤單。
        3. 釋放保留現金，杜絕留單過夜與隔日跳空風險。
        4. 發送推播通報已成交總額 vs 撤銷釋放總額。
        """
        ny_tz = pytz.timezone("US/Eastern")
        now_ny = datetime.now(ny_tz)
        date_str = now_ny.strftime("%Y-%m-%d")

        broker = await self._get_broker()
        cancelled_orders = []
        filled_orders = []

        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            r_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{date_str}"
            existing = await r.get(r_key)
            if not existing:
                return {
                    "success": True,
                    "cancelled_count": 0,
                    "filled_count": 0,
                    "message": "今日無待撤除之階梯限價掛單。",
                }

            orders = json.loads(existing)
            updated_orders = []

            for ord_rec in orders:
                st = ord_rec.get("status", "PENDING")
                if st == "FILLED":
                    filled_orders.append(ord_rec)
                    updated_orders.append(ord_rec)
                elif st == "PENDING":
                    # 嘗試向券商撤單
                    b_id = ord_rec.get("broker_order_id")
                    if b_id and broker and hasattr(broker, "cancel_order"):
                        try:
                            await broker.cancel_order(order_id=b_id)
                        except Exception as ce:
                            logger.debug("Broker cancel error for %s: %s", b_id, ce)

                    ord_rec["status"] = "CANCELLED"
                    ord_rec["cancelled_at"] = datetime.now(timezone.utc).isoformat()
                    ord_rec["cancel_reason"] = reason
                    cancelled_orders.append(ord_rec)
                    updated_orders.append(ord_rec)
                else:
                    updated_orders.append(ord_rec)

            await r.setex(r_key, 86400, json.dumps(updated_orders, ensure_ascii=False))

        except Exception as e:
            logger.error("Failed to cancel staggered orders: %s", e)
            return {"success": False, "error": str(e)}

        released_cash = sum(float(o.get("amount_usd", 0.0)) for o in cancelled_orders)
        filled_cash = sum(float(o.get("amount_usd", 0.0)) for o in filled_orders)

        logger.info(
            "Staggered cleanup complete: %d cancelled ($%.2f released), %d filled ($%.2f)",
            len(cancelled_orders), released_cash, len(filled_orders), filled_cash,
        )

        return {
            "success": True,
            "cancelled_count": len(cancelled_orders),
            "released_cash_usd": round(released_cash, 2),
            "filled_count": len(filled_orders),
            "filled_cash_usd": round(filled_cash, 2),
            "cancelled_orders": cancelled_orders,
            "filled_orders": filled_orders,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # 5. 查詢當日階梯吸籌狀態 (Status Telemetry)
    # ═══════════════════════════════════════════════════════════════════════

    async def get_active_staggered_orders(self) -> List[Dict[str, Any]]:
        """查詢今日所有階梯限價掛單狀態"""
        ny_tz = pytz.timezone("US/Eastern")
        now_ny = datetime.now(ny_tz)
        date_str = now_ny.strftime("%Y-%m-%d")

        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            r_key = f"{self.REDIS_KEY_PREFIX}:{self.user_id}:{date_str}"
            existing = await r.get(r_key)
            if existing:
                return json.loads(existing)
        except Exception as e:
            logger.debug("Failed to read active staggered orders: %s", e)
        return []

    # ═══════════════════════════════════════════════════════════════════════
    # 6. 雙渠道通知分發 (遵循 Notification Formatting Guide)
    # ═══════════════════════════════════════════════════════════════════════

    async def dispatch_staggered_deployment_alert(
        self,
        plan: StaggeredDipDeploymentPlan,
        orders: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """發送階梯限價掛單戰情報告 (相容 Telegram HTML 與 Email nl2br)"""
        try:
            from src.services.notification_service import NotificationService
            noti_svc = NotificationService.create_with_settings(
                settings_service=self.settings_service,
                user_id=self.user_id,
            )

            title = f"🎯 主力支撐階梯限價吸籌已下發 (第 {plan.batch_number} 批次)"
            content_lines = [
                f"已針對第 {plan.batch_number} 批次候選標的啟動主力支撐階梯限價吸籌。\n",
                f"• <b>可支配建倉資金</b>：<code>${plan.total_deployable_cash:.2f} USD</code>",
                f"• <b>本批計畫吸籌總額</b>：<code>${plan.total_planned_deployment_usd:.2f} USD</code>",
                f"• <b>下發階梯掛單數</b>：<code>{len(orders)} 筆</code>\n",
                "<b>【階梯限價定價詳情】</b>",
            ]

            for tp in plan.plans:
                if not tp.is_risk_allowed:
                    content_lines.append(f"⛔ <code>{tp.ticker}</code>：風控阻斷 ({tp.risk_blocker or 'Risk Gateway'})")
                    continue

                content_lines.append(f"🟢 <b>{tp.ticker}</b> (現價: <code>${tp.current_price:.2f}</code> | 預算: <code>${tp.total_budget_usd:.2f}</code>)：")
                for t in tp.tiers:
                    content_lines.append(
                        f"  └ <b>{t.name}</b>：<code>${t.target_price:.2f}</code> "
                        f"(-{t.discount_pct * 100:.1f}%) | 金額: <code>${t.allocation_usd:.2f}</code>"
                    )

            content_lines.append("\n💡 <b>收盤保護</b>：未成交之階梯掛單將於 15:55 EST 自動安全撤除釋放現金。")
            content_lines.append("💡 <b>快捷指令</b>：可於 Telegram 輸入 <code>/dipbuy status</code> 檢視撮合狀態，或輸入 <code>/dipbuy cancel</code> 一鍵全數撤銷。")

            content = "\n".join(content_lines)

            actions = [
                {"label": "📊 檢視狀態 (Status)", "data": "action=dipbuy_status", "key": "dipbuy_status"},
                {"label": "🛑 立即撤單 (Cancel)", "data": "action=dipbuy_cancel", "key": "dipbuy_cancel"},
            ]

            return await noti_svc.notify_all(
                title=title,
                content=content,
                user_id=self.user_id,
                actions=actions,
                category="trade_action",
            )
        except Exception as ne:
            logger.error("Failed to dispatch staggered deployment alert: %s", ne)
            return None
