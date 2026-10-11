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

    async def _get_broker(self) -> Any:
        if self.broker:
            return self.broker
        from src.services.broker_factory import BrokerFactory
        return BrokerFactory.get_broker(self.user_id)

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

    async def get_active_batch_number(self) -> int:
        """
        全自動判定當前應執行的批次 (1, 2, 3，若全數完成或資金達標則回傳 0)。
        判定依據：
        1. 檢視可支配建倉資金：若 deployable_cash < 10.0，無可動用資金，直接回傳 0 (建倉週期圓滿結束)。
        2. 檢視 Redis 中儲存的當前批次狀態 batch_deployment:current_batch:{user_id}
        3. 檢視券商真實持倉：
           - 若 NVDA 與 TSM 已持倉 (市值各 >= $40)，視為第 1 批次已完成，推進至第 2 批次。
           - 若 MU 與 AMD 已持倉 (市值各 >= $30)，視為第 2 批次已完成，推進至第 3 批次。
           - 若 SPCX 已持倉 (市值 >= $30)，視為第 3 批次已完成。
        4. 回傳當前有效批次 (1, 2, 3 或 0)。
        """
        try:
            status = await self.get_portfolio_status()
            deployable = float(status.get("deployable_cash", 0.0) or 0.0)
            if deployable < 10.0:
                return 0
        except Exception as e:
            logger.debug(f"Failed to check deployable cash for active batch: {e}")

        stored_batch = 1
        try:
            from src.infrastructure.cache.redis_client import get_redis
            r = await get_redis(decode_responses=True)
            val = await r.get(f"batch_deployment:current_batch:{self.user_id}")
            if val is not None:
                stored_batch = int(val)
        except Exception as e:
            logger.debug(f"Could not read active batch from redis: {e}")

        if stored_batch == 0:
            return 0

        holdings: Dict[str, float] = {}
        try:
            broker = await self._get_broker()
            if broker:
                positions = await broker.get_positions()
                for p in positions:
                    sym = getattr(p, "symbol", "")
                    for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                        if sym.endswith(suffix):
                            sym = sym[:-len(suffix)]
                    holdings[sym] = float(getattr(p, "market_value", 0.0) or 0.0)
        except Exception as e:
            logger.debug(f"Could not read positions for batch inference: {e}")

        has_b1_nvda = holdings.get("NVDA", 0.0) >= 40.0
        has_b1_tsm = holdings.get("TSM", 0.0) >= 40.0
        has_b2_mu = holdings.get("MU", 0.0) >= 30.0
        has_b2_amd = holdings.get("AMD", 0.0) >= 30.0
        has_b3_spcx = holdings.get("SPCX", 0.0) >= 30.0

        derived_batch = 1
        if has_b1_nvda and has_b1_tsm:
            derived_batch = 2
            if has_b2_mu and has_b2_amd:
                derived_batch = 3
                if has_b3_spcx:
                    derived_batch = 0

        if derived_batch == 0:
            return 0

        active_batch = max(stored_batch, derived_batch)
        if active_batch > 3:
            return 0
        return active_batch

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

        # 定義 3 大批次候選
        batches = {
            1: [
                {"ticker": "NVDA", "target_pct": 0.10, "base_amount": 114.00, "confidence": 6.86, "role": "Alpha Top 1 算力龍頭開倉"},
                {"ticker": "TSM",  "target_pct": 0.10, "base_amount": 144.00, "confidence": 6.69, "role": "Alpha Top 2 先進製程開倉"},
                {"ticker": "AAPL", "target_pct": 0.10, "base_amount": 89.00,  "confidence": 6.86, "role": "Top 3 核心終端生態底倉加碼補足"},
            ],
            2: [
                {"ticker": "MSFT", "target_pct": 0.10, "base_amount": 91.00,  "confidence": 6.47, "role": "雲端 AI 企業端加碼"},
                {"ticker": "MU",   "target_pct": 0.05, "base_amount": 79.00,  "confidence": 6.86, "role": "高頻寬記憶體 (HBM) 週期建倉"},
                {"ticker": "AMD",  "target_pct": 0.05, "base_amount": 77.00,  "confidence": 6.47, "role": "資料中心 GPU 第二梯隊補強"},
            ],
            3: [
                {"ticker": "SPCX", "target_pct": 0.05, "base_amount": 76.00,  "confidence": 6.47, "role": "太空經濟衛星通訊主題配置"},
            ],
        }

        selected_batch = batches.get(batch_number, batches[1])
        allocated_items = []
        all_candidates_summary = []
        total_batch_amount = 0.0

        for item in selected_batch:
            ticker = item["ticker"]
            base_amt = item["base_amount"]
            target_info = targets_map.get(ticker, {})
            conf = target_info.get("confidence_score")
            conf_val = float(conf) * 10.0 if (conf is not None and float(conf) <= 1.0) else (float(conf) if conf else item["confidence"])

            # 依目前真實總資產動態適應金額（若有較大偏差）
            if total_equity > 0:
                target_value = total_equity * item["target_pct"]
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

            # 財報日與宏觀黑名單避開守衛檢驗
            blackout_decision = await self.blackout_guard.evaluate_candidate(ticker)
            is_blackout = blackout_decision.is_blackout
            blackout_reason = blackout_decision.reason if is_blackout else None

            # 若標的落入財報/宏觀避開視窗，不於此批次執行以防極端波動
            if is_blackout:
                trade_amount = 0.0

            is_executable = (trade_amount >= 10.0 and not is_blackout)
            candidate_entry = {
                "ticker": ticker,
                "amount_usd": trade_amount if is_executable else 0.0,
                "allocated_amount": trade_amount if is_executable else 0.0,
                "confidence_score": round(conf_val, 2),
                "target_pct": item["target_pct"],
                "role": item["role"],
                "rationale": f"第 {batch_number} 批次建倉配置: {item['role']} (${trade_amount:.2f})",
                "already_satisfied": (current_val >= target_value * 0.95) if total_equity > 0 else False,
                "blackout_active": is_blackout,
                "blackout_reason": blackout_reason,
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

        return {
            "batch_number": batch_number,
            "status": status,
            "portfolio_status": status,
            "can_execute": can_execute,
            "total_batch_amount": round(total_batch_amount, 2),
            "items": allocated_items,
            "plan_items": allocated_items,
            "all_candidates": all_candidates_summary,
            "expected_remaining_cash": round(expected_remaining_cash, 2),
            "projected_cash_after_deployment": round(expected_remaining_cash, 2),
            "expected_cash_ratio": round(expected_cash_ratio, 2),
            "calendar_summary": calendar_summary,
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
    ) -> Dict[str, Any]:
        """
        執行特定批次建倉下單（整合開盤波動率防線與買賣價差熔斷守衛）。
        若 batch_number 為 None，自動調用 get_active_batch_number() 自適應推進。
        """
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
        if not force:
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
        if not force:
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

            # 防滑點與買賣價差熔斷守衛檢驗
            slippage_eval = await self.slippage_guard.evaluate_trade(
                ticker=ticker,
                action="BUY",
                amount_usd=amount_usd,
                check_opening_window=not force,
            )

            if not slippage_eval.passed and not force:
                logger.warning(
                    f"Slippage Circuit Breaker triggered for {ticker}: {slippage_eval.reason}. Skipping trade."
                )
                executed_trades.append({
                    "ticker": ticker,
                    "amount_usd": amount_usd,
                    "status": "circuit_breaker_deferred",
                    "reason": slippage_eval.reason,
                    "spread_pct": slippage_eval.spread_pct,
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
                "reason": fail_reason,
            })

            if not is_ok:
                errors.append(f"{ticker} buy failed: {fail_reason or 'unknown'}")
            else:
                logger.info(f"✓ Batch {batch_number}: Successfully executed BUY {ticker} (${amount_usd:.2f})")
                # 避免連續併發下單撞擊券商速率限制
                await asyncio.sleep(1.5)

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
            circuit_trades = [t for t in executed_trades if t.get("status") == "circuit_breaker_deferred"]
            other_deferred = [
                t for t in executed_trades
                if "deferred" in t.get("status", "") and t.get("status") not in ("blackout_deferred", "circuit_breaker_deferred")
            ]
            deferred_trades = blackout_trades + circuit_trades + other_deferred
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
