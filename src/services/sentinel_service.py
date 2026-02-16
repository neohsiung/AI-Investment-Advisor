import logging
import asyncio
import os
from typing import Dict, Any, List
from datetime import date

from src.services.market_data_service import MarketDataService
from src.services.search_service import InternetSearchService
from src.services.council_service import CouncilService
from src.services.transaction_service import TransactionService
from src.services.notification_service import NotificationService

from src.data.risk_keyword_repository import RiskKeywordRepository
from src.data.sentinel_repository import SentinelRepository
from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

class SentinelService:
    """
    The Sentinel: 24/7 Proactive Multi-Dimensional Monitoring Service.
    哨兵服務：24/7 主動多維監控與事件驅動核心。
    
    Trigger Dimensions (觸發維度):
    1. VIX Regime (Adaptive Z-Score) - 波動率體制。
    2. Position Price Moves (Intraday %) - 持倉價格異動。
    3. Breaking News Risk (Tavily) - 突發新聞風險。
    4. Macro Shifts (FRED) - 宏觀指標異動。
    """

    def __init__(
        self,
        market_service: MarketDataService = None,
        search_service: InternetSearchService = None,
        transaction_service: TransactionService = None,
        council_service: CouncilService = None,
        notification_service: NotificationService = None,
        settings_service: SettingsService = None,
    ):
        self.repo = SentinelRepository()
        self.settings_service = settings_service or SettingsService(user_id="supermfb@gmail.com")
        
        self.market_service = market_service or MarketDataService(settings_service=self.settings_service)
        self.search_service = search_service or InternetSearchService(settings_service=self.settings_service)
        self.transaction_service = transaction_service or TransactionService()
        self.council_service = council_service or CouncilService()
        self.notification_service = notification_service or NotificationService()
        
        # Thresholds (v3.5 - Defaults seeded to DB)
        self.default_thresholds = {
            "vix_high": 25.0,
            "vix_extreme": 40.0,
            "position_drop_pct": -5.0,    # 個股日跌 > 5% 觸發
            "position_spike_pct": 8.0,     # 個股日漲 > 8% 觸發 (可能泡沫)
            "fed_funds_change_bps": 25,    # 聯邦利率變動 > 25bps
            "news_risk_score": 0.6,
        }
        
        # Sync defaults and load current
        self.repo.seed_defaults(self.default_thresholds)
        self.thresholds = self.repo.get_all_thresholds()
        
        # Buffer State
        self._trigger_buffer: List[str] = []
        self._buffer_deadline: float = 0.0
        
        # Volatility State
        self.current_vix: float = 20.0 # Default fallback

    # ──────────────────────────────────────────
    # Main Entry Point
    # ──────────────────────────────────────────
        
    async def process_tick(self):
        """
        Main Event Loop: Multi-Dimensional Scan.
        Reloads dynamic thresholds to allow Agent-driven optimization.
        """
        self.thresholds = self.repo.get_all_thresholds()
        
        # [Optimization] Check and Flush Buffer if deadline reached
        await self._check_buffer_flush()
        
        logger.info(f"Sentinel Check Started with {len(self.thresholds)} thresholds.")
        try:
            triggers: List[str] = []
            
            # Dimension 1: VIX Regime (每次 tick)
            triggers += self._check_vix_anomaly()
            
            # Dimension 2: Position Price Moves (每次 tick)
            triggers += self._check_position_moves()
            
            # Dimension 3: Breaking News (每 10 分鐘, 節省 Tavily credits)
            # 使用 minute % 10 == 0 控制頻率
            from datetime import datetime
            if datetime.now().minute % 10 == 0:
                triggers += self._check_breaking_news()
            
            # Dimension 4: Macro Shifts (每小時, FRED 數據更新頻率低)
            if datetime.now().minute == 0:
                triggers += self._check_macro_shifts()
            
            # Dimension 5: Active Polling (v3.9 - 根據 UI 設定主動輪詢)
            triggers += await self._check_active_sources()
            
            # ACT: Summon Council + LINE if triggered
            if triggers:
                await self._escalate(triggers)
            else:
                logger.debug("Sentinel: All dimensions normal. No triggers.")
                
        except Exception as e:
            logger.error(f"Sentinel Tick Error: {e}", exc_info=True)

    # ──────────────────────────────────────────
    # Event-Driven Entry (v3.8)
    # ──────────────────────────────────────────

    async def process_event(self, event: Dict[str, Any]):
        """
        Handle asynchronous external events (Webhooks).
        處理非同步外部事件 (Webhooks)。
        """
        source = event.get("source", "unknown")
        data = event.get("data", {})
        msg = data.get("msg", "Event Triggered")
        ticker = data.get("ticker")
        
        logger.info(f"Sentinel Processing Event: [{source}] {msg}")
        
        triggers = [f"🔔 [{source.upper()}] {msg} " + (f"({ticker})" if ticker else "")]
        
        # If it's a technical signal or critical spike, escalate immediately
        await self._escalate(triggers, source=source)

    # ──────────────────────────────────────────
    # Dimension 1: VIX Regime (原有邏輯, 重構)
    # ──────────────────────────────────────────

    def _check_vix_anomaly(self) -> List[str]:
        """
        Adaptive VIX monitoring with Z-Score.
        自適應 VIX 監控 (Z-Score)。
        """
        triggers = []
        try:
            history_data = self.market_service.get_ohlcv("^VIX", days=60)
            if not history_data or not history_data.get("close"):
                return triggers
                
            closes = history_data["close"]
            if not closes:
                return triggers
                
            current_vix = closes[-1]
            window = 30
            
            if len(closes) >= window:
                recent = closes[-window:]
                avg_vix = sum(recent) / len(recent)
                variance = sum(((x - avg_vix) ** 2) for x in recent) / len(recent)
                std_dev = variance ** 0.5
                z_score = (current_vix - avg_vix) / std_dev if std_dev > 0 else 0
                threshold = avg_vix + (1.5 * std_dev)
                
                logger.info(
                    f"Sentinel VIX: {current_vix:.2f} "
                    f"(MA={avg_vix:.2f}, σ={std_dev:.2f}, threshold={threshold:.2f})"
                )
                
                if current_vix > threshold:
                    triggers.append(
                        f"🔴 VIX Spike: {current_vix:.2f} > {threshold:.2f} "
                        f"(Z={z_score:.1f}σ)"
                    )
            else:
                if current_vix > self.thresholds["vix_high"]:
                    triggers.append(f"⚠️ VIX High (Static): {current_vix:.2f}")
                
            # Update global state for adaptive compute
            self.current_vix = current_vix
                    
        except Exception as e:
            logger.warning(f"VIX check failed: {e}")
        return triggers

    # ──────────────────────────────────────────
    # Dimension 2: Position Price Moves
    # ──────────────────────────────────────────

    def _check_position_moves(self) -> List[str]:
        """
        Monitor active positions for significant intraday price moves.
        監控持倉的日內價格異動 (跌 > 5%, 漲 > 8%)。
        """
        triggers = []
        try:
            # Get all users for monitoring
            users = self._get_all_user_ids()
            all_tickers = set()
            for user_id in users:
                tickers = self.transaction_service.get_user_tickers(user_id, only_active=True)
                all_tickers.update(tickers)
            
            if not all_tickers:
                return triggers
            
            # Fetch current prices
            current_prices = self.market_service.get_current_prices(list(all_tickers))
            
            # Compare with previous close (via OHLCV)
            for ticker in all_tickers:
                current = current_prices.get(ticker, 0)
                if current <= 0:
                    continue
                    
                ohlcv = self.market_service.get_ohlcv(ticker, days=2)
                if not ohlcv or not ohlcv.get("close") or len(ohlcv["close"]) < 2:
                    continue
                
                prev_close = ohlcv["close"][-2]
                if prev_close <= 0:
                    continue
                    
                change_pct = ((current - prev_close) / prev_close) * 100
                
                if change_pct <= self.thresholds["position_drop_pct"]:
                    triggers.append(
                        f"📉 {ticker} 跌 {change_pct:.1f}% "
                        f"({prev_close:.2f} → {current:.2f})"
                    )
                elif change_pct >= self.thresholds["position_spike_pct"]:
                    triggers.append(
                        f"📈 {ticker} 漲 {change_pct:.1f}% "
                        f"({prev_close:.2f} → {current:.2f}) — 留意泡沫風險"
                    )
                    
        except Exception as e:
            logger.warning(f"Position move check failed: {e}")
        return triggers

    # ──────────────────────────────────────────
    # Dimension 3: Breaking News (Tavily)
    # ──────────────────────────────────────────
    
    def _check_breaking_news(self) -> List[str]:
        """
        Search for risk-relevant breaking news using weighted DB keywords.
        透過 Tavily 搜尋持倉相關的風險新聞，使用 DB 加權關鍵字評分。
        消耗 Tavily Credits (每 10 分鐘一次)。
        
        Scoring: Each search result is scored by summing weights of all
        matching keywords. Triggers if aggregate score >= threshold (0.6).
        """
        triggers = []
        try:
            # Load active keywords from DB
            repo = RiskKeywordRepository()
            active_keywords = repo.get_all(active_only=True)
            
            if not active_keywords:
                logger.warning("No active risk keywords in DB, skipping news check.")
                return triggers
            
            users = self._get_all_user_ids()
            all_tickers = set()
            for user_id in users:
                tickers = self.transaction_service.get_user_tickers(user_id, only_active=True)
                all_tickers.update(tickers)
            
            if not all_tickers:
                return triggers
            
            risk_threshold = self.thresholds.get("news_risk_score", 0.6)
            
            for ticker in all_tickers:
                query = f"{ticker} breaking news risk alert {date.today().isoformat()}"
                results = self.search_service.search_financial_context(query, max_results=3)
                
                if not results:
                    continue
                
                # Weighted keyword scoring
                for result in results:
                    snippet = (
                        result.get("snippet", "") + " " + result.get("title", "")
                    )
                    
                    total_score = 0.0
                    matched_keywords = []
                    
                    for kw in active_keywords:
                        score = kw.score(snippet)
                        if score > 0:
                            total_score += score
                            matched_keywords.append((kw, score))
                    
                    if total_score >= risk_threshold:
                        # Record hits for review/analytics
                        for kw, _ in matched_keywords:
                            repo.record_hit(kw.id)
                        
                        kw_summary = ", ".join(
                            f"{kw.keyword}(w={s:.2f})" 
                            for kw, s in sorted(matched_keywords, key=lambda x: -x[1])[:3]
                        )
                        triggers.append(
                            f"\U0001f4f0 {ticker} \u98a8\u96aa\u65b0\u805e: {result.get('title', 'N/A')} "
                            f"(\u52a0\u6b0a\u5206\u6578: {total_score:.2f}, \u95dc\u9375\u5b57: {kw_summary})"
                        )
                        break  # One trigger per ticker is enough
                        
        except Exception as e:
            logger.warning(f"Breaking news check failed: {e}")
        return triggers

    # ──────────────────────────────────────────
    # Dimension 4: Macro Shifts (FRED)
    # ──────────────────────────────────────────

    def _check_macro_shifts(self) -> List[str]:
        """
        Check for significant macro indicator changes via FRED.
        透過 FRED 檢查宏觀指標異動。
        """
        triggers = []
        try:
            macro = self.market_service.get_macro_data()
            economics = macro.get("economics", {})
            
            # Check Fed Funds Rate trend
            fed = economics.get("FedFunds", {})
            if fed and fed.get("trend") == "Up":
                triggers.append(
                    f"🏦 聯邦利率上升: {fed.get('value', 'N/A')}% "
                    f"(as of {fed.get('date', 'N/A')})"
                )
            
            # Check Yield Curve Inversion
            spread = economics.get("10Y2Y_Spread", {})
            if spread and isinstance(spread.get("value"), (int, float)):
                if spread["value"] < 0:
                    triggers.append(
                        f"⚠️ 殖利率曲線倒掛: 10Y-2Y = {spread['value']:.2f}%"
                    )
            
            # Check VIX from market indicators as supplementary
            market = macro.get("market_indicators", {})
            vix = market.get("^VIX", 0)
            if isinstance(vix, (int, float)) and vix > self.thresholds["vix_extreme"]:
                triggers.append(f"🔴 極端恐慌: VIX = {vix:.2f}")
                
        except Exception as e:
            logger.warning(f"Macro shift check failed: {e}")
        return triggers

    # Escalation: Council + Notifications
    # ──────────────────────────────────────────

    async def _escalate(self, triggers: List[str], source: str = "Sentinel"):
        """
        Escalate triggers. Applies buffering if source is Sentinel.
        """
        if not triggers:
             return

        # 1. Immediate Mode for Webhooks or Critical
        is_critical = any("🔴" in t or "CRITICAL" in t for t in triggers)
        is_internal = source == "Sentinel"
        
        if not is_internal or is_critical:
            # Flush immediately if critical or external
            self._trigger_buffer.extend(triggers)
            await self._flush_buffer(force=True, source=source)
            return

        # 2. Buffering Mode (Sentinel Routine)
        self._trigger_buffer.extend(triggers)
        
        # Deduplicate Buffer
        self._trigger_buffer = list(set(self._trigger_buffer))
        
        # Start Timer if needed
        from datetime import datetime
        if self._buffer_deadline == 0.0:
            # 15 minutes buffer
            self._buffer_deadline = datetime.now().timestamp() + (15 * 60)
            logger.info(f"Sentinel: Started alert buffer. deadline={self._buffer_deadline}")

    async def _check_buffer_flush(self):
        """Called by process_tick to optionally flush buffer."""
        await self._flush_buffer(force=False)

    async def _flush_buffer(self, force: bool = False, source: str = "Sentinel"):
        """Flush the buffer if deadline reached or forced."""
        if not self._trigger_buffer:
             return
             
        # Check deadline
        from datetime import datetime
        if force or (self._buffer_deadline > 0 and datetime.now().timestamp() >= self._buffer_deadline):
             unique_triggers = list(set(self._trigger_buffer))
             if unique_triggers:
                 await self._do_send_alert(unique_triggers, source=source)
             
             # Reset
             self._trigger_buffer = []
             self._buffer_deadline = 0.0

    async def _do_send_alert(self, triggers: List[str], source: str = "Sentinel"):
        """
        Escalate triggers to Council for deliberation, then notify.
        將觸發事件上報評議會並通知。
        """
        topic = f"{source.upper()} ALERT: {'; '.join(triggers)}"
        
        # 0. Deduplication (Cool-down)
        # Combine triggers and source to form unique content signature for this alert window
        content_signature = f"{topic}|{''.join(sorted(triggers))}" # Sorted for consistency
        if self.repo.is_duplicate_alert(title=topic, content=content_signature, hours=24):
            logger.info(f"Sentinel: Suppressing duplicate alert: {topic}")
            return

        logger.info(f"Sentinel: Escalating {len(triggers)} trigger(s) from {source}")
        
        context = {
            "source": source,
            "triggered_rules": triggers,
            "timestamp": date.today().isoformat(),
        }
        
        # Council Deliberation
        try:
            # [Fix] Pass user_id explicitly to ensure Agents get correct DB settings
            user_id = self.settings_service.user_id or "supermfb@gmail.com"
            
            result = await self.council_service.start_session(
                topic, 
                context, 
                market_volatility=self.current_vix,
                user_id=user_id
            )
            decision = result.get('consensus', 'No Consensus')
        except Exception as e:
            logger.error(f"Council session failed: {e}")
            decision = f"Council Unavailable — Raw Triggers: {'; '.join(triggers)}"
        
        logger.info(f"Sentinel: Council decision: {decision}")
        
        # LINE Notification (and others via notify_all)
        target_user = os.getenv("LINE_USER_ID", "broadcast")
        
        actions = []
        if any(kw in decision.lower() for kw in ["sell", "reduce", "trim"]):
            actions.append({"label": "前往 eToro 下單", "data": "action=etoro_link"})
        elif "buy" in decision.lower():
            actions.append({"label": "前往 eToro 下單", "data": "action=etoro_link"})
        
        # [Optimization] Structured Loop Format for Readability
        # 結構化迴圈排版，提升閱讀體驗
        formatted_triggers = ""
        for i, t in enumerate(triggers, 1):
            formatted_triggers += f"{i}. {t}\n"
            
        alert_content = (
            f"### 🛡️ Sentinel Event Loop\n"
            f"**Detected Signals ({len(triggers)})**:\n"
            f"{formatted_triggers}\n"
            f"---\n"
            f"{decision}\n"
        )

        # 1. Log Alert first (Pass content_signature as content for exact matching next time)
        self.repo.log_alert(topic, content_signature, metadata={"decision": decision, "full_content": alert_content})

        # 2. Notify All Channels
        self.notification_service.notify_all(
            user_id=target_user,
            title=f"⚠️ {source} Alert",
            content=alert_content,
            actions=actions,
            source=source,
            level="CRITICAL" if any(kw in decision.lower() for kw in ["sell", "reduce"]) else "WARNING"
        )

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def _get_all_user_ids(self) -> List[str]:
        """
        Get all registered user IDs for position monitoring.
        取得所有已註冊用戶 ID。
        """
        try:
            from src.data.database import get_db_connection
            from sqlalchemy import text
            with get_db_connection() as conn:
                rows = conn.execute(text("SELECT email FROM users")).fetchall()
                return [row[0] for row in rows] if rows else []
        except Exception as e:
            logger.warning(f"Failed to get user IDs: {e}")
            return []

    async def _check_active_sources(self) -> List[str]:
        """
        Poll enabled data sources defined in the Settings UI.
        根據 UI 設定，輪詢已啟用的資料源。
        """
        triggers = []
        settings = self.settings_service.get_all_settings()
        
        # Sources identified in the Matrix that support polling
        pollable_sources = [
            "alternative_me", "cryptopanic", "whale_alert", "glassnode",
            "tiingo", "news_api", "alpha_vantage", "fmp", "fred"
        ]
        
        for sid in pollable_sources:
            if settings.get(f"source_{sid}_enabled") == "true":
                try:
                    # Generic polling trigger (Routing logic can be expanded per sid)
                    res = await self._poll_single_source(sid, settings)
                    if res:
                        triggers.append(res)
                except Exception as e:
                    logger.error(f"Polling failed for {sid}: {e}")
        
        return triggers

    async def _poll_single_source(self, sid: str, settings: Dict[str, str]) -> str:
        """
        Routing logic for specific data source polling.
        """
        # Example for Fear & Greed (Alternative.me)
        if sid == "alternative_me":
            import requests
            resp = requests.get("https://api.alternative.me/fng/", timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data", [{}])[0]
                val = int(data.get("value", 50))
                label = data.get("value_classification", "Neutral")
                if val < 25 or val > 75:
                    return f"📊 市場情緒極端 ({label}): Fear & Greed = {val}"
        
        # Other sources would call their respective service methods
        # For now, we log the poll. In a full implementation, this 
        # would interact with MarketDataService or SearchService.
        logger.debug(f"Source {sid} polled as enabled.")
        return ""
