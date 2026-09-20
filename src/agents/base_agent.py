import os
import json
import asyncio
import logging
import requests
import hashlib
import re
import subprocess
import pathlib
from dataclasses import asdict
from src.utils.security import redact_secrets
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Generator, AsyncGenerator
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

    def __init__(self, name, prompt_path, use_cache=True, ttl_hours=24, tier="fast", user_id=None, settings_repo=None, state_repo=None, feedback_repo=None, identity_file="IDENTITY.md", llm_gateway: Optional[ILLMGateway] = None, persona: Optional[AgentPersona] = None, **kwargs):
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
        # [NEW] OpenClaw Components
        self.memory = None # DIP: Don't instantiate HybridMemory directly
        
        # Rule #8: Cognitive Memory Tiering
        from src.services.cognitive_memory_manager import CognitiveMemoryManager
        self.cognitive_memory = CognitiveMemoryManager(user_id=self.user_id)
        
        self.skill_loader = SkillLoader()
        
        # [NEW] Agentic Brain (Workspace)
        # Workspace directory comes from the agent's manifest
        # (config/agents/<id>.md, `workspace:` key). This was a hardcoded dict of
        # ten entries here, which is why adding an agent meant editing BaseAgent
        # as well as the factory and KNOWN_AGENT_NAMES.
        #
        # The slug fallback is retained: two of the ten mapped entries
        # ("Evaluator Judge", "Sensory Watchdog") have no manifest because no
        # factory branch ever constructed them, and several agents legitimately
        # want the slugged default.
        #
        # workspace 目錄改由 manifest 的 `workspace:` 提供。原本是此處硬編的十項
        # 對照表，這也是為何新增代理必須同時改 BaseAgent、factory 與 KNOWN_AGENT_NAMES。
        # 保留 slug 後備：其中兩項從未被 factory 建構過，故沒有對應 manifest。
        mapped_name = None
        try:
            from src.agents.registry import get_manifest

            manifest = get_manifest(self.name)
            if manifest and manifest.workspace:
                mapped_name = manifest.workspace
        except Exception as exc:  # registry unavailable — fall back to the slug
            logger.debug(f"workspace lookup via registry failed for {self.name}: {exc}")

        if not mapped_name:
            mapped_name = self.name.lower().replace(" ", "-")
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
        
        # [Task 1.1] Register run_script as a built-in generic tool
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """
        Register this agent's tools from `config/tools.yaml`.

        This used to hardcode `run_script` — a subprocess-spawning tool every
        agent got unconditionally, with no way to withhold it. The manifest also
        finally wires up `LlamaIndexTools`, whose `register()` had no callers at
        all, so its four RAG tools were reachable from no agent while the HTTP
        endpoint reimplemented the same four inline.
        原本硬編 run_script（會啟動子行程、所有 agent 無條件取得且無法收回）。
        manifest 同時接上 LlamaIndexTools——它的 register() 從未被呼叫，
        四個 RAG 工具沒有任何 agent 用得到，而 HTTP 端點另外重做了一遍。
        """
        from src.tools.tool_manifest import register_builtin_tools

        names = register_builtin_tools(self)
        self.logger.info(
            f"{self.name}: registered {len(names)} tool(s) from manifest: "
            f"{', '.join(names) or 'none'}"
        )

    async def bind_external_mcp_tools(self, settings_service=None) -> int:
        """
        Bind tools from external MCP servers declared in `config/tools.yaml`.

        This lived inside `conversation_agent`, which meant external MCP tools
        reached exactly one of the agents. It is on the base class so any agent
        can have them, and it is gated twice — the settings flag and the
        manifest's per-server `enabled` must both be true — so a server left in
        the manifest cannot quietly resume making outbound calls.

        Returns the number of tools bound. Never raises: an unreachable remote
        server must not stop an agent from running with its local tools.
        原本寫在 conversation_agent 內，外部 MCP 工具只有一個 agent 拿得到。
        移到基底類別，並以「設定開關」與「manifest 個別 enabled」雙重閘門控制。
        回傳綁定的工具數；不拋出例外——遠端無法連線不該讓 agent 失去本地工具。
        """
        import functools

        from src.tools.tool_manifest import (
            enabled_external_servers,
            external_mcp_config,
        )
        from src.tools.mcp_server import McpTool

        cfg = external_mcp_config()
        servers = enabled_external_servers()
        if not servers:
            return 0

        gate = cfg["enabled_setting"]
        if settings_service is not None and gate:
            try:
                raw = settings_service.get_setting(gate, False)
                allowed = raw is True or (isinstance(raw, str) and raw.strip().lower() == "true")
            except Exception as exc:
                # Fail closed: if the gate cannot be read, do not reach outward.
                # 讀不到開關就不對外連線（fail closed）。
                self.logger.error(f"{self.name}: cannot read '{gate}', skipping external MCP: {exc}")
                return 0
            if not allowed:
                self.logger.info(f"{self.name}: external MCP disabled by '{gate}'")
                return 0

        prefix = cfg["namespace_prefix"]
        bound = 0
        for server in servers:
            url = server["url"]
            try:
                from src.tools.mcp_client_adapter import get_mcp_client

                client = await get_mcp_client(url, self.user_id)
                for tool in client.list_tools():
                    # Namespaced so a remote server cannot shadow a local tool.
                    # 加前綴命名空間，避免遠端工具覆蓋本地同名工具。
                    self.register_tool(McpTool(
                        name=f"{prefix}{tool.name}",
                        description=f"[External] {tool.description}",
                        func=functools.partial(client.call_tool, tool.name),
                    ))
                    bound += 1
                self.logger.info(f"{self.name}: bound {bound} tool(s) from {url}")
            except Exception as exc:
                self.logger.warning(f"{self.name}: failed to bind external MCP {url}: {exc}")
        return bound

    async def run_script(self, skill_name: str, args: List[str] = None) -> str:
        """
        Execute a local python script (cli.py) from a skill directory.
        安全限制：只能執行 .agent/skills/ 或 src/agents/skills/ 下的 cli.py
        """
        if args is None:
            args = []
            
        # [Security] Path validation
        # Only allow alphanumeric and underscore for skill_name to prevent path traversal
        if not re.match(r"^[a-zA-Z0-9_\-]+$", skill_name):
            return "Error: Invalid skill_name format."

        # Search exclusively in src/agents/skills/ for business logic
        potential_paths = [
            pathlib.Path(f"src/agents/skills/{skill_name}/cli.py"),
            pathlib.Path(f"src/agents/skills/{skill_name}/main.py")
        ]
        
        script_path = None
        for p in potential_paths:
            if p.exists():
                script_path = p
                break
        
        if not script_path:
            return f"Error: Skill '{skill_name}' not found in runtime registry. Access to .agent/ is restricted."

        try:
            # Execute the script
            # Note: We use the current venv's python if possible or just "python"
            cmd = ["python", str(script_path)] + args
            self.logger.info(f"Executing: {' '.join(cmd)}")
            
            # Use run with timeout for safety
            result = subprocess.run( # nosec B603
                cmd,
                capture_output=True,
                text=True,
                timeout=30 # 30 seconds limit
            )
            
            if result.returncode != 0:
                return f"Error (Code {result.returncode}):\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            
            return result.stdout
        except subprocess.TimeoutExpired:
            return "Error: Script execution timed out."
        except Exception as e:
            return f"Error executing script: {str(e)}"
    def register_tool(self, tool: McpTool):
        """
        Register a tool for the agent to use.
        註冊一個工具供 Agent 使用
        """
        self.toold.register_tool(tool)

    def _load_config(self):
        """
        Read AI configuration strictly from llm_tier_bindings.
        讀取 AI 設定 (嚴格使用 llm_tier_bindings，確保模型名稱由 UI 管理)
        """
        try:
            # 1. Initialize dependencies for Router
            settings = SettingsService(user_id=self.user_id, settings_repo=self.settings_repo)
            token_logger = TokenLoggerService()
            router = BudgetAwareModelRouter(settings, token_logger)

            # 2. Try get_config_chain() → reads llm_tier_bindings table
            if not self.user_id:
                raise ValueError(f"Agent {self.name} initialized without user_id. DB config resolution impossible.")

            candidates = router.get_config_chain(
                user_id=self.user_id,
                tier=self.tier,
                agent_name=self.name,
            )
            
            if not candidates:
                 raise ValueError(
                    f"No model candidates configured in DB for user {self.user_id} and tier {self.tier}. "
                    "Please configure Tier Bindings in the AI Engine Management UI."
                )

            # Use the primary candidate (first in chain) to build config dict
            primary = candidates[0]
            # Resolve API key: candidate must carry it (from DB), no env fallbacks allowed in logic
            api_key = primary.api_key or ""
            
            config = {
                "provider": primary.provider_code,
                "model": primary.model_code,
                "api_key": api_key,
                "base_url": primary.base_url or "",
                "temperature": 0.7,
                "max_tokens": 8192,
                "timeout_seconds": int(primary.timeout_seconds),
                "max_retries": primary.max_retries,
                "_candidates": candidates,
            }
            
            self.logger.debug(
                f"[_load_config] Using llm_tier_bindings: "
                f"tier={self.tier} model={primary.model_code} "
                f"provider={primary.provider_code}"
            )
            return config

        except Exception as e:
            self.logger.error(f"[_load_config] Configuration failed: {e}")
            raise

    def _load_prompt(self):
        """
        Resolve this agent's system prompt.

        Order, highest priority first:

          1. `user_custom_prompts` row for (user_id, agent name) — the operator's
             own edit, or output from the RLHF meta-prompt agent. USER STATE, so
             it lives in the database, consistent with every other setting.
          2. The Markdown body of config/agents/<id>.md — the SHIPPED DEFAULT for
             this agent. Product definition, so it lives in a file and ships with
             the release.
          3. `workspace/<dir>/IDENTITY.md` + `SOUL.md` — the pre-existing
             per-agent prompt files, still authoritative for the agents that use
             them.
          4. The legacy `prompts/*.txt` path in `self.prompt_path`.

        Note on 1 vs 2: the plan for this milestone had the manifest body winning
        over the database. Inverted deliberately — a shipped default must not
        silently override an edit the operator made through the UI, and prompts a
        person changed are user state like any other setting.

        A persona prefix (config/personas/*.md) is prepended to whichever source
        wins, not just to the workspace one as before.

        解析順序：DB 的 user_custom_prompts（使用者狀態）> manifest 本文（出貨預設）
        > workspace 的 IDENTITY/SOUL > 舊的 prompts/*.txt。
        原計畫讓 manifest 優先於 DB，此處刻意反轉：出貨預設值不應覆寫使用者透過 UI
        做的修改，而使用者修改過的提示詞與其他設定一樣屬於使用者狀態。
        """
        # ── 1. database override ────────────────────────────────────────
        custom = self._load_prompt_override()
        if custom:
            self.logger.info(
                f"Using stored prompt override for agent '{self.name}' "
                f"(user {self.user_id})"
            )
            return self._with_persona(custom)

        # ── 2. manifest body (shipped default) ──────────────────────────
        try:
            from src.agents.registry import get_manifest

            manifest = get_manifest(self.name)
            if manifest and manifest.prompt.strip():
                return self._with_persona(manifest.prompt.strip())
        except Exception as exc:
            self.logger.debug(f"manifest prompt lookup skipped: {exc}")

        # ── 3. workspace IDENTITY.md + SOUL.md ──────────────────────────
        prompt_content = ""
        if getattr(self, "workspace_path", None) and os.path.exists(self.workspace_path):
            for filename in (self.identity_file, "SOUL.md"):
                candidate = os.path.join(self.workspace_path, filename)
                if os.path.exists(candidate):
                    with open(candidate, "r", encoding="utf-8") as fh:
                        prompt_content += fh.read() + "\n\n"

            if prompt_content.strip():
                return self._with_persona(prompt_content.strip())

        # ── 4. legacy prompts/*.txt ─────────────────────────────────────
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_path}")
        with open(self.prompt_path, "r", encoding="utf-8") as fh:
            return self._with_persona(fh.read())

    def _load_prompt_override(self):
        """
        The stored prompt override for this (user, agent), or None.

        Also fixes a session leak: the previous inline version called
        `session.close()` only on the path where NO override was found, so every
        agent construction that DID find one leaked a database session.
        同時修掉一個 session 洩漏：原本只在「找不到覆寫」的路徑呼叫 close()，
        因此每次成功取得覆寫的代理建構都會洩漏一個資料庫 session。
        """
        session = None
        try:
            from sqlalchemy.exc import OperationalError, ProgrammingError
            from sqlalchemy.orm import sessionmaker

            from src.data.database import get_db_engine
            from src.data.models import UserCustomPrompt

            Session = sessionmaker(bind=get_db_engine())
            session = Session()
            row = session.query(UserCustomPrompt).filter_by(
                user_id=self.user_id,
                agent_name=self.name,
            ).first()
            return row.custom_prompt if row and row.custom_prompt else None
        except Exception as exc:
            # Pre-migration schema, or no database at all — the file-based
            # sources below are a complete fallback.
            self.logger.debug(
                f"prompt override lookup skipped: {type(exc).__name__}: {str(exc)[:100]}"
            )
            return None
        finally:
            if session is not None:
                session.close()

    def _with_persona(self, prompt: str) -> str:
        """
        Prepend the persona prefix, if this agent has a persona.

        Previously applied only to the workspace branch, so an agent whose prompt
        came from the database or a legacy file silently lost its persona.
        原本只套用在 workspace 分支：提示詞來自資料庫或舊檔案的代理會靜默失去人格設定。
        """
        if self.persona and getattr(self.persona, "system_prompt_prefix", None):
            return f"{self.persona.render_prefix()}\n\n{prompt.strip()}"
        return prompt.strip()

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

    async def _perform_silent_flush(self, messages: List[Dict[str, str]]):
        """WAL Protocol flush - delegates to WalProtocol."""
        await self._wal_protocol.perform_silent_flush(messages, self.call_llm)

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
                loop.create_task(self._extract_and_save_takeaways(response))
            except RuntimeError:
                # Fallback if no event loop running
                asyncio.run(self._extract_and_save_takeaways(response))

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
        """
        HR Protocol: Rate an incoming request from another agent.
        HR 協議：對來自其他 Agent 的請求進行評分
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
        """Render user context - delegates to ContextAssembler."""
        return ContextAssembler.render_user_context(context)

    async def _extract_and_save_takeaways(self, agent_response: str) -> None:
        """
        [Phase 9] Extracts key takeaways from the agent's response and saves them to the Knowledge Vault.
        Uses a fast LLM model to distill the context.
        """
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
            
            result = await extractor.call_llm([{"role": "user", "content": prompt}], temperature=0.1)
            
            if result and "NONE" not in result.upper() and len(result.strip()) > 10:
                self.logger.info(f"Saving extracted takeaways to Knowledge Vault for {self.name}")
            if result and "NONE" not in result.upper() and len(result.strip()) > 10:
                self.logger.info(f"Saving extracted takeaways to Knowledge Vault for {self.name}")
                from src.services.cognitive_memory_manager import CognitiveMemoryManager
                memory_mgr = CognitiveMemoryManager(user_id=self.user_id)
                await memory_mgr.add_memory(
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
        model_raw = self.config.get('model') or ''
        model = model_raw.strip('"').strip("'") if isinstance(model_raw, str) else ''
        return LLMConfig(
            provider=self.config.get('provider') or '',
            model=model,
            api_key=self.config.get('api_key') or '',
            base_url=self.config.get('base_url') or '',
            temperature=temperature,
            max_retries=self.config.get('max_retries', 3),
            timeout_seconds=30,
        )

    async def call_llm(self, messages, temperature=0.7, response_format=None):
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

        self.logger.info(f"Calling LLM via Gateway for {self.name}")

        # Delegate to ILLMGateway
        config = self._build_llm_config(temperature=temperature)
        gateway_messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]
        return await self._llm_gateway.chat(gateway_messages, config)

    async def stream_llm(self, messages, temperature=0.7) -> AsyncGenerator[str, None]:
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
        async for chunk in self._llm_gateway.stream_chat(gateway_messages, config):
            yield chunk

    # Legacy aliases for backward compatibility (deprecated - will be removed)
    async def _mock_llm_call(self, prompt, system_prompt):
        """Legacy bridge: delegates to call_llm via gateway."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return await self.call_llm(messages)

    async def _call_real_llm(self, prompt, system_prompt):
        """Legacy bridge: delegates to call_llm via gateway."""
        return await self._mock_llm_call(prompt, system_prompt)

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
