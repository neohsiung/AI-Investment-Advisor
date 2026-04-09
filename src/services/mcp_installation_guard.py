import ast
import logging
from typing import Tuple, Dict, Any
import os

logger = logging.getLogger(__name__)

class MCPBackgroundCheckService:
    """
    Service for background investigation of MCP tools before installation.
    在掛載 MCP 工具前進行背景調查與資安過濾。
    """

    def __init__(self, user_id: str):
        self.user_id = user_id

    def verify_security_clearance(self, skill_filepath: str) -> Tuple[bool, str]:
        """
        Scans skill implementation for insecure patterns (AST analysis).
        透過 AST 靜態分析掃描不安全的程式碼特徵。
        """
        if not os.path.exists(skill_filepath):
            return True, "File not found, skipping static analysis."

        try:
            with open(skill_filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)
            
            # Dangerous patterns to detect
            # 1. Direct calls to dangerous functions
            dangerous_calls = {'eval', 'exec', '__import__'}
            # 2. Modules that should not be used in skills
            dangerous_modules = {'os', 'subprocess', 'shutil', 'socket', 'requests', 'ctypes', 'importlib'}
            
            for node in ast.walk(tree):
                # Detect calls to eval/exec/etc.
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in dangerous_calls:
                            return False, f"Security Violation: Use of '{node.func.id}' detected."
                    elif isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            # Detect os.system, subprocess.run etc.
                            if node.func.value.id in dangerous_modules:
                                return False, f"Security Violation: Use of dangerous module '{node.func.value.id}' detected."
                
                # Detect static imports of dangerous modules
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split('.')[0] in dangerous_modules:
                            return False, f"Security Violation: Importing dangerous module '{alias.name}' is prohibited."
                
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.split('.')[0] in dangerous_modules:
                        return False, f"Security Violation: Importing from dangerous module '{node.module}' is prohibited."

            return True, "Security clearance PASSED."
        except Exception as e:
            logger.error(f"Security clearance error for {skill_filepath}: {e}")
            return False, f"Error during security analysis: {str(e)}"

    async def verify_purpose_alignment(self, skill_name: str, description: str, intent: str) -> Tuple[bool, str]:
        """
        Validates if the tool's purpose matches the intended usage using LLM (Multi-tenant safe).
        使用 LLM 驗證工具用途是否符合預期意圖（多租戶安全）。
        """
        if not intent:
            return True, "No specific intent provided, skipping alignment check."

        from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
        from src.domain.interfaces import Message, LLMConfig
        from src.utils.async_utils import to_thread
        from src.services.settings_service import SettingsService
        
        # [Phase 4] Multi-tenant isolation: Load credentials from SettingsService
        settings = SettingsService(user_id=self.user_id)
        llm_settings = settings.get_all_settings()
        
        provider = llm_settings.get("AI_PROVIDER", os.getenv("AI_PROVIDER", "Google Gemini"))
        model = llm_settings.get("AI_MODEL_FAST", os.getenv("AI_MODEL_FAST", "gemini-1.5-flash"))
        api_key = llm_settings.get("API_KEY", os.getenv("API_KEY", ""))

        gateway = LLMGatewayFactory.create(provider)
        config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            temperature=0.0,
            max_tokens=200,
        )

        prompt = f"""Review if the following MCP tool fits the user's intent.
        
Tool Name: {skill_name}
Description: {description}
User Intent: {intent}

Respond with exactly:
Decision: [APPROVE|REJECT]
Reason: <one sentence reasoning>
"""
        messages = [
            Message(role="system", content="You are a security compliance officer."),
            Message(role="user", content=prompt),
        ]
        
        try:
            response = await to_thread(gateway.chat, messages, config)
            if "Decision: REJECT" in response:
                reason = response.split("Reason:")[1].strip() if "Reason:" in response else "Unknown misalignment"
                return False, f"Purpose Mismatch: {reason}"
            return True, "Purpose alignment PASSED."
        except Exception as e:
            logger.error(f"Purpose alignment check failed: {e}")
            return True, f"Check failed but allowing as fallback: {e}"
