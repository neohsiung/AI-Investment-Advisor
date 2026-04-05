import os
import json
import requests
import hashlib
import re
from dataclasses import asdict
from src.utils.security import redact_secrets
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Generator
from sqlalchemy import text
from jinja2 import Template
# from src.data.database import get_db_connection # Removed for DIP
from src.utils.logger import setup_logger
from src.utils.cache import ResponseCache
from src.repositories.settings_repository import AlchemySettingsRepository
from src.repositories.agent_state_repository import AlchemyAgentStateRepository
from src.repositories.feedback_repository import AlchemyFeedbackRepository
from src.tools.mcp_server import McpServer, McpTool
from src.infrastructure.memory.memory_manager import HybridMemory
from src.agents.persona.persona_provider import AgentPersona, get_default_persona_provider
from src.agents.skills.skill_loader import SkillLoader
from src.domain.interfaces import ILLMGateway, Message, LLMConfig
from src.agents.context import ContextAssembler
from src.agents.wal_protocol import WalProtocol
from src.agents.agent_loop import AgentLoop
from src.infrastructure.llm import BudgetAwareModelRouter
from src.services.token_logger_service import TokenLoggerService
from src.services.settings_service import SettingsService
import uuid
from datetime import datetime

class BaseAgent(ABC):

    def __init__(self, name, prompt_path, use_cache=True, ttl_hours=24, tier="smart", user_id=None, settings_repo=None, state_repo=None, feedback_repo=None, identity_file="IDENTITY.md", llm_gateway: Optional[ILLMGateway] = None, persona: Optional[AgentPersona] = None, **kwargs):
        self.name = name
        self.logger = setup_logger(name)
        self.prompt_path = prompt_path
        self.identity_file = identity_file
        self.tier = tier
        self.user_id = user_id
        
        # Dependency Injection with Defaults
        # 依賴注入與預設值
        self.settings_repo = settings_repo or AlchemySettingsRepository()
        self.state_repo = state_repo or AlchemyAgentStateRepository()
        self.feedback_repo = feedback_repo or AlchemyFeedbackRepository()
        
        # [NEW] OpenClaw Components
        self.memory = HybridMemory() # Shared DB for now (目前共用 DB)
        
        # Rule #8: Cognitive Memory Tiering
        from src.services.cognitive_memory_manager import CognitiveMemoryManager
        self.cognitive_memory = CognitiveMemoryManager(user_id=self.user_id)
        
        self.skill_loader = SkillLoader()
        
        # [NEW] Agentic Brain (Workspace)
        workspace_map = {
            "CIO": "captain",
            "Macro": "macro-evaluator",
            "Risk": "risk-assessor",
            "Sentiment": "sentiment-analyst",
            "Momentum": "market-scanner",
            "Fundamental": "data-prep",
            "Thematic": "portfolio-manager",
            "Engineer": "system-engineer"
        }
        mapped_name = workspace_map.get(self.name, self.name.lower().replace(" ", "-"))
        self.workspace_path = f"workspace/{mapped_name}"
        
        # [Phase 3] Agent Persona System
        # 人格系統：從 PersonaProvider 載入或使用注入的 persona
        if persona:
            self.persona = persona
        else:
            provider = get_default_persona_provider()
            self.persona = provider.get_persona(self.name)  # None if no file exists
        
        # Must load prompt after workspace_path is defined
        self.system_prompt = self._load_prompt()
        self.config = self._load_config()
        self.cache = ResponseCache(ttl_hours=ttl_hours) if use_cache else None
        
        # [Phase 1] LLM Gateway - Model Layer Injection (Model > Agent > Skill)
        # 注入 ILLMGateway 實作，實現 Model 層完全解耦
        self._llm_gateway = llm_gateway or self._create_default_gateway()
        
        # Set up Tool Server
        self.toold = McpServer(name=f"{self.name}_Tools")
        
        # Bind implementations
        from src.agents.skills.registry import bind_skills_to_agent
        bind_skills_to_agent(self)
        
        # [Phase 2] Composition: ContextAssembler, WalProtocol, AgentLoop
        self._context_assembler = ContextAssembler(
            skill_loader=self.skill_loader,
            memory=self.memory,
            cognitive_memory=self.cognitive_memory,
            toold=self.toold,
        )
        self._wal_protocol = WalProtocol(
            workspace_path=self.workspace_path,
            agent_name=self.name,
            redact_fn=self._redact_secrets,
        )
        self._agent_loop = AgentLoop(
            agent_name=self.name,
            toold=self.toold,
            user_id=self.user_id
        )
    def register_tool(self, tool: McpTool):
        """
        Register a tool for the agent to use.
        註冊一個工具供 Agent 使用
        """
        self.toold.register_tool(tool)

    def _load_config(self):
        """
        Read AI configuration (Priority: Budget Router > DB > Env > Default).
        讀取 AI 設定 (優先經由預算路由器，確保花費受控)
        """
        try:
            # 1. Initialize dependencies for Router
            # Use specific services to ensure consistency with router logic
            settings = SettingsService(user_id=self.user_id, settings_repo=self.settings_repo)
            token_logger = TokenLoggerService()
            router = BudgetAwareModelRouter(settings, token_logger)
            
            # 2. Get configuration from router (handles budget-based downgrading)
            config_obj = router.get_config(self.tier, self.user_id)
            
            # 3. Convert to dict for backward compatibility with base classes and tests
            # 將 LLMConfig 物件轉為字典，以容納目前的測試與基礎層邏輯
            return asdict(config_obj)
            
        except Exception as e:
            self.logger.error(f"[_load_config] Failed to use BudgetAwareModelRouter: {e}. Falling back to legacy loading.")
            # Fallback to legacy loading if router fails
            return self._legacy_load_config()

    def _legacy_load_config(self):
        """Legacy configuration loader (Fallback using TierConfig)."""
        from src.infrastructure.llm.tier_config import TierConfig
        try:
            db_settings = self._load_config_from_db()
        except Exception:
            db_settings = {}
            
        tier_cfg = TierConfig()
        # Priority: DB AI_MODEL > Tier Resolution
        default_model = db_settings.get("AI_MODEL", db_settings.get("ai_model", tier_cfg.resolve(self.tier, db_settings)))
        provider = db_settings.get("AI_PROVIDER", db_settings.get("ai_provider", os.getenv("AI_PROVIDER", "Google Gemini")))
        
        config = {
            "provider": provider,
            "model": default_model,
            "api_key": db_settings.get("API_KEY", db_settings.get("api_key", os.getenv("API_KEY", ""))),
            "base_url": db_settings.get("api_base_url", os.getenv("BASE_URL", "")),
            "temperature": float(db_settings.get("ai_temperature", 0.7)),
            "max_tokens": int(db_settings.get("ai_max_tokens", 4096)),
            "timeout_seconds": int(db_settings.get("ai_timeout", 60)),
        }

        # [Robustness] Clean quotes if any
        if isinstance(config.get("model"), str):
            config["model"] = config["model"].strip().strip('"').strip("'")
        return config

    def _load_config_from_db(self):
        """
        Load API settings from database (Via Repository).
        """
        settings = {}
        if not self.user_id:
            return settings
            
        try:
            # v4.3.0: Only fetch settings specifically for this user. No global fallback.
            user_rows = self.settings_repo.get_all(self.user_id)
            for row in user_rows:
                 key = row._mapping['key'] if hasattr(row, '_mapping') else row[0]
                 val = row._mapping['value'] if hasattr(row, '_mapping') else row[1]
                 settings[key] = val
        except Exception as e:
            # self.logger.warning(f"Failed to load settings from DB: {e}")
            pass  # nosec B110
        finally:
            self.settings_repo.close_session()
        return settings

    def _load_prompt(self):
        """
        [Phase 18] Dynamic Personalization - Check for user-specific prompt overrides
        This allows RLHF-optimized prompts to override static files.
        """
        try:
            from sqlalchemy.orm import sessionmaker
            from src.data.database import get_db_engine
            from src.data.models import UserCustomPrompt
            
            Session = sessionmaker(bind=get_db_engine())
            session = Session()
            custom = session.query(UserCustomPrompt).filter_by(
                user_id=self.user_id, 
                agent_name=self.name
            ).first()
            
            if custom and custom.custom_prompt:
                self.logger.info(f"✨ Using dynamically optimized prompt for user {self.user_id} (Agent: {self.name})")
                return custom.custom_prompt
            session.close()
        except Exception as e:
            self.logger.warning(f"Dynamic prompt check bypassed due to error: {e}")

        # [Phase 1] Attempt to load from new Workspace directories first
        prompt_content = ""
        if hasattr(self, 'workspace_path') and self.workspace_path and os.path.exists(self.workspace_path):
            identity_path = os.path.join(self.workspace_path, self.identity_file)
            soul_path = os.path.join(self.workspace_path, "SOUL.md")
            
            if os.path.exists(identity_path):
                with open(identity_path, 'r', encoding='utf-8') as f:
                    prompt_content += f.read() + "\n\n"
                    
            if os.path.exists(soul_path):
                with open(soul_path, 'r', encoding='utf-8') as f:
                    prompt_content += f.read() + "\n\n"
                    
            if prompt_content.strip():
                # Inject Persona prefix before workspace prompt
                if self.persona and self.persona.system_prompt_prefix:
                    persona_block = self.persona.render_prefix()
                    return f"{persona_block}\n\n{prompt_content.strip()}"
                return prompt_content.strip()

        # Fallback to legacy path
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_path}")
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def render_system_prompt(self, context):
        """
        Render System Prompt using Jinja2 - delegates to ContextAssembler.
        使用 Jinja2 渲染系統提示詞 - 委派至 ContextAssembler
        """
        return self._context_assembler.render(self.system_prompt, context)


    @abstractmethod
    async def run(self, context):
        """
        Execute Agent Task (Async).
        執行 Agent 任務 (同步)
        """
        pass

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count - delegates to WalProtocol."""
        return WalProtocol.estimate_tokens(text)

    def _check_context_window(self, messages: List[Dict[str, str]], reserve_floor: int = 4000, max_tokens: int = 32000) -> bool:
        """Check context window - delegates to WalProtocol."""
        return self._wal_protocol.check_context_window(messages, reserve_floor, max_tokens)

    def _perform_silent_flush(self, messages: List[Dict[str, str]]):
        """WAL Protocol flush - delegates to WalProtocol."""
        self._wal_protocol.perform_silent_flush(messages, self.call_llm)

    async def run_tool_loop(self, context, max_turns=3, thought_chain=False):
        """
        ReAct-style loop - delegates to AgentLoop.
        """
        if thought_chain:
            context = context.copy() if isinstance(context, dict) else {}
            context["thought_chain_mode"] = True

        messages = [
            {"role": "system", "content": self.render_system_prompt(context)},
            {"role": "user", "content": self._render_user_context(context)}
        ]

        # Lazy-init search service for legacy SEARCH handler
        from src.services.search_service import InternetSearchService
        self._agent_loop._search_service = InternetSearchService(user_id=self.user_id)

        response = await self._agent_loop.execute(
            messages=messages,
            call_llm_fn=self.call_llm,
            check_context_fn=lambda m: self._wal_protocol.check_context_window(m),
            flush_fn=lambda m: self._wal_protocol.perform_silent_flush(m, self.call_llm),
            max_turns=max_turns,
        )
        
        # [Phase 9] Auto-save insights to Knowledge Vault
        if thought_chain and response:
            from src.utils.async_utils import to_thread
            import asyncio
            
            # Fire and forget extraction to not block the main flow
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(to_thread(self._extract_and_save_takeaways, response))
            except RuntimeError:
                # Fallback if no event loop running
                self._extract_and_save_takeaways(response)

        return response

    # --- Context Guard ---



    async def call_swarm(self, agents: list, message: str, context: dict = None) -> dict:
        """
        Broadcasts a message to a swarm of agents effectively in parallel. [Phase 12]
        向 Agent Swarm 廣播訊息
        """
        self.logger.info(f"Swarm Broadcast Initiated: {self.name} -> {agents}")
        
        # Parallel Execution [Phase 12]
        tasks = [self.call_agent(agent_name, message, context) for agent_name in agents]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = {}
        for agent_name, response in zip(agents, responses):
            if isinstance(response, Exception):
                self.logger.error(f"Swarm Broadcast Failed for {agent_name}: {response}")
                results[agent_name] = f"Error: {response}"
            else:
                results[agent_name] = response
                
        return results

    def _parse_tool_call(self, text):
        """Parse tool calls - delegates to AgentLoop."""
        return AgentLoop.parse_tool_call(text)

    async def call_agent(self, agent_name: str, message: str, context: dict = None):
        """
        Agent-to-Agent Communication (Agent Mesh) - Async.
        Sends a message/task to another agent.
        Agent 對 Agent 通訊 (Agent Mesh) - 非同步
        發送訊息/任務給另一個 Agent
        """
        self.logger.info(f"Calling Agent {agent_name} with message: {message[:50]}...")
        
        from src.agents.factory import AgentFactory
        
        target_agent = None
        if agent_name.lower() == "cio":
            target_agent = AgentFactory.create_cio_agent(user_id=self.user_id)
        elif "fundamental" in agent_name.lower():
            target_agent = AgentFactory.create_fundamental_agent(user_id=self.user_id)
        elif "momentum" in agent_name.lower():
            target_agent = AgentFactory.create_momentum_agent(user_id=self.user_id)
        elif "sentiment" in agent_name.lower():
            target_agent = AgentFactory.create_sentiment_agent(user_id=self.user_id)
        
        if target_agent:
            call_context = context or {}
            call_context["user_request"] = message
            response = await target_agent.run(call_context)
            return response
        
        return f"Error: Agent {agent_name} not found."

    def rate_request(self, sender: str, score: int, comment: str, context_hash: str = None):
        # HR Protocol: Rate an incoming request from another agent.
        # HR 協議: 對來自其他 Agent 的請求進行評分
        try:
            self.feedback_repo.add_review(
                reviewer=self.name,
                reviewee=sender,
                score=score,
                comment=comment,
                context_hash=context_hash
            )
            self.logger.info(f"Recorded feedback for {sender}: {score}/5")
        except Exception as e:
            self.logger.error(f"Failed to record feedback: {e}")

    def _render_user_context(self, context):
        """Render user context - delegates to ContextAssembler."""
        return ContextAssembler.render_user_context(context)

    def _extract_and_save_takeaways(self, agent_response: str) -> None:
        # [Phase 9] Extracts key takeaways from the agent's response and saves them to the Knowledge Vault.
        # Uses a fast LLM model to distill the context.
        if len(agent_response) < 100:
            return  # Too short to contain meaningful long-term takeaways
            
        try:
            from src.agents.factory import AgentFactory
            extractor = AgentFactory.create_sentinel_agent(user_id=self.user_id, tier="fast")
            
            prompt = (
                "Extract 1-3 highly significant, long-term 'Key Takeaways' or 'Regime Shifts' from the following analysis. "
                "Only extract information that would be valuable for future investment decisions across different sessions. "
                "If there is nothing of long-term value, output 'NONE'. "
                "Return the takeaways as a concise bulleted list in Traditional Chinese.\n\n"
                f"Agent Name: {self.name}\n"
                f"Analysis:\n{agent_response[:2500]}"
            )
            
            result = extractor.call_llm([{"role": "user", "content": prompt}], temperature=0.1)
            
            if result and "NONE" not in result.upper() and len(result.strip()) > 10:
                self.logger.info(f"Saving extracted takeaways to Knowledge Vault for {self.name}")
                from src.infrastructure.memory.memory_manager import HybridMemory
                memory = HybridMemory()
                memory.add_memory(
                    user_id=self.user_id,
                    content=result,
                    category=f"{self.name.lower()}_takeaways",
                    metadata={"source": "auto_extraction", "agent": self.name}
                )
        except Exception as e:
            self.logger.warning(f"Failed to auto-extract takeaways: {e}")

    # ================================================================
    # LLM Gateway Factory & Delegation (Model > Agent > Skill)
    # ================================================================

    def _create_default_gateway(self) -> ILLMGateway:
        """
        Create a default ILLMGateway based on config.
        Creates a default LLM gateway if none is provided.
        """
        try:
            from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, RetryLLMGateway, LoggingLLMGateway
            # [Rule #14] Tiering & Logging Decorators
            # Use Mock if API Key is missing (Standardized fallback behavior)
            api_key = self.config.get('api_key', '')
            if not api_key or api_key == "":
                from src.infrastructure.llm.llm_gateway import MockLLMGateway
                return MockLLMGateway()

            provider = self.config.get('provider', os.getenv("AI_PROVIDER", "Google Gemini"))
            inner = LLMGatewayFactory.create(provider)
            # 1. Add Retry logic
            retrying = RetryLLMGateway(inner=inner, max_retries=3)
            
            # 2. Add Logging for centralized budget monitoring ($20/week limit)
            logged = LoggingLLMGateway(
                inner=retrying,
                agent_name=self.name,
                tier=self.tier,
                user_id=self.user_id
            )
            return logged
        except (ValueError, ImportError) as e:
            self.logger.warning(f"Gateway creation failed: {e}. Falling back to Mock.")
            from src.infrastructure.llm.llm_gateway import MockLLMGateway
            return MockLLMGateway()

    def _build_llm_config(self, temperature: float = 0.7) -> LLMConfig:
        """
        Build LLMConfig value object from agent config dict.
        """
        return LLMConfig(
            provider=self.config.get('provider', ''),
            model=self.config.get('model', '').strip('"').strip("'"),
            api_key=self.config.get('api_key', ''),
            base_url=self.config.get('base_url', ''),
            temperature=temperature,
            max_retries=self.config.get('max_retries', 3),
            timeout_seconds=30,
        )

    def call_llm(self, messages, temperature=0.7, response_format=None):
        """
        Unified method to call LLM - delegates to ILLMGateway.
        統一的 LLM 調用方法 - 委派至 ILLMGateway
        """
        system_prompt = ""
        user_prompt = ""
        for m in messages:
            if m['role'] == 'system': system_prompt += m['content'] + "\n"
            elif m['role'] == 'user': user_prompt += m['content'] + "\n"
            elif m['role'] == 'assistant': user_prompt += f"\n[Previous Output]: {m['content']}\n"

        system_prompt = system_prompt.strip()
        user_prompt = user_prompt.strip()

        # Cache check
        if self.cache:
            cached_response = self.cache.get(self.name, user_prompt)
            if cached_response:
                self.logger.info(f"Using Cached Response for {self.name}")
                return cached_response

        prompt_snippet = user_prompt[:50].replace('\n', ' ') + "..."
        self.logger.info(f"Calling LLM via Gateway | Prompt: {prompt_snippet}")

        # Delegate to ILLMGateway
        config = self._build_llm_config(temperature=temperature)
        gateway_messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]
        return self._llm_gateway.chat(gateway_messages, config)

    def stream_llm(self, messages, temperature=0.7) -> Generator[str, None, None]:
        """
        Unified method to stream LLM response - delegates to ILLMGateway.
        統一的 LLM 串流調用方法 - 委派至 ILLMGateway
        """
        system_prompt = ""
        user_prompt = ""
        for m in messages:
            if m['role'] == 'system': system_prompt += m['content'] + "\n"
            elif m['role'] == 'user': user_prompt += m['content'] + "\n"
            elif m['role'] == 'assistant': user_prompt += f"\n[Previous Output]: {m['content']}\n"

        system_prompt = system_prompt.strip()
        user_prompt = user_prompt.strip()

        self.logger.info(f"Streaming LLM via Gateway for {self.name}...")

        # Delegate to ILLMGateway
        config = self._build_llm_config(temperature=temperature)
        gateway_messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]
        return self._llm_gateway.stream_chat(gateway_messages, config)

    # Legacy aliases for backward compatibility (deprecated - will be removed)
    def _mock_llm_call(self, prompt, system_prompt):
        """Legacy bridge: delegates to call_llm via gateway."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return self.call_llm(messages)

    def _call_real_llm(self, prompt, system_prompt):
        """Legacy bridge: delegates to call_llm via gateway."""
        return self._mock_llm_call(prompt, system_prompt)

    def _redact_secrets(self, text_value):
        """
        Best-effort redaction of common secret patterns (API keys, bearer tokens)
        before persisting content to disk or logging.
        Delegates to centralized security utility.
        """
        return redact_secrets(text_value)

    def _compute_hash(self, data):
        """
        Compute SHA256 hash of the input data.
        計算輸入資料的 SHA256 雜湊值
        """
        try:
            if isinstance(data, dict):
                s = json.dumps(data, sort_keys=True, ensure_ascii=False)
            else:
                s = str(data)
            return hashlib.sha256(s.encode('utf-8')).hexdigest()
        except Exception as e:
            self.logger.warning(f"Failed to compute hash: {e}")
            return None

    def check_freshness(self, context, state_key=None):
        """
        Check if the input context is different from the last run.
        檢查輸入的 Context 是否與上次執行不同 (避免重複執行)
        """
        current_hash = self._compute_hash(context)
        if not current_hash:
            return True, None, None

        db_id = f"{self.name}_{state_key}" if state_key else self.name

        try:
            state = self.state_repo.get_state(db_id)
            if state:
                last_hash, last_output = state
                if last_hash == current_hash and last_output:
                    return False, current_hash, last_output
            
            return True, current_hash, None
        except Exception as e:
            self.logger.error(f"Error checking freshness: {e}")
            return True, current_hash, None

    def update_state(self, current_hash, output_content, state_key=None):
        """
        Update the agent_state table with new hash, time, and output.
        更新 agent_state 資料表，記錄新的雜湊值、時間與輸出
        """
        try:
            db_id = f"{self.name}_{state_key}" if state_key else self.name
            self.state_repo.save_state(db_id, self.name, current_hash, output_content)
        except Exception as e:
            self.logger.error(f"Error updating agent state: {e}")
