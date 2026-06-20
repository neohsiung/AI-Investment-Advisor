from src.utils.logger import setup_logger
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union, Awaitable
import sys
from datetime import datetime
from src.utils.time_utils import get_current_time
from src.services.transaction_service import TransactionService
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.services.market_data_service import MarketDataService
from src.agents.council_adapter import CouncilAgentAdapter
from src.services.performance_service import PerformanceService
from src.agents.factory import AgentFactory
from src.utils.time_utils import get_current_utc_time
import re
import inspect
import os
import json
import asyncio
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter, TierConfig
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, Message, LLMConfig, RetryLLMGateway
from src.repositories.settings_repository import AlchemySettingsRepository

async def safe_run(agent, ctx):
    """Helper to handle both async and sync agent run methods."""
    res = agent.run(ctx)
    if inspect.isawaitable(res):
        return await res
    return res

logger = setup_logger("WorkflowService")

from src.services.task_planning_service import TaskPlanningService
from src.services.memory_service import MemoryService
from src.repositories.memory_repository import AlchemyMemoryRepository
from src.infrastructure.agent_llm_provider import AgentLLMProvider
from src.utils.format_utils import format_agent_output

class BaseWorkflow(ABC):
    """
    Abstract base class for all investment workflows.
    投資工作流抽象基底類別。
    
    Implements the Template Method pattern for workflow execution.
    實作 Template Method 模式以執行工作流。
    """
    def __init__(self, user_id: str, transaction_repo: Any = None, transaction_service: Optional[TransactionService] = None, market_service: Optional[MarketDataService] = None) -> None:
        """
        Initialize the base workflow.
        初始化基底工作流。
        """
        self.user_id = user_id
        
        # Dependency Injection
        self.transaction_repo = transaction_repo or AlchemyTransactionRepository()
        self.transaction_service = transaction_service or TransactionService(repository=self.transaction_repo)
        self.market_service = market_service or MarketDataService(user_id=self.user_id)
        
        # Memory Service Injection
        self.memory_repo = AlchemyMemoryRepository()
        self.llm_provider = AgentLLMProvider(user_id=self.user_id)
        self.memory_service = MemoryService(repository=self.memory_repo, llm_provider=self.llm_provider)
        
        # PAD Phase 2: Initialize model router and gateway for LLM calls
        from src.data.database import get_db_engine
        self.settings_repo = AlchemySettingsRepository(engine=get_db_engine())
        self.model_router = SettingsAwareModelRouter(self.settings_repo)
        self.gateway = LLMGatewayFactory.create(provider="openrouter")
        
        self.context = {}
        self.logger = setup_logger(self.__class__.__name__)
        self.performance_service = PerformanceService(user_id=self.user_id)
        self.logger = logger  # Use global logger for Base

    async def _call_agent_llm(self, agent_name: str, context: Dict[str, Any], tier: str = "smart", 
                              temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """
        PAD Phase 2: Replace AgentFactory.create_*_agent().run() with direct gateway calls.
        Generic method to call LLM for any agent role.
        """
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

            chain = build_config_chain(self.user_id, tier)
            if not chain:
                raise ValueError(f"No model configured for tier={tier} user={self.user_id}")

            pipeline = ResilientLLMPipeline(config_chain=chain)

            from src.utils.prompt_utils import load_agent_prompt
            
            system_prompt = load_agent_prompt(agent_name)
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]

            logger.debug(f"WorkflowService: Calling {agent_name} agent via tier={tier} (user={self.user_id})")
            response, _ = await pipeline.execute(messages, temperature=temperature, max_tokens=max_tokens)

            if not isinstance(response, str):
                raise ValueError(f"Unexpected response type from pipeline: {type(response)}")

            return response
        except Exception as e:
            logger.error(f"WorkflowService: {agent_name} agent failed: {e}")
            raise

    def _parse_actionable_orders(self, final_report: str):
        """
        Parses the actionable orders table from the final report and populates the context.
        Supports both Markdown pipe tables and HTML <table> formats.
        """
        try:
            import re
            rows = []

            # --- Strategy 1: Markdown pipe table (preferred) ---
            lines = final_report.split('\n')
            for i, line in enumerate(lines):
                if '|' in line and '---' in line:
                    # Validate that this is likely the Actionable Orders table
                    prev_line = lines[i-1].lower() if i > 0 else ""
                    if any(x in prev_line for x in ["action", "動作", "代號", "ticker"]):
                        for j in range(i + 1, len(lines)):
                            row_line = lines[j].strip()
                            if not row_line.startswith('|'):
                                break
                            cols = [c.strip() for c in row_line.split('|') if c.strip()]
                            if len(cols) >= 4 and "---" not in row_line:
                                rows.append(cols)
                        break

            # --- Strategy 2: HTML <table> fallback ---
            if not rows:
                # Find all <tr> blocks, skip header row
                tr_blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', final_report, re.DOTALL | re.IGNORECASE)
                for tr in tr_blocks:
                    if '<th' in tr.lower():
                        continue
                    tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL | re.IGNORECASE)
                    cleaned = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
                    if len(cleaned) >= 4:
                        rows.append(cleaned)

            if not rows:
                self.logger.info("No Actionable Orders table found in CIO report.")
                return

            # --- Process parsed rows ---
            for cols in rows:
                ticker = cols[0].strip().upper()
                action = cols[1]
                quantity = cols[2]

                try:
                    score_raw = re.search(r"(\d+)", cols[3])
                    score = int(score_raw.group(1)) if score_raw else 5
                except (ValueError, IndexError):
                    score = 5

                u_act = action.upper()
                cio_signal = "HOLD"
                if any(x in u_act for x in ["BUY", "ACCUMULATE", "加碼", "買"]):
                    cio_signal = "BUY"
                elif any(x in u_act for x in ["SELL", "TRIM", "REDUCE", "LIQUIDATE", "減碼", "出清", "賣", "避險"]):
                    cio_signal = "SELL"

                if cio_signal != "HOLD":
                    # Get price for performance tracing
                    t_data = self.context.get('market_data', {}).get(ticker, {})
                    t_price = 0
                    if t_data:
                         raw = t_data.get('price_data', {}).get('close', 0)
                         if isinstance(raw, list) and raw: t_price = raw[-1]
                         else: t_price = raw

                    if self.performance_service:
                        self.performance_service.record_recommendation(
                            agent_name="CIO",
                            ticker=ticker,
                            signal=cio_signal,
                            price=t_price
                        )

                    if 'actionable_orders' not in self.context:
                        self.context['actionable_orders'] = []

                    self.context['actionable_orders'].append({
                        'ticker': ticker,
                        'action': cio_signal,
                        'quantity': quantity,
                        'score': score,
                        'reason': cols[4] if len(cols) >= 5 else f"CIO Signal ({cio_signal})"
                    })

            if self.context.get('actionable_orders'):
                self.logger.info(f"Parsed {len(self.context['actionable_orders'])} actionable orders.")

        except Exception as e:
            self.logger.warning(f"Failed to parse Actionable Orders table: {e}")

    async def run(self, dry_run: bool = False, force_refresh: bool = False) -> Any:
        """
        Execute the workflow skeleton asynchronously (Template Method).
        執行工作流骨架（樣板方法 - 非同步）。
        """
        self.logger.info(f"Starting {self.__class__.__name__} for user {self.user_id}")
        
        try:
            # Step 1: Data Collection & Pre-checks
            self.collect_data()
            
            # Step 2: Strategy/Analysis
            should_proceed = await self.execute_analysis(force_refresh)
            
            if not should_proceed:
                self.logger.info("Analysis determined no further action needed.")
                return "SKIPPED"

            # Step 3: Synthesis & Decision
            # [Optimization] If synthesize_results is sync, it runs normally. 
            # If we make it async, we must await it.
            if hasattr(self, 'synthesize_results_async'):
                final_report = await self.synthesize_results_async()
            else:
                final_report = self.synthesize_results()
                import asyncio
                if asyncio.iscoroutine(final_report):
                    final_report = await final_report
            
            # --- Translate to Traditional Chinese ---
            # v7.1 Fix: Use LLMGatewayFactory directly (NOT EngineerAgent which is a prompt optimizer and rejects translation tasks).
            #           Direct gateway call returns a clean string — no JSON wrapping.
            self.logger.info("Translating final report to Traditional Chinese...")
            try:
                from src.infrastructure.llm.llm_config_chain import build_config_chain
                from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

                chain = build_config_chain(self.user_id, "fast")
                if not chain:
                    raise ValueError(f"No fast-tier model configured for user={self.user_id}")
                pipeline = ResilientLLMPipeline(config_chain=chain)

                from src.utils.prompt_utils import load_agent_prompt
                
                translation_system = load_agent_prompt("report_translator")
                translation_user = (
                    "Translate the following investment report to Traditional Chinese (zh-TW). "
                    "Remember: output ONLY the translated text, nothing else.\n\n"
                    f"REPORT:\n{final_report}"
                )

                messages = [
                    Message(role="system", content=translation_system),
                    Message(role="user",   content=translation_user),
                ]
                translated_report, _ = await pipeline.execute(messages, temperature=0.3, max_tokens=4096)

                # gateway.chat returns a raw string — no dict parsing needed
                if translated_report and isinstance(translated_report, str) and translated_report.strip():
                    final_report = translated_report.strip()
                    self.logger.info(f"Translation successful ({len(final_report)} chars).")
                else:
                    self.logger.warning("Translation returned empty result, using original English report.")
            except Exception as e:
                self.logger.error(f"Translation failed: {e}. Falling back to original English report.")

                
            # Step 4: Reporting & Storage
            if not dry_run:
                await self.distribute_report(final_report)
                
                # [NEW] Multi-Agent Trade Execution (System 2 Integration)
                # -------------------------
                actionable_orders = self.context.get('actionable_orders', [])
                if actionable_orders:
                    self.logger.info(f"Processing {len(actionable_orders)} actionable orders via AutomatedTradingService.")
                    from src.services.automated_trading_service import AutomatedTradingService
                    auto_trade_svc = AutomatedTradingService()
                    
                    # v7.0: Build deliberation context for enriched notifications
                    debate_snippet = ""
                    deliberation = self.context.get('deliberation_context', '')
                    if deliberation:
                        debate_snippet = f"\n\n📋 **議會思辨摘要 (Council Deliberation)**:\n{str(deliberation)[:500]}..."
                    
                    for order_data in actionable_orders:
                        try:
                            # Parse quantity to float safely
                            try:
                                qty_val = float(str(order_data['quantity']).replace('%', ''))
                            except (ValueError, TypeError):
                                qty_val = 100.0 # Default fallback amount
                            
                            # Enrich rationale with deliberation reasoning
                            enriched_rationale = str(order_data.get('reason', 'CIO Signal'))
                            if debate_snippet:
                                enriched_rationale += debate_snippet
                                
                            # This handles threshold check, auto-exec, and notification/approval requests (Option A)
                            await auto_trade_svc.evaluate_and_execute_trade(
                                ticker=order_data['ticker'],
                                action=order_data['action'],
                                quantity=qty_val,
                                confidence_score=order_data['score'],
                                rationale=enriched_rationale,
                                user_id=self.user_id
                            )
                        except Exception as e:
                            self.logger.error(f"Failed to execute trade for {order_data['ticker']}: {e}")
            else:
                self.logger.info(f"[Dry Run] Report generated but not distributed:\n{final_report}")
                
            return final_report

        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            raise e

    async def _assemble_integrated_report(self, 
                                  cio_full_output: str, 
                                  detailed_debate_content: str, 
                                  agent_for_polish=None) -> str:
        """
        組合最終報告 (Integrated Pattern)。
        此方法統一了 Daily 與 Weekly 報告的生成邏輯，確保詳細分析被正確植入。

        1. 使用正則表達式將 CIO 的摘要版 'Great Debate' 替換為詳細版。
        2. 執行最終潤飾 (Polish) 以確保格式與語氣專業並包含行動指令表。
        
        Assembles the final report using the Integrated Pattern.
        1. Replaces CIO's summarized 'Great Debate' with the detailed version using Regex.
        2. Polishes the final output if an agent is provided.
        """
        import re
        
        # 定義替換模式：尋找 ## 3. (Debate) 與下一個 ## 標題之間的內容 (包含標題本身)
        # Define replacement pattern: Find content starting from ## 3 up to ## 4 or EOF
        # Assuming the generated detailed content INCLUDES the header "## 3. ..."
        pattern = r"(## 3\..*?)(?=## \d\.|$)"
        
        # 若無詳細內容，提供預設訊息
        if not detailed_debate_content:
             detailed_debate_content = "## 3. 議會深度審議 (Council Deep Dive)\n(No detailed transcript available / 暫無詳細辯論紀錄)"

        # 執行替換
        # Execute Replacement
        import re
        modified_report = re.sub(pattern, detailed_debate_content, cio_full_output, flags=re.DOTALL)
        
        final_report = modified_report
        
        # 若替換未發生 (例如找不到標題)，則將詳細內容附加於後，並發出警告
        # If replacement failed (headers not found), append logic and warn
        if modified_report == cio_full_output:
             self.logger.warning("Report Injection Failed: Header '## 3...' not found. Appending transcript.")
             # 嘗試簡單附加確保資訊不丟失
             final_report = f"{cio_full_output}\n\n{detailed_debate_content}"
        
        # 最終潤飾
        # Final Polish
        if agent_for_polish and hasattr(agent_for_polish, 'polish_report'):
             final_report = await agent_for_polish.polish_report(final_report)
             
        return final_report


    def collect_data(self):
        """Common data collection: Get active tickers."""
        # Filter for active positions only to avoid analyzing sold stocks
        user_tickers = self.transaction_service.get_user_tickers(self.user_id, only_active=True)
        # Fix v4.1.8: De-duplicate tickers to avoid redundant agent analysis
        unique_tickers = sorted(list(set(user_tickers)))
        self.context['tickers'] = unique_tickers
        logger.info(f"Unique active tickers to analyze: {unique_tickers}")
        
        # Prefetch Market Data (Technical + Fundamental)
        # Fixes missing financials/news for Agents
        self.context['market_data'] = self.market_service.get_market_context(user_tickers, enrich=True)

    @abstractmethod
    async def execute_analysis(self, force_refresh: bool) -> bool:
        """Execute specific analysis steps. Returns True if reporting is needed."""
        pass

    @abstractmethod
    async def synthesize_results(self) -> str:
        """Combine analysis results into a final report."""
        pass

    async def distribute_report(self, content: str) -> str:
        """Store in DB and send notifications via preferred channels."""
        title = f"Investment Report ({self.__class__.__name__}) - {get_current_time().strftime('%Y-%m-%d')}"
        try:
            from src.services.reporting_service import ReportingService
            reporting_service = ReportingService()
            html_content = reporting_service.generate_professional_html(content, title=title)
        except Exception as e:
            logger.error(f"HTML transformation failed: {e}. Falling back to markdown.")
            html_content = content
        
        # 1. Store in DB
        report_id = None
        try:
            from src.repositories.report_repository import AlchemyReportRepository
            report_repo = AlchemyReportRepository()
            
            # Save the generated HTML content
            report_id = report_repo.save(
                user_id=self.user_id,
                report_type=self.__class__.__name__,
                summary=title,
                content=html_content
            )
            logger.info(f"Report stored in database (ID: {report_id}).")
        except Exception as e:
            logger.error(f"Failed to store report: {e}")

        # 2. Dispatch Notifications (DB-driven, no invalid microservice call)
        await self._dispatch_notifications(title, html_content)
        
        return report_id

    async def _notify_user(self, report_id: str):
        """[PAD] Helper for WorkflowStages to dispatch notifications for a stored report."""
        try:
            from src.repositories.report_repository import AlchemyReportRepository
            report_repo = AlchemyReportRepository()
            
            # 1. Try to get specific report
            report = report_repo.get_by_id(report_id)
            if report:
                await self._dispatch_notifications(report['summary'], report['content'])
                return

            # 2. Fallback to latest if ID not found (transient consistency or legacy)
            df = report_repo.get_latest_reports(self.user_id, limit=1)
            if not df.empty:
                latest = df.iloc[0]
                await self._dispatch_notifications(latest['summary'], latest['content'])
            else:
                logger.warning(f"No report found for user {self.user_id} to notify.")
        except Exception as e:
            logger.error(f"Failed to notify user for report {report_id}: {e}")

    async def _dispatch_notifications(self, title: str, html_content: str):
        """Send notifications via Event Queue (Event Aggregation v2.0).
        
        Events are written to event_queue for agent pull-processing instead of
        being pushed to notification channels. Only P0 events bypass the queue.
        """
        from src.services.event_aggregator import EventAggregator

        try:
            aggregator = EventAggregator()

            # Extract summary from HTML for classification
            import re
            text_only = re.sub(r'<[^>]+>', ' ', html_content)
            text_only = re.sub(r'\s+', ' ', text_only).strip()[:2000]

            # Classify tier based on content
            event_data = {
                "title": title,
                "summary": text_only[:500],
                "has_html": True,
            }

            tier, priority = EventAggregator.classify_tier("report", event_data, text_only)
            aggregator.ingest_event(
                user_id=self.user_id,
                event_type="report",
                content=event_data,
                tier=tier,
                priority=priority,
            )
            logger.info(
                f"Workflow: report ingested as event [{tier}/p{priority}] — {title[:50]}"
            )

            # P0 reports → immediate notification (theoretical, unlikely for reports)
            if tier == "P0":
                from src.services.notification_service import NotificationService
                from src.services.settings_service import SettingsService
                from src.services.notification_settings_manager import NotificationSettingsManager
                from src.repositories.settings_repository import AlchemySettingsRepository

                settings_repo = AlchemySettingsRepository()
                nsm = NotificationSettingsManager(settings_repo=settings_repo, user_id=self.user_id)
                user_channels = nsm.get_active_notification_channels() or ["web"]
                settings_svc = SettingsService(user_id=self.user_id)
                notification_svc = NotificationService.create_with_settings(
                    settings_service=settings_svc, user_id=self.user_id
                )
                await notification_svc.notify_all(
                    title=title,
                    content=html_content,
                    user_id=self.user_id,
                    channels=user_channels,
                    category="report"
                )
                logger.info(f"Workflow: P0 report bypassed queue → notified via {user_channels}")
        except Exception as e:
            logger.error(f"Workflow: event ingestion failed: {e}")


class DailyWorkflow(BaseWorkflow):
    """
    Workflow for daily market checks and brief reporting.
    每日工作流：負責每日市場檢查與簡要報告。
    """
    async def execute_analysis(self, force_refresh: bool) -> bool:
        """
        Daily: Only check Momentum/News. If no major signal, skip.
        每日執行: 僅檢查動能訊號與新聞。若無重大訊號，則跳過。
        """
        if not self.context['tickers']:
            logger.info("No tickers to analyze.")
            return False

        # Lightweight analysis (e.g. Momentum only)
        # For simplicity, we assume we check all but filter in CIO
        
        # Here we run Momentum Agent & Sentiment Agent
        # Daily: Short TTL (1hr), assume force_refresh implies bypassing cache
        # PAD Phase 2: Replace AgentFactory calls with _call_agent_llm
        
        results = []
        ticker_reports = {}
        for ticker in self.context['tickers']:
            data = self.context['market_data'].get(ticker, {})
            
            ticker_ctx = {
                "ticker": ticker,
                "price_data": data.get("price_data", {}),
                "indicators": data.get("indicators", {}),
                "financials": self.market_service.get_financials(ticker),
                "news": self.market_service.get_news(ticker),
                "web_intelligence": data.get("web_intelligence", []),
                "yield_curve": self.context['market_data'].get('yield_curve', {}) 
            }

            # PAD Phase 2: Replace safe_run(agent) with _call_agent_llm
            res = await self._call_agent_llm("Momentum", ticker_ctx, tier="fast")
            results.append(res) # Keep for legacy check
            
            # Sentiment Analysis
            sent_res = await self._call_agent_llm("Sentiment", ticker_ctx, tier="fast")
            
            # Fundamental Analysis (Cached Reference)
            f_res = await self._call_agent_llm("Fundamental", ticker_ctx, tier="smart")

            ticker_reports[ticker] = {
                "momentum": res,
                "sentiment": sent_res,
                "fundamental": f_res
            }

            # Record Recommendations for Performance Tracking
            # Fix: Extract scalar price from list if needed
            raw_price = data.get("price_data", {}).get("close", 0)
            if isinstance(raw_price, list):
                if raw_price:
                    current_price = raw_price[-1]
                else:
                    current_price = 0.0
            else:
                current_price = raw_price
            
            # Simple Regex Signal Extraction (Robust to DSPy or Legacy text)
            # Look for explicit "BUY", "SELL", "HOLD"
            # 4. Record Sentiment Signal
            # ---------------------------
            # Parse Sentiment Score: > 0.6 BUY, < 0.4 SELL
            sent_score = 0.5
            if isinstance(sent_res, dict):
                sent_score = sent_res.get("score", 0.5)
            elif isinstance(sent_res, str):
                # Try to extract score or use a default based on keywords
                if "POSITIVE" in sent_res.upper() or "GOOD" in sent_res.upper():
                    sent_score = 0.7
                elif "NEGATIVE" in sent_res.upper() or "BAD" in sent_res.upper():
                    sent_score = 0.3
                s_signal = "HOLD"
                if sent_score >= 0.6:
                    s_signal = "BUY"
                elif sent_score <= 0.4:
                    s_signal = "SELL"
                
                if s_signal != "HOLD":
                    self.performance_service.record_recommendation(
                        agent_name="Sentiment",
                        ticker=ticker,
                        signal=s_signal,
                        price=current_price
                    )

            # 5. Record Momentum & Fundamental (Legacy String Parsing)
            # ----------------------------------------------------
            for agent_name, response in [("Momentum", res), ("Fundamental", f_res)]:
                signal = "HOLD"
                text_res = str(response).upper()
                if "BUY" in text_res:
                    signal = "BUY"
                elif "SELL" in text_res:
                    signal = "SELL"
                
                if signal != "HOLD":
                    self.performance_service.record_recommendation(
                        agent_name=agent_name,
                        ticker=ticker,
                        signal=signal,
                        price=current_price
                    )
            
            # Simple heuristic for 'significant change'
            if "STRONG" in res.upper():
                has_significant_change = True

        self.context['momentum_results'] = results
        self.context['ticker_reports'] = ticker_reports
        
        # Always proceed to report if user triggered it manually (implied by this flow usually)
        # Or if we want to be strict about signals. For now let's return True to generate the CIO report.
        return True

    async def synthesize_results(self) -> str:
        """
        Combine analysis results into a final report.
        將分析結果綜合成最終報告。
        """
        # Use CIO Agent for Daily Report (Daily Pulse Mode)
        # PAD Phase 2: CIO agent will be called via _call_agent_llm later in this method
        
        # --- Section 1: Memory & Macro Context ---
        
        # Retrieve simple macro data for context
        macro_data = self.market_service.get_macro_data()
        
        # v3.2 Update: Handle nested structure
        vix = "N/A"
        spy = "N/A"
        spread = "N/A"
        
        # Parse YFinance (Market Indicators)
        if "market_indicators" in macro_data:
             market_inds = macro_data["market_indicators"]
             vix = market_inds.get('^VIX', 'N/A')
             spy = market_inds.get('SPY', 'N/A')
        elif isinstance(macro_data, dict):
             vix = macro_data.get('^VIX', 'N/A')
             spy = macro_data.get('SPY', 'N/A')
             
        # Parse FRED (Economics)
        if "economics" in macro_data:
             econ = macro_data["economics"]
             if "10Y2Y_Spread" in econ:
                  spread_data = econ["10Y2Y_Spread"]
                  spread = f"{spread_data.get('value', 'N/A')} ({spread_data.get('trend', 'N/A')})"
        
        macro_summary_line = f"- VIX: {vix}\n- SPY: {spy}\n- Yield Spread (10Y-2Y): {spread}"

        # Run Macro Agent for Context via PAD Phase 2
        macro_deep = await self._call_agent_llm("Macro", {}, tier="smart")
    
        
        combined_macro = f"Daily Market Check (v3.2 Data):\n{macro_summary_line}\n\n[Reference Weekly Macro Context]:\n{macro_deep}"
        
        # --- Memory Consistency Check ---
        memory_consistency_note = ""
        if self.memory_service:
            # 1. Get recent context
            mem_ctx = self.memory_service.get_context(self.user_id, "daily")
            
            # 2. Synthesize current signal summary
            current_signals = []
            for t, data in self.context.get('ticker_reports', {}).items():
                mom = str(data.get('momentum', '')).upper()
                sent = str(data.get('sentiment', '')).upper()
                current_signals.append(f"{t}: Momentum={mom[:50]}..., Sentiment={sent[:50]}...")
            
            current_view_summary = f"Macro: {combined_macro[:200]}\nSignals: {'; '.join(current_signals)}"
            
            # 3. Detect Contradictions
            conflicts = await self.memory_service.detect_conflicts(current_view_summary, mem_ctx)
            
            if conflicts:
                logger.warning(f"Contradictions Detected: {conflicts}")
                memory_consistency_note = "\n\n**CRITICAL CONSISTENCY WARNING**:\n" + \
                                          "\n".join([f"- {c}" for c in conflicts]) + \
                                          "\n*Instruction*: You must explicitly acknowledge and justify these shifts in view compared to previous days."

        # --- Section 2: The Great Debate (Detailed Ticker Analysis) ---
        # Strategy: Build this section manually to ensure full detail is preserved inline.
        # [NEW] Include Holdings Context from TransactionService
        holdings_map = self.transaction_service.get_holdings_map(self.user_id)
        
        # --- [NEW] Multi-Broker Integration ---
        from src.services.broker_factory import BrokerFactory
        from src.infrastructure.risk_manager import RiskManager
        
        # Initialize Broker
        # Default to Etoro if not set, or read from settings
        broker = BrokerFactory.get_broker(self.user_id)
        risk_manager = RiskManager()
        
        broker_status_msg = ""
        broker_connected = False
        
        try:
            # 1. Sync History
            await broker.sync_history(self.user_id)  # ← async
            
            # 2. Check Risk Status (Constraints)
            # Fetch history and positions for Risk Manager
            history = await broker.get_history()    # ← async
            positions = await broker.get_positions() # ← async
            
            constraints_ok = risk_manager.check_constraints(self.user_id, history, positions)
            
            if not constraints_ok:
                broker_status_msg = f"🚨 **RISK ALERT ({broker.get_name()})**: AI Trading PAUSED. Manual Review Required."
            else:
                broker_status_msg = f"✅ **System Status ({broker.get_name()})**: Active & Monitoring."
            
            # 3. Get Financial Snapshot
            account = await broker.get_account()  # ← async
            if account:
                broker_status_msg += f"\n- **Total Equity**: ${account.total_equity:,.2f}"
                broker_status_msg += f"\n- **Cash**: ${account.available_cash:,.2f}"
            
            broker_connected = True
        except Exception as e:
            logger.warning(f"Broker ({broker.get_name()}) Service not available: {e}")

        # --- [NEW] Section 3: Capital Deployment Context (Sentinel Triggered) ---
        cash_deployment_context = ""
        if self.memory_service:
            # Query memory for recent 'cash_deployment' analysis (Sentinel triggered)
            deployment_mem = self.memory_service.get_context(self.user_id, "cash_deployment")
            if deployment_mem and deployment_mem.recent_items:
                latest = deployment_mem.recent_items[0]
                cash_deployment_context = f"\n\n[CAPITAL DEPLOYMENT OPPORTUNITY DETECTED ({latest.report_date})]:\n{latest.compressed_summary or latest.full_content[:2000]}"
        
        # Ensure broker_status_msg is not overwritten incorrectly
        if not broker_connected:
             broker_status_msg = f"⚠️ **Connection Alert**: {broker.get_name()} Bridge Offline."

        detailed_debate_section = "## 2. 議會焦點辯論 (The Great Debate & Detailed Analysis)\n\n"
        detailed_debate_section += f"{broker_status_msg}\n\n"
        detailed_debate_section += "本日針對投資組合進行深度多空思辨，並附上完整技術與基本面數據。\n\n"
        
        # Accumulate ticker contexts for CIO Synthesis
        ticker_contexts = []
        
        for t, data in self.context.get('ticker_reports', {}).items():
            # Truncate agent outputs for Daily (70% conciseness rule)
            def summarize(text):
                text = str(text or "N/A").strip()
                if not text or text == "N/A":
                    return "N/A"
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                # Take only the first few meaningful lines or bullet points
                summary_lines = [l for l in lines if l.startswith('-') or l.startswith('*') or len(l) > 15][:3]
                return "\n".join(summary_lines) if summary_lines else text[:150] + "..."

            mom = summarize(format_agent_output(data.get('momentum', 'N/A')))
            sent = summarize(format_agent_output(data.get('sentiment', 'N/A')))
            fun = summarize(format_agent_output(data.get('fundamental', 'N/A')))
            
            # [NEW] Add Quantity/Holding Info
            qty = holdings_map.get(t, {}).get('quantity', 0)
            
            detailed_debate_section += f"### {t} (Holdings: {qty})\n"
            detailed_debate_section += f"- **Technical (Mom)**: {mom}\n"
            detailed_debate_section += f"- **Quality (Fun)**: {fun}\n"
            detailed_debate_section += f"- **Psychology (Sent)**: {sent}\n\n"
            
            ticker_contexts.append(f"Ticker: {t} (Qty: {qty})\nData:\n- Mom: {mom}\n- Fun: {fun}\n- Sent: {sent}")

        # --- Section 3 & 4: CIO Synthesis & Orders ---
        # We instruct the CIO to generate ONLY the synthesis and orders based on the detailed debate we just built.
        
        # [NEW] Use rich portfolio string from Repo for CIO Context (so it knows weights/quantities for orders)
        # Using CIO's internal helper logic or just rely on Repo summary string
        # TransactionService relies on Repo. Let's just construct it here or call repo method.
        # Since we have holdings_map, let's build it.
        portfolio_str = ", ".join([f"{t} ({d['quantity']})" for t, d in holdings_map.items()])
        if not portfolio_str:
             portfolio_str = ", ".join(self.context['tickers']) if self.context['tickers'] else "No Tickers"
        
        cio_context = {
            "macro_report": combined_macro,
            # We pass the pre-formatted debate section as the 'swarm_context' effectively
            "council_transcript": "\n".join(ticker_contexts), 
            "portfolio": portfolio_str,
            "consistency_constraints": memory_consistency_note,
            "cash_deployment_context": cash_deployment_context, # Inject deployment insight
            "user_id": self.user_id,
            "report_focus": "Daily Synthesis"
        }
        
        # Call CIO
        # Note: The CIO prompt is structured to output the whole report usually.
        # We might get some redundancy if CIO outputs "The Great Debate" again.
        # However, since we are overriding the final report assembly, we can try to extract or just accept duplication for now
        # OR we can update the Prompt. 
        # Ideally, we want CIO to output 'Market Sentiment', 'CIO Synthesis', 'Actionable Orders'.
        # And we inject 'The Great Debate' in between.
        
        # PAD Phase 2: Replace AgentFactory with _call_agent_llm
        cio_output = await self._call_agent_llm("CIO", cio_context, tier="smart", max_tokens=3000)
        
        # --- Final Assembly (Integrated Pattern) ---
        # 組合最終報告 (集成模式)
        # v7.0: Store deliberation context for trade notification enrichment
        self.context['deliberation_context'] = detailed_debate_section
        
        final_report = await self._assemble_integrated_report(
            cio_full_output=cio_output,
            detailed_debate_content=detailed_debate_section,
            agent_for_polish=None  # PAD Phase 2: agent_for_polish removed as we use gateway now
        )

        # Store in Memory
        if self.memory_service:
            try:
                await self.memory_service.store_report(
                    user_id=self.user_id,
                    report_type="daily",
                    date=datetime.now().strftime("%Y-%m-%d"),
                    content=final_report
                )
            except Exception as e:
                logger.error(f"Failed to store report in memory: {e}")

        # Post-Process: Record Macro & CIO Signals
        # ... (rest of signal recording logic)
        # ----------------------------------------
        
        # 1. Macro Signal (Proxy on SPY)
        macro_signal = "HOLD"
        m_text = macro_deep.upper()
        if "BULLISH" in m_text or "RISK ON" in m_text:
            macro_signal = "BUY"
        elif "BEARISH" in m_text or "RISK OFF" in m_text:
            macro_signal = "SELL"
        
        if macro_signal != "HOLD":
            # Record against a market proxy like SPY
            spy_price = self.context['market_data'].get('SPY', {}).get('price_data', {}).get('close', 0)
            if isinstance(spy_price, list) and spy_price: spy_price = spy_price[-1] 
            
            self.performance_service.record_recommendation(
                agent_name="Macro",
                ticker="SPY",
                signal=macro_signal,
                price=spy_price
            )

        # 2. CIO Signals (Regex Extraction)
        try:
            # Extract Action lines based on ### [TICKER] blocks
            blocks = final_report.split("### ")
            
            for block in blocks:
                # Extract Ticker from first line e.g. "NVDA"
                ticker_match = re.match(r"([A-Z]+)", block)
                if not ticker_match: continue
                ticker = ticker_match.group(1)

                # Extract Action from the block
                action_match = re.search(r"\*\*Action\*\*:\s*\*\*(\w+)\*\*", block, re.IGNORECASE)
                if not action_match: continue
                
                u_act = action_match.group(1).upper()
                cio_signal = "HOLD"
                if any(x in u_act for x in ["BUY", "ACCUMULATE", "加碼"]):
                    cio_signal = "BUY"
                elif any(x in u_act for x in ["SELL", "TRIM", "REDUCE", "LIQUIDATE", "減碼", "出清"]):
                    cio_signal = "SELL"
                
                if cio_signal != "HOLD":
                    # Get price
                    t_data = self.context['market_data'].get(ticker, {})
                    t_price = 0
                    if t_data:
                         raw = t_data.get('price_data', {}).get('close', 0)
                         if isinstance(raw, list) and raw: t_price = raw[-1]
                         else: t_price = raw
                    
                    if self.performance_service:
                        self.performance_service.record_recommendation(
                            agent_name="CIO",
                            ticker=ticker,
                            signal=cio_signal,
                            price=t_price
                        )
        except Exception as e:
            logger.warning(f"Failed to extract CIO signals block by block: {e}")

        # [NEW] Global Parse for Actionable Orders Table
        self._parse_actionable_orders(final_report)

        return final_report




class WeeklyWorkflow(BaseWorkflow):
    """
    Workflow for comprehensive weekly analysis and strategy refinement.
    每週工作流：負責全面的每週分析與策略調整。
    """
    async def run_weekly_cycle(self, user_id: str, context_data: dict = None) -> str:
        """
        Enhanced Weekly Workflow using Antigravity Planning + Existing Agents.
        Implementation of the 'Plan -> Execute' pattern.
        """
        logger.info(f"Starting Weekly Cycle for {user_id}")
        
        context_data = context_data or {}
        
        # 0. Pre-load Data (Optimized Bulk Fetch)
        if 'tickers' not in self.context:
             self.collect_data()
        
        # 1. Plan Phase
        # If planner is available, use it to generate the structured plan
        if self.task_planner:
            # We pass current context (with loaded tickers/market data) to the planner
            plan_context = {
                "tickers": self.context.get('tickers', []),
                "market_data_summary": "Active" if self.context.get('market_data') else "Pending"
            }
            plan = self.task_planner.decompose_goal("Generate Weekly Report", plan_context)
            logger.info(f"Generated Plan: {[t.name for t in plan.tasks]}")
            
            # 2. Execution Phase
            task_results = {}
            
            # [NEW] Fetch Rich Portfolio for Council
            holdings_map = self.transaction_service.get_holdings_map(user_id)
            rich_portfolio = [{'symbol': t, 'quantity': d['quantity']} for t, d in holdings_map.items()]
            
            # 'execution_context' starts with global context (market data, etc)
            execution_context = {**self.context, **context_data, "portfolio": rich_portfolio} 
            
            # Fetch real-time macro data
            macro_data = self.market_service.get_macro_data()
            vix = macro_data.get('market_indicators', {}).get('^VIX', macro_data.get('^VIX', 'N/A'))
            spy = macro_data.get('market_indicators', {}).get('SPY', macro_data.get('SPY', 'N/A'))
            spread = macro_data.get('economics', {}).get('10Y2Y_Spread', {}).get('value', 'N/A')
            execution_context["macro_data_summary"] = f"- VIX: {vix}\n- SPY: {spy}\n- 10Y-2Y Spread: {spread}"
            
            for task in plan.tasks:
                logger.info(f"--- Executing Task: {task.name} ---")
                
                # 2.1 Agent Selection
                agent_info = self._select_agent_for_task(task.name, user_id, tier=task.model_tier)
                # 2.2 Input Prep
                agent_input = self._bridge_input_context(task, execution_context)
                
                # 2.3 Run Agent
                try:
                    # PAD Phase 2: Handle both tuple returns (agent_name, tier) and CouncilAgentAdapter instances
                    if isinstance(agent_info, tuple):
                        agent_name, tier = agent_info
                        response = await self._call_agent_llm(agent_name, agent_input, tier=tier, max_tokens=2000)
                    else:
                        # CouncilAgentAdapter case
                        response = await safe_run(agent_info, agent_input)
                    # 2.4 Capture Output
                    task_results[task.name] = response
                    execution_context[f"RESULT_{task.name}"] = response
                    if isinstance(response, dict):
                        execution_context.update(response) # Merge dict results
                except Exception as e:
                    logger.error(f"Task {task.name} Failed: {e}")
                    task_results[task.name] = f"Error: {e}"

            # 3. Final Synthesis (The Report)
            # Strategy: Separate High-Level Strategy from Detailed Map-Reduce Output
            
            # A. Extract Portfolio Details (Map-Reduce Transcript)
            portfolio_details = ""
            for res_key, res_val in task_results.items():
                if isinstance(res_val, dict) and "transcript" in res_val:
                    # Found the Council Output
                    portfolio_details = res_val["transcript"]
            
            # B. Progressive Debate & Synthesis (CIO)
            # Instead of a single pass, we have CIO review the map-reduce output and explicitly summarize the debate
            synthesis_agent_info = self._select_agent_for_task("Report Synthesis", user_id)
            
            # Map Execution Context keys to CIO's specific prompt requirements
            macro_report_combined = f"【即時宏觀指標】\n{execution_context.get('macro_data_summary', 'N/A')}\n\n【週期分析】\n{execution_context.get('RESULT_Market Cycle Analysis', 'N/A')}"
            
            syn_context = {
                **execution_context,
                "macro_report": macro_report_combined,
                "sector_strategy": execution_context.get("RESULT_Sector Rotation & Swarm Insight", "N/A"),
                "thematic_context": f"{self._fetch_base_thematic_context(user_id)}\n\n【供應鏈與產業深潛】\n{execution_context.get('RESULT_Supply Chain & Industry Deep-Dive', 'N/A')}"
            }
            
            # Progressive Debate Loop Prompt Injection
            debate_prompt = (
                "Please review the provided analyses (Macro, Sector, Portfolio Deep-Dive, Supply Chain). "
                "If you see divergent signals (e.g., strong fundamentals but weak momentum), explicitly debate them in the 'Council Deep Dive' section. "
                "Synthesize a final consensus strategy. Output the final markdown report based on your template."
            )
            syn_context["task_instruction"] = debate_prompt
            
            # PAD Phase 2: Handle tuple return from _select_agent_for_task
            if isinstance(synthesis_agent_info, tuple):
                agent_name, tier = synthesis_agent_info
                syn_response = await self._call_agent_llm(agent_name, syn_context, tier=tier, max_tokens=3000)
            else:
                # CouncilAgentAdapter case
                syn_response = await safe_run(synthesis_agent_info, syn_context)
            
            # C. Assemble Final Report (Integrated Pattern)
            
            # Pattern: Replace CIO's "Great Debate" or "Sector Strategy" (if it contains debate) with Detailed Council Transcript
            # We look for the standard header from CIO. If found, we inject.
            
            # Common headers for debate section in CIO output:
            # "## 2. 議會焦點辯論" or "## 2. The Great Debate"
            
            import re
            pattern = r"(## 2\..*?)(?=## 3\.)"
            
            # If portfolio_details (Transcript) is empty, warn
            # C. Assemble Final Report (Integrated Pattern)
            final_report = await self._assemble_integrated_report(
                cio_full_output=syn_response,
                detailed_debate_content=portfolio_details,
                agent_for_polish=None
            )
            
            # D. Parse & Execute Actionable Orders (v7.0: consistent with DailyWorkflow)
            # ─────────────────────────────────────────────────────────
            self._parse_actionable_orders(str(final_report))
            actionable_orders = self.context.get('actionable_orders', [])
            if actionable_orders:
                logger.info(f"WeeklyWorkflow: Processing {len(actionable_orders)} actionable orders via AutomatedTradingService.")
                from src.services.automated_trading_service import AutomatedTradingService
                auto_trade_svc = AutomatedTradingService()
                
                # Build deliberation context snippet for trade notifications
                debate_snippet = ""
                if portfolio_details:
                    # Truncate to first 500 chars for notification readability
                    debate_snippet = f"\n\n📋 **議會思辨摘要 (Council Deliberation)**:\n{portfolio_details[:500]}..."
                
                import asyncio
                for order_data in actionable_orders:
                    try:
                        try:
                            qty_val = float(str(order_data['quantity']).replace('%', ''))
                        except (ValueError, TypeError):
                            qty_val = 100.0
                        
                        # Enrich rationale with deliberation reasoning
                        enriched_rationale = str(order_data.get('reason', 'Weekly CIO Signal'))
                        if debate_snippet:
                            enriched_rationale += debate_snippet
                        
                        # Schedule async trade execution (sync context → event loop)
                        asyncio.create_task(auto_trade_svc.evaluate_and_execute_trade(
                            ticker=order_data['ticker'],
                            action=order_data['action'],
                            quantity=qty_val,
                            confidence_score=order_data['score'],
                            rationale=enriched_rationale,
                            user_id=user_id
                        ))
                    except Exception as e:
                        logger.error(f"WeeklyWorkflow: Failed to execute trade for {order_data['ticker']}: {e}")
            
            # 4. Memory Storage
            if self.memory_service:
                await self.memory_service.store_report(
                    user_id=user_id, 
                    report_type="weekly", 
                    date=datetime.now().strftime("%Y-%m-%d"), 
                    content=str(final_report)
                )
            
            return str(final_report)
            
        else:
            # Legacy Fallback
            logger.warning("TaskPlanner not injected. Running legacy workflow.")
            return await self._legacy_weekly_cycle(user_id)

    def _fetch_base_thematic_context(self, user_id: str) -> str:
        """Helper to get base thematic context for mapping."""
        try:
            from src.repositories.settings_repository import AlchemySettingsRepository
            settings_repo = AlchemySettingsRepository()
            physical_ai = settings_repo.get(user_id, "physical_ai_tickers")
            ai_energy = settings_repo.get(user_id, "ai_energy_tickers")
            supply_chain = settings_repo.get(user_id, "supply_chain_knowledge_graph")
            
            import json
            ctx = "### 目前追蹤之核心主題與供應鏈 (Current Thematic & Supply Chain Tracks)\n"
            if physical_ai: ctx += f"- **實體 AI (Physical AI)**: {physical_ai}\n"
            if ai_energy: ctx += f"- **AI 能源護城河 (AI Energy Moat)**: {ai_energy}\n"
            if supply_chain:
                sc_str = json.dumps(supply_chain, ensure_ascii=False) if isinstance(supply_chain, dict) else str(supply_chain)
                ctx += f"- **供應鏈瓶頸預測 (Supply Chain Bottlenecks)**: {sc_str}\n"
            return ctx
        except Exception:
            return "無法取得基礎主題數據。"

    def _select_agent_for_task(self, task_name: str, user_id: str, tier: str = "smart"):
        """
        PAD Phase 2: Map Task Name to agent names for _call_agent_llm
        Returns a tuple (agent_name, tier) instead of agent instances
        """
        name_lower = task_name.lower()
        if "market cycle" in name_lower or "macro" in name_lower:
            return ("Macro", tier)
        elif "sector" in name_lower or "swarm" in name_lower:
            return ("CIO", tier)
        elif "deep-dive" in name_lower or "supply chain" in name_lower:
            return ("Fundamental", tier)
        elif "portfolio analysis" in name_lower:
            # Use Council adapter for deep portfolio analysis
            return CouncilAgentAdapter(user_id=user_id, scope="portfolio", topic=f"Weekly Portfolio Review ({name_lower})")
        elif "recommendation" in name_lower or "balancing" in name_lower or "alpha" in name_lower:
            return ("CIO", tier)
        elif "synthesis" in name_lower:
            return ("CIO", tier)
        # Default to CIO
        return ("CIO", tier)

    def _bridge_input_context(self, task, context):
        """
        Adapts the global execution context to the specific input dict 
        required by the Agent for this task.
        """
        # Basic context always included
        agent_ctx = {
            "tickers": context.get("tickers", []),
            "market_data": context.get("market_data", {}),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "user_id": self.user_id,
            # CRITICAL: Inject the specific goal for this step
            "task_name": task.name,
            "task_instruction": task.description 
        }
        
        # [NEW] Pass Rich Portfolio if available (For Council)
        if "portfolio" in context:
            agent_ctx["portfolio"] = context["portfolio"]
        
        # Inject inputs from previous tasks if defined
        for key in task.input_keys:
            # We try to find the key in the context. 
            # If it's a "RESULT_X" key, we might need to map it.
            val = context.get(key)
            if val:
                agent_ctx[key] = val
            
            # Also just pass "previous_results" for generic chaining
            agent_ctx["previous_context"] = {k:v for k,v in context.items() if k.startswith("RESULT_")}
            
        return agent_ctx

    async def _legacy_weekly_cycle(self, user_id: str) -> str:
        """
        Legacy logic is deprecated. 
        If TaskPlanner is not injected, we raise an error or return a basic message 
        to encourage proper dependency injection.
        """
        logger.warning("_legacy_weekly_cycle is deprecated. Please inject TaskPlanner.")
        # Fallback to manual execution logic anyway if planner is missing
        try:
             # Basic Data Collection is done.
             # 1. Macro Analysis via PAD Phase 2
             macro_report = await self._call_agent_llm("Macro", {}, tier="smart")
             self.context['macro_report'] = macro_report
             
             # 2. Synthesis
             return await self.synthesize_results()
        except Exception as e:
             logger.error(f"Legacy fallback failed: {e}")
             return f"Error: {e}"

    async def synthesize_results(self) -> str:
        # Optimization Loop (System Engineer)
        # Move Engineer to BEFORE CIO to integrate feedback
        engineer_report = "無 (No recent optimizations)"
        try:
            # 1. Get Performance Stats
            perf_stats = self.performance_service.get_agent_performance()
            
            # 2. Engineer analyzes stats for THIS week via PAD Phase 2
            # However, Engineer mainly looks at stats.
            eng_context = {
                "cio_report": "PRE_GENERATION_CHECK", 
                "performance_stats": perf_stats
            }
            
            opt_result = await self._call_agent_llm("Engineer", eng_context, tier="fast", max_tokens=1000)
            logger.info(f"Engineer Optimization Result: {opt_result}")
            
            # Format for CIO Context
            if isinstance(opt_result, list) and opt_result:
                report_lines = []
                for item in opt_result:
                    if "error" in item: continue
                    target = item.get("target_agent", "Agent")
                    reason = item.get("reason", "N/A")
                    report_lines.append(f"- **{target}**: {reason}")
                
                if report_lines:
                    engineer_report = "\n".join(report_lines)
            elif isinstance(opt_result, str):
                engineer_report = opt_result

        except Exception as e:
            logger.warning(f"Engineer optimization failed: {e}")
            # Safety Fallback Mode (User Directive)
            engineer_report = (
                "⚠️ **SYSTEM ALERT**: Performance Service Unavailable.\n"
                "- **Action**: Enforce **Equal Weight Arbitration** (Average of Swarm Inputs).\n"
                "- **Constraint**: Max Leverage **0.95x** (Risk Off).\n"
                f"- **Error Details**: {e}"
            )

        # CIO Agent Synthesis (Weekly Strategy Mode) via PAD Phase 2
        # Construct CIO Context
        portfolio_str = ", ".join(self.context['tickers']) if self.context['tickers'] else "No Tickers"
        
        # Fix: Ensure macro_report exists
        macro_report = self.context.get('macro_report', "N/A (Macro Data Missing)")
        
        # --- [NEW] Capital Deployment Context ---
        cash_deployment_context = ""
        if self.memory_service:
            deployment_mem = self.memory_service.get_context(self.user_id, "cash_deployment")
            if deployment_mem and deployment_mem.recent_items:
                latest = deployment_mem.recent_items[0]
                cash_deployment_context = f"\n\n[WEEKLY CAPITAL UTILIZATION REVIEW]:\n{latest.compressed_summary or latest.full_content[:2000]}"

        cio_context = {
            "macro_report": macro_report,
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": portfolio_str,
            "engineer_report": engineer_report, # Pass integration context
            "cash_deployment_context": cash_deployment_context, # Inject deployment insight
            "user_id": self.user_id
        }
        
        # PAD Phase 2: Replace AgentFactory with _call_agent_llm
        final_report = await self._call_agent_llm("CIO", cio_context, tier="smart", max_tokens=3000)
        return final_report

    async def execute_analysis(self, force_refresh: bool) -> bool:
        # Stub
        return True


class EventAnalysisWorkflow(BaseWorkflow):
    """
    Workflow for processing individual external signals (Webhooks).
    事件分析工作流：處理單個外部信號（Webhooks）。
    """
    def __init__(self, user_id: str, event_source: str, event_data: Dict[str, Any], **kwargs):
        super().__init__(user_id=user_id, **kwargs)
        self.event_source = event_source
        self.event_data = event_data
        self.ticker = event_data.get("ticker", "GLOBAL")
        self.target_action = event_data.get("signal")  # e.g., "BUY", "SELL"

    async def execute_analysis(self, force_refresh: bool) -> bool:
        """
        Satisfies BaseWorkflow abstract method.
        EventAnalysisWorkflow uses its own 'run' logic but still needs concrete implementation.
        """
        return True

    async def synthesize_results(self) -> str:
        """
        Satisfies BaseWorkflow abstract method.
        Returns empty since logic is handled in custom 'run'.
        """
        return ""

    async def run(self, dry_run: bool = False, force_refresh: bool = False) -> str:
        """
        Custom run logic for event-driven analysis.
        """
        self.logger.info(f"Starting EventAnalysisWorkflow for {self.ticker} from {self.event_source}")
        
        try:
            # 1. Collect Data (Specific to the ticker)
            # GLOBAL: Handle macro news events — summarize + dispatch notification
            # GLOBAL: 處理宏觀新聞事件 — 摘要 + 發送通知
            if self.ticker == "GLOBAL":
                news_msg = self.event_data.get("msg", "Global market news")
                news_url = self.event_data.get("url", "")

                # Run macro analysis via fast tier (inline prompt, no heavy agent context needed)
                from src.infrastructure.llm.llm_config_chain import build_config_chain
                from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline

                chain = build_config_chain(self.user_id, "fast")
                pipeline = ResilientLLMPipeline(config_chain=chain)

                macro_prompt = (
                    "你是一位即時新聞分析師。請根據以下新聞事件，"
                    "用繁體中文提供簡要的市場影響分析。\n\n"
                    "分析重點：\n"
                    "1. 事件摘要（1-2句）\n"
                    "2. 對市場/板塊的潛在影響\n"
                    "3. 市場情緒判斷（正面/中性/負面）\n\n"
                    f"新聞來源：{self.event_source}\n"
                    f"新聞內容：{news_msg}\n"
                    f"連結：{news_url}\n\n"
                    "請簡潔回答，不超過150字。"
                )

                messages = [
                    Message(role="system", content=macro_prompt),
                    Message(role="user", content="請分析這則新聞。")
                ]

                try:
                    macro_res, _ = await pipeline.execute(
                        messages, temperature=0.3, max_tokens=500
                    )
                except Exception as llm_e:
                    self.logger.error(f"GLOBAL macro analysis failed: {llm_e}")
                    macro_res = f"**新聞摘要**: {news_msg}"

                final_report = (
                    f"## 宏觀快訊 ({self.event_source})\n\n"
                    f"{macro_res}\n\n"
                    f"---\n"
                    f"*來源: [{news_url}]({news_url})*"
                )

                if not dry_run:
                    await self.distribute_report(final_report)

                return final_report

            # Fetch market data context
            analysis_tickers = [self.ticker]
            market_context = self.market_service.get_market_context(analysis_tickers, enrich=True)
            self.context['market_data'] = market_context
            
            # 2. Execute Focused Analysis
            # For events, we want fresh data (use_cache=False if force_refresh)
            # PAD Phase 2: Replace AgentFactory calls with _call_agent_llm
            
            ticker_ctx = {
                "ticker": self.ticker,
                "price_data": market_context.get(self.ticker, {}).get("price_data", {}),
                "indicators": market_context.get(self.ticker, {}).get("indicators", {}),
                "news": self.market_service.get_news(self.ticker),
                "event_context": self.event_data
            }
            
            mom_res = await self._call_agent_llm("Momentum", ticker_ctx, tier="fast")
            sent_res = await self._call_agent_llm("Sentiment", ticker_ctx, tier="fast")
            
            # 3. Holding Reduction Analysis (If needed)
            holding_info = ""
            holdings = self.transaction_service.get_holdings_map(self.user_id)
            qty = holdings.get(self.ticker, {}).get('quantity', 0)
            
            if qty > 0:
                holding_info = f"\n現有持倉: {qty} 股。"
                # If signal is to SELL/REDUCE or event is negative
                is_negative = "SELL" in str(self.target_action).upper() or "NEGATIVE" in str(sent_res).upper()
                if is_negative:
                    self.logger.info(f"Performing reduction analysis for {self.ticker}")
                    # Could run a specialized 'Risk' check or just let CIO decide
            
            # 4. CIO Synthesis via PAD Phase 2
            cio_context = {
                "macro_report": "Event-Driven Context",
                "council_transcript": f"Ticker: {self.ticker}\n- Event Source: {self.event_source}\n- Event Detail: {self.event_data.get('msg')}\n- Momentum: {mom_res}\n- Sentiment: {sent_res}\n- Holdings: {holding_info}",
                "portfolio": f"{self.ticker} ({qty})",
                "user_id": self.user_id,
                "report_focus": f"Event Analysis: {self.event_source}"
            }
            
            cio_output = await self._call_agent_llm("CIO", cio_context, tier="smart", max_tokens=2000)
            
            # Polish and translate if needed
            final_report = cio_output # Simplified for event workflow
            
            # v7.0: Store deliberation context for trade notification enrichment
            self.context['deliberation_context'] = cio_context.get('council_transcript', '')
            
            # 5. Execute Action if actionable_orders table exists
            self._parse_actionable_orders(final_report)
            
            if not dry_run:
                # Distribute report (via Webhook/Notification)
                await self.distribute_report(final_report)
                
                # Auto-execution logic (System 2)
                actionable_orders = self.context.get('actionable_orders', [])
                if actionable_orders:
                    from src.services.automated_trading_service import AutomatedTradingService
                    auto_trade_svc = AutomatedTradingService()
                    for order_data in actionable_orders:
                        await auto_trade_svc.evaluate_and_execute_trade(
                            ticker=order_data['ticker'],
                            action=order_data['action'],
                            quantity=order_data['quantity'],
                            confidence_score=order_data['score'],
                            rationale=f"Webhook [{self.event_source}] Triggered: {order_data['reason']}",
                            user_id=self.user_id
                        )
            
            return final_report
            
        except Exception as e:
            self.logger.error(f"EventAnalysisWorkflow failed: {e}")
            raise e

    # Stubs for base class compatibility
    def collect_data(self): pass
    async def execute_analysis(self, force_refresh: bool) -> bool: return True
    def synthesise_results(self) -> str: return ""


class WorkflowService:
    """
    Coordinator service for all investment workflows.
    投資工作流協調服務。
    """
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.logger = setup_logger("WorkflowService")

    async def trigger_capital_deployment_workflow(self, analysis_result: str):
        """
        Processes a capital deployment trigger from Sentinel.
        處理來自哨兵的資金部署觸發。
        """
        self.logger.info(f"Triggering Capital Deployment Workflow for {self.user_id}")
        
        # 1. Store the analysis in Memory (so Daily/Weekly reports pick it up)
        from src.services.memory_service import MemoryService
        from src.repositories.memory_repository import AlchemyMemoryRepository
        from src.infrastructure.agent_llm_provider import AgentLLMProvider
        import json
        
        repo = AlchemyMemoryRepository()
        llm_provider = AgentLLMProvider(user_id=self.user_id)
        memory_service = MemoryService(repository=repo, llm_provider=llm_provider)
        
        # Ensure it is a string before storing in the database
        if not isinstance(analysis_result, str):
            analysis_result = json.dumps(analysis_result)
            
        date_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
        await memory_service.store_report(
            user_id=self.user_id,
            report_type="cash_deployment",
            date=date_str,
            content=analysis_result
        )
        
        # 2. Optionally: Trigger an EventAnalysisWorkflow if immediate action is desired
        # For now, we rely on the next scheduled report as per Phase 1 mandate.
        self.logger.info("Capital deployment analysis stored in memory for next report generation.")
