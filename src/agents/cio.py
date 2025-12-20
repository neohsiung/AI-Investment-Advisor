import pandas as pd
from src.data.database import get_db_connection
from sqlalchemy import text
from .base_agent import BaseAgent
from src.utils.time_utils import format_time
import json

class CIOAgent(BaseAgent):
    def __init__(self, use_cache=True):
        super().__init__(name="CIO", prompt_path="prompts/cio_agent.txt", use_cache=use_cache, ttl_hours=24, tier="smart")
        # Common ETFs to filter out for "Stock Picking" focus
        self.etf_list = {
            "SPY", "QQQ", "VOO", "IWM", "VT", "BND", "TLT", "VTI", "VEA", "VWO",
            "IVV", "AGG", "GLD", "SLV", "ARKK", "SOXX", "XLE", "XLF", "XLK", "XLV",
            "XLP", "XLY", "XLI", "XLU", "XLB", "XLRE"
        }

    def _get_portfolio_context(self, user_id=None):
        """
        Retrieves portfolio context: Leverage Ratio and Non-ETF Holdings.
        Returns: (leverage_ratio, holdings_summary_str)
        """
        try:
            conn = get_db_connection()
            
            # 1. Get Leverage Ratio from latest snapshot
            leverage_ratio = 1.0
            if user_id:
                snap = conn.execute(text("SELECT leverage_ratio FROM daily_snapshots WHERE user_id = :uid ORDER BY date DESC LIMIT 1"), {"uid": user_id}).fetchone()
                if snap and snap[0]:
                    leverage_ratio = float(snap[0])
            
            # 2. Get Holdings
            query = """
                SELECT ticker, SUM(CASE WHEN action='BUY' THEN quantity WHEN action='SELL' THEN -quantity ELSE 0 END) as net_qty
                FROM transactions
                WHERE user_id = :uid
                GROUP BY ticker
                HAVING net_qty > 0.0001
            """
            # If user_id is None (global run?), we might scan all? For now assume user_id is passed in context or we pick top 1
            if not user_id:
                # Fallback: try to find a user or return empty
                conn.close()
                return 1.0, "No User ID provided."

            df = pd.read_sql(text(query), conn, params={"uid": user_id})
            conn.close()

            if df.empty:
                return leverage_ratio, "目前無持倉 (No Holdings)"

            holdings = []
            non_etf_count = 0
            
            for _, row in df.iterrows():
                ticker = row['ticker']
                qty = row['net_qty']
                is_etf = ticker in self.etf_list
                holdings.append(f"{ticker} ({qty:.2f})")
                if not is_etf:
                    non_etf_count += 1
            
            holdings_str = f"總持倉: {', '.join(holdings)}. 非 ETF 持倉數: {non_etf_count}."
            return leverage_ratio, holdings_str

        except Exception as e:
            self.logger.error(f"Error calculating portfolio context: {e}")
            return 1.0, "Error retrieivng portfolio data."

    def run(self, context, mode="report"):
        """
        Run the CIO Agent.
        mode: 'report' (Final Report) or 'strategy' (Sector Strategy & Screening)
        """
        user_id = context.get("user_id")
        
        if mode == 'strategy':
            return self._run_strategy(context)
            
        # Default: Report Mode
        
        # 1. Get Dynamic Context
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
            "sector_strategy": context.get("sector_strategy", "無 (None)"), # Injected from Step 1
            "report_focus": context.get("report_focus", "Weekly Strategic")
        }

        # 3. Render System Prompt
        # Note: If mode is distinct, we might need a different prompt file.
        # But here we assume 'prompts/cio_agent.txt' is for reporting.
        system_prompt_rendered = self.render_system_prompt(prompt_data)
        
        # 4. User Prompt
        user_prompt = "請根據上述資料，生成本週的投資決策報告。"

        # 5. Call LLM
        response = self._mock_llm_call(user_prompt, system_prompt_rendered)

        return response

    def _run_strategy(self, context):
        """
        Step 1: Strategize and Screen Candidates.
        Returns: Dict { "sector_strategy": ..., "candidates": [...] }
        """
        # Load Strategy Prompt
        with open("prompts/cio_strategy_agent.txt", "r", encoding="utf-8") as f:
            strategy_prompt_template = f.read()
        
        # Prepare Context
        leverage_ratio, portfolio_str = self._get_portfolio_context(context.get("user_id"))
        
        # Simple Sector Analysis (Mock or derived from portfolio_str)
        # In a real system, we'd query sector data for each ticker.
        # For now, we let the LLM infer sectors from the ticker list string.
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
        response_str = self._call_real_llm(user_prompt, system_prompt)
        
        # Parse JSON
        try:
            # Clean markdown code blocks if present
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            return data
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse Strategy JSON: {response_str}")
            return {
                "sector_strategy": {"target_sectors": [], "rationale": "JSON Parse Error"},
                "candidates": []
            }

    def _generate_mock_report(self, leverage, portfolio_str):
        return f"""
# 投資決策報告 (Mock)

## 1. 執行摘要
雖然市場波動加大，但通膨數據受控。投資組合槓桿為 {leverage}x，持倉狀態: {portfolio_str}。建議維持中性配置。

## 2. 投資組合總體檢
- **AAPL**: 建議續抱 (Momentum 指出均線多頭排列)。
- **NVDA**: 觀察 (Fundamental 提示估值過高)。

## 3. 精選推薦
- **XLP**: 防禦型配置。

*由 CIO Agent 生成 (Mock)*
"""
