import os
import json
import requests
import hashlib
import re
from src.utils.security import redact_secrets
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
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
from src.agents.skills.skill_loader import SkillLoader
from src.domain.interfaces import ILLMGateway, Message, LLMConfig
from src.agents.context import ContextAssembler
from src.agents.wal_protocol import WalProtocol
from src.agents.agent_loop import AgentLoop
import uuid
from datetime import datetime

class BaseAgent(ABC):

    def __init__(self, name, prompt_path, use_cache=True, ttl_hours=24, tier="smart", user_id=None, settings_repo=None, state_repo=None, feedback_repo=None, identity_file="IDENTITY.md", llm_gateway: Optional[ILLMGateway] = None, **kwargs):
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
        self.skill_loader = SkillLoader()
        self.skill_loader.load_skills()
        
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
        
        # Must load prompt after workspace_path is defined
        self.system_prompt = self._load_prompt()
        self.config = self._load_config()
        self.cache = ResponseCache(ttl_hours=ttl_hours) if use_cache else None
        
        # [Phase 1] LLM Gateway — Model Layer Injection (Model > Agent > Skill)
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
        )
    def register_tool(self, tool: McpTool):
        """
        Register a tool for the agent to use.
        註冊一個工具供 Agent 使用。
        """
        self.toold.register_tool(tool)

    def _load_config(self):
        """
        Read AI configuration (Priority: DB > Env > Default).
        讀取 AI 設定 (優先順序: DB > Env > Default)。
        """
        if self.tier == "fast":
            default_model = os.getenv("AI_MODEL_FAST", os.getenv("AI_MODEL", "gemini-1.5-flash"))
        elif self.tier == "advanced":
            default_model = os.getenv("AI_MODEL_ADVANCED", os.getenv("AI_MODEL_SMART", "claude-3-5-sonnet-20240620"))
        else:
            default_model = os.getenv("AI_MODEL_SMART", os.getenv("AI_MODEL", "gemini-1.5-pro"))

        config = {
            "provider": os.getenv("AI_PROVIDER", "Google Gemini"),
            "model": default_model,
            "api_key": os.getenv("API_KEY", ""),
            "base_url": os.getenv("BASE_URL", "")
        }

        db_settings = self._load_config_from_db()
        self.logger.info(f"[_load_config] User: {self.user_id} | DB Settings Loaded: {list(db_settings.keys())}")
        
        # Apply DB Settings (Override Env)
        for key, value in db_settings.items():
            if key == "AI_PROVIDER": config["provider"] = value
            elif key == "AI_MODEL_ADVANCED" and self.tier == "advanced": config["model"] = value
            elif key == "AI_MODEL_SMART" and self.tier == "smart": config["model"] = value
            elif key == "AI_MODEL_FAST" and self.tier == "fast": config["model"] = value
            elif key == "AI_MODEL": config["model"] = value # DB AI_MODEL always overrides if specific tier key didn't already
            elif key == "API_KEY": config["api_key"] = value
            elif key == "BASE_URL": config["base_url"] = value
        
        if not config["model"]:
            if self.tier == "advanced":
                config["model"] = "claude-3-5-sonnet-20240620"
            elif self.tier == "smart":
                config["model"] = "gemini-1.5-pro"
            else:
                config["model"] = "gemini-1.5-flash"

        # [Robustness] Clean quotes if any (處理雙引號殘留問題)
        if isinstance(config.get("model"), str):
            config["model"] = config["model"].strip().strip('"').strip("'")

        # Explicit Warning for Env usage if DB is missing critical keys
        if not db_settings.get("API_KEY") and config["api_key"]:
             pass # Suppress for now, or log warning as requested: "Data should exist in DB"
             # self.logger.warning("Using API_KEY from Environment. Recommendation: Move to DB settings.")

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
            pass
        finally:
            self.settings_repo.close_session()
        return settings

    def _load_prompt(self):
        """
        Load system prompt from workspace if available, else fallback to prompt_path file.
        從檔案或獨立大腦載入系統提示詞。
        """
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
                return prompt_content.strip()

        # Fallback to legacy path
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_path}")
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def render_system_prompt(self, context):
        """
        Render System Prompt using Jinja2 — delegates to ContextAssembler.
        使用 Jinja2 渲染系統提示詞 — 委派至 ContextAssembler。
        """
        return self._context_assembler.render(self.system_prompt, context)


    @abstractmethod
    def run(self, context):
        """
        Execute Agent Task.
        執行 Agent 任務。
        """
        pass

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count — delegates to WalProtocol."""
        return WalProtocol.estimate_tokens(text)

    def _check_context_window(self, messages: List[Dict[str, str]], reserve_floor: int = 4000, max_tokens: int = 32000) -> bool:
        """Check context window — delegates to WalProtocol."""
        return self._wal_protocol.check_context_window(messages, reserve_floor, max_tokens)

    def _perform_silent_flush(self, messages: List[Dict[str, str]]):
        """WAL Protocol flush — delegates to WalProtocol."""
        self._wal_protocol.perform_silent_flush(messages, self.call_llm)

    def run_tool_loop(self, context, max_turns=3, thought_chain=False):
        """
        ReAct-style loop — delegates to AgentLoop.
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

        return self._agent_loop.execute(
            messages=messages,
            call_llm_fn=self.call_llm,
            check_context_fn=lambda m: self._wal_protocol.check_context_window(m),
            flush_fn=lambda m: self._wal_protocol.perform_silent_flush(m, self.call_llm),
            max_turns=max_turns,
        )

    # --- Context Guard ---



    def call_swarm(self, agents: list, message: str, context: dict = None) -> dict:
        """
        Broadcasts a message to a swarm of agents effectively in parallel.
        向 Agent Swarm 廣播訊息。
        """
        results = {}
        for agent_name in agents:
            try:
                self.logger.info(f"Swarm Broadcast: {self.name} -> {agent_name}")
                response = self.call_agent(agent_name, message, context)
                results[agent_name] = response
            except Exception as e:
                self.logger.error(f"Swarm Broadcast Failed for {agent_name}: {e}")
                results[agent_name] = f"Error: {e}"
        return results

    def _parse_tool_call(self, text):
        """Parse tool calls — delegates to AgentLoop."""
        return AgentLoop.parse_tool_call(text)

    def call_agent(self, agent_name: str, message: str, context: dict = None):
        """
        Agent-to-Agent Communication (Agent Mesh).
        Sends a message/task to another agent.
        Agent 對 Agent 通訊 (Agent Mesh)。
        發送訊息/任務給另一個 Agent。
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
            response = target_agent.run(call_context)
            return response
        
        return f"Error: Agent {agent_name} not found."

    def rate_request(self, sender: str, score: int, comment: str, context_hash: str = None):
        """
        HR Protocol: Rate an incoming request from another agent.
        HR 協議：對來自其他 Agent 的請求進行評分。
        """
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
        """Render user context — delegates to ContextAssembler."""
        return ContextAssembler.render_user_context(context)

    # ================================================================
    # LLM Gateway Factory & Delegation (Model > Agent > Skill)
    # ================================================================

    def _create_default_gateway(self) -> ILLMGateway:
        """
        Create default LLM Gateway based on config.
        基於當前配置建立預設 LLM 閘道。
        """
        provider = self.config.get('provider', '')
        api_key = self.config.get('api_key', '')

        if not api_key:
            from src.infrastructure.llm.llm_gateway import MockLLMGateway
            return MockLLMGateway()

        try:
            from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, RetryLLMGateway
            inner = LLMGatewayFactory.create(provider)
            max_retries = self.config.get('max_retries', 3)
            return RetryLLMGateway(inner, max_retries=max_retries)
        except ValueError:
            self.logger.warning(f"Unsupported provider '{provider}', falling back to Mock.")
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
        Unified method to call LLM — delegates to ILLMGateway.
        統一的 LLM 調用方法 — 委派至 ILLMGateway。
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

    # Legacy aliases for backward compatibility (deprecated — will be removed)
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
        計算輸入資料的 SHA256 雜湊值。
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
        檢查輸入的 Context 是否與上次執行不同 (避免重複執行)。
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
        更新 agent_state 資料表，記錄新的雜湊值、時間與輸出。
        """
        try:
            db_id = f"{self.name}_{state_key}" if state_key else self.name
            self.state_repo.save_state(db_id, self.name, current_hash, output_content)
        except Exception as e:
            self.logger.error(f"Error updating agent state: {e}")
