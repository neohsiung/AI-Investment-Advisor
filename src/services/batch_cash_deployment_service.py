"""
Batch Cash Deployment Service
=============================
美股開盤階梯式分批建倉服務 (Disciplined Batch Cash Deployment Service)

核心邏輯：
1. 嚴格遵守 20%~25% 防守現金儲備底線（拒絕盲目單次全倉梭哈）。
2. 將超額閒置現金分為 3 批次有序推進（第 1 批動用約 33% / ~$347）。
3. 第 1 批次優先建倉 Top 3 高確信度核心龍頭：
   - NVDA (~$114.00) — Alpha Top 1
   - TSM (~$144.00) — Alpha Top 2
   - AAPL (~$89.00) — 核心底倉加碼補足至 10%
   - 執行後現金儲備維持在 ~$1,057.09 (62.4%)，遠高於防禦門檻 ($338.50)。
4. 全程整合 SlippageGuardService：
   - 避開 09:30-09:35 EST 開盤前 5 分鐘極端撮合價差。
   - 下單前即時檢驗 Bid-Ask Spread <= 0.15%，超標自動觸發熔斷。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional
import pytz

from src.config.owner import resolve_user_id
from src.services.order_cap_policy import single_order_cap_usd
from src.utils.logger import setup_logger

logger = setup_logger("BatchCashDeploymentService")


class BatchCashDeploymentService:
    """階梯式分批建倉與開盤執行服務"""

    DEFAULT_DEFENSIVE_CASH_PCT = 20.0  # 預設 20% 防禦現金保留比率
    DEFAULT_BATCH_PORTION = 0.33        # 每批次動用可部署現金的 1/3 (~33%)

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        broker: Optional[Any] = None,
        slippage_guard: Optional[Any] = None,
        market_clock: Optional[Any] = None,
        blackout_guard: Optional[Any] = None,
        vpin_guard: Optional[Any] = None,
        jump_guard: Optional[Any] = None,
        rl_sor: Optional[Any] = None,
        event_graph: Optional[Any] = None,
        bayesian_hmm_factor: Optional[Any] = None,
        staggered_dip_service: Optional[Any] = None,
        alpha_spread_bidding_service: Optional[Any] = None,
        convex_optimizer: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        from src.services.settings_service import SettingsService
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        self.broker = broker
        from src.services.slippage_guard_service import SlippageGuardService
        self.slippage_guard = slippage_guard or SlippageGuardService(
            user_id=self.user_id,
            settings_service=self.settings_service,
        )
        from src.utils.market_clock import MarketClock
        self.market_clock = market_clock or MarketClock()
        from src.services.calendar_blackout_service import CalendarBlackoutService
        self.blackout_guard = blackout_guard or CalendarBlackoutService(
            user_id=self.user_id,
            settings_service=self.settings_service,
        )
        if vpin_guard is not None:
            self.vpin_guard = vpin_guard
        elif hasattr(self.slippage_guard, "vpin_guard") and self.slippage_guard.vpin_guard is not None:
            self.vpin_guard = self.slippage_guard.vpin_guard
        else:
            try:
                from src.services.vpin_toxicity_guard_service import VPINToxicityGuardService
                self.vpin_guard = VPINToxicityGuardService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                )
            except Exception:
                self.vpin_guard = None

        if jump_guard is not None:
            self.jump_guard = jump_guard
        elif hasattr(self.slippage_guard, "jump_guard") and self.slippage_guard.jump_guard is not None:
            self.jump_guard = self.slippage_guard.jump_guard
        else:
            try:
                from src.services.bayesian_jump_diffusion_guard_service import (
                    BayesianJumpDiffusionGuardService,
                )
                self.jump_guard = BayesianJumpDiffusionGuardService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                )
            except Exception:
                self.jump_guard = None

        if rl_sor is not None:
            self.rl_sor = rl_sor
        elif hasattr(self.slippage_guard, "rl_sor") and self.slippage_guard.rl_sor is not None:
            self.rl_sor = self.slippage_guard.rl_sor
        else:
            try:
                from src.services.rl_execution_sor_service import (
                    RLExecutionSmartOrderRoutingService,
                )
                self.rl_sor = RLExecutionSmartOrderRoutingService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                )
            except Exception:
                self.rl_sor = None

        if event_graph is not None:
            self.event_graph = event_graph
        else:
            try:
                from src.services.macro_event_causal_graph_service import (
                    MacroEventCausalGraphService,
                )
                self.event_graph = MacroEventCausalGraphService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                )
            except Exception:
                self.event_graph = None

        if bayesian_hmm_factor is not None:
            self.bayesian_hmm_factor = bayesian_hmm_factor
        else:
            try:
                from src.services.bayesian_hmm_factor_service import (
                    BayesianHMMFactorService,
                )
                self.bayesian_hmm_factor = BayesianHMMFactorService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                )
            except Exception:
                self.bayesian_hmm_factor = None

        try:
            from src.services.unified_risk_gateway_service import UnifiedRiskGatewayService
            self.risk_gateway = UnifiedRiskGatewayService(user_id=self.user_id)
        except Exception:
            self.risk_gateway = None

        if staggered_dip_service is not None:
            self.staggered_dip_service = staggered_dip_service
        else:
            try:
                from src.services.staggered_dip_buying_service import StaggeredDipBuyingService
                self.staggered_dip_service = StaggeredDipBuyingService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                    broker=self.broker,
                    market_clock=self.market_clock,
                )
            except Exception as sde:
                logger.debug(f"Could not initialize StaggeredDipBuyingService: {sde}")
                self.staggered_dip_service = None

        if alpha_spread_bidding_service is not None:
            self.alpha_spread_bidding_service = alpha_spread_bidding_service
        else:
            try:
                from src.services.alpha_spread_bidding_service import AlphaSpreadBiddingService
                self.alpha_spread_bidding_service = AlphaSpreadBiddingService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                    slippage_guard=self.slippage_guard,
                    vpin_guard=self.vpin_guard,
                )
            except Exception as abe:
                logger.debug(f"Could not initialize AlphaSpreadBiddingService: {abe}")
                self.alpha_spread_bidding_service = None

        if convex_optimizer is not None:
            self.convex_optimizer = convex_optimizer
        else:
            try:
                from src.services.multi_factor_convex_sharpe_optimizer_service import (
                    MultiFactorConvexSharpeOptimizerService,
                )
                self.convex_optimizer = MultiFactorConvexSharpeOptimizerService(
                    user_id=self.user_id,
                    settings_service=self.settings_service,
                )
            except Exception as coe:
                logger.debug(f"Could not initialize MultiFactorConvexSharpeOptimizerService: {coe}")
                self.convex_optimizer = None

    async def generate_staggered_dip_plan(
        self,
        batch_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """產出 3-Tier 主力支撐階梯限價吸籌規劃"""
        if self.staggered_dip_service is None:
            from src.services.staggered_dip_buying_service import StaggeredDipBuyingService
            self.staggered_dip_service = StaggeredDipBuyingService(
                user_id=self.user_id,
                settings_service=self.settings_service,
                broker=self.broker,
                market_clock=self.market_clock,
            )
        plan = await self.staggered_dip_service.generate_batch_staggered_plan(batch_number=batch_number)
        return plan.to_dict()

    async def execute_staggered_dip_deployment(
        self,
        batch_number: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """執行 3-Tier 主力支撐階梯限價吸籌"""
        if self.staggered_dip_service is None:
            from src.services.staggered_dip_buying_service import StaggeredDipBuyingService
            self.staggered_dip_service = StaggeredDipBuyingService(
                user_id=self.user_id,
                settings_service=self.settings_service,
                broker=self.broker,
                market_clock=self.market_clock,
            )
        return await self.staggered_dip_service.execute_staggered_dip_deployment(
            batch_number=batch_number,
            force=force,
        )


    async def _get_broker(self) -> Any:
        if self.broker:
            return self.broker
        from src.services.broker_factory import BrokerFactory
        return BrokerFactory.get_broker(self.user_id)

    def _is_risk_parity_enabled(self) -> bool:
        if self.settings_service:
            try:
                val = self.settings_service.get_setting("enable_dynamic_risk_parity")
                if val is not None:
                    return bool(val)
            except Exception:
                return False
        return False

    async def get_portfolio_status(self) -> Dict[str, Any]:
        """獲取帳戶當前資產、閒置現金與防守現金餘額"""
        broker = await self._get_broker()
        if not broker:
            return {"error": "Broker unavailable", "total_equity": 0.0, "available_cash": 0.0}

        account = await broker.get_account()
        total_equity = float(getattr(account, "total_equity", 0.0) or 0.0)
        available_cash = float(getattr(account, "available_cash", 0.0) or 0.0)

        # 動態現金防禦比率（結合體制與設定）
        regime_cash_pct = self.DEFAULT_DEFENSIVE_CASH_PCT
        try:
            from src.services.market_regime_service import MarketRegimeService
            regime_svc = MarketRegimeService()
            policy = await regime_svc.get_current_regime()
            regime_cash_pct = float(getattr(policy, "cash_reserve_pct", self.DEFAULT_DEFENSIVE_CASH_PCT))
        except Exception as e:
            logger.debug(f"Could not load dynamic regime cash reserve: {e}")

        # 設定覆寫（若使用者特別指定最低現金比例）
        target_cash_setting = self.settings_service.get_setting("target_cash_ratio")
        if target_cash_setting is not None:
            try:
                setting_pct = float(target_cash_setting) * 100.0 if float(target_cash_setting) <= 1.0 else float(target_cash_setting)
                regime_cash_pct = max(regime_cash_pct, setting_pct)
            except (ValueError, TypeError):
                pass

        required_reserve_usd = total_equity * (regime_cash_pct / 100.0)
        deployable_cash = max(0.0, available_cash - required_reserve_usd)
        cash_ratio_pct = (available_cash / total_equity * 100.0) if total_equity > 0 else 0.0

        return {
            "total_equity": round(total_equity, 2),
            "available_cash": round(available_cash, 2),
            "cash_ratio_pct": round(cash_ratio_pct, 2),
            "defensive_reserve_pct": round(regime_cash_pct, 2),
            "required_reserve_usd": round(required_reserve_usd, 2),
            "deployable_cash": round(deployable_cash, 2),
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Dynamic candidate selection (replaces the hardcoded 8-ticker batches)
    # 動態候選選擇（取代寫死的 8 檔批次）
    # ═══════════════════════════════════════════════════════════════════════

    def _setting_float(self, key: str, default: float) -> float:
        try:
            val = self.settings_service.get_setting(key, default)
            return float(val) if val is not None else default
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning("Invalid setting %s (%s); using default %s", key, e, default)
            return default

    @staticmethod
    def rank_candidates(
        target_records: List[Dict[str, Any]],
        active_tickers: set,
        holdings: Dict[str, float],
        total_equity: float,
        max_order_usd: float,
        max_tickers: int,
        min_confidence: float,
        min_trade_usd: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """
        Pick buy candidates from optimizer targets restricted to the active universe.
        Eligible = active universe member, target weight > 0, confidence >= min_confidence,
        and a funding gap (target value - current value) >= min_trade_usd. Ranked by
        confidence then gap; each order is capped at max_order_usd.
        自優化器目標（限 active 標的池）挑選買入候選：信心 >= 下限、仍有 >= 最低下單額的缺口，
        依信心再依缺口排序，單筆上限 max_order_usd。
        """
        ranked: List[Dict[str, Any]] = []
        for rec in target_records:
            sym = str(rec.get("ticker") or "").upper()
            if not sym or sym == "CASH" or sym not in active_tickers:
                continue
            weight = float(rec.get("target_weight") or 0.0)
            if weight <= 0:
                continue
            raw_conf = rec.get("confidence_score")
            if raw_conf is None:
                continue
            conf = float(raw_conf) * 10.0 if float(raw_conf) <= 1.0 else float(raw_conf)
            if conf < min_confidence:
                continue
            gap = total_equity * weight - float(holdings.get(sym, 0.0) or 0.0)
            if gap < min_trade_usd:
                continue
            ranked.append({
                "ticker": sym,
                "target_pct": weight,
                "base_amount": round(min(gap, max_order_usd), 2),
                "confidence": conf,
                "role": f"Universe target {weight:.1%} (conf {conf:.1f}/10, gap ${gap:.0f})",
                "_gap": gap,
            })
        ranked.sort(key=lambda c: (-c["confidence"], -c["_gap"]))
        return ranked[:max(1, int(max_tickers))]

    async def _select_dynamic_candidates(
        self,
        total_equity: float,
        holdings: Dict[str, float],
        target_records: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Load universe/targets and rank. Returns [] (with a warning) when nothing qualifies.
        載入標的池與目標並排序；無合格候選時回傳 [] 並記 warning，不退回寫死名單。"""
        from src.repositories.ticker_universe_repository import TickerUniverseRepository
        repo = TickerUniverseRepository()
        if target_records is None:
            target_records = repo.get_target_allocations(self.user_id)
        active = {
            str(u.get("ticker") or "").upper()
            for u in repo.get_all(self.user_id, status="active")
        }
        ranked = self.rank_candidates(
            target_records=target_records,
            active_tickers=active,
            holdings=holdings,
            total_equity=total_equity,
            max_order_usd=single_order_cap_usd(self.settings_service, None),
            max_tickers=int(self._setting_float("batch_deploy_max_tickers", 3)),
            min_confidence=self._setting_float("batch_deploy_min_confidence", 5.5),
        )
        if not ranked:
            logger.warning(
                "BatchCashDeployment: no eligible candidates (active universe=%d, targets=%d); nothing to deploy",
                len(active), len(target_records),
            )
        return ranked

    async def _load_holdings(self) -> Dict[str, float]:
        """Broker positions as {symbol: market_value}; raises on broker failure (no silent empty).
        券商持倉 {代號: 市值}；券商失敗時拋出例外，不靜默回傳空值。"""
        holdings: Dict[str, float] = {}
        broker = await self._get_broker()
        if not broker:
            raise RuntimeError("no broker available to read positions")
        for p in await broker.get_positions():
            sym = getattr(p, "symbol", "")
            for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                if sym.endswith(suffix):
                    sym = sym[:-len(suffix)]
            holdings[sym] = float(getattr(p, "market_value", 0.0) or 0.0)
        return holdings

    async def get_active_batch_number(self) -> int:
        """
        Returns 1 while there is deployable cash AND at least one eligible universe candidate
        with a funding gap; otherwise 0. No longer inferred from fixed tickers.
        有可動用資金且至少一檔 universe 候選仍有缺口時回傳 1，否則 0；不再由固定標的推斷。
        """
        try:
            status = await self.get_portfolio_status()
            deployable = float(status.get("deployable_cash", 0.0) or 0.0)
            if deployable < 10.0:
                return 0
            holdings = await self._load_holdings()
            candidates = await self._select_dynamic_candidates(
                total_equity=float(status.get("total_equity", 0.0) or 0.0),
                holdings=holdings,
            )
        except Exception as e:
            # Unknown state must not look like "all done": surface it.
            # 狀態未知不可偽裝成「已完成」：以 warning 記錄並視為無法判定（回傳 0 並標記）。
            logger.warning("get_active_batch_number: cannot evaluate deployment state (%s); returning 0", e)
            return 0
        return 1 if candidates else 0

    async def get_deployment_plan(self, batch_number: int = 1) -> Dict[str, Any]:
        """
        產出分批建倉規劃：
        第 1 批次（今晚開盤）：動用約 $347 建立 NVDA (~$114), TSM (~$144), AAPL (~$89)
        第 2 批次（下週一）：MSFT (~$91), MU (~$79), AMD (~$77)
        第 3 批次（下週三）：SPCX (~$76) 及高動能擴展
        """
        status = await self.get_portfolio_status()
        deployable = status.get("deployable_cash", 0.0)
        total_equity = status.get("total_equity", 0.0)

        # 讀取標的庫目標配置
        from src.repositories.ticker_universe_repository import TickerUniverseRepository
        repo = TickerUniverseRepository()
        target_records = repo.get_target_allocations(self.user_id)
        targets_map = {t["ticker"]: t for t in target_records if t.get("ticker") not in ("", "CASH")}

        # 讀取券商現有持倉
        broker = await self._get_broker()
        current_holdings = {}
        if broker:
            positions = await broker.get_positions()
            for p in positions:
                sym = getattr(p, "symbol", "")
                for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                    if sym.endswith(suffix):
                        sym = sym[:-len(suffix)]
                current_holdings[sym] = float(getattr(p, "market_value", 0.0) or 0.0)

        # 候選由 universe 目標與研究信心動態決定（不再使用寫死的 8 檔批次）
        selected_batch = await self._select_dynamic_candidates(
            total_equity=float(total_equity or 0.0),
            holdings=current_holdings,
            target_records=target_records,
        )

        # 跨板塊動能注入與 HHI 集中度自癒 (Phase 51)
        portfolio_sector_report = None
        cross_sector_injection_info = None
        alpha_bidding_result = None
        try:
            from src.services.sector_drift_guard_service import SectorDriftGuardService, SectorDriftStatus
            drift_guard = SectorDriftGuardService(
                user_id=self.user_id,
                settings_service=self.settings_service,
                repo=repo,
            )
            raw_positions = positions if broker else []
            portfolio_sector_report = drift_guard.analyze_portfolio_holdings(raw_positions, total_equity=total_equity)

            # 若啟用跨板塊注入，且實盤持倉有過度集中 (DRIFT_BREACH 或 HHI > 0.25 或科技股 > 30% NLV)
            # 單一持倉建立時不判定為板塊過度集中，必須至少持有 2 檔部位
            has_multiple_holdings = len(portfolio_sector_report.holdings_metrics) > 1
            is_breach = (
                has_multiple_holdings
                and (
                    portfolio_sector_report.status == SectorDriftStatus.DRIFT_BREACH
                    or portfolio_sector_report.hhi_index >= drift_guard.portfolio_hhi_breach_threshold
                    or portfolio_sector_report.nlv_sector_weights.get("Technology", 0.0) >= drift_guard.tech_concentration_cap_pct
                    or portfolio_sector_report.sector_weights.get("Technology", 0.0) >= 0.50
                )
            )

            if drift_guard.is_cross_sector_injection_enabled and is_breach and len(selected_batch) >= 2:
                batch_sectors = [drift_guard.resolve_ticker_sector(b["ticker"]) for b in selected_batch]
                tech_heavy_batch = all(s in ("Technology", "Communication Services") for s in batch_sectors)

                if tech_heavy_batch:
                    contender = None
                    excluded_candidates = set()
                    for _ in range(5):
                        candidate = drift_guard.discover_cross_sector_injection_contender(
                            current_positions=raw_positions,
                            total_equity=total_equity,
                            excluded_tickers=excluded_candidates,
                        )
                        if not candidate:
                            break
                        c_sym = candidate["ticker"]
                        # 檢查是否落入財報避開或宏觀黑名單
                        is_candidate_blocked = False
                        if self.blackout_guard:
                            try:
                                b_dec = await self.blackout_guard.evaluate_candidate(c_sym)
                                if b_dec.is_blackout:
                                    is_candidate_blocked = True
                                    logger.info(
                                        "BatchCashDeployment: Cross-sector candidate %s in blackout (%s), rotating to next leader",
                                        c_sym, b_dec.reason
                                    )
                            except Exception as be:
                                logger.debug(f"Candidate blackout check error for {c_sym}: {be}")

                        if is_candidate_blocked:
                            excluded_candidates.add(c_sym)
                        else:
                            contender = candidate
                            break

                    if contender:
                        quota_pct = drift_guard.cross_sector_injection_quota_pct  # 預設 0.35 (35%)

                        # 開盤前動態利差競標與自適應摩擦抵消 (Phase 57)
                        try:
                            if self.alpha_spread_bidding_service and self.alpha_spread_bidding_service.is_enabled:
                                alpha_bidding_result = await self.alpha_spread_bidding_service.evaluate_bidding_for_batch(
                                    batch_items=selected_batch,
                                    contender=contender,
                                    base_quota_pct=quota_pct,
                                )
                                quota_pct = alpha_bidding_result.cross_sector_adjusted_quota_pct
                                c_metric = alpha_bidding_result.candidates.get(contender["ticker"])
                                c_spread_str = f"{c_metric.net_alpha_spread_bps:+.1f} bps" if c_metric else "N/A"
                                logger.info(
                                    "BatchCashDeployment: Alpha spread bidding adjusted quota for %s from %.1f%% to %.1f%% (status: %s, net spread: %s)",
                                    contender["ticker"],
                                    alpha_bidding_result.base_quota_pct * 100.0,
                                    quota_pct * 100.0,
                                    alpha_bidding_result.bidding_status,
                                    c_spread_str,
                                )
                        except Exception as b_err:
                            logger.debug(f"Alpha spread bidding evaluation error: {b_err}")

                        total_orig_amt = sum(b.get("base_amount", 50.0) for b in selected_batch)
                        injected_amt = round(total_orig_amt * quota_pct, 2)
                        scale_factor = max(0.1, 1.0 - quota_pct)

                        new_batch = []
                        for b in selected_batch[:-1]:
                            scaled_b = dict(b)
                            scaled_b["base_amount"] = round(scaled_b["base_amount"] * scale_factor, 2)
                            scaled_b["target_pct"] = round(scaled_b["target_pct"] * scale_factor, 4)
                            new_batch.append(scaled_b)

                        total_batch_target_orig = sum(b.get("target_pct", 0.0) for b in selected_batch)
                        injected_item = {
                            "ticker": contender["ticker"],
                            "target_pct": round(total_batch_target_orig * quota_pct, 4),
                            "base_amount": injected_amt,
                            "confidence": 6.80,
                            "role": contender["role"],
                            "is_cross_sector_injected": True,
                            "injected_sector": contender["sector"],
                        }
                        new_batch.append(injected_item)
                        selected_batch = new_batch
                        cross_sector_injection_info = {
                            "injected_ticker": contender["ticker"],
                            "injected_sector": contender["sector"],
                            "injected_amount": injected_amt,
                            "injected_quota_pct": quota_pct,
                            "reason": f"實盤科技板塊過度集中 (HHI: {portfolio_sector_report.hhi_index:.3f}, 科技佔比: {portfolio_sector_report.sector_weights.get('Technology', 0.0):.1%})，注入非科技龍頭自癒",
                            "alpha_bidding_status": alpha_bidding_result.bidding_status if alpha_bidding_result else None,
                            "alpha_net_spread_bps": (
                                alpha_bidding_result.candidates[contender["ticker"]].net_alpha_spread_bps
                                if (alpha_bidding_result and contender["ticker"] in alpha_bidding_result.candidates)
                                else None
                            ),
                        }
                        logger.info(
                            "BatchCashDeployment: Cross-sector momentum injection active! Injected %s (%s, $%.2f) to de-concentrate HHI",
                            contender["ticker"], contender["sector"], injected_amt
                        )
        except Exception as cs_err:
            logger.debug(f"Cross-sector momentum injection evaluation error: {cs_err}")

        # 若未觸發跨板塊競標評估但利差競標已啟用，對當前批次進行利差與摩擦評估
        if alpha_bidding_result is None:
            try:
                if self.alpha_spread_bidding_service and self.alpha_spread_bidding_service.is_enabled:
                    alpha_bidding_result = await self.alpha_spread_bidding_service.evaluate_bidding_for_batch(
                        batch_items=selected_batch,
                        contender=None,
                    )
            except Exception as be:
                logger.debug(f"Alpha spread bidding batch evaluation error: {be}")

        allocated_items = []
        all_candidates_summary = []
        total_batch_amount = 0.0

        total_batch_target = sum(b.get("target_pct", 0.0) for b in selected_batch)
        # 嘗試加載動態風險平價權重微調 (Phase 33)
        risk_parity_weights = {}
        risk_parity_result = None
        if self._is_risk_parity_enabled():
            try:
                from src.services.risk_parity_cvar_service import RiskParityCVaRService
                rp_svc = RiskParityCVaRService(user_id=self.user_id, settings_service=self.settings_service)
                batch_symbols = [b["ticker"] for b in selected_batch]
                combined_symbols = list(set(batch_symbols + [k for k, v in current_holdings.items() if v > 10.0]))
                if len(combined_symbols) >= 2:
                    rp_res = await rp_svc.get_portfolio_risk_parity_assessment(symbols=combined_symbols)
                    if rp_res and rp_res.asset_metrics:
                        risk_parity_result = rp_res
                        batch_rp_weights = {
                            s: rp_res.asset_metrics[s].final_target_weight
                            for s in batch_symbols if s in rp_res.asset_metrics
                        }
                        sum_batch_rp = sum(batch_rp_weights.values())
                        if sum_batch_rp > 0:
                            for s, w in batch_rp_weights.items():
                                risk_parity_weights[s] = total_batch_target * (w / sum_batch_rp)
            except Exception as e:
                logger.debug(f"Risk parity allocation refinement skipped: {e}")

        for item in selected_batch:
            ticker = item["ticker"]
            base_amt = item["base_amount"]
            target_info = targets_map.get(ticker, {})
            conf = target_info.get("confidence_score")
            conf_val = float(conf) * 10.0 if (conf is not None and float(conf) <= 1.0) else (float(conf) if conf else item["confidence"])

            effective_target_pct = item["target_pct"]
            if risk_parity_weights and ticker in risk_parity_weights:
                effective_target_pct = risk_parity_weights[ticker]

            # 依目前真實總資產動態適應金額（若有較大偏差）
            if total_equity > 0:
                target_value = total_equity * effective_target_pct
                current_val = current_holdings.get(ticker, 0.0)
                need_amount = max(0.0, target_value - current_val)

                # 若現有持倉已達到或超過目標權重 95% 且缺額不足 $10，標記為已達標無需重複加碼
                if current_val >= target_value * 0.95 and need_amount < 10.0:
                    trade_amount = 0.0
                elif need_amount >= 10.0:
                    trade_amount = round(min(base_amt, need_amount), 2)
                elif need_amount > 2.0 and current_val < target_value * 0.85:
                    # 存在合理缺額但小於券商最低門檻，以最低起投額 $10.00 補足
                    trade_amount = 10.00
                else:
                    trade_amount = round(base_amt, 2)
            else:
                trade_amount = round(base_amt, 2)

            is_blackout = False
            blackout_reason = None
            is_jump_acute = False
            jump_intensity = 0.0
            jump_regime = "CALM_DIFFUSION"

            # 統一中央風控閘門檢驗 (Phase 39)
            if self.risk_gateway is not None:

                try:
                    risk_res = await self.risk_gateway.evaluate_trade_risk(
                        ticker=ticker, action="BUY", amount_usd=trade_amount
                    )
                    g_details = risk_res.guard_details or {}

                    cal_info = g_details.get("calendar_blackout") or {}
                    if cal_info.get("is_blackout"):
                        is_blackout = True
                        blackout_reason = cal_info.get("reason")

                    jump_info = g_details.get("jump_diffusion") or {}
                    if jump_info:
                        jump_intensity = jump_info.get("jump_intensity", 0.0)
                        jump_regime = jump_info.get("regime", "CALM_DIFFUSION")
                        if jump_info.get("is_acute_jump") and risk_res.primary_blocker == "JumpDiffusion":
                            is_jump_acute = True
                except Exception as rge:
                    logger.debug(f"Risk gateway unified check fallback for {ticker}: {rge}")

            # 財報日與宏觀黑名單避開守衛檢驗 (退回備份守衛若尚未判定)
            if not is_blackout and self.blackout_guard:
                blackout_decision = await self.blackout_guard.evaluate_candidate(ticker)
                is_blackout = blackout_decision.is_blackout
                blackout_reason = blackout_decision.reason if is_blackout else None

            # 盤中流動性黑洞與成交品質檢驗
            is_black_hole = False
            comp_multiplier = 1.0
            if hasattr(self.slippage_guard, "compensator") and self.slippage_guard.compensator:
                try:
                    c_metrics = self.slippage_guard.compensator.get_metrics(ticker)
                    comp_multiplier = c_metrics.slippage_multiplier
                    if c_metrics.sample_count >= 2 and c_metrics.slippage_multiplier >= 2.5 and c_metrics.adverse_selection_count >= 2:
                        is_black_hole = True
                except Exception:
                    is_black_hole = False

            # 貝葉斯跳躍擴散守衛檢驗 (若尚未由閘門判定)
            if not is_jump_acute and self.jump_guard and getattr(self.jump_guard, "is_enabled", True):
                try:
                    j_eval = await self.jump_guard.evaluate_ticker(ticker)
                    if j_eval:
                        jump_intensity = j_eval.jump_intensity
                        jump_regime = (
                            j_eval.regime.value
                            if hasattr(j_eval.regime, "value")
                            else str(j_eval.regime)
                        )
                        if j_eval.is_acute_jump or j_eval.recommended_action == "DEFER":
                            is_jump_acute = True
                except Exception as je:
                    logger.debug(f"Candidate jump evaluation non-blocking error for {ticker}: {je}")


            # 宏觀突發事件因果圖譜受損度檢驗 (Phase 37)
            is_event_shocked = False
            event_damage_score = 0.0
            event_damage_level = "NEUTRAL"
            event_shock_reason = None
            if self.event_graph and getattr(self.event_graph, "is_enabled", True):
                try:
                    dmg_eval = await self.event_graph.evaluate_ticker_damage(ticker)
                    if dmg_eval:
                        event_damage_score = dmg_eval.net_damage
                        event_damage_level = (
                            dmg_eval.damage_level.value
                            if hasattr(dmg_eval.damage_level, "value")
                            else str(dmg_eval.damage_level)
                        )
                        if (
                            event_damage_score <= -0.35
                            or dmg_eval.recommended_action in ("DEFER", "TRIM", "BLOCK")
                            or (event_damage_level in ("SEVERE_DAMAGE", "MODERATE_DAMAGE") and event_damage_score <= -0.30)
                        ):
                            is_event_shocked = True
                            event_shock_reason = (
                                f"因果傳播鏈受損嚴重 (受損度: {event_damage_score:+.2f}, 衝擊級別: {event_damage_level})"
                            )
                except Exception as ee:
                    logger.debug(f"Candidate event graph damage evaluation error for {ticker}: {ee}")

            # 若標的落入財報/宏觀避開視窗、流動性黑洞、跳躍熔斷或因果圖譜重創，不於此批次執行以防極端波動
            raw_trade_amount = trade_amount
            if is_blackout or is_black_hole or is_jump_acute or is_event_shocked:
                trade_amount = 0.0

            is_tail_alert = False
            if risk_parity_result and ticker in risk_parity_result.asset_metrics:
                is_tail_alert = bool(risk_parity_result.asset_metrics[ticker].tail_risk_flag)

            is_executable = (
                trade_amount >= 10.0
                and not is_blackout
                and not is_black_hole
                and not is_jump_acute
                and not is_event_shocked
            )
            candidate_entry = {
                "ticker": ticker,
                "amount_usd": trade_amount if is_executable else 0.0,
                "planned_amount_usd": round(raw_trade_amount, 2),
                "allocated_amount": trade_amount if is_executable else 0.0,
                "confidence_score": round(conf_val, 2),
                "target_pct": effective_target_pct,
                "base_target_pct": item["target_pct"],
                "risk_parity_target_pct": round(effective_target_pct, 4) if risk_parity_weights else None,
                "cvar_tail_risk_flag": is_tail_alert,
                "role": item["role"],
                "rationale": f"第 {batch_number} 批次建倉配置: {item['role']} (${raw_trade_amount:.2f})",
                "already_satisfied": (current_val >= target_value * 0.95) if total_equity > 0 else False,
                "is_cross_sector_injected": item.get("is_cross_sector_injected", False),
                "injected_sector": item.get("injected_sector"),
                "bidding_metric": (
                    alpha_bidding_result.candidates[ticker].to_dict()
                    if (alpha_bidding_result and ticker in alpha_bidding_result.candidates)
                    else None
                ),
                "blackout_active": is_blackout,
                "blackout_reason": blackout_reason,
                "liquidity_black_hole": is_black_hole,
                "slippage_multiplier": round(comp_multiplier, 2),
                "jump_intensity": round(jump_intensity, 4),
                "jump_regime": jump_regime,
                "is_acute_jump": is_jump_acute,
                "event_shock_active": is_event_shocked,
                "event_damage_score": round(event_damage_score, 4),
                "event_damage_level": event_damage_level,
                "event_shock_reason": event_shock_reason,
            }
            all_candidates_summary.append(candidate_entry)

            if is_executable:
                allocated_items.append(candidate_entry)
                total_batch_amount += trade_amount

        # 動態縮放：若所需金額超過可支配資金但可支配資金 >= 10.0，等比縮放以確保不穿透防守儲備
        if total_batch_amount > deployable and deployable >= 10.0 and allocated_items:
            ratio = deployable / total_batch_amount
            scaled_items = []
            rem_cash = deployable
            for it in allocated_items:
                scaled_amt = round(it["amount_usd"] * ratio, 2)
                if scaled_amt >= 10.0 and scaled_amt <= rem_cash:
                    it["amount_usd"] = scaled_amt
                    it["allocated_amount"] = scaled_amt
                    scaled_items.append(it)
                    rem_cash -= scaled_amt
            if scaled_items:
                allocated_items = scaled_items
                total_batch_amount = round(sum(i["amount_usd"] for i in allocated_items), 2)

        # 檢驗可動用資金是否足夠覆蓋批次下單
        can_execute = (
            deployable >= total_batch_amount
            and total_batch_amount >= 10.0
            and len(allocated_items) > 0
            and status.get("available_cash", 0.0) > status.get("required_reserve_usd", 0.0)
        )

        expected_remaining_cash = max(0.0, status.get("available_cash", 0.0) - total_batch_amount)
        expected_cash_ratio = (expected_remaining_cash / total_equity * 100.0) if total_equity > 0 else 0.0

        # 產出全批次標的財報與宏觀日曆摘要
        candidate_tickers = [c["ticker"] for c in all_candidates_summary]
        calendar_summary = await self.blackout_guard.get_upcoming_calendar_summary(tickers=candidate_tickers)

        # 產出候選標的流動性與成交品質追蹤摘要
        fill_quality_summary = {}
        if hasattr(self.slippage_guard, "compensator") and self.slippage_guard.compensator:
            try:
                fill_quality_summary = self.slippage_guard.compensator.get_fill_quality_summary(candidate_tickers)
            except Exception as fq_err:
                logger.debug(f"Non-blocking fill quality summary error: {fq_err}")

        # 產出候選標的微觀結構訂單流毒性與 Kyle's Lambda 摘要
        vpin_summary = {}
        if self.vpin_guard and getattr(self.vpin_guard, "is_enabled", True):
            try:
                vpin_obj = await self.vpin_guard.get_portfolio_vpin_assessment(candidate_tickers)
                vpin_summary = vpin_obj.to_dict()
                for it in allocated_items:
                    t_sym = it.get("ticker", "")
                    ass = vpin_obj.assessments.get(t_sym)
                    if ass:
                        it["vpin"] = ass.vpin
                        it["kyle_lambda"] = ass.kyle_lambda
                        it["vpin_regime"] = ass.regime.value
                        it["is_vpin_toxic"] = ass.is_toxic
                        if ass.is_toxic:
                            it["vpin_action"] = "DEFER"
            except Exception as vpin_err:
                logger.debug(f"Non-blocking VPIN summary error in deployment plan: {vpin_err}")

        # 產出候選標的多期動態貝葉斯跳躍擴散摘要
        jump_summary = {}
        if self.jump_guard and getattr(self.jump_guard, "is_enabled", True):
            try:
                jump_obj = await self.jump_guard.get_portfolio_jump_assessment(candidate_tickers)
                jump_summary = jump_obj.to_dict()
                for it in allocated_items:
                    t_sym = it.get("ticker", "")
                    ass = jump_obj.assessments.get(t_sym)
                    if ass:
                        it["jump_intensity"] = ass.jump_intensity
                        it["jump_regime"] = ass.regime.value
                        it["is_acute_jump"] = ass.is_acute_jump
                        if ass.is_acute_jump or ass.recommended_action == "DEFER":
                            it["jump_action"] = "DEFER"
            except Exception as jump_err:
                logger.debug(f"Non-blocking jump summary error in deployment plan: {jump_err}")

        # 產出候選標的強化學習自適應智慧拆單排程 (RL SOR Phase 36)
        rl_sor_summary = {}
        if self.rl_sor and getattr(self.rl_sor, "is_enabled", True):
            try:
                sor_plans = {}
                for it in allocated_items:
                    t_sym = it.get("ticker", "")
                    amt = it.get("amount_usd", 0.0)
                    if amt >= 10.0:
                        plan = await self.rl_sor.generate_execution_plan(
                            symbol=t_sym,
                            total_amount_usd=amt,
                            target_window_minutes=15,
                        )
                        sor_plans[t_sym] = {
                            "recommended_action": plan.selected_action,
                            "recommended_slices": plan.recommended_slices_count,
                            "expected_cost_bps": plan.total_expected_cost_bps,
                            "q_value": plan.q_value,
                            "summary": plan.strategy_summary,
                        }
                        it["sor_action"] = plan.selected_action
                        it["recommended_slices"] = plan.recommended_slices_count
                        it["sor_expected_cost_bps"] = plan.total_expected_cost_bps
                rl_sor_summary = {
                    "is_enabled": True,
                    "plans": sor_plans,
                }
            except Exception as sor_err:
                logger.debug(f"Non-blocking RL SOR summary error in deployment plan: {sor_err}")

        # 產出候選標的宏觀突發事件因果圖譜衝擊摘要 (Phase 37)
        event_graph_summary = {}
        if self.event_graph and getattr(self.event_graph, "is_enabled", True):
            try:
                g_eval = await self.event_graph.evaluate_portfolio_shock(candidate_tickers)
                event_graph_summary = g_eval.to_dict()
                for it in allocated_items:
                    t_sym = it.get("ticker", "")
                    t_dmg = g_eval.ticker_damages.get(t_sym)
                    if t_dmg:
                        it["event_damage_score"] = t_dmg.net_damage
                        it["event_damage_level"] = (
                            t_dmg.damage_level.value
                            if hasattr(t_dmg.damage_level, "value")
                            else str(t_dmg.damage_level)
                        )
            except Exception as eg_err:
                logger.debug(f"Non-blocking event graph summary error in deployment plan: {eg_err}")

        # 產出貝葉斯隱馬爾可夫體制機率與連續因子權重摘要 (Phase 38)
        bayesian_hmm_summary = {}
        if self.bayesian_hmm_factor and getattr(self.bayesian_hmm_factor, "is_enabled", True):
            try:
                post = self.bayesian_hmm_factor.get_current_posterior()
                bayesian_hmm_summary = post.to_dict()
            except Exception as hmm_err:
                logger.debug(f"Non-blocking Bayesian HMM summary error in deployment plan: {hmm_err}")

        # 產出最優夏普邊界二次規劃配置摘要 (Phase 60B)
        convex_sharpe_summary = None
        if self.convex_optimizer and getattr(self.convex_optimizer, "is_enabled", True) and candidate_tickers:
            try:
                opt_res = await self.convex_optimizer.optimize_recirculated_capital_allocation(
                    candidate_tickers=candidate_tickers,
                    available_capital_usd=total_batch_amount,
                )
                if opt_res:
                    convex_sharpe_summary = opt_res.to_dict()
                    weight_map = {w.ticker: w for w in opt_res.weights}
                    for it in allocated_items:
                        sym = it.get("ticker")
                        if sym in weight_map:
                            it["convex_optimal_weight"] = weight_map[sym].target_weight
                            it["convex_marginal_sharpe"] = weight_map[sym].marginal_sharpe_contribution
            except Exception as co_err:
                logger.debug(f"Non-blocking convex Sharpe optimization error in deployment plan: {co_err}")

        return {
            "batch_number": batch_number,
            "status": status,
            "portfolio_status": status,
            "can_execute": can_execute,
            # Explicit reason when nothing qualified, so callers can show it (never a silent empty plan).
            # 無任何合格候選時明確標記原因，呼叫端可顯示，不會是靜默的空計畫。
            "no_eligible_candidates": len(selected_batch) == 0,
            "total_batch_amount": round(total_batch_amount, 2),
            "items": allocated_items,
            "plan_items": allocated_items,
            "all_candidates": all_candidates_summary,
            "expected_remaining_cash": round(expected_remaining_cash, 2),
            "projected_cash_after_deployment": round(expected_remaining_cash, 2),
            "expected_cash_ratio": round(expected_cash_ratio, 2),
            "calendar_summary": calendar_summary,
            "fill_quality_summary": fill_quality_summary,
            "vpin_summary": vpin_summary,
            "jump_summary": jump_summary,
            "rl_sor_summary": rl_sor_summary,
            "event_graph_summary": event_graph_summary,
            "bayesian_hmm_summary": bayesian_hmm_summary,
            "risk_parity_applied": bool(risk_parity_weights),
            "risk_concentration_hhi": round(risk_parity_result.cvar_hhi_risk, 4) if risk_parity_result else None,
            "effective_risk_assets": round(risk_parity_result.effective_risk_assets_cvar, 2) if risk_parity_result else None,
            "portfolio_sector_report": portfolio_sector_report.to_dict() if portfolio_sector_report else None,
            "cross_sector_injection": cross_sector_injection_info,
            "alpha_bidding_summary": alpha_bidding_result.to_dict() if alpha_bidding_result else None,
            "convex_sharpe_summary": convex_sharpe_summary,
        }

    async def warmup_batch_quotes(
        self, batch_number: Optional[int] = None, force_refresh: bool = True
    ) -> Dict[str, Any]:
        """
        開盤前 15 分鐘 (09:20 EST) 預熱即將建倉標的報價與快取。
        1. 確定當前待執行批次（若為 None 則自適應推進）。
        2. 若 batch_number == 0，表示全數完成或無待建倉標的，直接回傳。
        3. 針對批次候選標的預先抓取即時報價 (Polygon/Finnhub/MarketDataService)，
           預熱連線池、計算買賣價差與預先驗證報價品質。
        4. 寫入 Redis 快取供開盤 09:35 EST 毫秒級讀取與守衛審核。
        """
        if batch_number is None or batch_number <= 0:
            batch_number = await self.get_active_batch_number()

        if batch_number == 0:
            logger.info("BatchCashDeployment: All batches completed, skipping quote warmup.")
            return {
                "status": "all_batches_completed",
                "batch_number": 0,
                "candidates_count": 0,
                "quotes": {},
                "message": "分批建倉已全數完成或可支配資金已達 20% 防守底線，無需預熱報價。",
            }

        plan = await self.get_deployment_plan(batch_number=batch_number)
        items = plan.get("items", [])
        if not items:
            return {
                "status": "empty_batch",
                "batch_number": batch_number,
                "candidates_count": 0,
                "quotes": {},
                "message": f"第 {batch_number} 批次無候選標的。",
            }

        logger.info(
            f"BatchCashDeployment: Warming up quotes for Batch {batch_number} "
            f"({len(items)} candidates: {[item['ticker'] for item in items]})"
        )

        quotes_map: Dict[str, Any] = {}
        for item in items:
            ticker = item["ticker"]
            try:
                quote = await self.slippage_guard.get_ticker_quote(ticker, force_refresh=force_refresh)
                spread_pct = quote.get("spread_pct")
                bid = quote.get("bid")
                ask = quote.get("ask")
                last = quote.get("last")
                has_price = (bid is not None and bid > 0) or (last is not None and last > 0)
                quotes_map[ticker] = {
                    "bid": bid,
                    "ask": ask,
                    "last": last,
                    "mid": quote.get("mid"),
                    "spread_pct": spread_pct,
                    "source": quote.get("source") or quote.get("provider", "unknown"),
                    "ready": bool(has_price),
                }
            except Exception as q_err:
                logger.warning(f"Failed to warmup quote for {ticker}: {q_err}")
                quotes_map[ticker] = {
                    "ready": False,
                    "error": str(q_err),
                }

        warmed_at = datetime.now(timezone.utc).isoformat()
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            warmup_payload = {
                "batch_number": batch_number,
                "warmed_at": warmed_at,
                "quotes": quotes_map,
                "can_execute": plan.get("can_execute", False),
            }
            await r.set(
                f"batch_deployment:warmup_quotes:{self.user_id}",
                json.dumps(warmup_payload),
                ex=1800,  # 30 分鐘有效
            )
            logger.info(f"✓ Cached warmup quotes for Batch {batch_number} in Redis (TTL: 1800s)")
        except Exception as r_err:
            logger.debug(f"Could not cache warmup quotes in Redis: {r_err}")

        return {
            "status": "warmed_up",
            "batch_number": batch_number,
            "candidates_count": len(items),
            "quotes": quotes_map,
            "can_execute": plan.get("can_execute", False),
            "warmed_at": warmed_at,
        }

    async def execute_batch(
        self,
        batch_number: Optional[int] = None,
        force: bool = False,
        enforce_market_hours: bool = True,
        deployment_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        執行特定批次建倉下單（整合開盤波動率防線與買賣價差熔斷守衛）。
        若 batch_number 為 None，自動調用 get_active_batch_number() 自適應推進。
        若 deployment_mode 為 STAGGERED_LIMIT，則執行主力支撐階梯限價吸籌。
        """
        if deployment_mode == "STAGGERED_LIMIT":
            logger.info("BatchCashDeploymentService: delegating to StaggeredDipBuyingService (SSOT execution)")
            return await self.execute_staggered_dip_deployment(batch_number=batch_number, force=force)

        # 0. 自適應判定當前應執行批次
        if batch_number is None or batch_number <= 0:
            batch_number = await self.get_active_batch_number()
            if batch_number == 0:
                msg = "分批建倉計畫已全數執行完畢，或可支配資金已達 20% 防守底線，無需額外建倉。"
                logger.info(f"Batch Cash Deployment: {msg}")
                return {
                    "success": True,
                    "status": "all_batches_completed",
                    "message": msg,
                    "batch_number": 0,
                    "executed_trades": [],
                    "errors": [],
                }
        # 1. 市場開市檢查
        if enforce_market_hours and not force:
            if not self.market_clock.is_market_open():
                status_clock = self.market_clock.get_market_status()
                msg = (
                    f"美股市場休市中（下次開市：{status_clock.get('next_open')}）。"
                    f"為保護資金免受非交易時段盤前盤後滑點侵蝕，請待開盤後（09:35 EST）執行。"
                )
                logger.warning(f"Batch Cash Deployment blocked: {msg}")
                return {
                    "success": False,
                    "status": "market_closed",
                    "message": msg,
                    "market_status": status_clock,
                }

        # 2. 開盤前 5 分鐘波動率視窗檢查 (09:30-09:35 EST)
        if enforce_market_hours and not force:
            is_opening, open_reason = self.slippage_guard.is_opening_auction_window()
            if is_opening:
                # 若僅相差 2 分鐘以內即將結束開盤保護窗口，非同步等待至保護結束後自動繼續執行，避免錯過交易日排程
                try:
                    now_ny = datetime.now(self.slippage_guard._nyse_tz)
                    open_time = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
                    delay_m = self.slippage_guard._get_setting_int("market_open_delay_minutes", 5)
                    delay_cutoff = open_time + timedelta(minutes=delay_m)
                    remaining = int((delay_cutoff - now_ny).total_seconds())
                    if 0 < remaining <= 120:
                        wait_sec = remaining + 2
                        logger.info(
                            f"Opening window active ({open_reason}). "
                            f"Auto-waiting {wait_sec}s for buffer window to clear before batch execution..."
                        )
                        await asyncio.sleep(wait_sec)
                        is_opening, open_reason = self.slippage_guard.is_opening_auction_window()
                except Exception as wait_err:
                    logger.debug(f"Failed to auto-wait opening window: {wait_err}")

            if is_opening:
                logger.warning(f"Batch Cash Deployment postponed: {open_reason}")
                return {
                    "success": False,
                    "status": "opening_window_deferred",
                    "message": open_reason,
                    "retry_after_seconds": 60,
                }

        # 2.5 重大宏觀事件避開視窗檢驗 (FOMC / CPI / NFP)
        if enforce_market_hours and not force:
            macro_eval = self.blackout_guard.evaluate_macro_blackout()
            if macro_eval.is_blackout:
                logger.warning(f"Batch Cash Deployment postponed due to macro blackout: {macro_eval.reason}")
                return {
                    "success": False,
                    "status": "macro_blackout_deferred",
                    "message": macro_eval.reason,
                    "event_type": macro_eval.event_type,
                    "event_name": macro_eval.event_name,
                    "event_time": macro_eval.event_time,
                }

        # 3. 產出批次建倉清單
        plan = await self.get_deployment_plan(batch_number=batch_number)
        if not plan.get("can_execute") and not force:
            msg = (
                f"可部署現金不足或未達最低下單門檻 (可部署: ${plan.get('status', {}).get('deployable_cash', 0):.2f}, "
                f"批次所需: ${plan.get('total_batch_amount', 0):.2f})。"
            )
            logger.info(f"Batch Cash Deployment: {msg}")
            return {
                "success": False,
                "status": "insufficient_deployable_cash",
                "message": msg,
                "plan": plan,
            }

        items = plan.get("items", [])
        executed_trades = []
        errors = []

        from src.services.automated_trading_service import AutomatedTradingService
        from src.services.notification_service import NotificationService
        trading_service = AutomatedTradingService(
            settings_repo=self.settings_service.settings_repo,
            notification_service=NotificationService.create_with_settings(
                settings_service=self.settings_service, user_id=self.user_id
            ),
        )

        logger.info(f"BatchCashDeployment: Starting execution of Batch {batch_number} ({len(items)} candidates)")

        for item in items:
            ticker = item["ticker"]
            amount_usd = round(item["amount_usd"], 2)
            conf = item["confidence_score"]
            role = item["role"]

            # 券商微股數與最低下單物理約束 ($10.00 USD)
            if amount_usd < 10.0:
                msg = f"下單金額 ${amount_usd:.2f} 低於券商最低門檻 ($10.00 USD)，略過不送出"
                logger.warning(f"Batch candidate {ticker}: {msg}")
                executed_trades.append({
                    "ticker": ticker,
                    "amount_usd": amount_usd,
                    "status": "skipped",
                    "reason": msg,
                })
                continue

            # 財報日與個股黑名單避開守衛檢驗
            blackout_eval = await self.blackout_guard.evaluate_candidate(ticker)
            if blackout_eval.is_blackout and not force:
                logger.warning(
                    f"Calendar Blackout Guard triggered for {ticker}: {blackout_eval.reason}. Skipping trade."
                )
                executed_trades.append({
                    "ticker": ticker,
                    "amount_usd": amount_usd,
                    "status": "blackout_deferred",
                    "reason": blackout_eval.reason,
                    "event_type": blackout_eval.event_type,
                })
                continue

            # 宏觀突發事件因果圖譜重創檢驗 (Phase 37)
            if self.event_graph and getattr(self.event_graph, "is_enabled", True) and not force:
                try:
                    eg_dmg = await self.event_graph.evaluate_ticker_damage(ticker)
                    if eg_dmg and (
                        eg_dmg.net_damage <= -0.35
                        or eg_dmg.recommended_action in ("DEFER", "TRIM", "BLOCK")
                        or (hasattr(eg_dmg, "damage_level") and getattr(eg_dmg.damage_level, "value", str(eg_dmg.damage_level)) == "SEVERE_DAMAGE")
                    ):
                        d_lvl = eg_dmg.damage_level.value if hasattr(eg_dmg.damage_level, "value") else str(eg_dmg.damage_level)
                        reason = (
                            f"宏觀突發事件因果圖譜熔斷觸發: {ticker} 淨受損度 {eg_dmg.net_damage:+.2f} "
                            f"({d_lvl})，受突發傳導衝擊波波及，暫緩建倉避免接飛刀"
                        )
                        logger.warning(reason)
                        executed_trades.append({
                            "ticker": ticker,
                            "amount_usd": amount_usd,
                            "status": "event_graph_deferred",
                            "reason": reason,
                            "event_damage_score": eg_dmg.net_damage,
                            "event_damage_level": d_lvl,
                            "causal_chains": [c.to_dict() for c in getattr(eg_dmg, "causal_chains", [])[:2]],
                        })
                        continue
                except Exception as eg_trade_err:
                    logger.debug(f"Non-blocking event graph trade check error: {eg_trade_err}")

            # 防滑點與買賣價差熔斷守衛檢驗
            slippage_eval = await self.slippage_guard.evaluate_trade(
                ticker=ticker,
                action="BUY",
                amount_usd=amount_usd,
                check_opening_window=not force,
            )

            if not slippage_eval.passed and not force:
                is_jump_acute = (
                    "跳躍" in (slippage_eval.reason or "")
                    or "jump" in (slippage_eval.reason or "").lower()
                    or getattr(slippage_eval, "jump_regime", "") == "ACUTE_JUMP_REGIME"
                    or (getattr(slippage_eval, "jump_intensity", None) is not None and getattr(slippage_eval, "jump_intensity", 0.0) >= 6.0)
                )
                is_vpin_toxic = (
                    "知情交易" in (slippage_eval.reason or "")
                    or "VPIN" in (slippage_eval.reason or "")
                    or (getattr(slippage_eval, "vpin", None) is not None and getattr(slippage_eval, "vpin", 0.0) >= 0.40)
                )
                is_black_hole = (
                    getattr(slippage_eval, "fill_quality_grade", "") == "F"
                    or "黑洞" in (slippage_eval.reason or "")
                    or "black hole" in (slippage_eval.reason or "").lower()
                )
                if is_jump_acute:
                    trade_status = "jump_diffusion_deferred"
                elif is_vpin_toxic:
                    trade_status = "vpin_toxicity_deferred"
                elif is_black_hole:
                    trade_status = "liquidity_black_hole_deferred"
                else:
                    trade_status = "circuit_breaker_deferred"

                logger.warning(
                    f"Slippage Circuit Breaker triggered for {ticker} ({trade_status}): {slippage_eval.reason}. Skipping trade."
                )
                executed_trades.append({
                    "ticker": ticker,
                    "amount_usd": amount_usd,
                    "status": trade_status,
                    "reason": slippage_eval.reason,
                    "spread_pct": slippage_eval.spread_pct,
                    "fill_quality_grade": getattr(slippage_eval, "fill_quality_grade", None),
                    "fill_quality_multiplier": getattr(slippage_eval, "fill_quality_multiplier", None),
                    "vpin": getattr(slippage_eval, "vpin", None),
                    "kyle_lambda": getattr(slippage_eval, "kyle_lambda", None),
                    "jump_intensity": getattr(slippage_eval, "jump_intensity", None),
                    "jump_regime": getattr(slippage_eval, "jump_regime", None),
                })
                continue

            # 透過 AutomatedTradingService 執行自動下單，含短暫瞬態錯誤重試 (Transient Error Retry)
            max_retries = 2
            attempt = 0
            result: Dict[str, Any] = {}

            while attempt < max_retries:
                attempt += 1
                try:
                    result = await trading_service.evaluate_and_execute_trade(
                        user_id=self.user_id,
                        ticker=ticker,
                        action="BUY",
                        quantity=amount_usd,
                        confidence_score=conf,
                        rationale=item["rationale"],
                        strategy_name="cash_deployment",
                    )
                    err_str = str(result.get("error") or result.get("reason") or "").lower()
                    is_transient = "429" in err_str or "rate limit" in err_str or "timeout" in err_str
                    if is_transient and attempt < max_retries:
                        logger.warning(
                            f"Transient broker error for {ticker} ({err_str}); retrying in 2.0s (attempt {attempt}/{max_retries})..."
                        )
                        await asyncio.sleep(2.0)
                        continue
                    break
                except Exception as trade_err:
                    err_str = str(trade_err).lower()
                    is_transient = "429" in err_str or "rate limit" in err_str or "timeout" in err_str
                    if is_transient and attempt < max_retries:
                        logger.warning(
                            f"Transient exception for {ticker} ({trade_err}); retrying in 2.0s (attempt {attempt}/{max_retries})..."
                        )
                        await asyncio.sleep(2.0)
                        continue
                    logger.error(f"Error executing cash deployment for {ticker}: {trade_err}", exc_info=True)
                    result = {"status": "error", "error": str(trade_err)}
                    break

            is_ok = (
                result.get("status") in ("success", "executed")
                or result.get("execution_status") in ("executed", "pending")
            )
            trade_status = "executed" if is_ok else result.get("status", "failed")
            order_id = result.get("order_id")
            fail_reason = result.get("reason") or result.get("error") or result.get("_fallback_reason")

            executed_trades.append({
                "ticker": ticker,
                "amount_usd": amount_usd,
                "status": trade_status,
                "order_id": order_id,
                "spread_pct": slippage_eval.spread_pct if slippage_eval else None,
                "adaptive_limit": slippage_eval.adaptive_limit_price if slippage_eval else None,
                "sor_action": getattr(slippage_eval, "rl_sor_action", None) if slippage_eval else None,
                "sor_slices": getattr(slippage_eval, "rl_sor_slices", None) if slippage_eval else None,
                "reason": fail_reason,
            })

            if not is_ok:
                errors.append(f"{ticker} buy failed: {fail_reason or 'unknown'}")
            else:
                logger.info(f"✓ Batch {batch_number}: Successfully executed BUY {ticker} (${amount_usd:.2f})")
                # 避免連續併發下單撞擊券商速率限制
                await asyncio.sleep(1.5)

        # 將事前避開之候選標的 (財報避開 / 流動性黑洞 / 跳躍熔斷) 納入執行審查記錄，確保不提前推進批次並如實呈報
        for cand in plan.get("all_candidates", []):
            c_ticker = cand.get("ticker")
            if any(t["ticker"] == c_ticker for t in executed_trades):
                continue
            planned_amt = cand.get("planned_amount_usd") or cand.get("amount_usd", 0.0)
            if cand.get("is_acute_jump"):
                executed_trades.append({
                    "ticker": c_ticker,
                    "amount_usd": planned_amt,
                    "status": "jump_diffusion_deferred",
                    "reason": f"標的 {c_ticker} 處於重度跳躍衝擊體制 (跳躍強度 {cand.get('jump_intensity', 6.0):.2f} 次/年)，觸發貝葉斯跳躍擴散熔斷暫緩下單",
                    "jump_intensity": cand.get("jump_intensity"),
                    "jump_regime": cand.get("jump_regime", "ACUTE_JUMP_REGIME"),
                })
            elif cand.get("liquidity_black_hole"):
                executed_trades.append({
                    "ticker": c_ticker,
                    "amount_usd": planned_amt,
                    "status": "liquidity_black_hole_deferred",
                    "reason": f"標的 {c_ticker} 近期成交品質嚴重惡化 (補償乘數 {cand.get('slippage_multiplier', 2.5):.2f}x)，觸發盤中流動性黑洞熔斷暫緩下單",
                    "slippage_multiplier": cand.get("slippage_multiplier"),
                    "fill_quality_grade": "F",
                })
            elif cand.get("blackout_active"):
                executed_trades.append({
                    "ticker": c_ticker,
                    "amount_usd": planned_amt,
                    "status": "blackout_deferred",
                    "reason": cand.get("blackout_reason", "落入財報/宏觀保護窗口"),
                })
            elif cand.get("event_shock_active"):
                executed_trades.append({
                    "ticker": c_ticker,
                    "amount_usd": planned_amt,
                    "status": "event_graph_deferred",
                    "reason": cand.get("event_shock_reason") or f"標的 {c_ticker} 遭受宏觀突發事件因果傳導重創，暫緩建倉",
                    "event_damage_score": cand.get("event_damage_score"),
                    "event_damage_level": cand.get("event_damage_level"),
                })

        # 交易後持倉撮合驗證 (Post-trade Position Verification)
        actual_filled_tickers: List[str] = []
        try:
            if any(t.get("status") in ("executed", "pending") for t in executed_trades):
                await asyncio.sleep(1.0)
            broker = await self._get_broker()
            if broker:
                fresh_positions = await broker.get_positions()
                for p in (fresh_positions or []):
                    sym = str(getattr(p, "symbol", "")).strip().upper()
                    for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                        if sym.endswith(suffix):
                            sym = sym[:-len(suffix)]
                    val = float(getattr(p, "market_value", 0.0) or getattr(p, "current_value", 0.0) or 0.0)
                    if val >= 10.0:
                        actual_filled_tickers.append(sym)
        except Exception as pos_err:
            logger.debug(f"Post-trade position verification non-blocking error: {pos_err}")

        for t in executed_trades:
            t["verified_in_holdings"] = (t["ticker"] in actual_filled_tickers)

        # 交易後資產與剩餘現金重算
        post_status = await self.get_portfolio_status()

        # 發送全自主執行通報
        await self._send_deployment_notification(
            batch_number=batch_number,
            executed_trades=executed_trades,
            post_status=post_status,
        )

        # 4. 批次推進狀態守衛：僅在當前批次全數成功（或資金已用罄）時才推進至下一批次
        successful_trades = [
            t for t in executed_trades
            if t.get("status") in ("executed", "pending") or t.get("verified_in_holdings")
        ]
        unfulfilled_trades = [
            t for t in executed_trades
            if t.get("status") not in ("executed", "pending") and not t.get("verified_in_holdings")
        ]

        if successful_trades:
            try:
                from src.infrastructure.cache.redis_client import get_redis
                r = await get_redis(decode_responses=True)
                now_iso = datetime.now(timezone.utc).isoformat()
                await r.set(f"batch_deployment:last_executed_at:{self.user_id}", now_iso)
                await r.set(f"batch_deployment:last_batch_executed:{self.user_id}", str(batch_number))

                if post_status.get("deployable_cash", 0.0) < 10.0:
                    next_batch = 0
                    await r.set(f"batch_deployment:current_batch:{self.user_id}", "0")
                    logger.info(
                        f"Deployable cash depleted (${post_status.get('deployable_cash', 0.0):.2f} < $10.00). "
                        f"Batch progression marked complete (0)."
                    )
                elif len(unfulfilled_trades) == 0:
                    next_batch = (batch_number + 1) if batch_number < 3 else 0
                    await r.set(f"batch_deployment:current_batch:{self.user_id}", str(next_batch))
                    logger.info(f"Advanced batch state to {next_batch} after full execution of Batch {batch_number}")
                else:
                    # 部分標的遭熔斷暫緩或下單失敗，保留當前批次以供後續補單，避免跳過標的
                    logger.info(
                        f"Batch {batch_number} partially executed ({len(successful_trades)}/{len(items)}). "
                        f"Retaining batch {batch_number} for subsequent completion of deferred candidates."
                    )
            except Exception as e:
                logger.warning(f"Failed to record batch advancement in redis: {e}")

        # 5. 若有待確認掛單 (pending orders)，排定 15 秒後自動對賬確認撮合成交
        pending_trades = [t for t in executed_trades if t.get("status") == "pending"]
        if pending_trades:
            try:
                from src.infrastructure.tasks import reconcile_pending_orders_task
                reconcile_pending_orders_task.apply_async(args=[self.user_id], countdown=15)
                logger.info(f"Scheduled prompt order reconciliation (in 15s) for {len(pending_trades)} pending batch orders.")
            except Exception as recon_err:
                logger.debug(f"Could not schedule prompt reconciliation task: {recon_err}")

        return {
            "success": len(errors) == 0 and any(t.get("status") == "executed" for t in executed_trades),
            "batch_number": batch_number,
            "executed_trades": executed_trades,
            "errors": errors,
            "post_status": post_status,
        }

    async def _send_deployment_notification(
        self,
        batch_number: int,
        executed_trades: List[Dict[str, Any]],
        post_status: Dict[str, Any],
    ) -> None:
        """發送開盤分批建倉執行報告至 Telegram / Web 通道"""
        try:
            from src.services.notification_service import NotificationService
            notifier = NotificationService.create_with_settings(
                settings_service=self.settings_service, user_id=self.user_id
            )

            success_trades = [t for t in executed_trades if t.get("status") in ("executed", "pending")]
            blackout_trades = [t for t in executed_trades if t.get("status") == "blackout_deferred"]
            black_hole_trades = [t for t in executed_trades if t.get("status") == "liquidity_black_hole_deferred"]
            jump_trades = [t for t in executed_trades if t.get("status") == "jump_diffusion_deferred"]
            circuit_trades = [t for t in executed_trades if t.get("status") == "circuit_breaker_deferred"]
            other_deferred = [
                t for t in executed_trades
                if "deferred" in t.get("status", "")
                and t.get("status") not in (
                    "blackout_deferred",
                    "circuit_breaker_deferred",
                    "liquidity_black_hole_deferred",
                    "jump_diffusion_deferred",
                )
            ]
            deferred_trades = blackout_trades + black_hole_trades + jump_trades + circuit_trades + other_deferred
            failed_trades = [t for t in executed_trades if t.get("status") in ("failed", "error")]
            skipped_trades = [t for t in executed_trades if t.get("status") == "skipped"]

            title = f"🚀 [美股開盤建倉] 第 {batch_number} 批次配置執行完成"
            lines = [
                f"**美股開盤階梯式建倉報告 (第 {batch_number} 批次)**",
                f"- **帳戶總資產 (NLV):** ${post_status.get('total_equity', 0.0):,.2f}",
                f"- **目前現金儲備:** ${post_status.get('available_cash', 0.0):,.2f} ({post_status.get('cash_ratio_pct', 0.0):.1f}%)",
                f"- **防守現金底線 (20%):** ${post_status.get('required_reserve_usd', 0.0):,.2f}",
                "",
                "**已執行訂單清單:**",
            ]

            if success_trades:
                for t in success_trades:
                    hold_check = " [持倉確認: ✅]" if t.get("verified_in_holdings") else ""
                    lines.append(
                        f"  • **{t['ticker']}**: 買進 ${t['amount_usd']:.2f} "
                        f"(單號: `{t.get('order_id', 'N/A')}`){hold_check} [防滑點與日曆守衛通過]"
                    )
            else:
                lines.append("  (無直接成交訂單)")

            if blackout_trades:
                lines.append("")
                lines.append("**📅 財報與重大宏觀避開守衛暫緩下單:**")
                for bt in blackout_trades:
                    lines.append(f"  • **{bt['ticker']}**: ${bt['amount_usd']:.2f} — {bt.get('reason', '落入財報/宏觀保護窗口')}")

            if black_hole_trades:
                lines.append("")
                lines.append("**🕳️ 盤中流動性黑洞熔斷暫緩下單:**")
                for bh in black_hole_trades:
                    lines.append(f"  • **{bh['ticker']}**: ${bh['amount_usd']:.2f} — {bh.get('reason', '成交品質惡化/逆向選擇防線生效')}")

            if jump_trades:
                lines.append("")
                lines.append("**⚡ 貝葉斯跳躍擴散熔斷暫緩下單:**")
                for jt in jump_trades:
                    lines.append(f"  • **{jt['ticker']}**: ${jt['amount_usd']:.2f} — {jt.get('reason', '極端跳躍風險/防裂口跌勢')}")

            if circuit_trades:
                lines.append("")
                lines.append("**🛡️ 防滑點熔斷暫緩下單:**")
                for dt in circuit_trades:
                    lines.append(f"  • **{dt['ticker']}**: ${dt['amount_usd']:.2f} — {dt.get('reason', '價差過寬')}")

            if other_deferred:
                lines.append("")
                lines.append("**⏳ 其他原因暫緩下單:**")
                for ot in other_deferred:
                    lines.append(f"  • **{ot['ticker']}**: ${ot['amount_usd']:.2f} — {ot.get('reason', '暫緩執行')}")

            if failed_trades or skipped_trades:
                lines.append("")
                lines.append("**⚠️ 未執行/略過標的:**")
                for ft in failed_trades:
                    lines.append(f"  • **{ft['ticker']}**: ${ft['amount_usd']:.2f} — 失敗: {ft.get('reason', '未知原因')}")
                for st in skipped_trades:
                    lines.append(f"  • **{st['ticker']}**: ${st['amount_usd']:.2f} — 略過: {st.get('reason', '未達門檻')}")

            lines.append("")
            if deferred_trades or failed_trades:
                lines.append(
                    f"📌 **執行狀態說明:** 本批次尚有標的暫緩或待補單，將於下一排程自動接續執行（保留第 {batch_number} 批次）。"
                )
            else:
                lines.append(
                    f"📌 **資金守衛摘要:** 完成第 {batch_number} 批次配置後，現金餘額保持 "
                    f"${post_status.get('available_cash', 0.0):,.2f}，穩居防禦底線之上，杜絕追高風險。"
                )

            content = "\n".join(lines)
            await notifier.notify_all(
                title=title,
                content=content,
                channels=["telegram", "web"],
                category="trading",
            )
        except Exception as e:
            logger.warning(f"Failed to send batch deployment notification: {e}")
