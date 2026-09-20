import os
import json
import uuid
import difflib
try:
    import dspy
    has_dspy = True
except ImportError:
    dspy = None
    has_dspy = False

from src.utils.logger import setup_logger
from src.repositories.settings_repository import AlchemySettingsRepository
from src.repositories.feedback_repository import AlchemyFeedbackRepository
from src.config.owner import resolve_user_id
# Re-exported for backwards compatibility: the factory no longer constructs
# these directly (src/agents/impls.py does, lazily), but other modules and
# tests import the names from here.
# 為相容保留：factory 本身已不直接建構，但其他模組與測試會從此處匯入。
from src.agents.swarm.momentum_swarm import MomentumSwarm
from src.agents.swarm.fundamental_swarm import FundamentalSwarm
from src.agents.swarm.sentiment_swarm import SentimentSwarm
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent
from src.agents.system_engineer_agent import SystemEngineerAgent
from src.agents.risk import RiskAgent
from src.agents.sentinel import SentinelAgent

logger = setup_logger("AgentFactory")

class AgentFactory:
    """
    Factory for creating Agent instances with consistent configuration.
    Implements **Factory Pattern** and **Dependency Injection**.
    建立 Agent 實例的工廠，確保配置一致。
    實作 **工廠模式 (Factory Pattern)** 與 **依賴注入 (Dependency Injection)**。
    """
    
    _dspy_configured = False

    @classmethod
    def _configure_dspy(cls, user_id: str = None):
        """
        Enable DSPy if installed and credentials are present (Env > User DB > Global DB).
        若已安裝 DSPy 且憑證存在 (Env > User DB > Global DB)，則啟用之。
        """
        if cls._dspy_configured:
            return
            
        if not has_dspy:
            cls._dspy_configured = True
            return

        # [STRICT] API Key MUST come from DB, no environment fallbacks (Rule #15)
        api_key = None
        base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
        
        # Use TierConfig for model selection (smart tier for DSPy)
        from src.infrastructure.llm.tier_config import TierConfig
        tier_config = TierConfig()
        model = tier_config.resolve("smart")

        try:
            repo = AlchemySettingsRepository()
            # 1. Try User Specific Key
            if user_id:
                api_key = repo.get(user_id, "API_KEY") or repo.get(user_id, "LLM_API_KEY")
            
            if not api_key:
                logger.warning(f"No API_KEY found in DB for user {user_id}. DSPy will not be configured.")
                cls._dspy_configured = True
                return
        except Exception as e:
            logger.warning(f"Failed to load API_KEY from DB for DSPy: {e}")
            cls._dspy_configured = True
            return

        if api_key:
            try:
                if hasattr(dspy, 'OpenAI'):
                    lm = dspy.OpenAI(model=model, api_key=api_key, api_base=base_url, max_tokens=2048)
                    dspy.settings.configure(lm=lm)
                    logger.info(f"DSPy configured with model: {model} for user: {user_id}")
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
             agent.feedback_repo = AlchemyFeedbackRepository()
        
        return agent

    @staticmethod
    def create_agent(agent_name, use_cache=True, user_id=None, **kwargs):
        """
        Construct an agent by name, via the manifest registry.

        This was a literal if/elif chain over ten hardcoded names that raised
        "Unknown agent type" for anything else — so the workflow YAML's
        "Momentum Scout" and "Verifier" were not constructible through it at all,
        and adding an agent meant editing this method, BaseAgent's workspace_map
        and LLMAgentOverrideService.KNOWN_AGENT_NAMES.

        Agents are now declared in config/agents/*.md. The implementations they
        reference are registered in src/agents/impls.py; a manifest cannot name
        anything else.

        原本是十個硬編名稱的 if/elif 鏈，其餘一律拋出 "Unknown agent type"：
        workflow YAML 中的 "Momentum Scout"、"Verifier" 根本無法經由它建構，
        且新增代理需同時修改此方法、workspace_map 與 KNOWN_AGENT_NAMES。
        """
        user_id = resolve_user_id(user_id)
        AgentFactory._configure_dspy(user_id=user_id)

        from src.agents.registry import AgentRegistryError, build

        try:
            agent = build(agent_name, use_cache=use_cache, user_id=user_id, **kwargs)
        except AgentRegistryError as exc:
            # Preserved as ValueError: callers (council_service, the DAG
            # AgentNode) already catch that type.
            # 仍拋 ValueError：既有呼叫端已在捕捉此型別。
            raise ValueError(str(exc)) from exc

        return AgentFactory._inject_dependencies(agent)

    # ─────────────────────────────────────────────────────────────────────
    # Named convenience constructors.
    #
    # These were eight near-identical methods, each repeating the dspy setup, the
    # user_id guard and a direct class call — a second construction path that
    # could (and did) drift from create_agent. create_cio_agent, for instance,
    # defaulted its prompt to "prompts/cio_weekly.txt", a file that does not
    # exist in the repository.
    #
    # They now delegate to create_agent, so there is one path through the
    # registry. Signatures are unchanged for existing callers.
    #
    # 原本是八個幾乎相同的方法，各自重複 dspy 設定、user_id 檢查與直接呼叫類別，
    # 形成會漂移的第二條建構路徑（create_cio_agent 的預設提示詞檔甚至不存在）。
    # 現全部委派給 create_agent，統一走註冊表；對外簽章不變。
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def create_thematic_agent(use_cache=True, user_id=None, **kwargs):
        return AgentFactory.create_agent("thematic", use_cache=use_cache,
                                         user_id=user_id, **kwargs)

    @staticmethod
    def create_momentum_agent(use_cache=True, user_id=None, **kwargs):
        return AgentFactory.create_agent("momentum", use_cache=use_cache,
                                         user_id=user_id, **kwargs)

    @staticmethod
    def create_fundamental_agent(use_cache=True, user_id=None, **kwargs):
        return AgentFactory.create_agent("fundamental", use_cache=use_cache,
                                         user_id=user_id, **kwargs)

    @staticmethod
    def create_macro_agent(use_cache=True, user_id=None, **kwargs):
        return AgentFactory.create_agent("macro", use_cache=use_cache,
                                         user_id=user_id, **kwargs)

    @staticmethod
    def create_sentiment_agent(use_cache=True, user_id=None, **kwargs):
        return AgentFactory.create_agent("sentiment", use_cache=use_cache,
                                         user_id=user_id, **kwargs)

    @staticmethod
    def create_risk_agent(use_cache=True, user_id=None, **kwargs):
        return AgentFactory.create_agent("risk", use_cache=use_cache,
                                         user_id=user_id, **kwargs)

    @staticmethod
    def create_sentinel_agent(use_cache=True, user_id=None, **kwargs):
        return AgentFactory.create_agent("sentinel", use_cache=use_cache,
                                         user_id=user_id, **kwargs)

    @staticmethod
    def create_cio_agent(use_cache=True, transaction_repo=None, mode="weekly",
                         tier="smart", user_id=None, **kwargs):
        """
        CIO agent.

        All three modes mapped to the same prompt file, and the `.get()` default
        pointed at "prompts/cio_weekly.txt" — which does not exist, so any mode
        outside the map produced a FileNotFoundError at prompt load. The map is
        gone: the single real path is passed directly, and the manifest/workspace
        chain supplies the prompt when no path is given.

        三個 mode 原本都對到同一個提示詞檔，而 .get() 的預設值指向不存在的
        prompts/cio_weekly.txt：map 之外的 mode 會在載入提示詞時拋 FileNotFoundError。
        """
        kwargs.setdefault("prompt_path", "prompts/cio_agent.txt")
        return AgentFactory.create_agent(
            "cio", use_cache=use_cache, user_id=user_id,
            transaction_repo=transaction_repo, mode=mode, tier=tier, **kwargs,
        )

