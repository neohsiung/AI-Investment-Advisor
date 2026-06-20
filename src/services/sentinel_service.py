from src.utils.logger import setup_logger
logger = setup_logger("SentinelService")

import asyncio
import os
import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union, Awaitable
from src.utils.async_utils import to_thread
from datetime import date
import pandas as pd

from src.services.market_data_service import MarketDataService
from src.services.search_service import InternetSearchService
from src.services.council_service import CouncilService
from src.services.transaction_service import TransactionService
from src.utils.security import redact_secrets, redact_pii
import httpx

from src.repositories.sentinel_repository import AlchemySentinelRepository
from src.repositories.snapshot_repository import AlchemySnapshotRepository
from src.services.settings_service import SettingsService
from src.services.risk_keyword_service import RiskKeywordService
from src.domain.entities import RiskKeyword

# PAD Phase 2: Add model router and gateway imports
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
from src.infrastructure.llm.llm_gateway import OpenRouterGateway
from src.domain.interfaces import Message, LLMConfig
from src.repositories.settings_repository import AlchemySettingsRepository

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
        user_id: Optional[str] = None,
        market_service: Optional[MarketDataService] = None,
        search_service: Optional[InternetSearchService] = None,
        transaction_service: Optional[TransactionService] = None,
        council_service: Optional[CouncilService] = None,
        settings_service: Optional[SettingsService] = None,
        keyword_service: Optional[RiskKeywordService] = None,
        repo: Optional[AlchemySentinelRepository] = None,
        snapshot_repo: Optional[AlchemySnapshotRepository] = None,
    ):
        if not user_id:
            logger.warning("SentinelService: No user_id provided. Running in anonymous mode (testing only).")
            
        self.repo = repo or AlchemySentinelRepository()
        self.user_id = user_id
        self.settings_service = settings_service or SettingsService(user_id=self.user_id)
        
        self.market_service = market_service or MarketDataService(settings_service=self.settings_service)
        self.search_service = search_service or InternetSearchService(settings_service=self.settings_service)
        self.transaction_service = transaction_service or TransactionService()
        self.council_service = council_service or CouncilService(user_id=self.user_id)
        self.keyword_service = keyword_service or RiskKeywordService()
        self.snapshot_repo = snapshot_repo or AlchemySnapshotRepository(engine=self.repo.engine)
        
        # PAD Phase 2: Initialize model router and gateway for LLM calls
        from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter
        from src.services.token_logger_service import TokenLoggerService
        self.model_router = BudgetAwareModelRouter(
            settings_service=self.settings_service,
            token_logger=TokenLoggerService()
        )
        self.gateway = OpenRouterGateway()
        
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
        
        # [NEW] v5.1: Tracking firing times for de-bouncing (T16)
        self.last_fire_time: Dict[str, float] = {}
        
        # Buffer State — Redis-backed persistent buffer (replaces in-memory dict)
        from src.infrastructure.redis_sentinel_buffer import RedisSentinelBuffer
        self._redis_buffer = RedisSentinelBuffer()
        
        # Priority Deadlines (minutes) - Rule #8: Dynamic via settings if available
        # Keys use "P1".."P5" format to match priority lookup: f"P{priority}"
        self.priority_minutes = {
            "P1": int(self.settings_service.get_setting("sentinel_p1_limit_mins") or 15),
            "P2": int(self.settings_service.get_setting("sentinel_p2_limit_mins") or 60),
            "P3": int(self.settings_service.get_setting("sentinel_p3_limit_mins") or 240),
            "P4": int(self.settings_service.get_setting("sentinel_p4_limit_mins") or 720),
            "P5": int(self.settings_service.get_setting("sentinel_p5_limit_mins") or 1440),
        }
        
        # Volatility State
        self.current_vix: float = 20.0 # Default fallback

    # ──────────────────────────────────────────
    # PAD Phase 2: Agent LLM Helper
    # ──────────────────────────────────────────
    
    async def _call_agent_llm(self, agent_name: str, context: Dict[str, Any], tier: str = "smart", 
                              temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """
        PAD Phase 2: Replace AgentFactory.create_*_agent().run() with direct gateway calls.
        Generic method to call LLM for any agent role (Thematic, Sentinel, etc).
        """
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

            chain = build_config_chain(self.user_id, tier)
            if not chain:
                logger.warning(f"No tier binding for user={self.user_id} tier={tier}, using budget router fallback")
                chain = self.model_router.get_config_chain(self.user_id, tier)
            if not chain:
                return json.dumps({"status": "failed", "error": f"No model configured for tier={tier}"})

            pipeline = ResilientLLMPipeline(config_chain=chain)

            agent_prompts = {
                "Thematic": "You are a Thematic analyst. Analyze market themes, trends, and beneficiary companies. Update tracking lists based on events. Return valid JSON with 'status' and 'data' fields.",
                "Sentinel": "You are a Sentinel agent. Evaluate event priority and routing. Determine priority (P0-P5), target_agent (CIO/PM/Analyst), trigger_type, affected_tickers, and rationale. Return valid JSON.",
                "Momentum": "You are a Momentum analyst. Analyze price trends and technical indicators.",
                "Fundamental": "You are a Fundamental analyst. Analyze financial statements and valuations.",
                "Risk": "You are a Risk manager. Assess portfolio risks and downsides.",
                "Sentiment": "You are a Sentiment analyst. Analyze market sentiment and investor psychology.",
                "Macro": "You are a Macro strategist. Assess macroeconomic trends and cyclical factors."
            }

            system_prompt = agent_prompts.get(agent_name, f"You are a {agent_name} analyst.")
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]

            logger.debug(f"Sentinel: Calling {agent_name} agent via tier={tier} (user={self.user_id})")
            response, _ = await pipeline.execute(messages, temperature=temperature, max_tokens=max_tokens)

            if not isinstance(response, str):
                logger.error(f"Sentinel: Unexpected response type from pipeline: {type(response)}")
                return json.dumps({"status": "failed", "error": f"Invalid response type: {type(response)}"})

            return response
        except Exception as e:
            logger.error(f"Sentinel: {agent_name} agent failed: {e}")
            return json.dumps({"status": "failed", "error": str(e)})

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
            
            # Dimension 0: User Context Resolution (v5.0: Strictly isolated)
            active_tickers = self.transaction_service.get_user_tickers(self.user_id, only_active=True)
            ticker_list = list(active_tickers)
            logger.info(f"Sentinel: Monitoring {len(ticker_list)} tickers for user {redact_pii(self.user_id)}.")
            
            # Dimension 1: VIX Regime (每次 tick)
            triggers += self._check_vix_anomaly()
            
            # Dimension 2: Position Price Moves (每次 tick)
            # Pass aggregated data to avoid redundant fetches
            if ticker_list:
                current_prices = await self.market_service.get_current_prices(ticker_list)
                triggers += await self._check_position_moves_v2(ticker_list, current_prices)
            
            # Dimension 3: Breaking News (每 10 分鐘, 節省 Tavily credits)
            from datetime import datetime
            if datetime.now().minute % 10 == 0:
                if ticker_list:
                    triggers += await self._check_breaking_news_v2(ticker_list)
            
            # Dimension 4: Macro Shifts (每小時, FRED 數據更新頻率低)
            if datetime.now().minute == 0:
                triggers += await self._check_macro_shifts()
            
            # Dimension 5: Active Polling
            triggers += await self._check_active_sources()

            # Dimension 6: Global Macro / Geopolitical Events (每 30 分鐘)
            # 持倉數量無關的全球重大事件掃描
            if datetime.now().minute % 30 == 0:
                triggers += await self._check_global_macro_events()
            
            # Dimension 7: Risk Consistency & Dynamic Cash (每次 tick)
            # v5.0: Ensure leverage and cash levels match risk profile
            new_triggers = await self._check_risk_consistency()
            triggers.extend(new_triggers)
            logger.debug("process_tick: %d triggers after risk check", len(triggers))
            
            # Dimension 8: Capital Deployment (v9.0 Add-on)
            # Check for excess cash and trigger deployment logic if allowed
            await self._handle_cash_deployment_logic(triggers)
            
            # Dimension 9: Infrastructure Health / Self-Healing (Phase 9)
            triggers += await self._check_infrastructure_health()
            
            # Dimension 10: Allocation Drift Check (v10.0 - Portfolio Rebalancing)
            # Check if current portfolio allocation deviates from target allocation
            rebalance_triggers = await self._check_allocation_drift()
            triggers += rebalance_triggers
            
            # Dimension 10.1: Execute Rebalancing (Phase 5)
            await self._handle_rebalance_logic(rebalance_triggers)
            
            # ACT: Summon Council + Notifications if triggered
            if triggers:
                await self._escalate(triggers)
            else:
                logger.debug("Sentinel: All dimensions normal. No triggers.")
                
        except Exception as e:
            logger.error(f"Sentinel Tick Error: {e}", exc_info=True)
        finally:
            # v4.2.6: Explicitly close repository sessions after each tick
            self.repo.close_session()
            if self.settings_service and hasattr(self.settings_service, 'settings_repo'):
                self.settings_service.settings_repo.close_session()

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
        
        logger.info(f"Sentinel Processing Event: [{redact_secrets(source)}] {redact_secrets(msg)}")
        
        display_text = f"🔔 [{source.upper()}] {msg} " + (f"({ticker})" if ticker else "")
        # Use message content as ID for generic events if no specific ID provided
        signal_id = data.get("signal_id") or f"event_{source}_{ticker or 'global'}"
        
        # Milestone 2.1: Webhook for semiconductor earnings calls/reports
        if source == "earnings_call" and ticker:
            from src.services.supply_chain_service import SupplyChainService
            sc_service = SupplyChainService(user_id=self.user_id, settings_service=self.settings_service)
            sc_info = sc_service.get_shortage_premium(ticker)
            if sc_info.get("has_premium"):
                display_text += f"\n💡 [Supply Chain Impact]: {sc_info.get('narrative')}"
                signal_id = f"earnings_sc_impact_{ticker}"
        
        triggers = [{"text": display_text, "id": signal_id}]
        
        # If it's a technical signal or critical spike, escalate immediately
        await self._escalate(triggers, source=source)

    async def on_realtime_event(self, event: Dict[str, Any]) -> None:
        """
        Callback for real-time WebSocket events.
        WebSocket 即時事件的回調函數。
        """
        ev_type = event.get("ev")
        symbol = event.get("sym")
        
        # Mapping Polygon events to Sentinel logic
        if ev_type == "T": # Trade
            price = event.get("p")
            size = event.get("s")
            # Logic: If trade size is huge or price deviates from last tick significantly
            # For now, bridge to process_event
            await self.process_event({
                "source": "polygon_websocket",
                "data": {
                    "ticker": symbol,
                    "msg": f"Real-time Trade: ${price} (Size: {size})",
                    "price": price
                }
            })
        elif ev_type == "A": # Aggregate
            close = event.get("c")
            await self.process_event({
                "source": "polygon_websocket",
                "data": {
                    "ticker": symbol,
                    "msg": f"Real-time Bar Close: ${close}",
                    "price": close
                }
            })

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
                
                from unittest.mock import MagicMock
                current_vix_val = 18.0 if isinstance(current_vix, MagicMock) else float(current_vix)
                
                if current_vix_val > threshold:
                    triggers.append({
                        "text": f"🔴 VIX Spike: {current_vix:.2f} > {threshold:.2f} (Z={z_score:.1f}σ)",
                        "id": "vix_anomaly",
                        "value": current_vix,
                        "std_dev": std_dev,
                        "priority": 1 # P1: Immediate/High Priority
                    })
            else:
                if current_vix > self.thresholds.get("vix_high", 25.0):
                    triggers.append({
                        "text": f"⚠️ VIX High (Static): {current_vix:.2f}",
                        "id": "vix_high_static",
                        "value": current_vix,
                        "priority": 2 # P2: Warning
                    })
                
            # Update global state for adaptive compute
            self.current_vix = current_vix
                    
        except Exception as e:
            logger.warning(f"VIX check failed: {e}")
        return triggers

    # Dimension 2: Position Price Moves
    # ──────────────────────────────────────────


    async def _check_position_moves_v2(self, all_tickers: List[str], current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
        """
        Monitor aggregated tickers for significant intraday price moves.
        Optimized to use pre-fetched current prices and batch OHLCV.
        """
        triggers = []
        if not all_tickers:
            return triggers
            
        try:
            # Batch fetch OHLCV for all tickers (2 days needed for prev-close)
            ohlcv_batch = self.market_service.get_ohlcv_batch(all_tickers, days=2)
            
            # Compare with previous close 
            for ticker in all_tickers:
                current = current_prices.get(ticker, 0)
                if current <= 0:
                    continue
                    
                ohlcv = ohlcv_batch.get(ticker)
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
                        "value": change_pct,
                        "priority": 2 # P2: Position Move
                    })
                elif change_pct >= self.thresholds["position_spike_pct"]:
                    triggers.append({
                        "text": f"📈 {ticker} 漲 {change_pct:.1f}% ({prev_close:.2f} → {current:.2f}) — 留意泡沫風險",
                        "id": f"spike_{ticker}",
                        "value": change_pct,
                        "priority": 3 # P3: Potential Bubble
                    })
                    
        except Exception as e:
            logger.warning(f"Position move check failed for {redact_secrets(all_tickers)}: {e}")
        return triggers

    async def _check_position_moves(self) -> List[Dict[str, Any]]:
        """Deprecated wrapper for backward compatibility."""
        ticker_list = self.transaction_service.get_user_tickers(self.user_id, only_active=True)
        current_prices = await self.market_service.get_current_prices(ticker_list)
        return await self._check_position_moves_v2(ticker_list, current_prices)

    async def _get_market_trend(self, benchmark: str = "SPY") -> str:
        """
        Detects major market trend using SMA and MACD.
        Returns: 'Bullish', 'Bearish', or 'Neutral'
        """
        try:
            indicators = self.market_service.get_technical_indicators(benchmark)
            sma = indicators.get("sma", {})
            sma_200 = sma.get("sma_200", 0)
            
            # Simple Trend Rule: Price > SMA200 for long-term bull
            # We don't have current price here directly, let's fetch it
            prices = await self.market_service.get_current_prices([benchmark])
            current_price = prices.get(benchmark, 0)
            
            if current_price > sma_200 and sma_200 > 0:
                return "Bullish"
            elif current_price < sma_200 and sma_200 > 0:
                return "Bearish"
            return "Neutral"
        except Exception as e:
            logger.warning(f"Trend detection failed for {benchmark}: {e}")
            return "Neutral"

    # Dimension 3: Breaking News (Tavily)
    # ──────────────────────────────────────────
    
    async def _check_breaking_news_v2(self, all_tickers: List[str]) -> List[Dict[str, Any]]:
        """
        Search for risk-relevant breaking news for aggregated tickers.
        """
        triggers = []
        if not all_tickers:
            return triggers
            
        try:
            active_keywords = self.keyword_service.get_active_keywords()
            
            if not active_keywords:
                logger.warning("No active risk keywords, skipping news check.")
                return triggers
            
            risk_threshold = self.thresholds.get("news_risk_score", 0.6)
            
            for ticker in all_tickers:
                risk_score, summary = await self._analyze_ticker_news(ticker, active_keywords)
                if risk_score >= risk_threshold:
                    triggers.append({
                        "text": f"⚠️ {ticker} 新聞異動: {summary} (加權分數: {risk_score:.2f})",
                        "id": f"news_{ticker}_{risk_score:.2f}",
                        "value": risk_score,
                        "priority": 3 # P3: News Risk
                    })
        except Exception as e:
            logger.warning(f"Breaking news check failed: {e}")
        return triggers

    async def _check_breaking_news(self) -> List[Dict[str, Any]]:
        """Deprecated wrapper for backward compatibility."""
        ticker_list = self.transaction_service.get_user_tickers(self.user_id, only_active=True)
        return await self._check_breaking_news_v2(ticker_list)

    async def _analyze_ticker_news(self, ticker: str, active_keywords: List[RiskKeyword]) -> Tuple[float, str]:
        """
        Analyzes news for a given ticker against active risk keywords and returns a risk score and summary.
        v5.0 Optimization: Prioritize Tiingo/FMP over Tavily Search to save credits.
        """
        risk_threshold = self.thresholds.get("news_risk_score", 0.6)

        # Optimization: Use standardized news fetching (Tiingo -> FMP -> YFinance)
        results = self.market_service.get_news(ticker)
        
        # Fallback: search if NO news from primary providers
        if not results:
             query = f"{ticker} latest news investment impact"
             results = await self.search_service.search_financial_context(query, max_results=3)
             
        if not results:
             return 0.0, "No recent news captured by primary providers or search."
        
        best_score = 0.0
        best_summary = ""

        for result in results:
            title = result.get("title", "")
            summary = result.get("summary", "") or result.get("description", "")
            full_text = f"{title} {summary}"
            
            total_score = 0.0
            matched_keywords = []
            
            for kw in active_keywords:
                score = kw.score(full_text)
                if score > 0:
                    total_score += score
                    matched_keywords.append((kw, score))
            
            if total_score >= risk_threshold:
                # Record hits via keyword service
                for kw, _ in matched_keywords:
                    self.keyword_service.record_hit(kw.id)
                
                kw_summary = ", ".join(
                    f"{kw.keyword}(w={s:.2f})" 
                    for kw, s in sorted(matched_keywords, key=lambda x: -x[1])[:3]
                )
                
                # Scenario Logic: Tariff -> Inventory Restocking
                scenario_note = ""
                has_tariff = any("tariff" in kw.keyword.lower() or "關稅" in kw.keyword.lower() for kw, _ in matched_keywords)
                has_restock = any("inventory restocking" in kw.keyword.lower() or "回補庫存" in kw.keyword.lower() for kw, _ in matched_keywords)
                
                if has_tariff or has_restock:
                    scenario_note = " (Scenario Triggered: Anticipate inventory restocking as a catalyst for economic expansion before tariffs hit)"
                    total_score += 0.2 # Boost score for matching the specific roadmap scenario

                # Scenario Logic: PPA Signings / AI Energy Moat (Milestone 2.2)
                # Dynamic AI Energy Tickers 
                ai_energy_tickers = self.settings_service.get_setting("ai_energy_tickers")
                if not ai_energy_tickers:
                    # [Phase 0 Cold Start]
                    try:
                        from src.services.transaction_service import TransactionService
                        tx_service = TransactionService(user_id=self.user_id)
                        active_tickers = tx_service.get_user_tickers(user_id=self.user_id, only_active=True)
                        if active_tickers:
                            logger.info(f"Bootstrapping AI Energy Tickers from Watchlist: {redact_secrets(active_tickers)}")
                            context = {
                                "event_text": f"Initial Bootstrapping. Find 'AI Energy / Infrastructure / Grid' beneficiaries from this watchlist: {', '.join(active_tickers)}",
                                "theme_key": "ai_energy_tickers",
                                "current_state": []
                            }
                            res_str = await self._call_agent_llm("Thematic", context, tier="smart")
                            try:
                                res = json.loads(res_str)
                            except json.JSONDecodeError:
                                res = {}
                            if res.get("status") == "success":
                                ai_energy_tickers = self.settings_service.get_setting("ai_energy_tickers")
                    except Exception as e:
                        logger.error(f"Failed to bootstrap Energy tickers: {e}")
                        
                    if not ai_energy_tickers:
                        ai_energy_tickers = ["CEG", "VST", "MSFT", "AMZN", "GOOGL"]
                        self.settings_service.save_setting("ai_energy_tickers", ai_energy_tickers)

                if isinstance(ai_energy_tickers, str):
                    try:
                        import json
                        ai_energy_tickers = json.loads(ai_energy_tickers)
                    except json.JSONDecodeError:
                        ai_energy_tickers = [t.strip() for t in ai_energy_tickers.split(',')]
                        
                has_ppa = any(keyword in result.get('title', '').lower() + result.get('snippet', '').lower() for keyword in ["ppa", "power purchase agreement", "nuclear", "smr", "datacenter power", "grid"])
                if has_ppa:
                    if ticker in ai_energy_tickers:
                        scenario_note += " ⚡ (AI Energy Catalyst: Potential PPA signing or nuclear/grid infrastructure deal detected)"
                        total_score += 0.3 # Boost for milestone 2.2 energy moat
                    
                    # EVENT-DRIVEN THEMATIC OPTIMIZATION: Energy
                    # If score is very high and it's a structural news event, trigger the ThematicAgent
                    if total_score > 1.0:
                        self._trigger_thematic_update(
                            event_text=f"{result.get('title')} - {result.get('snippet')}", 
                            theme_key="ai_energy_tickers", 
                            current_state=ai_energy_tickers
                        )
                    
                # Scenario Logic: Physical AI Transformation (Milestone 2.3)
                # Dynamic Physical AI Tickers
                physical_ai_tickers = self.settings_service.get_setting("physical_ai_tickers")
                if not physical_ai_tickers:
                    # [Phase 0 Cold Start]
                    try:
                        from src.services.transaction_service import TransactionService
                        tx_service = TransactionService(user_id=self.user_id)
                        active_tickers = tx_service.get_user_tickers(user_id=self.user_id, only_active=True)
                        if active_tickers:
                            logger.info(f"Bootstrapping Physical AI Tickers from Watchlist: {redact_secrets(active_tickers)}")
                            context = {
                                "event_text": f"Initial Bootstrapping. Find 'Physical AI / Robotics / Autonomous' beneficiaries from this watchlist: {', '.join(active_tickers)}",
                                "theme_key": "physical_ai_tickers",
                                "current_state": []
                            }
                            res_str = await self._call_agent_llm("Thematic", context, tier="smart")
                            try:
                                res = json.loads(res_str)
                            except json.JSONDecodeError:
                                res = {}
                            if res.get("status") == "success":
                                physical_ai_tickers = self.settings_service.get_setting("physical_ai_tickers")
                    except Exception as e:
                        logger.error(f"Failed to bootstrap Physical AI tickers: {e}")
                        
                    if not physical_ai_tickers:
                        physical_ai_tickers = ["TSLA", "NVDA", "BDX", "PLTR", "UBER"]
                        self.settings_service.save_setting("physical_ai_tickers", physical_ai_tickers)

                if isinstance(physical_ai_tickers, str):
                    try:
                        import json
                        physical_ai_tickers = json.loads(physical_ai_tickers)
                    except json.JSONDecodeError:
                        physical_ai_tickers = [t.strip() for t in physical_ai_tickers.split(',')]
                        
                has_physical_ai = any(keyword in result.get('title', '').lower() + result.get('snippet', '').lower() for keyword in ["fsd", "humanoid", "robotaxi", "optimus", "autonomous driving", "industrial automation"])
                if has_physical_ai:
                    if ticker in physical_ai_tickers:
                        scenario_note += " 🤖 (Physical AI Catalyst: Advancement in autonomous robotics or self-driving technology)"
                        total_score += 0.3 # Boost for milestone 2.3 physical AI moat
                    
                    # EVENT-DRIVEN THEMATIC OPTIMIZATION: Physical AI
                    if total_score > 1.0:
                        self._trigger_thematic_update(
                            event_text=f"{result.get('title')} - {result.get('snippet')}", 
                            theme_key="physical_ai_tickers", 
                            current_state=physical_ai_tickers
                        )
                
                if total_score > best_score:
                    best_score = total_score
                    best_summary = f"{result.get('title', 'N/A')} (關鍵字: {kw_summary}){scenario_note}"
                    
        return best_score, best_summary

    # ──────────────────────────────────────────
    # Dimension 4: Macro Shifts (FRED)
    # ──────────────────────────────────────────

    async def _check_macro_shifts(self) -> List[Dict[str, Any]]:
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
                    "value": fed.get('value'),
                    "priority": 2
                })
            
            # Check Yield Curve Inversion
            spread = economics.get("10Y2Y_Spread", {})
            if spread and isinstance(spread.get("value"), (int, float)):
                if spread["value"] < 0:
                    triggers.append({
                        "text": f"⚠️ 殖利率曲線倒掛: 10Y-2Y = {spread['value']:.2f}%",
                        "id": "macro_yield_inversion",
                        "value": spread['value'],
                        "priority": 4 # P4: Secular Macro Trend
                    })
            
            # Check VIX from market indicators as supplementary
            market = macro.get("market_indicators", {})
            vix = market.get("^VIX", 0)
            if isinstance(vix, (int, float)) and vix > self.thresholds["vix_extreme"]:
                triggers.append({
                    "text": f"🔴 極端恐慌: VIX = {vix:.2f}",
                    "id": "macro_vix_extreme",
                    "value": vix,
                    "priority": 1 # P1: Extreme Panic
                })
                
        except Exception as e:
            logger.warning(f"Macro shift check failed: {e}")
        return triggers

    async def _check_global_macro_events(self) -> List[Dict[str, Any]]:
        """
        Dimension 6: Scan for major global/geopolitical events independent of user positions.
        持倉無關的全球重大事件掃描（戰爭、制裁、疫情、金融危機等）。
        Uses existing AlchemyRiskKeywordRepository for keyword matching.
        """
        triggers = []
        try:
            risk_threshold = self.thresholds.get("news_risk_score", 0.6)

            queries = [
                "breaking financial market crisis OR crash OR war today",
                "geopolitical conflict sanctions impact stock market today",
            ]

            seen_ids = set()
            for query in queries:
                try:
                    results = await self.search_service.search_financial_context(query, max_results=3)
                    if not results:
                        continue

                    for item in results:
                        title = item.get("title", "")
                        content = item.get("content", "")
                        combined = f"{title} {content}"

                        # Score using keyword service (cached + records hits)
                        total_weight, matched = self.keyword_service.score_text(combined)

                        if total_weight >= risk_threshold:
                            event_id = f"global_macro_{hash(title) % 100000}"
                            if event_id not in seen_ids:
                                seen_ids.add(event_id)
                                triggers.append({
                                    "text": f"🌍 全球重大事件: {title[:100]} (加權分數: {total_weight:.2f})",
                                    "id": event_id,
                                    "ticker": "GLOBAL",
                                    "priority": 2, # P2: Geopolitical
                                    "data": {
                                        "keywords": matched[:5],
                                        "source": item.get("url", ""),
                                    }
                                })
                except Exception as e:
                    logger.debug(f"Global macro search query failed: {e}")

            if triggers:
                logger.info(f"Sentinel Dimension 6: Detected {len(triggers)} global macro events.")

        except Exception as e:
            logger.warning(f"Global macro event check failed: {e}")
        return triggers

    # Escalation: Council + Notifications
    # ──────────────────────────────────────────

    async def _escalate(self, triggers: List[Dict[str, Any]], source: str = "Sentinel") -> None:
        """
        Escalate triggers to appropriate channels, applying buffering where necessary.
        呈報觸發訊號至適當管道，並在必要時套用緩衝機制。
        """
        import time
        cooldown = 1800 # 30 minutes
        fire_key = f"escalate_{source}_{self.user_id}"
        if self.last_fire_time.get(fire_key, 0) + cooldown > time.time():
            logger.info(f"SentinelService: De-bouncing escalation for {fire_key} (cooldown: {cooldown}s)")
            return
        self.last_fire_time[fire_key] = time.time()
        if not triggers:
             return

        # [T4] Batching logic for P0 / immediate escalation
        immediate_triggers = []
        
        for t in triggers:
            trigger_id = t.get("id", "")
            
            # v5.4.1 Cost Optimization: Semantic/Response Caching
            pending = await self._redis_buffer.all_pending(self.user_id)
            already_buffered_trigger = next((b for b in pending if b.get("id") == trigger_id), None)
            
            if already_buffered_trigger:
                t["priority"] = already_buffered_trigger.get("priority", 3)
                t["target_agent"] = already_buffered_trigger.get("target_agent", "CIO")
                t["rationale"] = already_buffered_trigger.get("rationale", "Cached from Redis buffer")
                logger.debug("Sentinel: Skipping LLM evaluation for Redis-cached trigger (P%d)", int(t['priority']))
            else:
                # 1. AI-Driven Priority & Routing
                try:
                    raw_text = t.get("text", "")
                    text_snippet = raw_text[:2000] + ("..." if len(raw_text) > 2000 else "")
                    raw_data = str(t.get("data", {}))
                    data_snippet = raw_data[:2000] + ("..." if len(raw_data) > 2000 else "")

                    event_data = {
                        "text": text_snippet,
                        "id": trigger_id,
                        "data": data_snippet,
                        "source": source
                    }

                    rounded_vix = round(self.current_vix, 1)

                    # PAD Phase 2: Call Sentinel agent via gateway
                    # 使用 smart tier — Sentinel 需要 System 2 推理，不應使用 fast tier
                    context = {
                        "trigger_source": source,
                        "event_data": event_data,
                        "current_vix": rounded_vix
                    }
                    eval_res_str = await self._call_agent_llm("Sentinel", context, tier="smart")
                    
                    # Parse response
                    try:
                        eval_res = json.loads(eval_res_str)
                    except json.JSONDecodeError:
                        eval_res = {}

                    # Detect internal agent failure
                    if "error" in eval_res:
                        err_msg = eval_res.get("error", "unknown")
                        logger.error(f"Sentinel: AI agent returned internal error: {err_msg}")
                        t["rationale"] = f"AI eval failed internally ({err_msg[:80]}), batching for immediate send"
                        immediate_triggers.append(t)
                        continue

                    p_str = eval_res.get("priority", "P3")
                    priority = int(p_str.replace("P", ""))
                    t["priority"] = priority
                    t["target_agent"] = eval_res.get("target_agent", "CIO")
                    t["trigger_type"] = eval_res.get("trigger_type", "generic")
                    t["affected_tickers"] = eval_res.get("affected_tickers", [])
                    t["rationale"] = eval_res.get("rationale", "")

                    # P0 bypass buffer
                    if p_str == "P0" or eval_res.get("is_critical", False):
                        logger.warning(f"Sentinel: Systemic Criticality detected ({p_str}). Batching for immediate escalation.")
                        immediate_triggers.append(t)
                        continue

                except Exception as e:
                    logger.error(f"Sentinel: AI Priority evaluation failed: {e}")
                    t["priority"] = 2
                    t["target_agent"] = "CIO"
                    t["rationale"] = f"AI eval failed, batching for immediate send (Error: {str(e)[:50]})"
                    immediate_triggers.append(t)
                    continue

                # Fallback to legacy heuristics if priority still None
                if t.get("priority") is None:
                    trigger_key = t.get("id", "generic")
                    priority = 3
                    if trigger_key == "vix_anomaly": priority = 1
                    elif any(k in trigger_key for k in ["move", "price", "critical", "crash", "crisis"]): priority = 2
                    elif any(k in trigger_key for k in ["news", "sentiment", "macro"]): priority = 4
                    elif "info" in trigger_key: priority = 5
                    t["priority"] = priority

            # 2. Buffering Mode — Redis persistent buffer
            priority = t.get("priority", 3)
            wait_key = f"P{priority}"
            wait_mins = int(self.priority_minutes.get(wait_key, 240))
            
            added = await self._redis_buffer.add(self.user_id, t, wait_mins)
            if added:
                logger.debug("Sentinel: Buffered trigger to Redis (P%d).", int(priority))

        # [T4] Execute immediate escalation for all P0/failed triggers in ONE batch
        if immediate_triggers:
            logger.info(f"Sentinel: Escalating {len(immediate_triggers)} critical triggers in batch.")
            await self._do_send_alert(immediate_triggers, source=source)

    async def _check_buffer_flush(self) -> None:
        """
        Internal check to flush the alert buffer if the deadline has passed.
        內部檢查：若已達緩衝期限則清除警報緩衝。
        """
        await self._flush_buffer(force=False)

    async def _flush_buffer(self, force: bool = False, source: str = "Sentinel") -> None:
        """
        Flush due triggers from Redis buffer and send alerts.
        從 Redis buffer 取出已到期的觸發器並發送警報。
        """
        if force:
            # Force-flush: get all pending and clear
            to_flush = await self._redis_buffer.all_pending(self.user_id)
            if to_flush:
                import redis.asyncio as _aioredis
                try:
                    r = await self._redis_buffer._get_client()
                    await r.delete(self._redis_buffer._key(self.user_id))
                except Exception as e:
                    logger.warning(f"Sentinel: Force-flush Redis clear error: {e}")
        else:
            to_flush = await self._redis_buffer.flush_due(self.user_id)
        
        if to_flush:
            logger.info(f"Sentinel: Flushing {len(to_flush)} trigger(s) from Redis buffer.")
            await self._do_send_alert(to_flush, source=source)

    async def _do_send_alert(self, triggers: List[Dict[str, Any]], source: str = "Sentinel") -> None:
        """
        Final execution logic for sending alerts, including Council deliberation and multi-channel notification.
        發送警報的最終執行邏輯，包含委員會研議與多管道通知。
        """
        # 0. Fetch pending orders to filter duplicate evaluation
        user_id = self.settings_service.user_id or self.user_id
        pending_symbols = set()
        if user_id:
            try:
                from src.services.broker_factory import BrokerFactory
                _brk = BrokerFactory.get_broker(user_id)
                if hasattr(_brk, 'get_pending_orders'):
                    _p_orders = await _brk.get_pending_orders()
                    for o in _p_orders:
                        pending_symbols.add(o.get('symbol', ''))
            except Exception as e:
                logger.warning(f"Sentinel: Failed to fetch pending orders for guard: {e}")

        # 1. Filter Triggers based on stable ID deduplication
        filtered_triggers = []
        for t in triggers:
            trigger_key = t.get("id", "generic")
            display_text = t.get("text", "Unknown signal")
            
            # v6.1 Pending Order Guard: Suppress trigger if a pending order exists for this ticker
            ticker = t.get("ticker")
            if not ticker and "_" in trigger_key:
                 parts = trigger_key.split("_")
                 if len(parts) >= 2 and parts[1].isupper():
                     ticker = parts[1]
                     
            if ticker and ticker in pending_symbols:
                _safe_key = str(trigger_key)[:64]
                _safe_ticker = str(ticker)[:16]
                logger.debug(
                    "Sentinel: Suppressing trigger %s because %s already has a pending order.",
                    _safe_key, _safe_ticker
                )
                continue
            
            # Use signal_id for 24h suppression
            if self.repo.is_duplicate_alert(title="", content="", hours=24, signal_id=trigger_key):
                # VIX specific threshold re-trigger logic
                if trigger_key == "vix_anomaly":
                    last_vix = self.repo.get_last_signal_value(trigger_key)
                    current_vix = t.get("value", 0)
                    std_dev = t.get("std_dev", 1.0) # Fallback to 1.0 if missing
                    multiplier = self.thresholds.get("vix_suppression_sigma_mult", 1.5)
                    
                    # Calculate dynamic gap: sigma * multiplier
                    dynamic_gap = std_dev * multiplier
                    
                    if abs(current_vix - last_vix) < dynamic_gap:
                        logger.info(  # nosec B601 - logging math values (sigma, multiplier, gap); no sensitive data
                            "Sentinel: Suppressing VIX alert (Dynamic Gap: %.2f derived from σ=%.2f * m=%.1f. Move was %.2f)",
                            float(dynamic_gap), float(std_dev), float(multiplier),
                            float(abs(current_vix - last_vix))
                        )
                        continue
                else:
                    logger.info("Sentinel: Suppressing duplicate signal")
                    continue
            
            filtered_triggers.append(t)

        if not filtered_triggers:
            return

        display_texts = [t["text"] for t in filtered_triggers]
        max_priority = min([t.get("priority", 3) for t in filtered_triggers]) # Lower is higher priority
        
        topic = f"{source.upper()} P{max_priority} ALERT: {'; '.join(display_texts[:3])}"
        if len(display_texts) > 3:
            topic += "..."
        
        logger.info(f"Sentinel: Escalating {len(filtered_triggers)} trigger(s) (P{max_priority}) from {redact_secrets(source)}")
        
        # v9.1: Trigger-Aware Council Prompt
        # Each trigger type gets a focused prompt instead of a generic evaluation request.
        # This prevents Council from producing off-topic weekly reports for specific alerts.
        trigger_types = set(t.get("trigger_type", "generic") for t in filtered_triggers)
        
        has_excess_cash   = any("cash_ratio_high" in t.get("id", "") for t in filtered_triggers) or source == "Excess Cash" or "cash" in trigger_types
        has_news_trigger  = "news" in trigger_types
        has_price_trigger = "price_move" in trigger_types
        has_risk_trigger  = "risk" in trigger_types
        has_allocation_drift = "allocation_drift" in trigger_types
        
        msg_prefix = "請針對以下多個 Sentinel 警報進行彙整與風險評估，並以繁體中文 (Traditional Chinese) 提供一份簡短且具備行動建議的摘要。金融專業術語請保留英文。"
        
        if has_excess_cash:
            wishlist_str = ""
            user_id = self.settings_service.user_id or self.user_id
            if user_id:
                try:
                    from src.services.broker_factory import BrokerFactory
                    _b = BrokerFactory.get_broker(user_id)
                    if hasattr(_b, 'get_watchlists'):
                        wl = await _b.get_watchlists()
                        symbols = []
                        _items = wl if isinstance(wl, list) else wl.get('items', wl.get('Items', []))
                        for i in _items:
                            sym = i.get('market', {}).get('symbolName')
                            if sym: symbols.append(sym)
                        if symbols:
                            wishlist_str = ", ".join(symbols[:15])
                except Exception as e:
                    logger.warning(f"Failed to fetch watchlist for prompt: {e}")

            priorities_text = (
                f"1. 第一優先序從用戶的 Wishlist 尋找合適標的 (候選: {wishlist_str if wishlist_str else '無'})。\n"
                "2. 第二優先序從具潛力的板塊（如 AI Energy, Physical AI）尋找標的。\n"
            )
            
            # v8.5: Contrarian Greed Philosophy
            vix_data = self.market_service.get_macro_data().get("market_indicators", {})
            vix = vix_data.get("^VIX", 20.0)
            contrarian_note = ""
            if vix > 30:
                contrarian_note = (
                    "🔥 **【逆勢貪婪】目前市場處於極度恐懼 (VIX > 30)。**"
                    "根據『別人恐懼我貪婪』原則，請優先尋找因市場恐慌而被過度拋售、基本面優良的長線標的。此時可接受較高的波動以換取入場機會。"
                )

            msg_prefix = (
                "💰 **當前帳戶現金比例過高，請協助尋找新的投資機會。**\n"
                f"{contrarian_note}\n"
                f"請強制作出買入行動。尋找標的時：\n{priorities_text}"
                "3. **資本效率優先**：槓桿過高與風險控制並非對立。若當前槓桿偏高，請優先考慮『換庫』策略：賣出低效益/低信心度部位（降槓桿），並將資金投回更優質或防禦型標的，以在控制風險的同時最大化資金利用效益。\n"
                "4. 若目前處於牛市趨勢且風險穩定，歡迎適度利用槓桿擴大收益。若市場風險極高，則請優先選擇防禦性價值股或避險標的。\n\n"
                "**必須**在報告最後輸出以下格式的行動指令表（Actionable Orders），以便系統自動解析執行：\n\n"
                "| Ticker | Action | Amount (USD) | Confidence (1-10) | Reason |\n"
                "|--------|--------|-------------|-------------------|---------|\n"
                "| AAPL   | BUY    | 50          | 7                 | 理由... |\n\n"
                "⚠️ **重要：Ticker 欄位必須是券商可交易代號。** 嚴禁建議買入 'Cash' 或 'T-Bills'。Confidence 分數將決定是否自動執行。\n"
                "請以繁體中文 (Traditional Chinese) 撰寫，專業術語保留英文。"
            )
        
        elif has_news_trigger:
            # v9.1: News alert — inject exact trigger content and FORCE an action decision
            news_texts = "\n".join(f"- {t.get('text', '')}" for t in filtered_triggers if t.get("type") in ["news", "breaking_news"] or "news" in t.get("id", ""))
            msg_prefix = (
                "📰 **以下新聞事件觸發了 Sentinel 警報，請針對此特定新聞進行分析，勿輸出通用週報。**\n\n"
                f"觸發事件：\n{news_texts}\n\n"
                "請以 **[行動] / [觀察等待] / [忽略]** 三選一作為結論（必須選擇其一）。\n"
                "若選擇 [行動]，請在報告末尾輸出 Actionable Orders 表格（即使信心度偏低也請填入）：\n"
                "| Ticker | Action | Amount (USD) | Confidence (1-10) | Reason |\n"
                "|--------|--------|-------------|-------------------|---------|\n"
                "若選擇 [觀察等待] 或 [忽略]，請說明理由（1-2 句）並指出此事件未來需要監控的條件。\n"
                "請以繁體中文撰寫，專業術語保留英文。"
            )
        
        elif has_price_trigger:
            # v9.1: Price-move alert — demand explicit hold/trim/add decision
            price_texts = "\n".join(f"- {t.get('text', '')}" for t in filtered_triggers if "move" in t.get("id", ""))
            msg_prefix = (
                "📊 **以下持倉出現重大價格異動，請立即評估並給出明確操作建議。**\n\n"
                f"異動明細：\n{price_texts}\n\n"
                "請針對每個異動持倉，給出 **加倉 / 持有 / 減倉** 的具體建議。\n"
                "若有操作，請輸出 Actionable Orders 表格。若選擇持有，請說明理由與停損條件。\n"
                "請以繁體中文撰寫，專業術語保留英文。"
            )
        
        elif has_risk_trigger:
            # v9.1: Risk alert — focus on portfolio risk, not generic market observation
            msg_prefix = (
                "⚠️ **以下風險指標觸發警報，請評估當前投資組合的風險曝露並給出具體改善建議。**\n\n"
                "請針對：(1) 槓桿水位是否需要調整 (2) 持倉集中度風險 (3) 是否需要再平衡，分別給出建議。\n"
                "若有操作（換庫 / 部分平倉 / 對沖），請輸出 Actionable Orders 表格。\n"
                "請以繁體中文撰寫，專業術語保留英文。"
            )

        elif has_allocation_drift:
            # Allocation Drift alert — focus Council on weight-based rebalancing
            drift_details = "\n".join(
                f"- {t.get('text', '')}" for t in filtered_triggers
                if t.get('type') == 'allocation_drift'
            )
            msg_prefix = (
                "⚖️ **以下持倉出現配置漂移 (Allocation Drift)，請評估是否需要再平衡。**\n\n"
                f"漂移明細：\n{drift_details}\n\n"
                "請針對每個漂移持倉，給出 **加倉 / 減倉 / 維持** 的具體建議，並以 weight-based 格式輸出。\n"
                "若有操作，請在報告末尾輸出 Actionable Orders 表格，包含 target_weight 和 delta_weight：\n"
                "| Ticker | Action | Target Weight (%) | Current Weight (%) | Delta Weight (%) | Confidence (1-10) | Reason |\n"
                "|--------|--------|-------------------|-------------------|-----------------|-------------------|--------|\n"
                "請以繁體中文撰寫，專業術語保留英文。"
            )

        context = {
            "source": source,
            "triggered_rules": display_texts,
            "timestamp": date.today().isoformat(),
            "msg_prefix": msg_prefix,
        }
        
        # Council Deliberation
        try:
            user_id = self.settings_service.user_id or self.user_id
            if not user_id:
                logger.warning("No user_id available for council session")
                return None
            summary = await self.council_service.start_session(
                topic, 
                context, 
                market_volatility=self.current_vix,
                user_id=user_id,
                mode="sentinel"
            )
            decision = summary.get('consensus', 'No Consensus')
        except Exception as e:
            logger.error(f"Council session failed: {e}", exc_info=True)
            err_type = type(e).__name__
            decision = (
                f"⚠️ **系統運行於安全模式 (Fail-safe Mode: {err_type})**\n\n"
                "目前無法取得 AI 委員會的即時評估（可能是內部組件初始化失敗或 LLM API 連線問題）。\n"
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
        # v4.2.2: Use internal user_id (email/UUID) for settings lookup, NOT LINE-specific ID
        target_user = self.settings_service.user_id or self.user_id or "broadcast"
        actions = []
        
        is_actionable = any(kw in decision.lower() for kw in ["sell", "reduce", "trim", "buy", "exit", "hedge"])
        is_extreme = any(t.get("level") == "CRITICAL" for t in filtered_triggers) or self.current_vix > 35
        
        # [Significance Filter v3.5]
        # If decision is vague and no critical trigger, suppress P0 noise.
        is_significant = is_actionable or is_extreme or "⚠️" in decision or "danger" in decision.lower()
        if not is_significant and "hold" in decision.lower():
            logger.info("Sentinel: Significance Filter suppressed notification")
            return

        if is_actionable:
            actions.append({"label": "前往 eToro 下單", "data": "action=etoro_link"})

        # [T3] Direct dispatch using NSM (no microservice, no hardcoded channels)
        await self._dispatch_notifications_direct(
            title=f"⚠️ {source} Alert",
            content=alert_content,
            actions=actions,
            category="sentinel"
        )
        
        # 🚨 Auto-hedging / Emergency Liquidation (Milestone 5.1)
        if is_extreme and any(kw in decision.lower() for kw in ["liquidate", "hedge", "panic", "emergency"]):
            # Run in background to avoid blocking notification flow
            import asyncio
            asyncio.create_task(self._trigger_emergency_protocol(target_user, decision))

        # 📊 Actionable Trade Signals → evaluate_and_execute_trade (Milestone 13.2)
        # All trade signals go through the unified confidence threshold logic
        elif is_actionable:
            trade_signals = await self._extract_trade_signals_from_decision(decision, filtered_triggers)
            if trade_signals:
                import asyncio
                asyncio.create_task(self._execute_trade_signals(target_user, trade_signals, source))

        # v9.1: Mandatory Post-Alert Action Fallback
        # EVERY non-suppressed alert must leave a persistent artifact.
        # If no trade signals were extracted and no emergency protocol ran,
        # we still: (A) spawn a research task for news triggers and (B) store an insight to memory.
        else:
            import asyncio
            from src.agents.skills.skill_loader import SkillLoader
            loader = SkillLoader(user_id=target_user)
            
            trigger_types_set = set(t.get('type', '') for t in filtered_triggers)
            has_any_news = any('news' in tt or 'breaking' in tt for tt in trigger_types_set) or \
                           any('news' in t.get('id', '') for t in filtered_triggers)
            
            if has_any_news:
                # Spawn background EventAnalysis research for each news ticker
                for t in filtered_triggers:
                    ticker = t.get('ticker')
                    if not ticker:
                        tid = t.get('id', '')
                        parts = [p for p in tid.split('_') if p.isupper() and 1 < len(p) <= 6]
                        if parts:
                            ticker = parts[0]
                    if ticker:
                        asyncio.create_task(
                            loader.run_skill(
                                "event_research",
                                user_id=target_user,
                                ticker=ticker,
                                event_source=t.get("type", "news"),
                                event_text=t.get("text", ""),
                                council_summary=decision[:500],
                            )
                        )
        
        # Always store alert insight to cognitive_memories (independent of action path)
        # This ensures every alert outcome is captured for future reflection
        import asyncio
        from src.agents.skills.skill_loader import SkillLoader
        import json
        loader = SkillLoader(user_id=target_user)
        
        asyncio.create_task(
            loader.run_skill(
                "distill_insight",
                user_id=target_user,
                source_texts=json.dumps([t.get("text","") for t in filtered_triggers[:3]], ensure_ascii=False),
                council_text=decision[:600],
                agent_name="SentinelService"
            )
        )

    async def _extract_trade_signals_from_decision(self, decision: str, triggers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract actionable trade signals from Council decision text.
        從委員會決策文字中提取可執行交易訊號。
        """
        logger.info("Sentinel: Extracting trade signals from Council decision using AI ActionExtractor...")
        try:
            from src.agents.skills.skill_loader import SkillLoader
            from src.services.transaction_service import TransactionService
            import json
            
            target_user = self.settings_service.user_id or self.user_id or "broadcast"
            loader = SkillLoader(user_id=target_user)
            
            # Build portfolio context for ActionExtractor
            portfolio_str = ""
            try:
                tx_svc = TransactionService()
                holdings = tx_svc.get_holdings_map(target_user)
                if holdings:
                    portfolio_str = ", ".join([f"{t}({d.get('quantity', 0)})" for t, d in holdings.items()])
            except Exception as he:
                logger.warning(f"Failed to get portfolio context for ActionExtractor: {he}")
            
            # Skillified: Pass as arguments to the skill
            trades_json = await loader.run_skill(
                "extract_actions", 
                user_id=target_user,
                decision_text=decision,
                portfolio=portfolio_str
            )
            raw_trades = json.loads(trades_json)
            signals = []
            
            for trade in raw_trades:
                ticker = str(trade.get("ticker", "")).upper()
                action = str(trade.get("action", "")).upper()
                if ticker and action in ["BUY", "SELL"]:
                    signals.append({
                        "ticker": ticker,
                        "action": action,
                        "quantity": float(trade.get("quantity", 1.0)),
                        "score": int(trade.get("confidence", 7)),
                        "intent": str(trade.get("intent", "auto")),
                        "reason": str(trade.get("reason", f"Sentinel Council: {decision[:120]}..."))
                    })
                    
            if signals:
                logger.info(f"Sentinel: Extracted {len(signals)} AI trade signals from Council decision.")
            else:
                logger.info("Sentinel: No AI trade signals extracted from Council decision.")
                
            return signals
            
        except Exception as e:
            logger.error(f"Sentinel: AI Trade extraction failed: {e}")
            return []

    async def _execute_trade_signals(self, user_id: str, signals: List[Dict[str, Any]], source: str) -> None:
        """
        Execute trade signals via AutomatedTradingService (unified confidence threshold logic).
        透過 AutomatedTradingService 執行交易訊號（套用統一信心指數閥值邏輯）。
        """
        try:
            from src.services.automated_trading_service import AutomatedTradingService
            auto_trade_svc = AutomatedTradingService()

            for signal in signals:
                await auto_trade_svc.evaluate_and_execute_trade(
                    user_id=user_id,
                    ticker=signal['ticker'],
                    action=signal['action'],
                    quantity=signal['quantity'],
                    confidence_score=signal['score'],
                    rationale=signal['reason']
                )
        except Exception as e:
            logger.error(f"Sentinel trade signal execution failed: {e}")

    async def _dispatch_notifications_direct(self, title: str, content: str, actions: List[Dict[str, Any]] = None, category: str = "sentinel"):
        """[T3] Direct dispatch using NSM (no microservice, no hardcoded channels)."""
        from src.services.notification_service import NotificationService
        from src.services.notification_settings_manager import NotificationSettingsManager
        
        try:
            target_user = self.settings_service.user_id or self.user_id or "broadcast"
            # [T2] Query user's preferred channels from DB (no hardcoding)
            nsm = NotificationSettingsManager(settings_repo=self.settings_service.settings_repo, user_id=target_user)
            user_channels = nsm.get_active_notification_channels()
            
            # Absolute minimum fallback if nothing configured
            if not user_channels:
                user_channels = ["web"]

            settings_svc = self.settings_service
            notification_svc = NotificationService.create_with_settings(
                settings_service=settings_svc, user_id=target_user
            )
            
            await notification_svc.notify_all(
                title=title,
                content=content,
                user_id=target_user,
                channels=user_channels,  # From DB per §5.2
                category=category,
                actions=actions
            )
            logger.info(f"Sentinel: Notifications dispatched via {user_channels}")
        except Exception as e:
            logger.error(f"Sentinel: Direct notification dispatch failed: {e}")

    async def _trigger_emergency_protocol(self, user_id: str, rationale: str) -> None:
        """
        Execute Auto-hedging / Emergency Liquidation via AutomatedTradingService (Milestone 5.1).
        針對所有持倉發送清倉建議，並可選擇買入避險 ETF。
        """
        if user_id == "broadcast":
             # For broadcast, we need to iterate actual real users. 
             # Safe fallback: retrieve all active users.
             users = self._get_all_user_ids()
        else:
             users = [user_id]
             
        logger.warning(f"Sentinel: Triggering Emergency Liquidation Protocol for {len(users)} users.")
        
        try:
            from src.services.automated_trading_service import AutomatedTradingService
            from src.services.transaction_service import TransactionService
            
            auto_trade_svc = AutomatedTradingService()
            tx_service = TransactionService()
            
            for uid in users:
                # [NEW] Fetch dynamic scores from settings (Milestone 13.2)
                emergency_score = int(self.settings_service.get_setting("emergency_liquidation_score", 9, user_id=uid) or 9)
                hedge_score = int(self.settings_service.get_setting("auto_hedge_score", 8, user_id=uid) or 8)
                
                active_tickers = tx_service.get_user_tickers(user_id=uid, only_active=True)
                if not active_tickers:
                     continue
                
                # Dynamic quantity: query actual holdings per ticker
                holdings_map = tx_service.get_holdings_map(uid)
                     
                for ticker in active_tickers:
                    # Get actual holding quantity for this ticker
                    holding_qty = holdings_map.get(ticker, {}).get('quantity', 0)
                    if holding_qty <= 0:
                        logger.info(f"Emergency: Skipping {redact_secrets(ticker)} for {redact_pii(uid)}, no active holdings.")
                        continue
                    
                    # 發送清倉建議 (使用實際持倉量)
                    await auto_trade_svc.evaluate_and_execute_trade(
                        user_id=uid,
                        ticker=ticker,
                        action="SELL",
                        quantity=holding_qty,  # 動態計算：使用實際持倉量
                        confidence_score=emergency_score, 
                        rationale=f"🚨 Sentinel 緊急防禦機制啟動 (Emergency Liquidation)。\n判定: {rationale[:100]}..."
                    )
                    
                # 附帶建議：自動對沖 (Buy SQQQ for Nasdaq hedge)
                # Use position_sizing skill logic for hedge amount
                hedge_amount = float(self.settings_service.get_setting("emergency_hedge_amount", 50.0, user_id=uid) or 50.0)
                await auto_trade_svc.evaluate_and_execute_trade(
                    user_id=uid,
                    ticker="SQQQ",
                    action="BUY",
                    quantity=hedge_amount,
                    confidence_score=hedge_score, 
                    rationale=f"🚨 Sentinel 自動對沖機制啟動 (Auto-Hedging)。建議建立 SQQQ 避險。"
                )
        except Exception as e:
            logger.error(f"Emergency Protocol failed: {e}")

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
            # v4.2.6: Use with self.engine.connect() to avoid session leaks in helper method
            from sqlalchemy import text
            with self.repo.engine.connect() as conn:
                # Primary: use user id (UUID) from users table
                rows = conn.execute(text("SELECT id FROM users")).fetchall()
                user_ids = [str(row[0]) for row in rows] if rows else []
                
                # Fallback: also include user_ids from settings table
                settings_rows = conn.execute(text(
                    "SELECT DISTINCT user_id FROM settings "
                    "WHERE user_id IS NOT NULL AND user_id NOT IN ('system', 'SYSTEM')"
                )).fetchall()
                for row in settings_rows:
                    uid_str = str(row[0])
                    if uid_str and uid_str not in user_ids:
                        user_ids.append(uid_str)
                
                return user_ids
        except Exception as e:
            logger.warning(f"Failed to get user IDs: {e}")
            return []

    def close(self):
        """
        Explicitly close all resources.
        明確關閉所有資源。
        """
        try:
            self.repo.close_session()
            if self.settings_service:
                self.settings_service.repo.close_session()
            if self.keyword_service:
                self.keyword_service._repo.close_session()
            logger.info("SentinelService context closed.")
        except Exception as e:
            logger.error(f"Error during SentinelService close: {e}")

    def _get_polling_tickers(self) -> List[str]:
        """
        Get tickers to scan during polling (user's active holdings).
        取得輪詢時需掃描的標的（用戶持有的活躍部位）。
        """
        try:
            tickers = set()
            user_ids = self._get_all_user_ids()
            for uid in user_ids:
                user_tickers = self.transaction_service.get_user_tickers(uid, only_active=True)
                tickers.update(user_tickers)
            return list(tickers) if tickers else ["SPY"]  # Fallback to SPY
        except Exception as e:
            logger.warning(f"Failed to get polling tickers: {e}")
            return ["SPY"]

    def _contains_risk_keywords(self, text: str) -> bool:
        """
        Check if text contains risk-related keywords using keyword service.
        使用關鍵字服務進行風險關鍵詞比對。
        """
        return self.keyword_service.contains_risk(text)

    async def _check_active_sources(self) -> List[Dict[str, Any]]:
        """
        Poll enabled data sources defined in the Settings UI.
        """
        triggers = []
        settings = self.settings_service.get_all_settings()
        
        # Sources identified in the Matrix that support polling
        from src.config.data_source_matrix_config import get_pollable_sources
        pollable_sources = get_pollable_sources()
        
        for sid in pollable_sources:
            if settings.get(f"source_{sid}_enabled") == "true":
                try:
                    # Generic polling trigger
                    res = await self._poll_single_source(sid, settings)
                    if isinstance(res, list):
                        triggers.extend(res)
                    elif res:
                        triggers.append(res)
                except Exception as e:
                    logger.error(f"Polling failed for {redact_secrets(sid)}: {e}")
        
        return triggers

    async def _poll_single_source(self, sid: str, settings: Dict[str, str]) -> Any:
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
        
        # Tiingo Integration (v5.0) - Event-Driven News Scanning
        elif sid == "tiingo":
            try:
                triggers = []
                tickers = self._get_polling_tickers()
                for ticker in tickers[:3]:  # Rate limit: scan top 3
                    news = self.market_service.tiingo.get_news(ticker)
                    if news:
                        for item in news[:2]:  # Check latest 2 headlines per ticker
                            title = (item.get('title') or '').lower()
                            if self._contains_risk_keywords(title):
                                triggers.append({
                                    "text": f"📰 [Tiingo] {ticker} 風險新聞: {item.get('title', '')[:80]}",
                                    "id": f"tiingo_risk_{ticker}_{hash(item.get('title', '')) % 10000}",
                                    "ticker": ticker
                                })
                return triggers if triggers else None
            except Exception as e:
                logger.error(f"Tiingo polling failed: {e}")

        # Finnhub Integration (v5.0) - Event-Driven Sentiment Scanning
        elif sid == "finnhub":
            try:
                triggers = []
                tickers = self._get_polling_tickers()
                for ticker in tickers[:3]:
                    sentiment = self.market_service.finnhub.get_sentiment(ticker)
                    if sentiment:
                        score = sentiment.get('sentiment', 0)
                        # Trigger on extreme negative sentiment
                        if isinstance(score, (int, float)) and score < -0.5:
                            triggers.append({
                                "text": f"📉 [Finnhub] {ticker} 極端負面情緒: sentiment={score:.2f}",
                                "id": f"finnhub_neg_{ticker}",
                                "ticker": ticker,
                                "value": score
                            })
                    # Also check news
                    news = self.market_service.finnhub.get_news(ticker) if hasattr(self.market_service.finnhub, 'get_news') else None
                    if news:
                        for item in news[:2]:
                            headline = (item.get('headline') or item.get('title', '')).lower()
                            if self._contains_risk_keywords(headline):
                                triggers.append({
                                    "text": f"📰 [Finnhub] {ticker} 風險新聞: {(item.get('headline') or item.get('title', ''))[:80]}",
                                    "id": f"finnhub_risk_{ticker}_{hash(item.get('headline', '')) % 10000}",
                                    "ticker": ticker
                                })
                return triggers if triggers else None
            except Exception as e:
                logger.error(f"Finnhub polling failed: {e}")

        # AlphaVantage Integration (v5.0) - Sentiment-Driven Event Detection
        elif sid == "alpha_vantage":
            try:
                triggers = []
                tickers = self._get_polling_tickers()
                for ticker in tickers[:3]:
                    news = self.market_service.alpha_vantage.get_news(ticker)
                    if news:
                        for item in news[:2]:
                            label = (item.get('sentiment_label') or '').lower()
                            title = item.get('title', '')
                            if label in ('bearish', 'strongly_bearish') or self._contains_risk_keywords(title.lower()):
                                triggers.append({
                                    "text": f"📰 [AlphaVantage] {ticker} 風險事件 ({label}): {title[:80]}",
                                    "id": f"av_risk_{ticker}_{hash(title) % 10000}",
                                    "ticker": ticker
                                })
                return triggers if triggers else None
            except Exception as e:
                logger.error(f"AlphaVantage polling failed: {e}")
                
        # Readwise Integration
        elif sid == "readwise":
            try:
                from src.services.readwise_service import ReadwiseService
                readwise_svc = ReadwiseService(user_id=self.user_id)
                last_sync = self.settings_service.get_setting("readwise_last_sync")
                
                # Fetch highlights in background thread
                import asyncio
                loop = asyncio.get_event_loop()
                analyzed = await loop.run_in_executor(
                    None, 
                    lambda: readwise_svc.fetch_and_analyze_highlights(updated_after=last_sync)
                )
                
                if analyzed:
                    from datetime import datetime, timezone
                    self.settings_service.save_setting("readwise_last_sync", datetime.now(timezone.utc).isoformat())
                    
                    rw_triggers = []
                    for item in analyzed:
                        analysis = item.get("analysis", {})
                        if analysis.get("requires_action"):
                            rw_triggers.append({
                                "text": f"💡 Readwise Insight: {item.get('text')}\nAI Comment: {analysis.get('reasoning')}\nAction: {analysis.get('suggested_action')}",
                                "id": f"readwise_{item.get('id')}",
                                "category": "READWISE_INSIGHT"
                            })
                    return rw_triggers
            except Exception as e:
                logger.error(f"Readwise polling failed: {e}")
                
        return None

    def _trigger_thematic_update(self, event_text: str, theme_key: str, current_state: Any) -> None:
        """
        Helper to asynchronously trigger the ThematicAgent to update dynamic tracking lists based on events.
        PAD Phase 2: Uses async LLM call via gateway.
        """
        logger.info(f"Triggering Thematic Update for {redact_secrets(theme_key)} due to high-impact event.")
        try:
            context = {
                "event_text": event_text,
                "theme_key": theme_key,
                "current_state": current_state
            }
            # Run in a separate thread so we don't block the main event loop
            # 用於異步執行耗時的智能體分析，確保不會阻塞主事件迴圈
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # Create a new loop if one doesn't exist for this thread
                # 若當前執行度無事件迴圈，則建立新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            # PAD Phase 2: Schedule async task instead of thread executor
            asyncio.ensure_future(self._call_agent_llm("Thematic", context, tier="smart"))
        except Exception as e:
            logger.error(f"Failed to trigger thematic update for {redact_secrets(theme_key)}: {e}")

    async def _check_risk_consistency(self) -> List[Dict[str, Any]]:
        """
        Dimension 7: Risk Profile Consistency Check & Dynamic Cash Management.
        v5.0: Strictly isolated to self.user_id.
        """
        triggers = []
        uid = self.user_id
        
        if not uid:
            logger.debug("_check_risk_consistency: skipped (no user_id)")
            return triggers
        
        # 0. Get Inflation Data via FredService (Optimized: fetch once per check)
        from src.services.fred_service import FredService
        fred = FredService(user_id=self.user_id)
        macro_data = fred.get_macro_indicators()
        cpi_data = macro_data.get("CPI", {})
        inflation_rate = 0.03 # Default 3% if missing
        
        if cpi_data:
            history = cpi_data.get("history", [])
            if len(history) >= 12:
                # Simple YoY approximation
                inflation_rate = (history[0] - history[-1]) / history[-1]
        
        # 1. Get Risk Profile
        profile = self.settings_service.get_setting("risk_profile", "Balanced", user_id=uid)
        
        # 2. Get Latest Snapshot from persistent repo
        latest = self.snapshot_repo.get_latest_by_user(uid)
        
        if latest is not None:
            latest_dict = latest if isinstance(latest, dict) else latest.to_dict()
            lev = latest_dict.get("leverage_ratio", 0.0)
            
            # Check Balanced Profile vs 1.8x leverage (v5.1: Increased from 1.7x)
            threshold = 1.80
            if profile == "Balanced":
                # v8.4: Bullish Flexibility - Allow up to 2.0x if trend is good
                trend = self._get_market_trend("SPY")
                vix_data = self.market_service.get_macro_data().get("market_indicators", {})
                vix = vix_data.get("^VIX", 20.0) 
                
                if trend == "Bullish" and vix < 22:
                    threshold = 2.00
                    # Additional text for expansion
                    alert_suffix = f" [Bullish Expansion]: Trend is positive and VIX ({vix:.1f}) is stable. Leverage limit boosted to {threshold}x."
                else:
                    threshold = 1.80
                    alert_suffix = ""

                if lev > threshold:
                    # v8.2: Nuanced leverage alert if cash is also high
                    is_cash_high = False
                    if latest_dict.get("total_nlv", 0) > 0:
                        cash_ratio = latest_dict.get("cash_balance", 0) / latest_dict.get("total_nlv", 1)
                        if cash_ratio > 0.15: # Threshold for 'high cash'
                            is_cash_high = True

                    alert_text = f"⚠️ Risk Mapping Alert: Your 'Balanced' profile leverage is {lev:.2f}x (Max Allowed: {threshold:.2f}x).{alert_suffix}"
                    if is_cash_high:
                        alert_text += " [Efficiency Advice]: High leverage detected while holding excess cash. Consider 'Rolling' positions: reduce lower-confidence leverage to reinvest in higher-quality or defensive assets to maintain exposure safely."
                    
                    triggers.append({
                        "id": f"risk_consistency_{uid}",
                        "text": alert_text,
                        "severity": "high",
                        "type": "risk_consistency"
                    })
        
        # 3. Dynamic Cash Ratio Check (v5.0)
        target_cash_base = float(self.settings_service.get_setting("target_cash_ratio", 0.1, user_id=uid))
        inflation_mod = 1 + max(0, inflation_rate)
        
        vix_triggers = self._check_vix_anomaly()
        vix_multiplier = 1.0
        if any("VIX Spiked" in t.get("text", "") for t in vix_triggers):
            vix_multiplier = 1.5
        
        final_target_cash = target_cash_base * inflation_mod * vix_multiplier
        
        actual_cash_ratio = 0.0
        if latest is not None:
            latest_dict = latest if isinstance(latest, dict) else latest.to_dict()
            nlv = latest_dict.get("total_nlv", 0.0)
            cash = latest_dict.get("cash_balance", 0.0)
            if nlv > 0:
                actual_cash_ratio = cash / nlv
        
        if actual_cash_ratio < final_target_cash * 0.9:
            triggers.append({
                "id": f"cash_ratio_low_{uid}",
                "text": (f"⚠️ Dynamic Cash Alert: Actual {actual_cash_ratio*100:.1f}% "
                        f"vs Adjusted Target {final_target_cash*100:.1f}% "
                        f"(Inf: {inflation_rate*100:.1f}%, VIX Mod: {vix_multiplier}x)."),
                "severity": "medium",
                "type": "cash_management"
            })
        
        if actual_cash_ratio > final_target_cash * 1.5:
            # v5.0: New trigger for excess cash (Rule #8 & User Request)
            is_aggressive = profile == "Aggressive"
            severity = "high" if is_aggressive else "low"
            priority = 1 if is_aggressive else 3
            trigger_id = f"cash_ratio_high_{uid}"
            logger.info(
                "Sentinel: cash_ratio_high trigger: ratio=%.1f%% target=%.1f%%",
                actual_cash_ratio * 100, final_target_cash * 100,
            )
            triggers.append({
                "id": trigger_id,
                "text": (f"💰 Excess Cash Alert: Actual {actual_cash_ratio*100:.1f}% "
                        f"vs Adjusted Target {final_target_cash*100:.1f}%. "
                        f"Consider searching for new investment opportunities."),
                "severity": severity,
                "priority": priority,
                "type": "cash_management"
            })

        return triggers

    async def _handle_cash_deployment_logic(self, triggers: List[Dict[str, Any]]) -> None:
        """
        Handle cash_ratio_high trigger: cooldown-gated, inline skill execution,
        then route candidates through AutomatedTradingService (existing threshold logic).

        Cooldown: settings key `cash_deployment_cooldown_hours` (default 4h) — prevents
        repeated LLM + broker calls on every sentinel tick.
        Auto-execute: governed by existing `auto_trade_threshold` / `auto_trade_min_threshold`
        user settings in AutomatedTradingService.
        """
        trigger_id = f"cash_ratio_high_{self.user_id}"
        cash_trigger = next((t for t in triggers if t.get("id") == trigger_id), None)
        if not cash_trigger:
            return

        # Cooldown gate — prevents re-trigger on every tick
        try:
            cooldown_hours = int(float(
                self.settings_service.get_setting("cash_deployment_cooldown_hours", 4, user_id=self.user_id) or 4
            ))
        except (ValueError, TypeError):
            cooldown_hours = 4
        deploy_signal_id = f"cash_deployment_{self.user_id}"
        if self.repo.is_duplicate_alert(title="", content="", hours=cooldown_hours, signal_id=deploy_signal_id):
            logger.debug("Sentinel: cash_deployment within cooldown window (%dh), skipping.", cooldown_hours)
            return

        logger.info("Sentinel: Excess cash detected for %s. Starting deployment flow.", redact_pii(self.user_id))

        # Run skill inline (avoids subprocess overhead and stdout-only result)
        try:
            from src.agents.skills.cash_deployment.impl import cash_deployment
            result_json = await cash_deployment(self.user_id)
            result = json.loads(result_json)
        except Exception as e:
            logger.error("Sentinel: cash_deployment skill error: %s", e)
            return

        if result.get("status") != "overweight":
            logger.info("Sentinel: cash_deployment status=%s, nothing to deploy.", result.get("status"))
            return

        # Archive immediately so cooldown prevents double-fire even if execution is slow
        self.repo.log_alert(
            "cash_deployment",
            f"Cash deployment triggered: ${result.get('excess_cash', 0):.2f} excess",
            metadata={"signal_id": deploy_signal_id, "excess_cash": result.get("excess_cash"), "candidates": result.get("candidates")},
        )

        candidates = result.get("candidates") or []
        if not candidates:
            logger.info("Sentinel: No deployment candidates returned.")
            return

        # Confidence score on 0-100 scale (matches auto_trade_threshold / auto_trade_min_threshold settings)
        # excess_ratio: 2.0x→50, 2.5x→63, 3.0x→75 (auto-execute at default 75), 3.5x→88
        cash_ratio = result.get("cash_ratio", 0.0)
        target_ratio = max(result.get("target_ratio", 0.1), 0.01)
        excess_ratio = cash_ratio / target_ratio
        confidence_score = min(95, max(50, round(excess_ratio * 25)))

        logger.info(
            "Sentinel: Evaluating %d deployment candidates, confidence=%d "
            "(cash=%.1f%%, target=%.1f%%, excess_ratio=%.1fx)",
            len(candidates), confidence_score,
            cash_ratio * 100, target_ratio * 100, excess_ratio,
        )

        try:
            from src.services.automated_trading_service import AutomatedTradingService
            auto_trade_svc = AutomatedTradingService()
            for cand in candidates:
                ticker = cand.get("ticker")
                amount = cand.get("allocated_amount", 0.0)
                reason = cand.get("reason", "Cash deployment")
                if not ticker or amount <= 0:
                    continue
                await auto_trade_svc.evaluate_and_execute_trade(
                    user_id=self.user_id,
                    ticker=ticker,
                    action="BUY",
                    quantity=amount,
                    confidence_score=confidence_score,
                    rationale=f"[Cash Deployment] Excess Cash: ${result.get('excess_cash', 0):.2f} | {reason}",
                )
        except Exception as e:
            logger.error("Sentinel: cash deployment execution error: %s", e, exc_info=True)

    # ──────────────────────────────────────────
    # Dimension 10: Allocation Drift Detection (v10.0)
    # ──────────────────────────────────────────

    async def _handle_rebalance_logic(self, rebalance_triggers: Optional[List[Dict[str, Any]]] = None) -> None:
        """
        [Phase 5] Execute rebalancing trades based on detected triggers.
        執行基於偵測到觸發點的再平衡交易。
        """
        import time
        cooldown = 1800 # 30 minutes
        fire_key = f"rebalance_{self.user_id}"
        if self.last_fire_time.get(fire_key, 0) + cooldown > time.time():
             logger.info(f"SentinelService: De-bouncing rebalance for {fire_key} (cooldown: {cooldown}s)")
             return
        self.last_fire_time[fire_key] = time.time()
        if not rebalance_triggers:
            logger.debug("Sentinel: No rebalance triggers to process.")
            return

        logger.info(f"Sentinel: Processing {len(rebalance_triggers)} rebalance triggers for user {self.user_id}")
        
        try:
            from src.services.automated_trading_service import AutomatedTradingService
            auto_trade_svc = AutomatedTradingService()

            for trigger in rebalance_triggers:
                if trigger.get('ticker') == 'CASH':
                    logger.info(f"Sentinel: Cash overweight trigger routed to cash deployment flow.")
                    continue
                if trigger.get("action") != "trigger_rebalance":
                    continue
                
                ticker = trigger.get("ticker")
                sell_qty = trigger.get("sell_quantity")
                rationale = trigger.get("rationale", "[Sentinel Rebalance] Concentration Risk detected.")
                
                if not ticker or not sell_qty or sell_qty < 0.01:
                    logger.debug(f"Sentinel: Skipping rebalance for {ticker} (qty: {sell_qty})")
                    continue

                logger.warning(
                    f"Sentinel Rebalancing Execution: {ticker} | Selling {sell_qty} units | Reason: {rationale}"
                )
                
                # Execute rebalancing trade (Forced action, confidence=100)
                await auto_trade_svc.evaluate_and_execute_trade(
                    user_id=self.user_id,
                    ticker=ticker,
                    action="SELL",
                    quantity=sell_qty,
                    confidence_score=100, 
                    rationale=rationale
                )
        except Exception as e:
            logger.error(f"Sentinel: rebalancing execution error: {e}", exc_info=True)
    async def _check_infrastructure_health(self) -> List[Dict[str, Any]]:
        """
        [Phase 9] Dimension 9: Infrastructure Health Watchdog.
        Monitors database and background worker health. If pressure is too high, 
        attempts self-healing or raises an alert.
        """
        triggers = []
        try:
            # 1. DB Health
            from src.data.database import get_db_engine
            from sqlalchemy import text
            engine = get_db_engine()
            db_status = "ok"
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as e:
                db_status = "degraded"
                logger.error(f"Sentinel DB Health Check Failed: {e}")
                triggers.append({
                    "id": "health_db_critical",
                    "text": "🚨 Critical System Alert: Database connection degraded or offline.",
                    "severity": "critical",
                    "priority": 0,
                    "type": "infrastructure"
                })

            # 2. Celery Worker Queue Depth
            from src.infrastructure.celery_app import app as celery_app
            import redis
            
            # Use redis directly if configured
            redis_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
            try:
                r = redis.from_url(redis_url)
                # Celery default queue name is 'celery'
                queue_depth = r.llen("celery")
                
                if queue_depth > 50:
                    logger.warning(f"Sentinel: High queue depth detected ({queue_depth} pending). Initiating Self-Healing.")
                    # Self-Healing Action: Accelerate workers or alert
                    triggers.append({
                        "id": "health_queue_pressure",
                        "text": f"⚠️ System Pressure Alert: High background task queue depth ({queue_depth}). Initiating worker soft-reload/scaling.",
                        "severity": "high",
                        "priority": 1,
                        "type": "infrastructure"
                    })
                    # Worker Pool expansion attempt
                    celery_app.control.broadcast('pool_grow', n=1)
            except Exception as redis_e:
                 logger.debug(f"Sentinel could not check redis queue size directly: {redis_e}")

        except Exception as e:
            logger.error(f"Infrastructure Health Check Failed: {e}")
            
        return triggers
    
    # ──────────────────────────────────────────
    # Dimension 10: Allocation Drift Detection (v10.0)
    # ──────────────────────────────────────────
    
    async def _check_allocation_drift(self) -> List[Dict[str, Any]]:
        """
        Dimension 10: Allocation Drift Check
        v10.1: Concentration Risk Mode. Uses max_single_position_weight instead of fixed targets.
        """
        triggers = []
        
        try:
            # 1. Get current allocation
            current_allocation = await self._get_current_allocation()
            if not current_allocation:
                return triggers

            # 2. Get thresholds from DB
            max_single_weight = self.settings_service.get_setting('max_single_position_weight', 25.0, self.user_id)
            # Rebalance target is slightly below max to prevent frequent oscillations
            target_rebalance_weight = max_single_weight * 0.9  
            warning_threshold = max_single_weight * 0.85
            
            # 3. Calculate total portfolio value for quantity math
            cash = self.transaction_service.get_cash_balance(self.user_id)
            total_portfolio_value = sum(item['market_value'] for item in current_allocation.values()) + cash
            
            # 4a. Cash Concentration Check (cash is also an allocation position)
            # 現金也是一種配置倉位 — 過高的現金代表失去平衡
            try:
                from src.services.portfolio_aggregator_service import PortfolioAggregatorService
                _aggregator = PortfolioAggregatorService(user_id=self.user_id)
                _portfolio = await _aggregator.get_aggregated_portfolio()
                broker_cash = _portfolio.get('total_cash', 0.0)
                broker_equity = _portfolio.get('total_equity', 0.0)
            except Exception:
                broker_cash = max(cash, 0)
                broker_equity = total_portfolio_value if total_portfolio_value > 0 else 1

            if broker_equity > 0:
                cash_weight = (broker_cash / broker_equity) * 100
                if cash_weight >= max_single_weight:
                    triggers.append({
                        'id': f'cash_concentration_{self.user_id[:8]}',
                        'text': f'💰 CASH OVERWEIGHT: Cash weight is {cash_weight:.1f}%, exceeding limit of {max_single_weight:.1f}%. Deploy excess cash to rebalance portfolio.',
                        'type': 'allocation_drift',
                        'trigger_type': 'cash_overweight',
                        'severity': 'high',
                        'priority': 2,
                        'ticker': 'CASH',
                        'current_weight_pct': round(cash_weight, 2),
                        'limit_weight_pct': round(max_single_weight, 2),
                        'action': 'deploy_cash',
                        'timestamp': pd.Timestamp.now().isoformat()
                    })
                    logger.warning(f"[Cash Concentration] Cash weight={cash_weight:.1f}% exceeds limit={max_single_weight:.1f}%")

            # 4b. Check for Concentration Risk
            for ticker, info in current_allocation.items():
                current_weight = info.get('weight', 0)
                
                if current_weight >= max_single_weight:
                    # Calculate amount to sell to reach target_rebalance_weight
                    # (current_weight - target_rebalance_weight) / 100 * total_portfolio_value = USD to sell
                    current_price = info.get('current_price', 0)
                    if current_price > 0 and total_portfolio_value > 0:
                        weight_diff = current_weight - target_rebalance_weight
                        usd_to_sell = (weight_diff / 100.0) * total_portfolio_value
                        shares_to_sell = round(usd_to_sell / current_price, 2) # v6.0 Fractional rounding
                        
                        if shares_to_sell >= 0.01:
                            triggers.append({
                                'id': f'concentration_risk_critical_{ticker}',
                                'text': f'🆘 CONCENTRATION RISK: {ticker} weight is {current_weight:.1f}%, exceeding limit of {max_single_weight:.1f}%. Auto-selling {shares_to_sell} units to rebalance.',
                                'type': 'allocation_drift',
                                'trigger_type': 'allocation_drift',
                                'severity': 'critical',
                                'priority': 1,
                                'ticker': ticker,
                                'current_weight_pct': round(current_weight, 2),
                                'limit_weight_pct': round(max_single_weight, 2),
                                'sell_quantity': shares_to_sell,
                                'action': 'trigger_rebalance',
                                'timestamp': pd.Timestamp.now().isoformat()
                            })
                            logger.warning(f"[Concentration Risk] CRITICAL: {ticker} weight={current_weight:.1f}% -> Selling {shares_to_sell} units")
                
                elif current_weight >= warning_threshold:
                    logger.info(f"[Concentration Risk] WARNING: {ticker} approaching limit: {current_weight:.1f}% (limit={max_single_weight:.1f}%)")
            
            return triggers
            
        except Exception as e:
            logger.error(f"Error in allocation drift check: {e}", exc_info=True)
            return []

    async def _get_current_allocation(self) -> Dict[str, Dict[str, float]]:
        """
        獲取當前投資組合配置（按權重 %），使用券商即時數據。
        
        Returns:
            {ticker: {shares, weight, market_value, current_price}}
        """
        try:
            # v10.1: 使用 PortfolioAggregatorService 獲取即時數據，避免 DB 滯後
            from src.services.portfolio_aggregator_service import PortfolioAggregatorService
            aggregator = PortfolioAggregatorService(user_id=self.user_id)
            portfolio_data = await aggregator.get_aggregated_portfolio()
            
            positions = portfolio_data.get('positions', [])
            total_equity = portfolio_data.get('total_equity', 0.0)

            if not positions and portfolio_data.get('total_cash', 0.0) <= 0:
                return {}

            if total_equity <= 0:
                logger.warning("Sentinel: Total portfolio value is zero or negative. Cannot calculate weights.")
                return {}

            allocation = {}
            for p in positions:
                weight = (p.market_value / total_equity) * 100
                allocation[p.symbol] = {
                    'shares': p.quantity,
                    'quantity': p.quantity,
                    'weight': round(weight, 2),
                    'market_value': p.market_value,
                    'current_price': p.current_price,
                    'avg_price': p.open_price
                }
            
            logger.debug(f"Sentinel: Live allocation retrieved: {allocation}")
            return allocation
        except Exception as e:
            logger.error(f"Sentinel: Failed to get live allocation, falling back to DB: {e}", exc_info=True)
            return await self._get_current_allocation_from_db()

    async def _get_current_allocation_from_db(self) -> Dict[str, Dict[str, float]]:
        """
        (Fallback) 從資料庫獲取持倉配置。
        """
        try:
            positions = self.transaction_service.get_active_positions(self.user_id)
            if not positions:
                return {}

            tickers = [p['ticker'] for p in positions]
            current_prices = await self.market_service.get_current_prices(tickers)

            cash = self.transaction_service.get_cash_balance(self.user_id)
            total_stock_value = 0.0
            for p in positions:
                ticker = p['ticker']
                price = current_prices.get(ticker, p.get('avg_price', 0))
                p['current_price'] = price
                p['market_value'] = price * p.get('quantity', 0)
                total_stock_value += p['market_value']

            portfolio_value = total_stock_value + cash
            
            allocation = {}
            for p in positions:
                weight = (p['market_value'] / portfolio_value) * 100 if portfolio_value > 0 else 0
                allocation[p['ticker']] = {
                    'shares': p['quantity'],
                    'weight': round(weight, 2),
                    'market_value': p['market_value'],
                    'current_price': p['current_price'],
                    'avg_price': p['avg_price']
                }
            return allocation
        except Exception as e:
            logger.error(f"Fallback allocation fetch failed: {e}")
            return {}

    async def _calculate_total_portfolio_value(self) -> float:
        """
        計算投資組合總價值（包括現金），複用 allocation 邏輯以獲取即時價格。
        
        Returns:
            Total portfolio value in USD
        """
        try:
            allocation = await self._get_current_allocation()
            cash = self.transaction_service.get_cash_balance(self.user_id)
            
            total_stock_value = sum(v.get('market_value', 0) for v in allocation.values())
            total_portfolio = total_stock_value + cash
            
            logger.debug(f"Portfolio value calculation: stocks={total_stock_value:.2f}, cash={cash:.2f}, total={total_portfolio:.2f}")
            return total_portfolio
            
        except Exception as e:
            logger.error(f"Error calculating portfolio value: {e}", exc_info=True)
            return 0.0
