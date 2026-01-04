import os
import json
import requests
from abc import ABC, abstractmethod
from sqlalchemy import text
from jinja2 import Template
# from src.data.database import get_db_connection # Removed for DIP
from src.utils.logger import setup_logger
from src.utils.cache import ResponseCache
from src.repositories.settings_repository import SqliteSettingsRepository
from src.repositories.agent_state_repository import SqliteAgentStateRepository

class BaseAgent(ABC):

    def __init__(self, name, prompt_path, use_cache=True, ttl_hours=24, tier="smart", user_id="system", settings_repo=None, state_repo=None, **kwargs):
        self.name = name
        self.logger = setup_logger(name)
        self.prompt_path = prompt_path
        self.tier = tier
        self.user_id = user_id
        
        # Dependency Injection withDefaults
        self.settings_repo = settings_repo or SqliteSettingsRepository()
        self.state_repo = state_repo or SqliteAgentStateRepository()
        
        self.system_prompt = self._load_prompt()
        self.config = self._load_config()
        self.cache = ResponseCache(ttl_hours=ttl_hours) if use_cache else None
        
        # Initialize Search Service (lazy load or instance?)
        # BaseAgent shouldn't depend heavily on service layer, but for tool loop we need it.
        # We can import inside the method to avoid circular imports.

    def _load_config(self):
        """
        讀取 AI 設定 (優先順序: DB > Env > Default)
        Read AI configuration (Priority: DB > Env > Default).
        
        Support Model Tiering:
        - AI_MODEL_SMART (e.g. gemini-1.5-pro)
        - AI_MODEL_FAST (e.g. gemini-1.5-flash)
        - AI_MODEL (Legacy fallback)
        """
        
        # Determine target model env var based on tier
        if self.tier == "fast":
            default_model = os.getenv("AI_MODEL_FAST", os.getenv("AI_MODEL", "gemini-1.5-flash"))
        else:
            default_model = os.getenv("AI_MODEL_SMART", os.getenv("AI_MODEL", "gemini-1.5-pro"))

        config = {
            "provider": os.getenv("AI_PROVIDER", "Google Gemini"),
            "model": default_model,
            "api_key": os.getenv("API_KEY", ""),
            "base_url": os.getenv("BASE_URL", "")
        }

        db_settings = self._load_config_from_db()
        for key, value in db_settings.items():
            if key == "AI_PROVIDER": config["provider"] = value
            # Override model if specific tier setting exists in DB
            elif key == "AI_MODEL_SMART" and self.tier == "smart": config["model"] = value
            elif key == "AI_MODEL_FAST" and self.tier == "fast": config["model"] = value
            elif key == "AI_MODEL" and "model" not in config: config["model"] = value # Only fallback if not set by tier
            elif key == "API_KEY": config["api_key"] = value
            elif key == "BASE_URL": config["base_url"] = value
        
        # If DB overrode base AI_MODEL but we want tier specific, logic above might be slightly loose.
        # But generally, if AI_MODEL_SMART is in DB, it wins. 
        
        # Final check if model is still empty (shouldn't happen with defaults)
        if not config["model"]:
            config["model"] = "gemini-1.5-pro" if self.tier == "smart" else "gemini-1.5-flash"

        return config

    def _load_config_from_db(self):
        """從資料庫載入 API 設定 (Via Repository)"""
        settings = {}
        try:
            # Load Global
            global_rows = self.settings_repo.get_global()
            for row in global_rows:
                 # Row might be tuple or mapping
                 key = row._mapping['key'] if hasattr(row, '_mapping') else row[0]
                 val = row._mapping['value'] if hasattr(row, '_mapping') else row[1]
                 settings[key] = val
            
            # Load User Specific (Override)
            if self.user_id:
                user_rows = self.settings_repo.get_all(self.user_id)
                for row in user_rows:
                     key = row._mapping['key'] if hasattr(row, '_mapping') else row[0]
                     val = row._mapping['value'] if hasattr(row, '_mapping') else row[1]
                     settings[key] = val

        except Exception as e:
            print(f"[{self.name}] Warning: Failed to load settings from DB: {e}")
        return settings

    def _load_prompt(self):
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_path}")
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    def render_system_prompt(self, context):
        """
        使用 Jinja2 渲染 System Prompt
        Render System Prompt using Jinja2.
        """
        try:
            template = Template(self.system_prompt)
            return template.render(**context)
        except Exception as e:
            self.logger.error(f"Error rendering system prompt: {e}")
            return self.system_prompt


    @abstractmethod
    def run(self, context):
        """
        執行 Agent 任務
        Execute Agent Task.
        
        context: dict, 包含 Agent 所需的輸入數據 (Context data required by Agent)
        return: dict or str, Agent 的輸出 (Agent's output)
        """
        pass

    def run_tool_loop(self, context, max_turns=3):
        """
        Executes a ReAct-style loop where the agent can request tools.
        執行 ReAct 風格的迴圈，Agent 可以請求使用工具。
        
        Supported Tools (支援工具):
        - SEARCH: "query" -> uses InternetSearchService (使用網路搜索服務)
        """
        messages = [
            {"role": "system", "content": self.render_system_prompt(context)},
            {"role": "user", "content": self._render_user_context(context)}
        ]

        from src.services.search_service import InternetSearchService
        search_service = InternetSearchService()

        for turn in range(max_turns):
            # 1. Call LLM
            response_text = self.call_llm(messages)
            
            # 2. Check for Tool Command
            if "SEARCH:" in response_text:
                # Extract query
                # Assumption: Format is strict `SEARCH: "query"` or `SEARCH: query`
                # Let's handle simple parsing
                lines = response_text.split('\n')
                search_query = None
                for line in lines:
                    if "SEARCH:" in line:
                        parts = line.split("SEARCH:", 1)
                        if len(parts) > 1:
                            search_query = parts[1].strip().strip('"').strip("'")
                            break
                
                if search_query:
                    self.logger.info(f"Agent requested search: {search_query}")
                    messages.append({"role": "assistant", "content": response_text})
                    
                    # Execute Search
                    # 執行搜索
                    results = search_service.search_financial_context(search_query, max_results=3)
                    
                    # Format Observation
                    # 格式化觀察結果回傳給 Agent
                    observation = f"System: [Search Results for '{search_query}']\n"
                    if results:
                        for r in results:
                            observation += f"- {r.get('title')}: {r.get('snippet')} ({r.get('link')})\n"
                    else:
                        observation += "No relevant results found.\n"
                    
                    messages.append({"role": "user", "content": observation})
                    continue # Loop again with observation
            
            # If no tool used, or after tool use we want final answer? 
            # Actually ReAct usually outputs Thought -> Action -> Observation -> Thought -> Final Answer.
            # If response didn't have SEARCH, we assume it's the final answer.
            return response_text

        return response_text # Return last response if max turns reached

    def _render_user_context(self, context):
        """
        Default user context renderer. 
        Can be overridden or we just dump the context as JSON/String.
        Most agents currently construct user prompt inside run() or use Jinja.
        To support standard run_tool_loop, we need a standard way to get initial user prompt.
        For now, let's assume 'context' is passed directly if it's a string, or dumped.
        """
        # Hack for legacy compatibility: many agents construct prompt in run() then call call_llm
        # We need them to pass the INITIAL user content.
        # But wait, run() usually constructs specific prompts.
        # So we expect run() to call run_tool_loop with prepared messages?
        # Let's adjust run_tool_loop signature or usage.
        # Better: run_tool_loop receives constructed initial_user_prompt.
        if isinstance(context, str):
            return context
        return json.dumps(context, indent=2, ensure_ascii=False)

    def call_llm(self, messages, temperature=0.7, response_format=None):
        """
        Unified method to call LLM with messages list.
        messages: list of dicts [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
        """
        # Extract System Prompt and User Prompt from messages for legacy support
        system_prompt = ""
        user_prompt = ""
        for m in messages:
            if m['role'] == 'system':
                system_prompt += m['content'] + "\n"
            elif m['role'] == 'user':
                user_prompt += m['content'] + "\n"
        
        system_prompt = system_prompt.strip()
        user_prompt = user_prompt.strip()

        # Call logic
        return self._mock_llm_call(user_prompt, system_prompt)

    def _mock_llm_call(self, prompt, system_prompt):
        """
        模擬 LLM 調用 (Phase 3 初期使用 Mock)
        實際專案應整合 Gemini API 或其他 LLM Client
        """
        # Retry Logic
        # 重試邏輯
        import time
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            # 嘗試使用真實 API
            if self.config.get('api_key'):
                try:
                    return self._call_real_llm(prompt, system_prompt)
                except Exception as e:
                    last_error = e
                    self.logger.error(f"Error calling real LLM (Attempt {attempt+1}/{max_retries}): {e}")
                    # Simple exponential backoff: 2s, 4s, 8s
                    # 簡單的指數退避：2秒、4秒、8秒
                    time.sleep(2 ** (attempt + 1))
            else:
                break # No API Key, fallback immediately
        
        provider = self.config.get('provider')
        model = self.config.get('model')
        self.logger.info(f"Falling back to Mock LLM ({provider} - {model})...")

        return f"Mock response from {self.name} due to error: {last_error}. Context received: {len(str(prompt))} chars."

    def _call_real_llm(self, prompt, system_prompt):
        """
        呼叫真實 LLM API
        """
        import requests
        import json

        provider = self.config.get('provider')
        model = self.config.get('model')
        api_key = self.config.get('api_key')
        base_url = self.config.get('base_url')

        # Log with more context (first 50 chars of prompt)
        prompt_snippet = prompt[:50].replace('\n', ' ') + "..."

        # Check Cache
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
                "HTTP-Referer": "http://localhost:8501", # Optional
                "X-Title": "AI Investment Advisor" # Optional
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

                try:
                    return response.json()['choices'][0]['message']['content']
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to decode JSON response from OpenRouter. Status: {response.status_code}")
                    self.logger.error(f"Response content (first 1000 chars): {response.text[:1000]}")
                    raise e
            except requests.exceptions.RequestException as e:
                 self.logger.error(f"Request failed: {e}")
                 if hasattr(e.response, 'text'):
                     self.logger.error(f"Error response content: {e.response.text[:1000]}")
                 raise e

        elif provider == "Google Gemini":
            # 使用 Google Generative AI REST API
            # https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}

            # 若 model 名稱不包含 'models/', 嘗試自動補全
            model_id = model if model.startswith("models/") else f"models/{model}"

            url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{
                    "parts": [{"text": f"{system_prompt}\n\n{prompt}"}]
                }]
            }

            try:
                response = requests.post(url, headers=headers, json=data, timeout=30)
                response.raise_for_status()
                try:
                    return response.json()['candidates'][0]['content']['parts'][0]['text']
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to decode JSON response from Gemini. Status: {response.status_code}")
                    self.logger.error(f"Response content (first 1000 chars): {response.text[:1000]}")
                    raise e
            except requests.exceptions.RequestException as e:
                 self.logger.error(f"Request failed: {e}")
                 if hasattr(e.response, 'text'):
                     self.logger.error(f"Error response content: {e.response.text[:1000]}")
                 raise e

        elif provider == "OpenAI":
             # OpenAI 格式
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
                try:
                    return response.json()['choices'][0]['message']['content']
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to decode JSON response from OpenAI. Status: {response.status_code}")
                    self.logger.error(f"Response content (first 1000 chars): {response.text[:1000]}")
                    raise e
            except requests.exceptions.RequestException as e:
                 self.logger.error(f"Request failed: {e}")
                 if hasattr(e.response, 'text'):
                     self.logger.error(f"Error response content: {e.response.text[:1000]}")
                 raise e

        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _compute_hash(self, data):
        """Compute SHA256 hash of the input data (dict or str)"""
        import hashlib
        try:
            if isinstance(data, dict):
                # Sort keys for consistent hashing
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
