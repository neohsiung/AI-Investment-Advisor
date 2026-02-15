from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.engineer import SystemEngineerAgent
from src.agents.engineer import SystemEngineerAgent
from src.agents.sentiment import SentimentAgent
from src.agents.risk import RiskAgent
import os
import logging
import traceback

# [NEW] Imports for DI
# [NEW] 依賴注入引入
from src.repositories.feedback_repository import SqliteFeedbackRepository
from src.repositories.settings_repository import SqliteSettingsRepository
from src.tools.market_tools import create_market_server

# Safe Import for DSPy
# 安全引入 DSPy
has_dspy = False
try:
    import dspy
    # Check if a valid dspy module
    # 檢查是否為有效的 dspy 模組
    if hasattr(dspy, 'OpenAI'):
        has_dspy = True
    else:
        # Try finding where OpenAI might be, or just fallback
        # 嘗試尋找 OpenAI 類別位置，或直接使用備案
        pass
except ImportError:
    pass

logger = logging.getLogger(__name__)

class AgentFactory:
    """
    Factory for creating Agent instances with consistent configuration.
    Implements **Factory Pattern** and **Dependency Injection**.
    建立 Agent 實例的工廠，確保配置一致。
    實作 **工廠模式 (Factory Pattern)** 與 **依賴注入 (Dependency Injection)**。
    """
    
    _dspy_configured = False

    @classmethod
    def _configure_dspy(cls):
        """
        Enable DSPy if installed and credentials are present (Env > DB).
        若已安裝 DSPy 且憑證存在 (Env > DB)，則啟用之。
        """
        if cls._dspy_configured:
            return
            
        if not has_dspy:
            cls._dspy_configured = True
            return

        api_key = os.getenv("LLM_API_KEY") or os.getenv("API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        model = os.getenv("LLM_MODEL_SMART", "google/gemini-2.0-flash-exp")

        if not api_key:
            try:
                repo = SqliteSettingsRepository()
                rows = repo.get_global()
                for row in rows:
                     k = row._mapping['key'] if hasattr(row, '_mapping') else row[0]
                     v = row._mapping['value'] if hasattr(row, '_mapping') else row[1]
                     if k == "API_KEY" and v:
                         api_key = v
                         break
            except Exception as e:
                logger.warning(f"Failed to load API_KEY from DB for DSPy: {e}")

        if api_key:
            try:
                if hasattr(dspy, 'OpenAI'):
                    lm = dspy.OpenAI(model=model, api_key=api_key, api_base=base_url, max_tokens=2048)
                    dspy.settings.configure(lm=lm)
                    logger.info(f"DSPy configured with model: {model}")
                else:
                     logger.warning("DSPy module present but missing OpenAI class.")
            except Exception as e:
                logger.warning(f"Failed to configure DSPy: {e}")
        
        cls._dspy_configured = True

    @staticmethod
    def _inject_dependencies(agent):
        """
        Helper to inject common dependencies.
        注入通用依賴的輔助函數。
        """
        if not hasattr(agent, 'feedback_repo') or agent.feedback_repo is None:
             agent.feedback_repo = SqliteFeedbackRepository()
        
        market_server = create_market_server()
        for tool in market_server.list_tools():
            real_tool = market_server.tools.get(tool['name'])
            if real_tool:
                agent.register_tool(real_tool)
        
        return agent

    @staticmethod
    def create_agent(agent_name, use_cache=True, user_id="system", **kwargs):
        AgentFactory._configure_dspy()
        name_lower = agent_name.lower()
        
        agent = None
        if name_lower == 'momentum':
            agent = MomentumAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'fundamental':
            agent = FundamentalAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'macro':
            agent = MacroAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'cio':
            agent = CIOAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'engineer':
            agent = SystemEngineerAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'sentiment':
            agent = SentimentAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        elif name_lower == 'risk':
            agent = RiskAgent(use_cache=use_cache, user_id=user_id, **kwargs)
        else:
            raise ValueError(f"Unknown agent type: {agent_name}")
            
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_momentum_agent(use_cache=True, user_id="system", **kwargs):
        AgentFactory._configure_dspy()
        tier = kwargs.pop('tier', 'fast')
        agent = MomentumAgent(use_cache=use_cache, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_fundamental_agent(use_cache=True, user_id="system", **kwargs):
        tier = kwargs.pop('tier', 'smart')
        agent = FundamentalAgent(use_cache=use_cache, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)
        
    @staticmethod
    def create_macro_agent(use_cache=True, user_id="system", **kwargs):
        tier = kwargs.pop('tier', 'smart')
        agent = MacroAgent(use_cache=use_cache, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_sentiment_agent(use_cache=True, user_id="system", **kwargs):
        tier = kwargs.pop('tier', 'fast')
        agent = SentimentAgent(use_cache=use_cache, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_risk_agent(use_cache=True, user_id="system", **kwargs):
        tier = kwargs.pop('tier', 'fast')
        agent = RiskAgent(use_cache=use_cache, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)

    @staticmethod
    def create_cio_agent(use_cache=True, transaction_repo=None, mode="weekly", tier="smart", user_id="system", **kwargs):
        prompt_map = {
            "daily": "prompts/cio_daily.txt",
            "weekly": "prompts/cio_weekly.txt"
        }
        prompt_path = prompt_map.get(mode, "prompts/cio_weekly.txt")
        agent = CIOAgent(use_cache=use_cache, transaction_repo=transaction_repo, prompt_path=prompt_path, mode=mode, tier=tier, user_id=user_id, **kwargs)
        return AgentFactory._inject_dependencies(agent)
