import json
import typing
import os
from dataclasses import replace
from typing import List, Dict, Tuple, Any, Optional, Callable
from sqlalchemy import text
from src.utils.logger import setup_logger
from src.repositories.sentinel_repository import ISentinelRepository, AlchemySentinelRepository
from src.repositories.transaction_repository import ITransactionRepository, AlchemyTransactionRepository
from src.infrastructure.memory.wisdom_vault import WisdomVault
from src.domain.interfaces import LLMConfig, Message
from src.services.budget_aware_model_router import BudgetAwareModelRouter
from src.services.settings_service import SettingsService
from src.services.token_logger_service import TokenLoggerService

logger = setup_logger("ExperienceReplay")

class ExperienceReplayService:
    """
    Experience Replay Service (Rule #8/Rule #9).
    復盤服務：分析警報歷史與投資組合表現以動態調整參數。
    
    Analyses: 
    1. Signal-to-Noise Ratio (SNR): Did an alert lead to correct action?
    2. False Positive Mitigation: Adjust thresholds upwards if ROI didn't justify the alert.
    """
    
    def __init__(
        self, 
        sentinel_repo: ISentinelRepository = None,
        trans_repo: ITransactionRepository = None,
        llm_gateway: Optional[typing.Any] = None, # Using Any to avoid circular import if needed
        agent_name: str = "ExperienceReplayService",
        user_id: str = "system",
        tier: str = "fast",
        wisdom_vault: Optional[WisdomVault] = None
    ):
        self.sentinel_repo = sentinel_repo or AlchemySentinelRepository()
        self.trans_repo = trans_repo or AlchemyTransactionRepository()
        self._wisdom_vault = wisdom_vault or WisdomVault()
        
        self.agent_name = agent_name
        self.user_id = user_id
        self.tier = tier
        
        # [Rule #14] Budget-Aware Model Routing
        settings = SettingsService(user_id=self.user_id)
        token_logger = TokenLoggerService()
        self._router = BudgetAwareModelRouter(settings, token_logger)
        
        if llm_gateway:
            self._llm_gateway = llm_gateway
        else:
            # Fallback to creating a bridge gateway
            from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, LoggingLLMGateway
            # Resolve provider from settings or default
            provider = settings.get_setting("ai_provider", "OpenRouter")
            inner = LLMGatewayFactory.create(provider)
            # Wrap with Logging for token/cost tracking
            self._llm_gateway = LoggingLLMGateway(
                inner=inner,
                agent_name=self.agent_name,
                tier=self.tier,
                user_id=self.user_id
            )

    def optimize_thresholds(self, user_id: str) -> Dict[str, Any]:
        """
        Main optimization loop.
        主優化迴圈。
        """
        results = {}
        logger.info(f"Starting Experience Replay optimization for user: {user_id}")
        
        # 1. Analyze Alert Density vs Portfolio Volatility
        # 2. Adjust VIX thresholds if alerts are too frequent (> 3 per day)
        vix_adj = self._optimize_vix_thresholds(user_id)
        if vix_adj:
            results["vix"] = vix_adj
            
        return results

    def _optimize_vix_thresholds(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Adjust VIX thresholds based on recent alert frequency.
        基於近期警報頻率調整 VIX 閾值。
        """
        try:
            from src.repositories.data_repository import AlchemyDataRepository
            data_repo = AlchemyDataRepository()
            
            # Count Sentinel alerts in the last 7 days
            recent_logs = data_repo.get_recent_event_logs(days=7, limit=100)
            alert_count = sum(1 for row in recent_logs if "VIX" in row.title)
                
            if alert_count > 10: # More than ~1.5 per day is "noisy"
                current = self.sentinel_repo.get_all_thresholds()
                v_high = current.get("vix_high", 25.0)
                
                # Increase threshold by 5% to reduce noise
                new_val = round(v_high * 1.05, 2)
                self.sentinel_repo.update_threshold(
                    "vix_high", 
                    new_val, 
                    "ExperienceReplay", 
                    f"Reduced noise: {alert_count} alerts in 7d detected."
                )
                return {"key": "vix_high", "old": v_high, "new": new_val, "reason": "High frequency noise suppression"}
                
        except Exception as e:
            logger.error(f"VIX optimization failed: {e}")
        return None

    def record_feedback(
        self, 
        user_id: str, 
        category: str, 
        principle: str, 
        confidence: float,
        conflicts_with: Optional[str] = None
    ) -> None:
        """
        Record wisdom feedback into WisdomVault.
        將回饋記錄至智慧金庫。
        """
        if conflicts_with:
            # Handle conflict resolution: supersede old principle
            self._wisdom_vault.supersede_wisdom(
                user_id=user_id,
                category=category,
                old_principle=conflicts_with,
                new_principle=principle,
                confidence=confidence
            )
            logger.info(f"ExperienceReplay: Recorded feedback (superseded) for {user_id}/{category}")
        else:
            # Store new principle
            self._wisdom_vault.store_wisdom(
                user_id=user_id,
                category=category,
                principle=principle,
                confidence=confidence
            )
            logger.info(f"ExperienceReplay: Recorded feedback for {user_id}/{category}")

    async def distill_feedback(
        self, user_message: str, last_ai_response: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        [Phase 3] Distill behavioral feedback from user message using LLM self-assessment.
        從使用者訊息中提煉行為回饋。
        """
        # [Fix 3X-6] Fast cognitive filtering for noise/short messages
        SKIP_PATTERNS = ["好", "嗯", "謝謝", "OK", "了解", "收到", "yes", "no", "對", "錯"]
        if user_message.strip().lower() in SKIP_PATTERNS or len(user_message.strip()) < 4:
            return None

        try:
            # 1. Load existing wisdom as context for conflict detection
            existing_summary = self._wisdom_vault.get_wisdom_summary(user_id)
            
            # 2. Load prompt template
            current_dir = os.path.dirname(os.path.abspath(__file__))
            prompt_path = os.path.abspath(os.path.join(current_dir, "../../prompts/feedback_distiller.txt"))
            
            if not os.path.exists(prompt_path):
                logger.error(f"Distill feedback failed: Prompt file not found at {prompt_path}")
                return None
                
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()

            system_prompt = (
                template
                .replace("{{existing_wisdom}}", existing_summary or "None")
                .replace("{{user_message}}", user_message)
                .replace("{{last_ai_response}}", last_ai_response)
            )

            # 3. Call LLM (Get budget-aware config from router)
            config = self._router.get_config("fast", user_id)
            config = replace(config, temperature=0.1, max_tokens=500) # Overwrite for distillation
            
            messages = [
                Message(role="system", content="You are a JSON-only response agent."),
                Message(role="user", content=system_prompt)
            ]
            
            response_str = self._llm_gateway.chat(messages, config)
            
            # 4. Parse & Validate JSON
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            # Handle case where LLM yields non-JSON start
            if not cleaned.startswith("{"):
                start_idx = cleaned.find("{")
                if start_idx != -1:
                    cleaned = cleaned[start_idx:]
            
            data = json.loads(cleaned)
            
            # Confidence/Action Validation
            action = data.get("action", "none")
            confidence = data.get("confidence", 0.0)
            
            # Self-assessment Routing
            if action == "store" and confidence >= 0.7:
                # High confidence, ready to store
                logger.info(f"ExperienceReplay: High confidence feedback detected ({confidence})")
                return data
            elif action == "clarify" or (confidence >= 0.4 and confidence < 0.7):
                # Medium confidence, need clarification
                logger.info(f"ExperienceReplay: Medium confidence feedback detected ({confidence}), suggesting clarification")
                data["action"] = "clarify"
                return data
            else:
                # Low confidence or no feedback
                return None

        except Exception as e:
            logger.error(f"Distill feedback failed: {e}")
            return None

    def analyze_narrative_drift(self, user_id: str, current_market_data: str) -> Dict[str, Any]:
        """
        Milestone 3.2: Narrative Drift Analysis.
        敘事偏離度分析：對比上週週報的共識與本週的實際行情。
        """
        logger.info(f"Starting Narrative Drift Analysis for user {user_id}")
        
        try:
            # 1. Retrieve the last weekly CIO report
            from src.repositories.report_repository import AlchemyReportRepository
            report_repo = AlchemyReportRepository()
            reports_df = report_repo.get_latest_reports(user_id=user_id, limit=5)
            
            past_consensus = None
            if not reports_df.empty:
                for _, row in reports_df.iterrows():
                    if "Weekly Macro" in str(row['summary']):
                        past_consensus = row['content']
                        break
            
            # 1.5. Retrieve Conviction & Time Horizon History (v5.0)
            from src.repositories.snapshot_repository import AlchemySnapshotRepository
            snap_repo = AlchemySnapshotRepository()
            history_df = snap_repo.get_history_by_user(user_id)
            conviction_context = "No conviction history found."
            if not history_df.empty:
                # Get last 14 days to see the narrative evolution
                tail = history_df.tail(14)
                if 'conviction_level' in tail.columns and 'time_horizon' in tail.columns:
                    conviction_context = tail[['date', 'conviction_level', 'time_horizon']].to_json(orient='records', force_ascii=False)
                
            if not past_consensus:
                logger.warning("No past weekly report found for narrative drift analysis.")
                return {"accuracy_score": 10, "suggested_correction": "無歷史參考資料 (No historical data)."}
            
            # 2. Call LLM directly to analyze the drift
            from src.infrastructure.llm_router import DynamicModelRouter
            from src.utils.llm_clients.openrouter_client import OpenRouterClient
            import os
            
            router = DynamicModelRouter()
            tier = router.select_tier("Narrative Drift Analysis", round_num=99)
            
            # Retrieve Model config
            from src.repositories.settings_repository import AlchemySettingsRepository
            settings_repo = AlchemySettingsRepository()
            config_res_val = settings_repo.get(user_id, 'ai_models_config')
                
            provider = "openrouter"
            model_id = "openai/gpt-4o-mini" # Default fallback
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            
            if config_res_val:
                config = json.loads(config_res_val) if isinstance(config_res_val, str) else config_res_val
                model_info = config.get(tier, {})
                provider = model_id.split('/')[0] if '/' in model_info.get("model", "") else "openrouter"
                model_id = model_info.get("model", model_id)
                api_key = config.get("api_keys", {}).get(provider, api_key)
            
            prompt_path = "prompts/narrative_drift_agent.txt"
            with open(prompt_path, "r", encoding="utf-8") as f:
                sys_prompt_template = f.read()
                
            system_prompt = (
                sys_prompt_template
                .replace("{{past_consensus}}", past_consensus)
                .replace("{{market_data}}", current_market_data)
                .replace("{{conviction_history}}", conviction_context)
            )
            
            from src.domain.interfaces import LLMConfig, Message
            
            # Use gateway with budget-aware configuration
            config = self._router.get_config("fast", user_id)
            config = replace(config, temperature=0.3, max_tokens=2000)
            
            messages = [Message(role="user", content=system_prompt + "\n\n" + "Analyze the narrative drift and output JSON only.")]
            
            response_str = self._llm_gateway.chat(messages, config)
            
            # Clean and Parse JSON
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            logger.info(f"Narrative Delta Score: {data.get('accuracy_score')}/10")
            return data
            
        except Exception as e:
            logger.error(f"Narrative Drift Analysis failed: {e}")
            return {"accuracy_score": 10, "suggested_correction": f"分析失敗 (Analysis Failed): {e}"}

    def optimize_cash_ratio(self, user_id: str) -> Dict[str, Any]:
        """
        v5.0: Dynamic Cash Ratio Optimization.
        根據歷史回撤與通膨趨勢優化現金比例門檻。
        """
        try:
            from src.repositories.snapshot_repository import AlchemySnapshotRepository
            from src.services.fred_service import FredService
            
            snap_repo = AlchemySnapshotRepository()
            history = snap_repo.get_history_by_user(user_id)
            
            if history.empty or len(history) < 10:
                return {"status": "skipped", "reason": "Insufficient history"}
            
            # Calculate Drawdown
            history['cummax'] = history['total_nlv'].cummax()
            history['drawdown'] = (history['total_nlv'] - history['cummax']) / history['cummax']
            max_dd = abs(history['drawdown'].min())
            
            # Get Inflation
            fred = FredService(user_id=self.user_id)
            macro = fred.get_macro_indicators()
            cpi_val = macro.get("CPI", {}).get("value", 3.0) # Assume 3% if error
            
            from src.services.settings_service import SettingsService
            settings = SettingsService(user_id=user_id)
            current_target = float(settings.get_setting(user_id, "target_cash_ratio", 0.1))
            
            # Heuristic: If drawdown is high (>15%), increase cash buffer
            # If inflation is very high (>5%), tilt towards assets, but maintain liquidity
            new_target = current_target
            if max_dd > 0.15:
                new_target += 0.05
            elif max_dd < 0.05:
                new_target -= 0.02
                
            new_target = max(0.05, min(0.40, new_target))
            
            if abs(new_target - current_target) > 0.01:
                settings.settings_repo.set(user_id, "target_cash_ratio", new_target)
                return {"old": current_target, "new": new_target, "reason": f"MDD: {max_dd:.1%}, CPI: {cpi_val}"}
            
        except Exception as e:
            logger.error(f"Cash ratio optimization failed: {e}")
            
        return {"status": "unchanged"}
