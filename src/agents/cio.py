import os
import pandas as pd
import json
from .base_agent import BaseAgent
from src.utils.time_utils import format_time
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.repositories.settings_repository import AlchemySettingsRepository
from src.utils.json_utils import json_loads_safe

class CIOAgent(BaseAgent):
    def __init__(self, use_cache=True, transaction_repo=None, prompt_path="prompts/cio_agent.txt", mode="report", **kwargs):
        # Allow tier override or kwargs
        tier = kwargs.pop('tier', 'smart')
        mode_map = {
            "daily": "IDENTITY_daily.md",
            "weekly": "IDENTITY_weekly.md"
        }
        identity_file = kwargs.pop('identity_file', mode_map.get(mode, "IDENTITY_weekly.md"))
        super().__init__(name="CIO", prompt_path=prompt_path, identity_file=identity_file, use_cache=use_cache, ttl_hours=24, tier=tier, **kwargs)
        
        self.transaction_repo = transaction_repo or AlchemyTransactionRepository()
        self.mode = mode
        
        # Common ETFs to filter out for "Stock Picking" focus
        self.etf_list = {
            "SPY", "QQQ", "VOO", "IWM", "VT", "BND", "TLT", "VTI", "VEA", "VWO",
            "IVV", "AGG", "GLD", "SLV", "ARKK", "SOXX", "XLE", "XLF", "XLK", "XLV",
            "XLP", "XLY", "XLI", "XLU", "XLB", "XLRE"
        }

    async def run(self, context, mode=None):
        """
        Run the CIO Agent (Async).
        mode: 'report' (Final Report) or 'strategy' (Sector Strategy & Screening)
        """
        # Determine effective mode
        effective_mode = mode or self.mode
        
        if effective_mode == 'strategy' or effective_mode == 'sector_analysis':
            return await self._run_strategy(context)
        
        # Report Mode (Default)
        return await self._run_report(context)

    async def _run_report(self, context):
        """
        Generates the final investment report using Swarm Intelligence & IC Protocol (Async).
        使用蜂群智慧與投資委員會協議生成最終投資報告 (非同步)。
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
        
        # 3. Get Thematic Data (Milestone 3.1)
        # 3. 取得主題資料 (整合實體 AI, AI 能源與供應鏈瓶頸)
        try:
            settings_repo = AlchemySettingsRepository()
            physical_ai = settings_repo.get(user_id, "physical_ai_tickers")
            ai_energy = settings_repo.get(user_id, "ai_energy_tickers")
            supply_chain = settings_repo.get(user_id, "supply_chain_knowledge_graph")
            
            thematic_context = "### 目前追蹤之核心主題與供應鏈 (Current Thematic & Supply Chain Tracks)\n"
            if physical_ai: thematic_context += f"- **實體 AI (Physical AI)**: {physical_ai}\n"
            if ai_energy: thematic_context += f"- **AI 能源護城河 (AI Energy Moat)**: {ai_energy}\n"
            if supply_chain:
                # Convert dict to string if it's stored as JSON dict
                sc_str = json.dumps(supply_chain, ensure_ascii=False) if isinstance(supply_chain, dict) else str(supply_chain)
                thematic_context += f"- **供應鏈瓶頸預測 (Supply Chain Bottlenecks)**: {sc_str}\n"
        except Exception as e:
            self.logger.error(f"Failed to load thematic context for CIO: {e}")
            thematic_context = "無法取得主題數據 (Failed to load thematic context)."

        # 4. Get Narrative Drift (Milestone 3.2)
        # 4. 取得敘事偏離度分析
        try:
            from src.services.experience_replay_service import ExperienceReplayService
            er_service = ExperienceReplayService()
            # For market data, we pass a simplified string of current macro/portfolio
            current_market_data = f"Macro: {context.get('macro_report', 'N/A')} | Portfolio: {portfolio_str}"
            drift_data = er_service.analyze_narrative_drift(user_id, current_market_data)
            
            narrative_drift_context = (
                f"### 上週敘事偏離復盤 (Narrative Drift Analysis)\n"
                f"- **準確度評分 (Accuracy)**: {drift_data.get('accuracy_score', 'N/A')}/10\n"
                f"- **偏離理由 (Rationale)**: {drift_data.get('narrative_delta_rationale', 'N/A')}\n"
                f"- **本週修正建議 (Correction)**: {drift_data.get('suggested_correction', 'N/A')}\n"
            )
        except Exception as e:
            self.logger.error(f"Failed to load narrative drift: {e}")
            narrative_drift_context = "無敘事偏離數據 (No narrative drift data)."

        # 5. Get Cash Deployment Context (Dynamic Calculation)
        # 5. 取得現金部署上下文 (動態計算)
        if "cash_deployment_context" not in context or not context.get("cash_deployment_context"):
            cash_deployment_context = self._get_cash_deployment_context(user_id)
        else:
            cash_deployment_context = context.get("cash_deployment_context", "")

        # 6. Prepare Data for Prompt Template
        mode_focus_map = {
            "daily": "Daily Tactical",
            "weekly": "Weekly Strategic",
            "sentinel": "Sentinel Breach Reaction"
        }
        default_focus = mode_focus_map.get(self.mode, "Weekly Strategic")

        prompt_data = {
            "current_date": format_time(fmt="%Y-%m-%d"),
            "leverage_ratio": f"{leverage_ratio:.2f}",
            "portfolio": portfolio_str,
            "risk_profile": context.get("risk_profile", "Balanced (穩健型)"),
            "macro_report": context.get("macro_report", "無 (None)"),
            "engineer_report": context.get("engineer_report", "無 (No Constraints)"),
            "swarm_context": swarm_context, 
            "thematic_context": thematic_context, 
            "narrative_drift_context": narrative_drift_context, # [NEW] Milestone 3.2 Context
            "sector_strategy": context.get("sector_strategy", "無 (None)"),
            "cash_deployment_context": cash_deployment_context, # [FIX] Dynamic cash level calculation
            "report_focus": context.get("task_instruction") or context.get("report_focus") or default_focus,
            "topic": context.get("topic", "未指定 (Not Specified)"),
            "memory_chain": context.get("memory_chain", "無相關歷史記憶 (No existing memory)")
        }

        # 6. Call Agent Tool Loop with Thought Chain (IC Protocol Enforcement)
        response = await self.run_tool_loop(
            context=prompt_data, 
            max_turns=3,
            thought_chain=True # [NEW] Enable R.P.A. Loop
        )
        
        # 7. Task 15.2: Post-Processing - Compliance Check (Evaluator) [Phase 15]
        try:
            from .evaluator_agent import EvaluatorAgent
            evaluator = EvaluatorAgent(user_id=user_id)
            eval_res_str = await evaluator.run({"report_content": response})
            eval_res = json_loads_safe(eval_res_str)
            
            if eval_res.get("is_compliant") is False:
                violation = eval_res.get("violation_reason", "Unknown Violation")
                self.logger.warning(f"CIOAgent: Compliance violation detected: {violation}")
                warning_prefix = (
                    "### 🛑 系統風險與合規性警告 (System Risk & Compliance Warning)\n"
                    f"**本報告經評估後可能違反投資規範**：{violation}\n"
                    "請使用者謹慎評估，僅供參考，不構成投資建議。\n\n---\n\n"
                )
                response = warning_prefix + response
        except Exception as e:
            self.logger.error(f"CIOAgent: Compliance check failed to execute: {e}")

        # 8. Task 15.3: Deterministic Rule Enforcement - Position Guard [Phase 15]
        from src.domain.portfolio_guard import enforce_position_limits
        try:
            response = enforce_position_limits(response, max_weight=0.2)
        except Exception as e:
            self.logger.error(f"CIOAgent: Portfolio guard failed: {e}")

        return response

    async def _run_strategy(self, context):
        """Generates Sector Strategy & Candidates (JSON) (Async)."""
        
        # Load Strategy Prompt (Ideally use _load_prompt but different path)
        strategy_prompt_template = ""
        # New Workspace path priority
        workspace_path = "workspace/captain/IDENTITY_strategy.md"
        legacy_path = "prompts/cio_strategy_agent.txt"
        
        try:
            if os.path.exists(workspace_path):
                with open(workspace_path, "r", encoding="utf-8") as f:
                    strategy_prompt_template = f.read()
            else:
                with open(legacy_path, "r", encoding="utf-8") as f:
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
        response_str = await self.call_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            response_format={"type": "json_object"} 
        )
        
        # Parse JSON
        data = json_loads_safe(response_str)
        
        # v9.1: Basic integrity check
        if not data or "sector_strategy" not in data:
            self.logger.error(f"CIOAgent: Strategy JSON invalid or incomplete. Raw: {response_str[:200]}...")
            return {
                "sector_strategy": {"target_sectors": [], "rationale": "Incomplete or Invalid JSON"},
                "candidates": []
            }
        return data

    async def polish_report(self, report_content: str) -> str:
        """
        Refines the final report for readability and tone. 
        Ensures Actionable Orders table includes holdings context if available in text.
        
        潤飾最終報告以提升可讀性與語氣。
        確保行動指令表 (Actionable Orders) 包含持倉上下文 (若文本中有提供)。
        """
        editor_identity_path = os.path.join(self.workspace_path, "IDENTITY_editor.md")
        if os.path.exists(editor_identity_path):
            with open(editor_identity_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
        else:
            # Fallback if file missing
            system_prompt = (
                "You are the Chief Investment Officer (Editor Mode). "
                "Polish the following report for readability and tone in Traditional Chinese."
            )
        
        user_prompt = f"Please polish this report:\n\n{report_content}"
        
        try:
            response = await self.call_llm(
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

    def _get_cash_deployment_context(self, user_id):
        """
        計算並返回現金部署上下文 (Dynamic Cash Deployment Context).
        基於帳戶現金水位提出建議。
        """
        if not user_id:
            return "無法取得用戶 ID (No user ID)."
        
        try:
            # Get account cash position
            # 取得帳戶現金部位
            from src.repositories.broker_account_repository import AlchemyBrokerAccountRepository
            from src.repositories.holdings_repository import AlchemyHoldingsRepository
            
            account_repo = AlchemyBrokerAccountRepository()
            holdings_repo = AlchemyHoldingsRepository()
            
            # Get latest account snapshot
            account = account_repo.get_latest_by_user(user_id)
            if not account:
                return "無法取得帳戶信息 (No broker account info)."
            
            nlv = account.nlv if hasattr(account, 'nlv') else account.total_equity
            cash = account.cash if hasattr(account, 'cash') else account.available_cash
            
            if nlv <= 0:
                return "帳戶尚未初始化 (Account not initialized)."
            
            cash_ratio = (cash / nlv * 100)
            
            # Dynamic assessment based on cash ratio
            # 基於現金比例的動態評估
            if cash_ratio > 30:
                status = "🔴 **現金水位明顯過高** (Excess Cash >30%)"
                signal = "URGENT: 現金再投資"
                recommendation = f"建議立即啟動「現金再投資」模組。目標: 將現金比例從 {cash_ratio:.1f}% 降至 15-20%。"
            elif cash_ratio > 25:
                status = "🔴 **現金水位過高** (High Cash 25-30%)"
                signal = "HIGH: 現金再投資"
                recommendation = f"建議在下一個交易機會啟動現金佈局。目標比例: 15-20%。"
            elif cash_ratio > 15:
                status = "🟡 **現金水位略高** (Moderate {cash_ratio:.1f}%)"
                signal = "NORMAL: 分期佈局"
                recommendation = "可考慮分期逢低吸納，但無急迫性。"
            elif cash_ratio > 10:
                status = "🟢 **現金水位正常** (Optimal {cash_ratio:.1f}%)"
                signal = "HOLD: 保持策略"
                recommendation = "現金配置合理，繼續按計劃投資。"
            else:
                status = "🔵 **現金水位低** (Low <10%)"
                signal = "CAUTION: 保持流動性"
                recommendation = "現金不足，應在下一輪獲利回吐時補充現金儲備。"
            
            # Build context string
            context_str = f"""
### 現金部署戰略 (Cash Deployment Strategy)
{status}

**帳戶快照 (Account Snapshot)**:
- 淨資產值 (NLV): ${nlv:,.2f}
- 可用現金: ${cash:,.2f}
- 現金比例: {cash_ratio:.1f}%

**信號 (Signal)**: {signal}

**建議 (Recommendation)**: {recommendation}
"""
            
            self.logger.info(f"Cash deployment context: {status} ({cash_ratio:.1f}%)")
            return context_str
            
        except Exception as e:
            self.logger.error(f"Failed to calculate cash deployment context: {e}")
            return "無法計算現金水位 (Unable to calculate cash position)."

