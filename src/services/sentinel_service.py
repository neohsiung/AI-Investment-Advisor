import logging
import asyncio
import os
from typing import Dict, Any, List, Optional
from datetime import date
import pandas as pd

from src.services.market_data_service import MarketDataService
from src.services.search_service import InternetSearchService
from src.services.council_service import CouncilService
from src.services.transaction_service import TransactionService
from src.services.notification_service import NotificationService

from src.repositories.risk_keyword_repository import RiskKeywordRepository
from src.repositories.sentinel_repository import SentinelRepository
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
        market_service: Optional[MarketDataService] = None,
        search_service: Optional[InternetSearchService] = None,
        transaction_service: Optional[TransactionService] = None,
        council_service: Optional[CouncilService] = None,
        notification_service: Optional[NotificationService] = None,
        settings_service: Optional[SettingsService] = None,
    ):
        self.repo = SentinelRepository()
        self.settings_service = settings_service or SettingsService(user_id="supermfb@gmail.com")
        
        self.market_service = market_service or MarketDataService(settings_service=self.settings_service)
        self.search_service = search_service or InternetSearchService(settings_service=self.settings_service)
        self.transaction_service = transaction_service or TransactionService()
        self.council_service = council_service or CouncilService()
        self.notification_service = notification_service or NotificationService.create_with_settings(self.settings_service)
        
        # Thresholds (v3.5 - Defaults seeded to DB)
        self.default_thresholds = {
            "vix_high": 25.0,
            "vix_extreme": 40.0,
            "vix_spike_sigma": 2.5,       # Z-Score Spike threshold (v3.5)
            "position_drop_pct": -5.0,    # 個股日跌 > 5% 觸發
            "position_spike_pct": 8.0,     # 個股日漲 > 8% 觸發 (可能泡沫)
            "fed_funds_change_bps": 25,    # 聯邦利率變動 > 25bps
            "news_risk_score": 0.6,
            "vix_suppression_sigma_mult": 1.5, # 抑制回報門檻 (sigma 倍數)
        }
        
        # 1. Sync / Seed initial thresholds
        self.repo.seed_defaults(self.default_thresholds)
        self.thresholds = self.repo.get_all_thresholds()
        
        # 2. Dynamic Calibration (Rule #8)
        # Perform initial statistical calibration if historical data is available
        self._calibrate_thresholds()
        
        # Buffer State
        self._trigger_buffer: List[str] = []
        self._buffer_deadline: float = 0.0
        
        # Volatility State
        self.current_vix: float = 20.0 # Default fallback

    # ──────────────────────────────────────────
    # Main Entry Point
    # ──────────────────────────────────────────
        
    async def process_tick(self) -> None:
        """
        Main Event Loop: Perform multi-dimensional scanning and threshold-based monitoring.
        主事件迴圈：執行多維度掃描與基於門檻值的監控。
        """
        self.thresholds = self.repo.get_all_thresholds()
        
        # [Optimization] Check and Flush Buffer if deadline reached
        await self._check_buffer_flush()
        
        logger.info(f"Sentinel Check Started with {len(self.thresholds)} thresholds.")
        try:
            triggers: List[Dict[str, Any]] = []
            
            # Dimension 1: VIX Regime (每次 tick)
            triggers += self._check_vix_anomaly()
            
            # Dimension 2: Position Price Moves (每次 tick)
            triggers += self._check_position_moves()
            
            # Dimension 3: Breaking News (每 10 分鐘, 節省 Tavily credits)
            from datetime import datetime
            if datetime.now().minute % 10 == 0:
                triggers += self._check_breaking_news()
            
            # Dimension 4: Macro Shifts (每小時, FRED 數據更新頻率低)
            if datetime.now().minute == 0:
                triggers += self._check_macro_shifts()
            
            # Dimension 5: Active Polling
            triggers += await self._check_active_sources()
            
            # ACT: Summon Council + Notifications if triggered
            if triggers:
                await self._escalate(triggers)
            else:
                logger.debug("Sentinel: All dimensions normal. No triggers.")
                
        except Exception as e:
            logger.error(f"Sentinel Tick Error: {e}", exc_info=True)

    # ──────────────────────────────────────────
    # Event-Driven Entry (v3.8)
    # ──────────────────────────────────────────

    async def process_event(self, event: Dict[str, Any]) -> None:
        """
        Handle asynchronous external events (Webhooks) and trigger appropriate alerts.
        處理非同步外部事件（Webhooks）並觸發對應警報。
        """
        source = event.get("source", "unknown")
        data = event.get("data", {})
        msg = data.get("msg", "Event Triggered")
        ticker = data.get("ticker")
        
        logger.info(f"Sentinel Processing Event: [{source}] {msg}")
        
        display_text = f"🔔 [{source.upper()}] {msg} " + (f"({ticker})" if ticker else "")
        # Use message content as ID for generic events if no specific ID provided
        signal_id = f"event_{source}_{ticker or 'global'}"
        
        triggers = [{"text": display_text, "id": signal_id}]
        
        # If it's a technical signal or critical spike, escalate immediately
        await self._escalate(triggers, source=source)

    # ──────────────────────────────────────────
    # Dimension 1: VIX Regime (原有邏輯, 重構)
    # ──────────────────────────────────────────

    def _check_vix_anomaly(self) -> List[Dict[str, Any]]:
        """
        Adaptive VIX monitoring with Z-Score.
        Returns List of dicts with 'text' and 'id'.
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
                
                # Dynamic Threshold (v3.5)
                sigma_limit = self.thresholds.get("vix_spike_sigma", 2.5)
                threshold = avg_vix + (sigma_limit * std_dev)
                
                logger.info(
                    f"Sentinel VIX: {current_vix:.2f} "
                    f"(MA={avg_vix:.2f}, σ={std_dev:.2f}, threshold={threshold:.2f}, Z={z_score:.1f}σ)"
                )
                
                if current_vix > threshold:
                    triggers.append({
                        "text": f"🔴 VIX Spike: {current_vix:.2f} > {threshold:.2f} (Z={z_score:.1f}σ)",
                        "id": "vix_anomaly",
                        "value": current_vix,
                        "std_dev": std_dev
                    })
            else:
                if current_vix > self.thresholds.get("vix_high", 25.0):
                    triggers.append({
                        "text": f"⚠️ VIX High (Static): {current_vix:.2f}",
                        "id": "vix_high_static",
                        "value": current_vix
                    })
                
            # Update global state for adaptive compute
            self.current_vix = current_vix
                    
        except Exception as e:
            logger.warning(f"VIX check failed: {e}")
        return triggers

    # ──────────────────────────────────────────
    # Dimension 2: Position Price Moves
    # ──────────────────────────────────────────

    def _check_position_moves(self) -> List[Dict[str, Any]]:
        """
        Monitor active positions for significant intraday price moves.
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
                    triggers.append({
                        "text": f"📉 {ticker} 跌 {change_pct:.1f}% ({prev_close:.2f} → {current:.2f})",
                        "id": f"drop_{ticker}",
                        "value": change_pct
                    })
                elif change_pct >= self.thresholds["position_spike_pct"]:
                    triggers.append({
                        "text": f"📈 {ticker} 漲 {change_pct:.1f}% ({prev_close:.2f} → {current:.2f}) — 留意泡沫風險",
                        "id": f"spike_{ticker}",
                        "value": change_pct
                    })
                    
        except Exception as e:
            logger.warning(f"Position move check failed: {e}")
        return triggers

    # ──────────────────────────────────────────
    # Dimension 3: Breaking News (Tavily)
    # ──────────────────────────────────────────
    
    def _check_breaking_news(self) -> List[Dict[str, Any]]:
        """
        Search for risk-relevant breaking news using weighted keywords from the repository.
        使用儲存庫中的加權關鍵字搜尋與風險相關的突發新聞。
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
                        triggers.append({
                            "text": f"📰 {ticker} 風險新聞: {result.get('title', 'N/A')} (加權分數: {total_score:.2f}, 關鍵字: {kw_summary})",
                            "id": f"news_{ticker}_{result.get('title', 'N/A')[:20]}",
                            "value": total_score
                        })
                        break  # One trigger per ticker is enough
                        
        except Exception as e:
            logger.warning(f"Breaking news check failed: {e}")
        return triggers

    # ──────────────────────────────────────────
    # Dimension 4: Macro Shifts (FRED)
    # ──────────────────────────────────────────

    def _check_macro_shifts(self) -> List[Dict[str, Any]]:
        """
        Check for significant macro indicator changes via FRED.
        """
        triggers = []
        try:
            macro = self.market_service.get_macro_data()
            economics = macro.get("economics", {})
            
            # Check Fed Funds Rate trend
            fed = economics.get("FedFunds", {})
            if fed and fed.get("trend") == "Up":
                triggers.append({
                    "text": f"🏦 聯邦利率上升: {fed.get('value', 'N/A')}% (as of {fed.get('date', 'N/A')})",
                    "id": "macro_fed_rate_up",
                    "value": fed.get('value')
                })
            
            # Check Yield Curve Inversion
            spread = economics.get("10Y2Y_Spread", {})
            if spread and isinstance(spread.get("value"), (int, float)):
                if spread["value"] < 0:
                    triggers.append({
                        "text": f"⚠️ 殖利率曲線倒掛: 10Y-2Y = {spread['value']:.2f}%",
                        "id": "macro_yield_inversion",
                        "value": spread['value']
                    })
            
            # Check VIX from market indicators as supplementary
            market = macro.get("market_indicators", {})
            vix = market.get("^VIX", 0)
            if isinstance(vix, (int, float)) and vix > self.thresholds["vix_extreme"]:
                triggers.append({
                    "text": f"🔴 極端恐慌: VIX = {vix:.2f}",
                    "id": "macro_vix_extreme",
                    "value": vix
                })
                
        except Exception as e:
            logger.warning(f"Macro shift check failed: {e}")
        return triggers

    # Escalation: Council + Notifications
    # ──────────────────────────────────────────

    async def _escalate(self, triggers: List[Dict[str, Any]], source: str = "Sentinel") -> None:
        """
        Escalate triggers to appropriate channels, applying buffering where necessary.
        呈報觸發訊號至適當管道，並在必要時套用緩衝機制。
        """
        if not triggers:
             return

        # 1. Immediate Mode for Webhooks or Critical
        is_critical = any("🔴" in t.get("text", "") or "CRITICAL" in t.get("text", "") for t in triggers)
        is_internal = source == "Sentinel"
        
        if not is_internal or is_critical:
            # Flush immediately if critical or external
            self._trigger_buffer.extend(triggers)
            await self._flush_buffer(force=True, source=source)
            return

        # 2. Buffering Mode (Sentinel Routine)
        self._trigger_buffer.extend(triggers)
        
        # Deduplicate Buffer by ID if possible
        seen_ids = set()
        unique_buffer = []
        for t in self._trigger_buffer:
            tid = t.get("id")
            if tid not in seen_ids:
                unique_buffer.append(t)
                seen_ids.add(tid)
        self._trigger_buffer = unique_buffer
        
        # Start Timer if needed
        from datetime import datetime
        if self._buffer_deadline == 0.0:
            # 15 minutes buffer
            self._buffer_deadline = datetime.now().timestamp() + (15 * 60)
            logger.info(f"Sentinel: Started alert buffer. deadline={self._buffer_deadline}")

    async def _check_buffer_flush(self) -> None:
        """
        Internal check to flush the alert buffer if the deadline has passed.
        內部檢查：若已達緩衝期限則清除警報緩衝。
        """
        await self._flush_buffer(force=False)

    async def _flush_buffer(self, force: bool = False, source: str = "Sentinel") -> None:
        """
        Flush the buffered triggers and send alerts if conditions are met.
        清除緩衝的觸發訊號，並在符合條件時發送警報。
        """
        if not self._trigger_buffer:
             return
             
        # Check deadline
        from datetime import datetime
        if force or (self._buffer_deadline > 0 and datetime.now().timestamp() >= self._buffer_deadline):
             # Internal deduplication already happened in _escalate
             await self._do_send_alert(self._trigger_buffer, source=source)
             
             # Reset
             self._trigger_buffer = []
             self._buffer_deadline = 0.0

    async def _do_send_alert(self, triggers: List[Dict[str, Any]], source: str = "Sentinel") -> None:
        """
        Final execution logic for sending alerts, including Council deliberation and multi-channel notification.
        發送警報的最終執行邏輯，包含委員會研議與多管道通知。
        """
        # 1. Filter Triggers based on stable ID deduplication
        filtered_triggers = []
        for t in triggers:
            tid = t.get("id", "generic")
            display_text = t.get("text", "Unknown signal")
            
            # Use signal_id for 24h suppression
            if self.repo.is_duplicate_alert(title="", content="", hours=24, signal_id=tid):
                # VIX specific threshold re-trigger logic
                if tid == "vix_anomaly":
                    last_vix = self.repo.get_last_signal_value(tid)
                    current_vix = t.get("value", 0)
                    std_dev = t.get("std_dev", 1.0) # Fallback to 1.0 if missing
                    multiplier = self.thresholds.get("vix_suppression_sigma_mult", 1.5)
                    
                    # Calculate dynamic gap: sigma * multiplier
                    dynamic_gap = std_dev * multiplier
                    
                    if abs(current_vix - last_vix) < dynamic_gap:
                        logger.info(
                            f"Sentinel: Suppressing VIX alert (Dynamic Gap: {dynamic_gap:.2f} "
                            f"derived from σ={std_dev:.2f} * m={multiplier:.1f}. "
                            f"Move was {abs(current_vix - last_vix):.2f})"
                        )
                        continue
                else:
                    logger.info(f"Sentinel: Suppressing duplicate signal: {tid}")
                    continue
            
            filtered_triggers.append(t)

        if not filtered_triggers:
            return

        display_texts = [t["text"] for t in filtered_triggers]
        topic = f"{source.upper()} ALERT: {'; '.join(display_texts)}"
        
        logger.info(f"Sentinel: Escalating {len(filtered_triggers)} trigger(s) from {source}")
        
        context = {
            "source": source,
            "triggered_rules": display_texts,
            "timestamp": date.today().isoformat(),
        }
        
        # Council Deliberation
        try:
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
            decision = (
                "⚠️ **系統運行於安全模式 (Fail-safe Mode)**\n\n"
                "目前無法取得 AI 委員會的即時評估（可能是 API 連線問題）。\n"
                "請根據下方原始觸發訊號進行判斷。"
            )
        
        # Format Notification (Improved UX)
        formatted_triggers = ""
        for i, t in enumerate(filtered_triggers, 1):
            formatted_triggers += f"• {t['text']}\n"
            
        alert_content = (
            f"### 🛡️ Sentinel 監控警報 (Sentinel Alert)\n\n"
            f"**偵測到以下重要訊號 ({len(filtered_triggers)}):**\n"
            f"{formatted_triggers}\n"
            f"---\n"
            f"**🤖 AI 委員會評估 (Council Assessment):**\n"
            f"{decision}\n"
        )

        # Log Alert with Signal IDs for future suppression
        for t in filtered_triggers:
            # Store metadata including signal_id and current value
            meta = {"decision": decision, "signal_id": t.get("id"), "value": t.get("value")}
            self.repo.log_alert(topic, t["text"], metadata=meta)

        # Notify All Channels (Significance Filter applied)
        target_user = os.getenv("LINE_USER_ID", "broadcast")
        actions = []
        
        is_actionable = any(kw in decision.lower() for kw in ["sell", "reduce", "trim", "buy", "exit", "hedge"])
        is_extreme = any(t.get("level") == "CRITICAL" for t in filtered_triggers) or self.current_vix > 35
        
        # [Significance Filter v3.5]
        # If decision is vague and no critical trigger, suppress P0 noise.
        is_significant = is_actionable or is_extreme or "⚠️" in decision or "danger" in decision.lower()
        
        if not is_significant and "hold" in decision.lower():
            logger.info(f"Sentinel: Significance Filter suppressed notification for '{topic}' (Council: {decision[:50]}...)")
            return

        if is_actionable:
            actions.append({"label": "前往 eToro 下單", "data": "action=etoro_link"})

        await self.notification_service.notify_all(
            user_id=target_user,
            title=f"⚠️ {source} Alert",
            content=alert_content,
            actions=actions,
            category="sentinel",
            source=source,
            level="CRITICAL" if is_extreme or any(kw in decision.lower() for kw in ["sell", "reduce"]) else "WARNING"
        )

    def _calibrate_thresholds(self) -> None:
        """
        Dynamically calibrate thresholds based on historical distributions (Rule #8).
        基於歷史分佈動態校準閾值 (規則 #8)。
        """
        try:
            # VIX Percentiles (1-year context)
            vix_history = self.market_service.get_ohlcv("^VIX", days=252)
            if vix_history and vix_history.get("close"):
                closes = pd.Series(vix_history["close"])
                # 90th percentile as 'High', 97.5th as 'Extreme'
                v_high = float(closes.quantile(0.90))
                v_extreme = float(closes.quantile(0.975))
                v_sigma = float(closes.std())
                
                self.repo.update_threshold("vix_high", round(v_high, 2), "System-Stats", "90th percentile (252d)")
                self.repo.update_threshold("vix_extreme", round(v_extreme, 2), "System-Stats", "97.5th percentile (252d)")
                self.repo.update_threshold("vix_spike_sigma", 2.5, "System-Stats", "Fixed Sigma Standard") # Keep sigma for now
                
                logger.info(f"Sentinel: Calibrated VIX thresholds (High: {v_high:.2f}, Extreme: {v_extreme:.2f})")

            # Position Moves (Adaptive based on SPY volatility or fixed quantiles)
            # Defaulting to -5.0%/8.0% as statistically 'rare' events, but could be tuned here.
            
            # Sync back
            self.thresholds = self.repo.get_all_thresholds()
        except Exception as e:
            logger.error(f"Failed to calibrate thresholds: {e}")

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

    async def _check_active_sources(self) -> List[Dict[str, Any]]:
        """
        Poll enabled data sources defined in the Settings UI.
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
                    # Generic polling trigger
                    res_dict = await self._poll_single_source(sid, settings)
                    if res_dict:
                        triggers.append(res_dict)
                except Exception as e:
                    logger.error(f"Polling failed for {sid}: {e}")
        
        return triggers

    async def _poll_single_source(self, sid: str, settings: Dict[str, str]) -> Optional[Dict[str, Any]]:
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
                    return {
                        "text": f"📊 市場情緒極端 ({label}): Fear & Greed = {val}",
                        "id": "fng_extreme",
                        "value": val
                    }
        return None
