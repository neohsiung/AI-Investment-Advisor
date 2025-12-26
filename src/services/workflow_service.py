from abc import ABC, abstractmethod
import logging
import sys
from datetime import datetime
from src.utils.time_utils import get_current_time
from src.services.transaction_service import TransactionService
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.market_data import MarketDataService
from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.engineer import SystemEngineerAgent
from src.data.database import get_db_connection
from sqlalchemy import text
from src.agents.factory import AgentFactory
from src.services.performance_service import PerformanceService
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
        self.logger = logging.getLogger(self.__class__.__name__) # Using existing logging setup
        self.cio_agent = AgentFactory.create_cio_agent(
             transaction_repo=self.transaction_service.repository
        )
        self.performance_service = PerformanceService()

    def run(self, dry_run=False, force_refresh=False):
        """Template Method defining the workflow structure."""
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
            final_report = self.synthesize_results()
            
            # Step 4: Reporting & Storage
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
        """Daily: Only check Momentum/News. If no major signal, skip."""
        if not self.context['tickers']:
            logger.info("No tickers to analyze.")
            return False

        # Lightweight analysis (e.g. Momentum only)
        # For simplicity, we assume we check all but filter in CIO
        # Real implementation: Check specific alerts?
        
        # Here we run Momentum Agent & Sentiment Agent
        # Daily: Short TTL (1hr), assume force_refresh implies bypassing cache
        mom_agent = AgentFactory.create_momentum_agent(ttl_hours=1, use_cache=not force_refresh)
        sent_agent = AgentFactory.create_sentiment_agent(ttl_hours=4, use_cache=not force_refresh)
        
        results = []
        has_significant_change = False
        
        ticker_reports = {}
        for ticker in self.context['tickers']:
            # Short TTL for daily
            ticker_data = self.context['market_data'].get(ticker, {})
            agent_context = {
                "ticker": ticker,
                "price_data": ticker_data.get("price_data", {}),
                "indicators": ticker_data.get("indicators", {})
            }
            res = mom_agent.run(agent_context)
            results.append(res) # Keep for legacy check
            
            # Sentiment Analysis
            news = self.market_service.get_news(ticker)
            sent_context = {
                "ticker": ticker,
                "news": news
            }
            sent_res = sent_agent.run(sent_context)
            
            # Fundamental Analysis (Cached Reference)
            f_agent = AgentFactory.create_fundamental_agent(ttl_hours=168, use_cache=True) 
            # Note: We rely on cache. If miss, it runs.
            # We need to fetch financials/news for it if not cached? 
            # BaseAgent handles calls. We should construct context.
            # Ideally FundamentalAgent runs on same context logic as Weekly.
            f_context = {
                "ticker": ticker,
                "financials": self.market_service.get_financials(ticker), # Might be slow if not cached by requests_cache? 
                # Actually MarketDataService uses yfinance which caches? No.
                # But fundamental data updates rarely.
                # Let's assume for now we fetch it. Providing full context ensures accuracy if cache miss.
                "news": news # Reuse fetched news
            }
            f_res = f_agent.run(f_context)

            # Format for CIO: Daily has Momentum, Sentiment, and Fundamental (Context)
            ticker_reports[ticker] = {
                "momentum": res,
                "sentiment": sent_res,
                "fundamental": f_res
            }

            # Record Recommendations for Performance Tracking
            # Fix: Extract scalar price from list if needed
            raw_price = ticker_data.get("price_data", {}).get("close", 0)
            if isinstance(raw_price, list):
                if raw_price:
                    current_price = raw_price[-1]
                else:
                    current_price = 0.0
            else:
                current_price = raw_price
            
            # Simple Regex Signal Extraction (Robust to DSPy or Legacy text)
            # Look for explicit "BUY", "SELL", "HOLD"
            for agent_name, response in [("Momentum", res), ("Fundamental", f_res), ("Sentiment", str(sent_res))]:
                signal = "HOLD"
                text_res = str(response).upper()
                if "BUY" in text_res:
                    signal = "BUY"
                elif "SELL" in text_res:
                    signal = "SELL"
                
                # Only log if strong signal (not HOLD)
                if signal != "HOLD":
                    self.performance_service.record_recommendation(
                        agent_name=agent_name,
                        ticker=ticker,
                        signal=signal,
                        price=current_price
                    )
            
            # Simple heuristic: if 'BUY' or 'SELL' in response and 'STRONG'
            if "STRONG" in res.upper():
                has_significant_change = True

        self.context['momentum_results'] = results
        self.context['ticker_reports'] = ticker_reports
        
        # Always proceed to report if user triggered it manually (implied by this flow usually)
        # Or if we want to be strict about signals. For now let's return True to generate the CIO report.
        return True

    def synthesize_results(self) -> str:
        # Use CIO Agent for Daily Report (Daily Pulse Mode)
        cio = AgentFactory.create_cio_agent(mode="daily")
        
        # Retrieve simple macro data for context (not full report)
        macro_data = self.market_service.get_macro_data()
        macro_summary = f"Daily Market Check: VIX={macro_data.get('^VIX', 'N/A')}, SPY={macro_data.get('SPY','N/A')}"

        # Run Cached Macro Agent for Context
        macro_agent = AgentFactory.create_macro_agent(ttl_hours=24, use_cache=True)
        macro_deep = macro_agent.run({})
        
        combined_macro = f"{macro_summary}\n\n[Reference Weekly Macro Context]:\n{macro_deep}"
        
        # Format metrics for CIO
        portfolio_str = ", ".join(self.context['tickers']) if self.context['tickers'] else "No Tickers"

        cio_context = {
            "macro_report": combined_macro,
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": portfolio_str,
            "report_focus": "Daily Tactical"
        }
        
        final_report = cio.run(cio_context)
        return final_report


class WeeklyWorkflow(BaseWorkflow):
    def execute_analysis(self, force_refresh: bool) -> bool:
        """Weekly: Full Deep Dive (Macro -> Sector -> Ticker)."""
        
        # 1. Macro Analysis
        macro_agent = AgentFactory.create_macro_agent(ttl_hours=24, use_cache=not force_refresh)
        macro_report = macro_agent.run({})
        self.context['macro_report'] = macro_report
        
        if not self.context['tickers']:
            logger.info("No tickers, but will do macro report.")
            
        # 2. Ticker Analysis (Fundamental + Momentum)
        fun_ttl = 168 # 1 week
        mom_ttl = 1 # 1 hour
        fund_agent = AgentFactory.create_fundamental_agent(ttl_hours=fun_ttl, use_cache=not force_refresh)
        mom_agent = AgentFactory.create_momentum_agent(ttl_hours=mom_ttl, use_cache=not force_refresh)
        sent_agent = AgentFactory.create_sentiment_agent(ttl_hours=4, use_cache=not force_refresh)
        
        ticker_reports = {}
        ticker_reports = {}
        for ticker in self.context['tickers']:
            # Fetch Fundamental Data on demand (Weekly)
            financials = self.market_service.get_financials(ticker)
            news = self.market_service.get_news(ticker)
            
            f_context = {
                "ticker": ticker,
                "financials": financials,
                "news": news
            }
            f_res = fund_agent.run(f_context)
            
            # Momentum Data (already fetched in collect_data)
            ticker_data = self.context['market_data'].get(ticker, {})
            m_context = {
                "ticker": ticker,
                "price_data": ticker_data.get("price_data", {}),
                "indicators": ticker_data.get("indicators", {})
            }
            m_res = mom_agent.run(m_context)
            
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
        # CIO Agent Synthesis (Weekly Strategy Mode)
        cio = AgentFactory.create_cio_agent(mode="weekly")
        
        # Construct CIO Context
        portfolio_str = ", ".join(self.context['tickers']) if self.context['tickers'] else "No Tickers"
        
        cio_context = {
            "macro_report": self.context['macro_report'],
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": portfolio_str 
        }
        
        final_report = cio.run(cio_context)
        
        # Optimization Loop (System Engineer)
        try:
            # 1. Get Performance Stats
            perf_stats = self.performance_service.get_agent_performance()
            
            # 2. Engineer analyzes report + stats
            engineer = AgentFactory.create_agent("Engineer", use_cache=False)
            
            # Context includes Report Feedback AND Quant/Performance Feedback
            eng_context = {
                "cio_report": final_report,
                "performance_stats": perf_stats
            }
            
            opt_result = engineer.run(eng_context)
            logger.info(f"Engineer Optimization Result: {opt_result}")
            
            # Append optimization result to the report if relevant? 
            # Ideally notify user separately or just log it. 
            # For now, we log it.
        except Exception as e:
            logger.warning(f"Engineer optimization failed: {e}")
            
        return final_report
