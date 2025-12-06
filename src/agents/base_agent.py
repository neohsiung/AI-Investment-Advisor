import os
import json
import requests
from abc import ABC, abstractmethod
from sqlalchemy import text
from src.database import get_db_connection
from src.utils.logger import setup_logger
from src.utils.cache import ResponseCache

class BaseAgent(ABC):
    def __init__(self, name, prompt_path, use_cache=True, ttl_hours=24):
        self.name = name
        self.logger = setup_logger(name)
        self.prompt_path = prompt_path
        self.system_prompt = self._load_prompt()
        self.config = self._load_config()
        self.cache = ResponseCache(ttl_hours=ttl_hours) if use_cache else None

    def _load_config(self):
        """從資料庫讀取 AI 設定"""
        config = {
            "provider": "Google Gemini",
            "model": "gemini-1.5-pro",
            "api_key": "",
            "base_url": ""
        }
        
        db_settings = self._load_config_from_db()
        for key, value in db_settings.items():
            if key == "AI_PROVIDER": config["provider"] = value
            elif key == "AI_MODEL": config["model"] = value
            elif key == "API_KEY": config["api_key"] = value
            elif key == "BASE_URL": config["base_url"] = value
            
        return config

    def _load_config_from_db(self):
        """從資料庫載入 API 設定"""
        settings = {}
        try:
            conn = get_db_connection()
            # Replace cursor with direct execution
            rows = conn.execute(text("SELECT key, value FROM settings")).fetchall()
            
            # Attempt to access by _mapping first, then by index for compatibility
            if rows:
                try:
                    settings = {row._mapping['key']: row._mapping['value'] for row in rows}
                except AttributeError: # Fallback for older SQLAlchemy versions or different row objects
                    settings = {row[0]: row[1] for row in rows}
            
            conn.close()
        except Exception as e:
            # Logger 可能還沒初始化，這裡用 print 或延後 log
            print(f"[{self.name}] Warning: Failed to load settings from DB: {e}")
        return settings

    def _load_prompt(self):
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_path}")
        with open(self.prompt_path, 'r', encoding='utf-8') as f:
            return f.read()

    @abstractmethod
    def run(self, context):
        """
        執行 Agent 任務
        context: dict, 包含 Agent 所需的輸入數據
        return: dict or str, Agent 的輸出
        """
        pass

    def _mock_llm_call(self, prompt, system_prompt):
        """
        模擬 LLM 調用 (Phase 3 初期使用 Mock)
        實際專案應整合 Gemini API 或其他 LLM Client
        """
        # 嘗試使用真實 API
        if self.config.get('api_key'):
            try:
                return self._call_real_llm(prompt, system_prompt)
            except Exception as e:
                self.logger.error(f"Error calling real LLM: {e}. Falling back to mock.")
        
        provider = self.config.get('provider')
        model = self.config.get('model')
        self.logger.info(f"Calling Mock LLM ({provider} - {model})...")
        
        return f"Mock response from {self.name} using {model}. Context received: {len(str(prompt))} chars."

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
                response = requests.post(url, headers=headers, json=data)
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
                response = requests.post(url, headers=headers, json=data)
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
                response = requests.post(url, headers=headers, json=data)
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
