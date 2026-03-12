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
from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.engineer import SystemEngineerAgent
from src.agents.factory import AgentFactory
from src.agents.council_adapter import CouncilAgentAdapter
from src.services.performance_service import PerformanceService
from src.utils.time_utils import get_current_utc_time
import re

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
        
        self.context = {}
        self.logger = setup_logger(self.__class__.__name__)
        self.cio_agent = AgentFactory.create_cio_agent(
             transaction_repo=self.transaction_service.repository,
             user_id=self.user_id
        )
        self.performance_service = PerformanceService(user_id=self.user_id)

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
            should_proceed = self.execute_analysis(force_refresh)
            
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
            
            # --- Translate to Traditional Chinese ---
            self.logger.info("Translating final report to Traditional Chinese...")
            try:
                from src.agents.factory import AgentFactory
                translator = AgentFactory.create_agent("Engineer", use_cache=True, user_id=self.user_id)
                prompt = (
                    "TASK: Please translate the following investment report into Traditional Chinese (zh-TW).\n"
                    "RULES:\n"
                    "1. Keep all financial domain terms (like 'Momentum', 'Fundamental', 'Sentiment', ticker symbols, etc.) in English.\n"
                    "2. Do NOT translate proper nouns (company names, asset classes if better known in English).\n"
                    "3. Keep ALL formatting strictly intact (Markdown, HTML, brackets, tables).\n"
                    "4. Output ONLY the translated text, no conversational filler.\n\n"
                    f"REPORT TO TRANSLATE:\n{final_report}"
                )
                res = translator.run(prompt)
                translated_report = str(res.get("content", res.get("output", res))) if isinstance(res, dict) else str(res)
                if translated_report.strip():
                    final_report = translated_report
                self.logger.info("Translation successful.")
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
                    
                    for order_data in actionable_orders:
                        try:
                            # Parse quantity to float safely
                            try:
                                qty_val = float(str(order_data['quantity']).replace('%', ''))
                            except (ValueError, TypeError):
                                qty_val = 100.0 # Default fallback amount
                                
                            # This handles threshold check, auto-exec, and notification/approval requests (Option A)
                            await auto_trade_svc.evaluate_and_execute_trade(
                                ticker=order_data['ticker'],
                                action=order_data['action'],
                                quantity=qty_val,
                                confidence_score=order_data['score'],
                                rationale=order_data['reason'], # Passing our internal 'reason' as 'rationale'
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

    def _assemble_integrated_report(self, 
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
        
        # 定義替換模式：尋找 ## 2. (Debate) 與 ## 3. (Synthesis) 之間的內容 (包含標題本身)
        # Define replacement pattern: Find content starting from ## 2 up to ## 3
        # Assuming the generated detailed content INCLUDES the header "## 2. ..."
        pattern = r"(## 2\..*?)(?=## 3\.)"
        
        # 若無詳細內容，提供預設訊息
        if not detailed_debate_content:
             detailed_debate_content = "## 2. 議會焦點辯論 (The Great Debate)\n(No detailed transcript available / 暫無詳細辯論紀錄)"

        # 執行替換
        # Execute Replacement
        modified_report = re.sub(pattern, detailed_debate_content, cio_full_output, flags=re.DOTALL)
        
        final_report = modified_report
        
        # 若替換未發生 (例如找不到標題)，則將詳細內容附加於後，並發出警告
        # If replacement failed (headers not found), append logic and warn
        if modified_report == cio_full_output:
             self.logger.warning("Report Injection Failed: Header '## 2...' or '## 3...' not found. Appending transcript.")
             # 嘗試簡單附加確保資訊不丟失
             final_report = f"{cio_full_output}\n\n{detailed_debate_content}"
        
        # 最終潤飾
        # Final Polish
        if agent_for_polish and hasattr(agent_for_polish, 'polish_report'):
             final_report = agent_for_polish.polish_report(final_report)
             
        return final_report


    def collect_data(self):
        """Common data collection: Get active tickers."""
        # Filter for active positions only to avoid analyzing sold stocks
        user_tickers = self.transaction_service.get_user_tickers(self.user_id, only_active=True)
        self.context['tickers'] = user_tickers
        logger.info(f"Active tickers: {user_tickers}")
        
        # Prefetch Market Data (Technical + Fundamental)
        # Fixes missing financials/news for Agents
        self.context['market_data'] = self.market_service.get_market_context(user_tickers, enrich=True)

    @abstractmethod
    def execute_analysis(self, force_refresh: bool) -> bool:
        """Execute specific analysis steps. Returns True if reporting is needed."""
        pass

    @abstractmethod
    def synthesize_results(self) -> str:
        """Combine analysis results into a final report."""
        pass

    async def distribute_report(self, content: str):
        """Store in DB and send Email asynchronously."""
        title = f"Investment Report ({self.__class__.__name__}) - {get_current_time().strftime('%Y-%m-%d')}"
        try:
            from src.services.reporting_service import ReportingService
            reporting_service = ReportingService()
            html_content = reporting_service.generate_professional_html(content, title=title)
        except Exception as e:
            logger.error(f"HTML transformation failed: {e}. Falling back to markdown.")
            html_content = content
        
        # 1. Store in DB
        try:
            from src.repositories.report_repository import AlchemyReportRepository
            report_repo = AlchemyReportRepository()
            
            # Save the generated HTML content (We still pass content as 'markdown' 
            # and HTML as 'html_content' if schema is updated, but for now just pass to repo)
            report_repo.save(
                user_id=self.user_id,
                report_type=self.__class__.__name__,
                summary=title, # use title as summary for now
                content=html_content # store HTML
            )
            logger.info("Report stored in database (HTML format).")
        except Exception as e:
            logger.error(f"Failed to store report: {e}")

        # 2. Send Notifications (Email & Web)
        import os
        import httpx
        
        notification_api_url = os.getenv("NOTIFICATION_API_URL", "http://localhost:8001/api/v1/notify")
        subject = f"Investment Report ({self.__class__.__name__}) - {get_current_time().strftime('%Y-%m-%d')}"
        
        payload = {
            "user_id": self.user_id,
            "title": subject,
            "content": html_content,
            "channels": ["email", "web"], # Explicitly target Email and Web for reports
            "category": "report"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(notification_api_url, json=payload, timeout=10.0)
                if response.status_code == 202:
                    logger.info("Report notifications queued successfully via API.")
                else:
                    logger.warning(f"Notification API returned {response.status_code}: {response.text}")
                    # Fallback to direct call if API exists but returned non-202
                    await self._fallback_direct_notify(title, html_content)
        except Exception as e:
            logger.error(f"Failed to trigger Report Notification via API: {e}. Attempting direct fallback.")
            await self._fallback_direct_notify(title, html_content)

    async def _fallback_direct_notify(self, title: str, html_content: str):
        """Fallback to use direct NotificationService if API is down"""
        try:
            from src.services.notification_service import NotificationService
            from src.services.settings_service import SettingsService
            
            settings_svc = SettingsService(user_id=self.user_id)
            notification_svc = NotificationService.create_with_settings(settings_service=settings_svc, user_id=self.user_id)
            
            await notification_svc.notify_all(
                title=title,
                content=html_content,
                user_id=self.user_id,
                channels=["email", "web"],
                category="report"
            )
            logger.info("Fallback direct notification successful.")
        except Exception as fallback_e:
            logger.error(f"Fallback direct notification failed: {fallback_e}")


class DailyWorkflow(BaseWorkflow):
    """
    Workflow for daily market checks and brief reporting.
    每日工作流：負責每日市場檢查與簡要報告。
    """
    def execute_analysis(self, force_refresh: bool) -> bool:
        """
        Daily: Only check Momentum/News. If no major signal, skip.
        每日執行: 僅檢查動能訊號與新聞。若無重大訊號，則跳過。
        """
        if not self.context['tickers']:
            logger.info("No tickers to analyze.")
            return False

        # Lightweight analysis (e.g. Momentum only)
        # For simplicity, we assume we check all but filter in CIO
        # Real implementation: Check specific alerts?
        
        # Here we run Momentum Agent & Sentiment Agent
        # Daily: Short TTL (1hr), assume force_refresh implies bypassing cache
        mom_agent = AgentFactory.create_momentum_agent(ttl_hours=1, use_cache=not force_refresh, user_id=self.user_id)
        sent_agent = AgentFactory.create_sentiment_agent(ttl_hours=4, use_cache=not force_refresh, user_id=self.user_id)
        
        results = []
        has_significant_change = False
        
        ticker_reports = {}
        for ticker in self.context['tickers']:
            # Short TTL for daily
            data = self.context['market_data'].get(ticker, {})
            
            # Prepare Context for Agent
            ticker_ctx = {
                "ticker": ticker,
                "price_data": data.get("price_data", {}),
                "indicators": data.get("indicators", {}),
                "financials": self.market_service.get_financials(ticker),
                "news": self.market_service.get_news(ticker),
                "web_intelligence": data.get("web_intelligence", []),
                "yield_curve": self.context['market_data'].get('yield_curve', {}) 
            }

            res = mom_agent.run(ticker_ctx)
            results.append(res) # Keep for legacy check
            
            # Sentiment Analysis
            sent_res = sent_agent.run(ticker_ctx)
            
            # Fundamental Analysis (Cached Reference)
            f_agent = AgentFactory.create_fundamental_agent(ttl_hours=168, use_cache=True, user_id=self.user_id) 
            # Note: We rely on cache. If miss, it runs.
            # We need to fetch financials/news for it if not cached? 
            # BaseAgent handles calls. We should construct context.
            # Ideally FundamentalAgent runs on same context logic as Weekly.
            f_res = f_agent.run(ticker_ctx)

            # Format for CIO: Daily has Momentum, Sentiment, and Fundamental (Context)
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

    def synthesize_results(self) -> str:
        """
        Combine analysis results into a final report.
        將分析結果綜合成最終報告。
        """
        # Use CIO Agent for Daily Report (Daily Pulse Mode)
        cio = AgentFactory.create_cio_agent(mode="daily", user_id=self.user_id)
        
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

        # Run Cached Macro Agent for Context
        macro_agent = AgentFactory.create_macro_agent(ttl_hours=24, use_cache=True, user_id=self.user_id)
        macro_deep = macro_agent.run({})
        
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
            conflicts = self.memory_service.detect_conflicts(current_view_summary, mem_ctx)
            
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
            broker.sync_history(self.user_id)
            
            # 2. Check Risk Status (Constraints)
            # Fetch history and positions for Risk Manager
            history = broker.get_history()
            positions = broker.get_positions()
            
            constraints_ok = risk_manager.check_constraints(self.user_id, history, positions)
            
            if not constraints_ok:
                broker_status_msg = f"🚨 **RISK ALERT ({broker.get_name()})**: AI Trading PAUSED. Manual Review Required."
            else:
                broker_status_msg = f"✅ **System Status ({broker.get_name()})**: Active & Monitoring."
            
            # 3. Get Financial Snapshot
            account = broker.get_account()
            if account:
                broker_status_msg += f"\n- **Total Equity**: ${account.total_equity:,.2f}"
                broker_status_msg += f"\n- **Cash**: ${account.available_cash:,.2f}"
            
            broker_connected = True
        except Exception as e:
            logger.warning(f"Broker ({broker.get_name()}) Service not available: {e}")
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
        
        cio_output = cio.run(cio_context)
        
        # --- Final Assembly (Integrated Pattern) ---
        # 組合最終報告 (集成模式)
        final_report = self._assemble_integrated_report(
            cio_full_output=cio_output,
            detailed_debate_content=detailed_debate_section,
            agent_for_polish=cio
        )

        # Store in Memory
        if self.memory_service:
            self.memory_service.store_report(
                user_id=self.user_id,
                report_type="daily",
                date=datetime.now().strftime("%Y-%m-%d"),
                content=final_report
            )

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

    def _parse_actionable_orders(self, final_report: str):
        """
        Parses the actionable orders table from the final report and populates the context.
        Supports both Markdown pipe tables and HTML <table> formats.
        解析最終報告中的可執行指令表格，支援 Markdown 與 HTML 格式。
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
                    if "action" in prev_line or "動作" in prev_line or "代號" in prev_line or "ticker" in prev_line:
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
                    # Skip header rows containing <th>
                    if '<th' in tr.lower():
                        continue
                    tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL | re.IGNORECASE)
                    cleaned = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
                    if len(cleaned) >= 4:
                        rows.append(cleaned)

            if not rows:
                logger.info("No Actionable Orders table found in CIO report.")
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
                        'reason': cols[4] if len(cols) >= 5 else f"CIO Daily Signal ({cio_signal})"
                    })

            if self.context.get('actionable_orders'):
                logger.info(f"Parsed {len(self.context['actionable_orders'])} actionable orders from CIO report.")

        except Exception as e:
            logger.warning(f"Failed to parse Actionable Orders table: {e}")



class WeeklyWorkflow(BaseWorkflow):
    """
    Workflow for comprehensive weekly analysis and strategy refinement.
    每週工作流：負責全面的每週分析與策略調整。
    """
    def run_weekly_cycle(self, user_id: str, context_data: dict = None) -> str:
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
            
            for task in plan.tasks:
                logger.info(f"--- Executing Task: {task.name} ---")
                
                # 2.1 Agent Selection
                agent = self._select_agent_for_task(task.name, user_id, tier=task.model_tier)
                # 2.2 Input Prep
                agent_input = self._bridge_input_context(task, execution_context)
                
                # 2.3 Run Agent
                try:
                    response = agent.run(agent_input)
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
            
            # B. Synthesis (CIO) - Focus on Strategy
            # We explicitly ask CIO to synthesize the Strategy, not the Portfolio Details
            synthesis_agent = self._select_agent_for_task("Report Synthesis", user_id)
            
            # Construct Synthesis Context (Excluding giant transcript to avoid token waste/compression)
            syn_context = {**execution_context}
            # Remove the giant transcript from context passed to CIO to force it to focus on Strategy
            # (or we pass it but instruct it to ignore?)
            # Better: We rely on the "Report Synthesis" task instructions from Planner.
            # But here we override to ensure "Append" behavior.
            
            syn_response = synthesis_agent.run(syn_context)
            
            # C. Assemble Final Report (Integrated Pattern)
            
            # Pattern: Replace CIO's "Great Debate" or "Sector Strategy" (if it contains debate) with Detailed Council Transcript
            # We look for the standard header from CIO. If found, we inject.
            
            # Common headers for debate section in CIO output:
            # "## 2. 議會焦點辯論" or "## 2. The Great Debate"
            
            import re
            pattern = r"(## 2\..*?)(?=## 3\.)"
            
            # If portfolio_details (Transcript) is empty, warn
            # C. Assemble Final Report (Integrated Pattern)
            final_report = self._assemble_integrated_report(
                cio_full_output=syn_response,
                detailed_debate_content=portfolio_details,
                agent_for_polish=synthesis_agent
            )
            
            # 4. Memory Storage
            if self.memory_service:
                self.memory_service.store_report(
                    user_id=user_id, 
                    report_type="weekly", 
                    date=datetime.now().strftime("%Y-%m-%d"), 
                    content=str(final_report)
                )
            
            return str(final_report)
            
        else:
            # Legacy Fallback
            logger.warning("TaskPlanner not injected. Running legacy workflow.")
            return self._legacy_weekly_cycle(user_id)

    def _select_agent_for_task(self, task_name: str, user_id: str, tier: str = "smart"):
        """Map Task Name to Existing Agent implementations"""
        name_lower = task_name.lower()
        if "market cycle" in name_lower or "macro" in name_lower:
            return AgentFactory.create_macro_agent(user_id=user_id, tier=tier)
        elif "sector" in name_lower or "swarm" in name_lower:
            return AgentFactory.create_cio_agent(user_id=user_id, mode="sector_analysis", tier=tier) 
        elif "deep-dive" in name_lower or "supply chain" in name_lower:
            return AgentFactory.create_fundamental_agent(user_id=user_id, tier=tier)
        elif "portfolio analysis" in name_lower:
            # Use Map-Reduce Council for deep portfolio analysis
            return CouncilAgentAdapter(user_id=user_id, scope="portfolio", topic=f"Weekly Portfolio Review ({name_lower})")
        elif "recommendation" in name_lower or "balancing" in name_lower or "alpha" in name_lower:
            return AgentFactory.create_cio_agent(user_id=user_id, mode="weekly", tier=tier)
        elif "synthesis" in name_lower:
            return AgentFactory.create_cio_agent(user_id=user_id, mode="synthesis", tier=tier)

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

    def _legacy_weekly_cycle(self, user_id: str) -> str:
        """
        Legacy logic is deprecated. 
        If TaskPlanner is not injected, we raise an error or return a basic message 
        to encourage proper dependency injection.
        """
        logger.warning("_legacy_weekly_cycle is deprecated. Please inject TaskPlanner.")
        # Fallback to manual execution logic anyway if planner is missing
        try:
             # Basic Data Collection is done.
             # 1. Macro Analysis
             macro_agent = AgentFactory.create_macro_agent(user_id=user_id)
             macro_report = macro_agent.run({})
             self.context['macro_report'] = macro_report
             
             # 2. Synthesis
             return self.synthesize_results()
        except Exception as e:
             logger.error(f"Legacy fallback failed: {e}")
             return f"Error: {e}"

    def synthesize_results(self) -> str:
        # Optimization Loop (System Engineer)
        # Move Engineer to BEFORE CIO to integrate feedback
        engineer_report = "無 (No recent optimizations)"
        try:
            # 1. Get Performance Stats
            perf_stats = self.performance_service.get_agent_performance()
            
            # 2. Engineer analyzes stats for THIS week
            # However, Engineer mainly looks at stats.
            engineer = AgentFactory.create_agent("Engineer", use_cache=False, user_id=self.user_id)
            
            eng_context = {
                "cio_report": "PRE_GENERATION_CHECK", 
                "performance_stats": perf_stats
            }
            
            opt_result = engineer.run(eng_context)
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

        # CIO Agent Synthesis (Weekly Strategy Mode)
        cio = AgentFactory.create_cio_agent(mode="weekly", user_id=self.user_id)
        
        # Construct CIO Context
        portfolio_str = ", ".join(self.context['tickers']) if self.context['tickers'] else "No Tickers"
        
        # Fix: Ensure macro_report exists
        macro_report = self.context.get('macro_report', "N/A (Macro Data Missing)")
        
        cio_context = {
            "macro_report": macro_report,
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": portfolio_str,
            "engineer_report": engineer_report, # Pass integration context
            "user_id": self.user_id
        }
        
        final_report = cio.run(cio_context)
        return final_report

    # Required Abstract Method Stub - Not used in new Plan flow directly, but needed for BaseWorkflow
    def execute_analysis(self, force_refresh: bool) -> bool:
        # OR put the logic inside `execute_analysis` and `synthesize_results`.
        
        # BETTER PLAN: Implement `execute_analysis` to run the tasks, store results in context.
        # Implement `synthesize_results` to format the final report.
        # But the Planner creates a holistic plan including synthesis.
        
        # I will stick to overriding `run` in WeeklyWorkflow to bypass the rigid BaseWorkflow template if needed.
        # Or just have `run_weekly_cycle` be the main entry point if that's how it's called externally.
        # Checking implementation_plan.md -> "Extends existing WorkflowService methods (run_weekly_report)".
        # The file I edited calls it `WeeklyWorkflow`.
        return True # Stub
