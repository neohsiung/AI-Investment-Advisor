import os
import json
import requests
import hashlib
import re
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
import uuid
from datetime import datetime

class BaseAgent(ABC):

    def __init__(self, name, prompt_path, use_cache=True, ttl_hours=24, tier="smart", user_id=None, settings_repo=None, state_repo=None, feedback_repo=None, identity_file="IDENTITY.md", **kwargs):
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
        
        # Set up Tool Server
        self.toold = McpServer(name=f"{self.name}_Tools")
        
        # Bind implementations
        from src.agents.skills.registry import bind_skills_to_agent
        bind_skills_to_agent(self)
        
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
        Render System Prompt using Jinja2.
        使用 Jinja2 渲染系統提示詞。
        """
        try:
            # 1. Inject Time Context
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 2. Inject Tool Definitions (Prioritize Skills XML + MCP JSON)
            # Legacy MCP Tools
            mcp_tools_json = json.dumps(self.toold.list_tools(), indent=2)
            # New Skills XML
            skills_xml = self.skill_loader.get_skill_registry_xml()
            
            # 3. Inject Dynamic Memory (Contextual)
            # If context has 'query' or 'topic', try to fetch memory
            memory_context_str = ""
            # Ensure context is dict
            context_dict = context if isinstance(context, dict) else {}
            
            # Explicit Historical Context (from CouncilService)
            if "historical_context" in context_dict:
                 memory_context_str += f"\n[Historical Context]:\n{context_dict['historical_context']}\n"

            topic = context_dict.get("topic")
            if topic and not "historical_context" in context_dict: # Avoid Double Injection
                # Retrieve relevant memories
                # We need an embedding for the topic. 
                # For now, we will just use Keyword Search or rely on hybrid if we had an embedder here.
                # Since BaseAgent doesn't have an embedder yet, we skip vector part or pass dummy.
                # In full implementation, we'd call self.llm_provider.embed(topic).
                memories = self.memory.search(topic, query_vector=None, limit=3)
                if memories:
                    memory_context_str += "\n".join([f"- {m['content']} (Score: {m['score']:.2f})" for m in memories])

            context_with_tools = context_dict.copy()
            context_with_tools["tools"] = mcp_tools_json # Keep for backward compatibility in templates
            context_with_tools["skills_xml"] = skills_xml
            context_with_tools["current_time"] = current_time
            context_with_tools["memory_context"] = memory_context_str
            
            template = Template(self.system_prompt)
            return template.render(**context_with_tools)
        except Exception as e:
            self.logger.error(f"Error rendering system prompt: {e}")
            return self.system_prompt


    @abstractmethod
    def run(self, context):
        """
        Execute Agent Task.
        執行 Agent 任務。
        """
        pass

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count (approx. 4 chars per token).
        """
        return len(text) // 4

    def _check_context_window(self, messages: List[Dict[str, str]], reserve_floor: int = 4000, max_tokens: int = 32000) -> bool:
        """
        Check if the current context approaches the token limit.
        如果上下文超過安全線，提早觸發 Flush 訊號。
        """
        total_tokens = sum(self._estimate_tokens(msg.get("content", "")) for msg in messages)
        if total_tokens > (max_tokens - reserve_floor):
            self.logger.warning(f"Context Window approaching limit! Tokens: {total_tokens} (Reserve: {reserve_floor})")
            return True
        return False

    def _perform_silent_flush(self, messages: List[Dict[str, str]]):
        """
        WAL Protocol: Write state context out and truncate history to preserve trajectory.
        將當前思考軌跡壓縮，寫入狀態日誌，避免斷片。
        """
        self.logger.info(f"[{self.name}] Initiating Silent Pre-Compaction Flush & WAL")
        
        # 1. Ask LLM to summarize and generate a WAL checkpoint
        flush_prompt = (
            "SYSTEM SILENT COMMAND: The context window is almost full. "
            "Please summarize your current reasoning state, memory trajectory, and any pending tool calls. "
            "Output MUST be in markdown format prefixed with 'WAL_CHECKPOINT:' so I can restore this session."
        )
        temp_messages = messages + [{"role": "user", "content": flush_prompt}]
        
        try:
            # Simple sync call for the summary
            wal_state = self.call_llm(temp_messages, temperature=0.1)
            
            # 2. Write WAL to Workspace /STATE.md (Rule #1)
            if hasattr(self, 'workspace_path') and self.workspace_path:
                state_path = os.path.join(self.workspace_path, "STATE.md")
                # Redact any accidental secrets before writing to disk
                safe_wal_state = self._redact_secrets(wal_state)
                with open(state_path, "w", encoding="utf-8") as f:
                    f.write(f"# Session Checkpoint: {datetime.now().isoformat()}\n\n{safe_wal_state}")
            
            # 3. Truncate History: Keep System Prompt, latest WAL state, and drop the middle
            if len(messages) > 3:
                system_msg = messages[0]
                messages.clear()
                messages.append(system_msg)
                messages.append({"role": "user", "content": f"Session Restored from Checkpoint:\n\n{wal_state}\n\nPlease continue where you left off."})
                self.logger.info("Context truncated via WAL.")
        except Exception as e:
            self.logger.error(f"Silent flush failed: {e}")

    def run_tool_loop(self, context, max_turns=3, thought_chain=False):
        """
        Executes a ReAct-style loop where the agent can request generic tools via MCP.
        執行 ReAct 風格的迴圈，Agent 可以透過 MCP 請求使用通用工具。
        """
        # Inject Thought Chain context if enabled
        if thought_chain:
            context = context.copy() if isinstance(context, dict) else {}
            context["thought_chain_mode"] = True
            
        messages = [
            {"role": "system", "content": self.render_system_prompt(context)},
            {"role": "user", "content": self._render_user_context(context)}
        ]

        from src.services.search_service import InternetSearchService
        search_service = InternetSearchService(user_id=self.user_id)

        for turn in range(max_turns):
            # [Context Guard]
            if self._check_context_window(messages):
                self._perform_silent_flush(messages)

            response_text = self.call_llm(messages)
            
            # [NEW] Generic Tool Parsing (通用工具解析)
            tool_call = self._parse_tool_call(response_text)
            
            if tool_call:
                name, args = tool_call
                self.logger.info(f"Agent requested tool: {name} with {args}")
                messages.append({"role": "assistant", "content": response_text})
                
                try:
                    result = ""
                    if name == "SEARCH": # Legacy Handler (舊版處理器)
                         # Search usually returns list of dicts
                         q = args.get("query", str(args))
                         res_list = search_service.search_financial_context(q, max_results=3)
                         
                         if res_list:
                            for r in res_list:
                                result += f"- {r.get('title')}: {r.get('snippet')} ({r.get('link')})\n"
                         else:
                            result = "No results found."
                         
                    else:
                        # MCP Tool Call (MCP 工具調用)
                        if name in self.toold.tools:
                            raw_res = self.toold.call_tool(name, args)
                            result = json.dumps(raw_res, ensure_ascii=False)
                        else:
                            # Try binding mapping just in case text differs from mapped name
                            result = f"Error: Tool '{name}' not found."
                    
                    observation = f"System: [Tool '{name}' Output]\n{result}\n"
                
                except Exception as e:
                    self.logger.error(f"Tool execution failed: {e}")
                    observation = f"System: [Tool Error] {e}\n"
                
                messages.append({"role": "user", "content": observation})
                # Loop continues
            else:
                return response_text

        return response_text 

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
        """
        Heuristic parsing for tool calls.
        啟發式工具調用解析。
        Supported formats (支援格式):
        1. SEARCH: "query"
        2. CALL: tool_name({"arg": "val"})
        """
        for line in text.splitlines():
            if "SEARCH:" in line:
                # Legacy strict format often found in prompts
                parts = line.split("SEARCH:", 1)
                if len(parts) > 1:
                    query = parts[1].strip().strip('"').strip("'")
                    return ("SEARCH", {"query": query})
            
            if line.strip().startswith("CALL:"):
                # CALL: get_price({"ticker": "AAPL"})
                content = line.strip().replace("CALL:", "").strip()
                if "(" in content and content.endswith(")"):
                    name = content.split("(", 1)[0].strip()
                    args_str = content.split("(", 1)[1][:-1]
                    try:
                        args = json.loads(args_str)
                        return (name, args)
                    except json.JSONDecodeError:
                        return (name, {"arg": args_str})
        return None

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
        if isinstance(context, str):
            return context
        return json.dumps(context, indent=2, ensure_ascii=False)

    def call_llm(self, messages, temperature=0.7, response_format=None):
        """
        Unified method to call LLM.
        統一的 LLM 調用方法。
        """
        system_prompt = ""
        user_prompt = ""
        for m in messages:
            if m['role'] == 'system': system_prompt += m['content'] + "\n"
            elif m['role'] == 'user': user_prompt += m['content'] + "\n"
            elif m['role'] == 'assistant': user_prompt += f"\n[Previous Output]: {m['content']}\n"

        system_prompt = system_prompt.strip()
        user_prompt = user_prompt.strip()

        return self._mock_llm_call(user_prompt, system_prompt)

    def _mock_llm_call(self, prompt, system_prompt):
        import time
        max_retries = self.config.get('max_retries', 3)
        
        for attempt in range(max_retries):
            if self.config.get('api_key'):
                try:
                    return self._call_real_llm(prompt, system_prompt)
                except Exception as e:
                    self.logger.error(f"Error calling real LLM (Attempt {attempt+1}/{max_retries}): {e}")
                    time.sleep(2 ** (attempt + 1))
            else:
                break
        
        provider = self.config.get('provider')
        model = self.config.get('model')
        self.logger.info(f"Falling back to Mock LLM ({provider} - {model})...")

        simulated_response = f"""
### ⚠️ Simulation Mode (Missing API Key)

**Agent**: {self.name}

#### Analysis
- **Trend**: Neutral/Simulated.
- **Signal**: HOLD.
- **Reasoning**: System is running in simulation mode because valid API keys were not found.

#### Recommendations
- Validate your `.env` configuration.
- Add `API_KEY` for {provider}.

(Context received: {len(str(prompt))} chars)
"""
        return simulated_response.strip()

    def _call_real_llm(self, prompt, system_prompt):
        provider = self.config.get('provider')
        model = self.config.get('model')
        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url')

        prompt_snippet = prompt[:50].replace('\n', ' ') + "..."

        if self.cache:
            cached_response = self.cache.get(self.name, prompt)
            if cached_response:
                self.logger.info(f"Using Cached Response for {self.name}")
                return cached_response

        self.logger.info(f"Calling Real LLM ({provider} - {model}) | Prompt: {prompt_snippet}")

        if not api_key:
            raise ValueError("API Key not found in settings")

        if provider == "OpenRouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8501", 
                "X-Title": "AI Investment Advisor"
            }
            data = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            }
            try:
                response = requests.post(url, headers=headers, json=data, timeout=30)
                response.raise_for_status()
                return response.json()['choices'][0]['message']['content']
            except Exception as e:
                if 'response' in locals() and response is not None:
                    self.logger.error(f"OpenRouter Request failed: {e} | Body: {response.text}")
                else:
                    self.logger.error(f"OpenRouter Request failed: {e}")
                raise e

        elif provider == "Google Gemini":
            model_id = model if model.startswith("models/") else f"models/{model}"
            url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            data = {"contents": [{"parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}]}

            try:
                response = requests.post(url, headers=headers, json=data, timeout=30)
                response.raise_for_status()
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            except Exception as e:
                self.logger.error(f"Gemini Request failed: {e}")
                raise e

        elif provider == "OpenAI":
            url = base_url if base_url else "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            }
            try:
                response = requests.post(url, headers=headers, json=data, timeout=30)
                response.raise_for_status()
                return response.json()['choices'][0]['message']['content']
            except Exception as e:
                self.logger.error(f"OpenAI Request failed: {e}")
                raise e

        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _redact_secrets(self, text_value):
        """
        Best-effort redaction of common secret patterns (API keys, bearer tokens)
        before persisting content to disk or logging.
        """
        if not isinstance(text_value, str):
            return text_value

        redacted = text_value

        # Redact obvious bearer tokens (e.g., "Authorization: Bearer <token>" or "Bearer <token>")
        redacted = re.sub(
            r"(Authorization:\s*Bearer\s+)[^\s\"']+",
            r"\1[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            r"(Bearer\s+)[^\s\"']+",
            r"\1[REDACTED]",
            redacted,
            flags=re.IGNORECASE,
        )

        # Redact common api_key patterns in code / JSON / config-like text
        redacted = re.sub(
            r"([\"']?api_key[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
            r"\1[REDACTED]\2",
            redacted,
            flags=re.IGNORECASE,
        )
        redacted = re.sub(
            r"([\"']?API_KEY[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
            r"\1[REDACTED]\2",
            redacted,
            flags=re.IGNORECASE,
        )

        return redacted

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
