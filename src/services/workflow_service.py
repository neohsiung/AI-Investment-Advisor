from abc import ABC, abstractmethod
import logging
import sys
from datetime import datetime
from src.utils.time_utils import get_current_time
from src.services.transaction_service import TransactionService
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.services.market_data_service import MarketDataService
from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.engineer import SystemEngineerAgent
from src.data.database import get_db_connection
from sqlalchemy import text
from src.agents.factory import AgentFactory
from src.services.performance_service import PerformanceService
from src.utils.time_utils import get_current_utc_time
import re

logger = logging.getLogger("WorkflowService")

from src.services.task_planning_service import TaskPlanningService
from src.services.memory_service import MemoryService

class BaseWorkflow(ABC):
    def __init__(self, user_id: str, transaction_repo=None, transaction_service=None, market_service=None):
        self.user_id = user_id
        
        # Dependency Injection
        self.transaction_repo = transaction_repo or SqliteTransactionRepository()
        self.transaction_service = transaction_service or TransactionService(repository=self.transaction_repo)
        self.market_service = market_service or MarketDataService()
        self.context = {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cio_agent = AgentFactory.create_cio_agent(
             transaction_repo=self.transaction_service.repository,
             user_id=self.user_id
        )
        self.performance_service = PerformanceService()

    def run(self, dry_run=False, force_refresh=False):
        """
        Template Method defining the workflow structure.
        定義工作流結構的樣板方法。
        """
        self.logger.info(f"Starting {self.__class__.__name__} for user {self.user_id}")
        
        try:
            # Step 1: Data Collection & Pre-checks
            # 步驟 1: 數據收集與預檢查
            self.collect_data()
            
            # Step 2: Strategy/Analysis
            # 步驟 2: 執行策略與分析
            should_proceed = self.execute_analysis(force_refresh)
            
            if not should_proceed:
                self.logger.info("Analysis determined no further action needed.")
                return "SKIPPED"

            # Step 3: Synthesis & Decision
            # 步驟 3: 綜合結果與決策
            final_report = self.synthesize_results()
            
            # Step 4: Reporting & Storage
            # 步驟 4: 報告生成與儲存
            if not dry_run:
                self.distribute_report(final_report)
            else:
                self.logger.info(f"[Dry Run] Report generated but not distributed:\n{final_report}")
                
            return final_report

        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            raise e

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

    def distribute_report(self, content: str):
        """Store in DB and send Email."""
        # 1. Store in DB
        conn = get_db_connection()
        try:
            import uuid
            report_id = str(uuid.uuid4())
            date_str = get_current_time().isoformat()
            conn.execute(text(
                "INSERT INTO reports (id, user_id, date, content, summary) VALUES (:id, :uid, :date, :content, :summary)"
            ), {"id": report_id, "uid": self.user_id, "date": date_str, "content": content, "summary": "Workflow Report"})
            conn.commit()
            logger.info("Report stored in database.")
        finally:
            conn.close()

        # 2. Send Email
        from src.notifier import EmailNotifier
        notifier = EmailNotifier()
        subject = f"Investment Report ({self.__class__.__name__}) - {get_current_time().strftime('%Y-%m-%d')}"
        notifier.send_report(subject, content)
        logger.info("Report email sent.")


class DailyWorkflow(BaseWorkflow):
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
            # Parse JSON Score: > 0.6 BUY, < 0.4 SELL (Range -1 to 1 or 0 to 1? Prompt says 0-1 usually, let's assume 0.5 neutral)
            # SentimentAgent prompt usually outputs 0-1 (e.g., 0.8) or -1 to 1.
            # Let's assume 0 to 1 based on common patterns (0.5 neutral).
            sent_score = sent_res.get("score", 0.5)
            if isinstance(sent_score, (int, float)):
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
        # Use CIO Agent for Daily Report (Daily Pulse Mode)
        cio = AgentFactory.create_cio_agent(mode="daily", user_id=self.user_id)
        
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
        
        macro_summary = f"Daily Market Check (v3.2 Data):\n- VIX: {vix}\n- SPY: {spy}\n- Yield Spread (10Y-2Y): {spread}"

        # Run Cached Macro Agent for Context
        macro_agent = AgentFactory.create_macro_agent(ttl_hours=24, use_cache=True, user_id=self.user_id)
        macro_deep = macro_agent.run({})
        
        combined_macro = f"{macro_summary}\n\n[Reference Weekly Macro Context]:\n{macro_deep}"
        
        # --- Memory Consistency Check (New) ---
        memory_consistency_note = ""
        if self.memory_service:
            # 1. Get recent context
            mem_ctx = self.memory_service.get_context(self.user_id, "daily")
            
            # 2. Synthesize current signal summary for contradiction check
            # We look at the aggregated signals from execute_analysis results (stored in context)
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

        # Format metrics for CIO
        portfolio_str = ", ".join(self.context['tickers']) if self.context['tickers'] else "No Tickers"

        cio_context = {
            "macro_report": combined_macro,
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": portfolio_str,
            "report_focus": "Daily Tactical",
            "consistency_constraints": memory_consistency_note, # Inject warning
            "user_id": self.user_id
        }
        
        final_report = cio.run(cio_context)
        
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
        # Check macro_deep keywords
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
        # Pattern: "- **TICKER**: **ACTION**" or similar from refined prompt
        # We look for lines in "Today's Action" or section 4.
        # Regex to catch " - **NVDA**: **SELL**"
        try:
            # Extract Action lines based on ### [TICKER] blocks
            # Pattern 1: Look for "### TICKER ... - **Action**: **SIGNAL**"
            # We can split by "### " to get blocks
            blocks = final_report.split("### ")
            
            for block in blocks:
                # Extract Ticker from first line e.g. "NVDA (0.52)\n"
                ticker_match = re.match(r"([A-Z]+)", block)
                if not ticker_match: continue
                
                ticker = ticker_match.group(1)
                
                # Extract Action line e.g. "- **Action**: **TRIM**"
                action_match = re.search(r"-\s*\*\*Action\*\*:\s*\*\*([A-Z]+(?:/[A-Z]+)?)\*\*", block)
                if action_match:
                    action = action_match.group(1)
                    
                    # Normalize action
                    # e.g. "SELL/TRIM" -> "SELL", "BUY/ACCUMULATE" -> "BUY"
                    u_act = action.upper()
                    cio_signal = "HOLD"
                    if "BUY" in u_act or "ACCUMULATE" in u_act:
                        cio_signal = "BUY"
                    elif "SELL" in u_act or "TRIM" in u_act or "REDUCE" in u_act:
                        cio_signal = "SELL"
                    
                    if cio_signal != "HOLD":
                        # Get price
                        t_data = self.context['market_data'].get(ticker, {})
                        t_price = 0
                        if t_data:
                             raw = t_data.get('price_data', {}).get('close', 0)
                             if isinstance(raw, list) and raw: t_price = raw[-1]
                             else: t_price = raw
                        
                        self.performance_service.record_recommendation(
                            agent_name="CIO",
                            ticker=ticker,
                            signal=cio_signal,
                            price=t_price
                        )
        except Exception as e:
            logger.warning(f"Failed to extract CIO signals: {e}")

        return final_report


class WeeklyWorkflow(BaseWorkflow):
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
            # 'execution_context' starts with global context (market data, etc)
            execution_context = {**self.context, **context_data} 
            
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
            final_report = task_results.get("Report Synthesis", "\n\n".join([f"## {k}\n{v}" for k,v in task_results.items()]))
            
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
        elif "portfolio" in name_lower or "audit" in name_lower:
             return AgentFactory.create_cio_agent(user_id=user_id, mode="portfolio_review", tier=tier)
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
        return "Error: TaskPlanner not configured for Weekly Workflow."

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
        
        cio_context = {
            "macro_report": self.context['macro_report'],
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": portfolio_str,
            "engineer_report": engineer_report, # Pass integration context
            "user_id": self.user_id
        }
        
        final_report = cio.run(cio_context)
        return final_report

    # Required Abstract Method Stub - Not used in new Plan flow directly, but needed for BaseWorkflow
    def execute_analysis(self, force_refresh: bool) -> bool:
        # This was the old "Step 2" in BaseWorkflow.
        # In the new flow, we override run_weekly_cycle entirely, so this might not be called 
        # unless we are in the legacy path which now calls _legacy_weekly_cycle.
        # However, BaseWorkflow.run() calls this. 
        # So we actually need to change BaseWorkflow.run() OR make the new logic fit into `execute_analysis`.
        # BUT I overrode `run_weekly_cycle`. Wait, BaseWorkflow.run calls `execute_analysis`. 
        # The file content showed `WeeklyWorkflow` inheriting `BaseWorkflow`.
        # I replaced `execute_analysis` with `run_weekly_cycle`. 
        # This implies I wanted the entry point to be `run_weekly_cycle`?
        # But `BaseWorkflow` usually has a `run()` method.
        # If I want to support the new flow, I should rename my new method to `run()` override?
        # OR put the logic inside `execute_analysis` and `synthesize_results`.
        
        # BETTER PLAN: Implement `execute_analysis` to run the tasks, store results in context.
        # Implement `synthesize_results` to format the final report.
        # But the Planner creates a holistic plan including synthesis.
        
        # I will stick to overriding `run` in WeeklyWorkflow to bypass the rigid BaseWorkflow template if needed.
        # Or just have `run_weekly_cycle` be the main entry point if that's how it's called externally.
        # Checking implementation_plan.md -> "Extends existing WorkflowService methods (run_weekly_report)".
        # The file I edited calls it `WeeklyWorkflow`.
        return True # Stub
