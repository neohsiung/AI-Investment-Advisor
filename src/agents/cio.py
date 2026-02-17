import pandas as pd
import json
from .base_agent import BaseAgent
from src.utils.time_utils import format_time
from src.repositories.transaction_repository import TransactionRepositoryImpl
from src.repositories.settings_repository import AlchemySettingsRepository

class CIOAgent(BaseAgent):
    def __init__(self, use_cache=True, transaction_repo=None, prompt_path="prompts/cio_weekly.txt", mode="report", **kwargs):
        # Allow tier override or kwargs
        tier = kwargs.pop('tier', 'smart')
        super().__init__(name="CIO", prompt_path=prompt_path, use_cache=use_cache, ttl_hours=24, tier=tier, **kwargs)
        
        self.transaction_repo = transaction_repo or TransactionRepositoryImpl()
        self.mode = mode
        
        # Common ETFs to filter out for "Stock Picking" focus
        self.etf_list = {
            "SPY", "QQQ", "VOO", "IWM", "VT", "BND", "TLT", "VTI", "VEA", "VWO",
            "IVV", "AGG", "GLD", "SLV", "ARKK", "SOXX", "XLE", "XLF", "XLK", "XLV",
            "XLP", "XLY", "XLI", "XLU", "XLB", "XLRE"
        }

    def run(self, context, mode=None):
        """
        Run the CIO Agent.
        mode: 'report' (Final Report) or 'strategy' (Sector Strategy & Screening)
        """
        # Determine effective mode
        effective_mode = mode or self.mode
        
        if effective_mode == 'strategy' or effective_mode == 'sector_analysis':
            return self._run_strategy(context)
        
        # Report Mode (Default)
        return self._run_report(context)

    def _run_report(self, context):
        """
        Generates the final investment report using Swarm Intelligence & IC Protocol.
        使用蜂群智慧與投資委員會協議生成最終投資報告。
        """
        user_id = context.get("user_id") or self.user_id
        
        # 1. Get Dynamic Context (Portfolio)
        # 1. 取得動態上下文 (投資組合)
        leverage_ratio, portfolio_str = self._get_portfolio_context(user_id)
        
        # 2. Format Swarm Inputs (Aggregating Sub-Agent Reports)
        # 2. 格式化蜂群輸入 (聚合子 Agent 的報告)
        # [Map-Reduce Support]: Use pre-aggregated transcript if available
        if "council_transcript" in context:
            swarm_context = context["council_transcript"]
        else:
            # Legacy/Standard Mode: Aggregate from ticker_data dict
            ticker_data = context.get("ticker_data", {})
            swarm_context = ""
            if ticker_data:
                for ticker, reports in ticker_data.items():
                    swarm_context += f"### {ticker}\n"
                    swarm_context += f"- **Fundamental**: {reports.get('fundamental', 'N/A')}\n"
                    swarm_context += f"- **Momentum**: {reports.get('momentum', 'N/A')}\n"
                    swarm_context += f"- **Sentiment**: {reports.get('sentiment', 'N/A')}\n\n"
        
        # 3. Prepare Data for Prompt Template
        prompt_data = {
            "current_date": format_time(fmt="%Y-%m-%d"),
            "leverage_ratio": f"{leverage_ratio:.2f}",
            "portfolio": portfolio_str,
            "risk_profile": context.get("risk_profile", "Balanced (穩健型)"),
            "macro_report": context.get("macro_report", "無 (None)"),
            "engineer_report": context.get("engineer_report", "無 (No Constraints)"),
            "swarm_context": swarm_context, # [NEW] Consolidated Swarm Inputs
            "sector_strategy": context.get("sector_strategy", "無 (None)"),
            # Use task_instruction if available (from TaskPlanner), else fallback to generic focus
            "report_focus": context.get("task_instruction") or context.get("report_focus", "Weekly Strategic")
        }

        # 4. Call Agent Tool Loop with Thought Chain (IC Protocol Enforcement)
        response = self.run_tool_loop(
            context=prompt_data, 
            max_turns=3,
            thought_chain=True # [NEW] Enable R.P.A. Loop
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
        
        # Use call_llm directly for strategy JSON as it's a specific format request, not a report
        # Unless we want Strategy agent to also search? 
        # Strategy generation usually based on already synthesized context. Keep as call_llm or simple loop.
        # But wait, run_tool_loop re-renders system prompt.
        # Here we manually render a DIFFERENT template. run_tool_loop uses self.system_prompt.
        # So we stick to call_llm for this specific sub-task or trick it.
        # Let's keep call_llm for strategy to minimize risk of breaking JSON generation.
        response_str = self.call_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            response_format={"type": "json_object"} 
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

    def polish_report(self, report_content: str) -> str:
        """
        Refines the final report for readability and tone. 
        Ensures Actionable Orders table includes holdings context if available in text.
        
        潤飾最終報告以提升可讀性與語氣。
        確保行動指令表 (Actionable Orders) 包含持倉上下文 (若文本中有提供)。
        """
        system_prompt = (
            "You are the Chief Investment Officer (Editor Mode). "
            "Your task is to review the following investment report. "
            "1. Improve readability, flow, and formatting. "
            "2. Ensure the 'Actionable Orders' table is clear, well-formatted, and includes a 'Quantity/Weight' column if data allows. "
            "3. DO NOT remove the Detailed Analysis sections. Keep them intact but fix any markdown issues. "
            "4. Add a final professional concluding remark if missing. "
            "5. Ensure all headers are consistent (e.g., '## 1. Market Sentiment'). "
            "Output the polished report in Markdown."
        )
        
        user_prompt = f"Please polish this report:\n\n{report_content}"
        
        try:
            response = self.call_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            return response
        except Exception as e:
            self.logger.error(f"Polish failed: {e}")
            return report_content

    def _get_portfolio_context(self, user_id):
        """Retrieves portfolio context using Repository."""
        if not user_id:
            return 1.0, "No User ID provided."

        try:
            # Get Portfolio from Repository (Need to implement or use raw sql if repo missing method)
            # Use raw sql for now as repo might not have 'get_holdings_summary'
            # Or better, iterate tickers from repo
            tickers = self.transaction_repo.get_active_tickers(user_id)
            if not tickers:
                return 1.0, "目前無持倉 (No Holdings)"

            # We need quantities. Repo returns list of tickers. 
            # We might need to access the DataFrame method or add a new method to Repo.
            # For backward compatibility within this refactor, I'll use the repo's internal session if exposed,
            # but ideally strict encapsulation.
            # Let's add `get_portfolio_snapshot` to Repo later. For now, use a simple SQL via repo's connection helper if available.
            
            # Use Repository for Holdings & Leverage
            # 使用 Repository 獲取持倉與槓桿
            holdings_list = self.transaction_repo.get_holdings_summary(user_id)
            leverage = self.transaction_repo.get_latest_leverage(user_id)
            
            holdings_str_list = []
            non_etf_count = 0
            for ticker, qty in holdings_list:
                # Format as bullet point for clearer LLM parsing
                holdings_str_list.append(f"- {ticker} ({qty:.2f})")
                if ticker not in self.etf_list:
                    non_etf_count += 1
            
            # Join with newlines
            holdings_str = f"總持倉 (Non-ETF Count: {non_etf_count}):\n" + "\n".join(holdings_str_list)
            return leverage, holdings_str

        except Exception as e:
            self.logger.error(f"Error calculating portfolio context: {e}")
            return 1.0, "Error retrieving data."
