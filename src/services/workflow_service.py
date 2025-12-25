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
        # Use Factory
        self.cio_agent = AgentFactory.create_cio_agent(
             transaction_repo=self.transaction_service.repository
        )

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
        user_tickers = self.transaction_service.get_user_tickers(self.user_id)
        # TODO: Filter out tiny positions?
        self.context['tickers'] = user_tickers
        logger.info(f"Active tickers: {user_tickers}")

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
        
        # Here we run Momentum Agent
        # Daily: Short TTL (1hr), assume force_refresh implies bypassing cache
        agent = AgentFactory.create_momentum_agent(ttl_hours=1, use_cache=not force_refresh)
        results = []
        has_significant_change = False
        
        for ticker in self.context['tickers']:
            # Short TTL for daily
            # Short TTL for daily
            res = agent.run({"ticker": ticker})
            results.append(res)
            # Simple heuristic: if 'BUY' or 'SELL' in response and 'STRONG'
            if "STRONG" in res.upper():
                has_significant_change = True

        self.context['momentum_results'] = results
        
        # If no significant change, maybe skip reporting?
        # But user usually wants a daily summary if they asked for it.
        # Let's say if list is empty we skip.
        return True

    def synthesize_results(self) -> str:
        # Use Light CIO or simple summary
        return "\n\n".join(self.context.get('momentum_results', []))


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
        
        ticker_reports = {}
        for ticker in self.context['tickers']:
            f_res = fund_agent.run({"ticker": ticker})
            m_res = mom_agent.run({"ticker": ticker})
            ticker_reports[ticker] = {"fundamental": f_res, "momentum": m_res}
            
        self.context['ticker_reports'] = ticker_reports
        return True

    def synthesize_results(self) -> str:
        # CIO Agent Synthesis
        cio = AgentFactory.create_cio_agent()
        
        # Construct CIO Context
        cio_context = {
            "macro_report": self.context['macro_report'],
            "ticker_data": self.context.get('ticker_reports', {}),
            "portfolio": self.context['tickers'] # simple list
        }
        
        final_report = cio.run(cio_context)
        
        # Optimization Loop (System Engineer)
        try:
            engineer = AgentFactory.create_agent("Engineer")
            # Feed input to optimization (simplified)
            # engineer.optimize_prompts(...) 
            pass
        except Exception as e:
            logger.warning(f"Engineer optimization failed: {e}")
            
        return final_report
