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
        
        # Prefetch Market Data (Technical) - Fixes Momentum Agent missing data
        self.context['market_data'] = self.market_service.get_market_context(user_tickers)

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
        
        # Retrieve simple macro data for context (not full report)
        macro_data = self.market_service.get_macro_data()
        
        # v3.2 Update: Handle nested structure (economics/market_indicators)
        vix = "N/A"
        spy = "N/A"
        spread = "N/A"
        
        # Parse YFinance (Market Indicators)
        if "market_indicators" in macro_data:
             market_inds = macro_data["market_indicators"]
             vix = market_inds.get('^VIX', 'N/A')
             spy = market_inds.get('SPY', 'N/A')
        elif isinstance(macro_data, dict): # Fallback for flat structure
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
        
        # Format metrics for CIO
        portfolio_str = ", ".join(self.context['tickers']) if self.context['tickers'] else "No Tickers"

        cio_context = {
            "macro_report": combined_macro,
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": portfolio_str,
            "report_focus": "Daily Tactical",
            "user_id": self.user_id
        }
        
        final_report = cio.run(cio_context)

        # Post-Process: Record Macro & CIO Signals
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
    def execute_analysis(self, force_refresh: bool) -> bool:
        """
        Weekly: Full Deep Dive (Macro -> Sector -> Ticker).
        每週執行: 全面深度分析 (總經 -> 版塊 -> 個股)。
        """
        
        # 1. Macro Analysis
        macro_agent = AgentFactory.create_macro_agent(ttl_hours=24, use_cache=not force_refresh, user_id=self.user_id)
        macro_report = macro_agent.run({})
        self.context['macro_report'] = macro_report
        
        if not self.context['tickers']:
            logger.info("No tickers, but will do macro report.")
            
        # 2. Collect Data (Parallel)
        self.logger.info(" collecting market data...")
        market_context = self.market_service.get_market_context(self.context['tickers'])
        
        # 2.1 Yield Curve (Keep this as global macro data)
        yield_curve = self.market_service.get_yield_curve_inversion()
        self.context['market_data']['yield_curve'] = yield_curve
        
        # No Search Pre-fetch (Agents will search on demand)
        
        self.context['market_data'].update(market_context) # Update the main market_data context
            
        # 3. Ticker Analysis (Fundamental + Momentum)
        fun_ttl = 168 # 1 week
        mom_ttl = 1 # 1 hour
        fund_agent = AgentFactory.create_fundamental_agent(ttl_hours=fun_ttl, use_cache=not force_refresh, user_id=self.user_id)
        mom_agent = AgentFactory.create_momentum_agent(ttl_hours=mom_ttl, use_cache=not force_refresh, user_id=self.user_id)
        sent_agent = AgentFactory.create_sentiment_agent(ttl_hours=4, use_cache=not force_refresh, user_id=self.user_id)
        
        ticker_reports = {}
        for ticker in self.context['tickers']:
            # Fetch Fundamental Data on demand (Weekly)
            ticker_data = self.context['market_data'].get(ticker, {})
            
            # Prepare Context for Agent
            ticker_ctx = {
                "ticker": ticker,
                "price_data": ticker_data.get("price_data", {}),
                "indicators": ticker_data.get("indicators", {}),
                "financials": self.market_service.get_financials(ticker),
                "news": self.market_service.get_news(ticker),
                # Agent searches autonomously
                "yield_curve": self.context['market_data'].get('yield_curve', {})
            }
            
            # Cache news for sentiment use
            news = ticker_ctx["news"]

            f_res = fund_agent.run(ticker_ctx)
            
            # Momentum Data (already fetched in collect_data)
            m_res = mom_agent.run(ticker_ctx)
            
            # Sentiment Data (Weekly check for narrative shifts)
            s_context = {
                "ticker": ticker,
                "news": news
            }
            s_res = sent_agent.run(s_context)
            
            ticker_reports[ticker] = {
                "fundamental": f_res, 
                "momentum": m_res,
                "sentiment": s_res
            }
            
        self.context['ticker_reports'] = ticker_reports
        return True

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
            engineer_report = f"Error retrieving optimization data: {e}"

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
