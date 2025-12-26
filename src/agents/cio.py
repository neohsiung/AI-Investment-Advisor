import pandas as pd
import json
from .base_agent import BaseAgent
from src.utils.time_utils import format_time
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.repositories.settings_repository import SqliteSettingsRepository

class CIOAgent(BaseAgent):
    def __init__(self, use_cache=True, transaction_repo=None, prompt_path="prompts/cio_weekly.txt"):
        # Default to Weekly if not specified
        super().__init__(name="CIO", prompt_path=prompt_path, use_cache=use_cache, ttl_hours=24, tier="smart")
        
        self.transaction_repo = transaction_repo or SqliteTransactionRepository()
        
        # Common ETFs to filter out for "Stock Picking" focus
        self.etf_list = {
            "SPY", "QQQ", "VOO", "IWM", "VT", "BND", "TLT", "VTI", "VEA", "VWO",
            "IVV", "AGG", "GLD", "SLV", "ARKK", "SOXX", "XLE", "XLF", "XLK", "XLV",
            "XLP", "XLY", "XLI", "XLU", "XLB", "XLRE"
        }

    def run(self, context, mode="report"):
        """
        Run the CIO Agent.
        mode: 'report' (Final Report) or 'strategy' (Sector Strategy & Screening)
        """
        if mode == 'strategy':
            return self._run_strategy(context)
        
        # Report Mode (Default)
        return self._run_report(context)

    def _run_report(self, context):
        """Generates the final investment report."""
        user_id = context.get("user_id")
        
        # 1. Get Dynamic Context (Portfolio)
        leverage_ratio, portfolio_str = self._get_portfolio_context(user_id)
        
        # 2. Prepare Data for Prompt Template
        prompt_data = {
            "current_date": format_time(fmt="%Y-%m-%d"),
            "leverage_ratio": f"{leverage_ratio:.2f}",
            "portfolio": portfolio_str,
            "risk_profile": context.get("risk_profile", "Balanced (穩健型)"),
            "momentum_reports": context.get("momentum_reports", "無 (None)"),
            "fundamental_reports": context.get("fundamental_reports", "無 (None)"),
            "macro_report": context.get("macro_report", "無 (None)"),
            "sector_strategy": context.get("sector_strategy", "無 (None)"),
            "report_focus": context.get("report_focus", "Weekly Strategic")
        }

        # 3. Render System Prompt
        system_prompt = self.render_system_prompt(prompt_data)
        user_prompt = "請根據上述資料，生成本週的投資決策報告。"

        # 4. Call LLM (BaseAgent handles Cache & Mock/Real)
        response = self.call_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        return response

    def _run_strategy(self, context):
        """Generates Sector Strategy & Candidates (JSON)."""
        
        # Load Strategy Prompt (Ideally use _load_prompt but different path)
        try:
            with open("prompts/cio_strategy_agent.txt", "r", encoding="utf-8") as f:
                strategy_prompt_template = f.read()
        except FileNotFoundError:
            self.logger.warning("Strategy prompt not found, using fallback.")
            strategy_prompt_template = "Generate a sector strategy JSON."

        # Prepare Context
        leverage_ratio, portfolio_str = self._get_portfolio_context(context.get("user_id"))
        portfolio_sector_analysis = f"持倉概況: {portfolio_str}. (請基於此推斷板塊暴露)"
        
        prompt_data = {
            "current_date": format_time(fmt="%Y-%m-%d"),
            "portfolio_sector_analysis": portfolio_sector_analysis,
            "macro_report": context.get("macro_report", "無 (None)")
        }
        
        # Render
        from jinja2 import Template
        t = Template(strategy_prompt_template)
        system_prompt = t.render(**prompt_data)
        
        user_prompt = "請制定戰略並篩選 15 檔候選股 (No ETFs)。Output JSON."
        
        # Call LLM
        response_str = self.call_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            response_format={"type": "json_object"} # Hint for OpenAI/Provider
        )
        
        # Parse JSON
        try:
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            return data
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse Strategy JSON: {response_str}")
            return {
                "sector_strategy": {"target_sectors": [], "rationale": "JSON Parse Error"},
                "candidates": []
            }

    def _get_portfolio_context(self, user_id):
        """Retrieves portfolio context using Repository."""
        if not user_id:
            return 1.0, "No User ID provided."

        try:
            # Get Portfolio from Repository (Need to implement or use raw sql if repo missing method)
            # Use raw sql for now as repo might not have 'get_holdings_summary'
            # Or better, iterate tickers from repo
            tickers = self.transaction_repo.get_user_tickers(user_id)
            if not tickers:
                return 1.0, "目前無持倉 (No Holdings)"

            # We need quantities. Repo returns list of tickers. 
            # We might need to access the DataFrame method or add a new method to Repo.
            # For backward compatibility within this refactor, I'll use the repo's internal session if exposed,
            # but ideally strict encapsulation.
            # Let's add `get_portfolio_snapshot` to Repo later. For now, use a simple SQL via repo's connection helper if available.
            
            # Temporary: accessing the DB strictly for this query until Repo is upgraded
            from src.data.database import get_db_connection
            conn = get_db_connection() # This violates DI slightly but keeps it functional without touching Repo yet
            
            # Simple query for summary
            # ... (Logic from before)
            # But wait, we should fix the DI. 
            pass 

            # Using direct SQL for now to keep logic intact but inside this private method
            query = text("""
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions WHERE user_id = :uid GROUP BY ticker HAVING net_qty > 0.0001
            """)
            rows = conn.execute(query, {"uid": user_id}).fetchall()
            
            # Get Leverage
            snap = conn.execute(text("SELECT leverage_ratio FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1"), {"uid": user_id}).fetchone()
            leverage = float(snap[0]) if snap and snap[0] else 1.0
            
            conn.close()
            
            holdings = []
            non_etf_count = 0
            for row in rows:
                t, q = row[0], row[1]
                holdings.append(f"{t} ({q:.2f})")
                if t not in self.etf_list:
                    non_etf_count += 1
            
            holdings_str = f"總持倉: {', '.join(holdings)}. 非 ETF 持倉數: {non_etf_count}."
            return leverage, holdings_str

        except Exception as e:
            self.logger.error(f"Error calculating portfolio context: {e}")
            return 1.0, "Error retrieving data."
