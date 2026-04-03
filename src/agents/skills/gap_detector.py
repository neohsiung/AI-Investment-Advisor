"""
Gap Detector — Capability Gap Analysis Engine.
缺口偵測器 — 能力缺口分析引擎。

Analyzes whether a user's request exceeds the agent's current skill set
and suggests new skills to fill the gap.

遵循規範:
  - 規範一 (Clean Architecture): 依賴注入，不直接實例化 infra
  - 規範四 (模組化設計): 獨立可單元測試
  - 規範十五 (AI-Support First): 結構化 JSON 輸出
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List

from src.domain.interfaces import Message, LLMConfig, ILLMGateway
from src.agents.skills.skill_loader import SkillLoader, SkillMetadata

logger = logging.getLogger(__name__)


@dataclass
class GapReport:
    """
    Structured result from gap detection analysis.
    缺口偵測分析的結構化結果。
    """
    is_gap: bool                      # 是否偵測到能力缺口
    suggested_skill_name: str = ""    # 建議的 Skill 名稱 (snake_case)
    suggested_category: str = ""      # 建議的分類 (market_data, analysis, etc.)
    reasoning: str = ""               # LLM 推理過程
    can_auto_scaffold: bool = False   # 是否可自動建立骨架
    existing_similar: str = ""        # 最接近的既有 Skill

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GapDetector:
    """
    Detects capability gaps by comparing user intent against registered skills.
    透過比對使用者意圖與已註冊 Skill 來偵測能力缺口。

    Uses Fast-tier LLM for lightweight classification.
    """

    # Simple heuristic patterns that are never gaps (greetings, confirmations, etc.)
    NON_GAP_PATTERNS = [
        "你好", "嗨", "哈囉", "hello", "hi", "hey",
        "謝謝", "感謝", "thanks", "thank you",
        "好", "嗯", "OK", "了解", "收到",
        "是", "否", "對", "不",
    ]

    def __init__(
        self,
        skill_loader: SkillLoader = None,
        llm_gateway: ILLMGateway = None,
    ):
        self._skill_loader = skill_loader or SkillLoader()
        self._llm_gateway = llm_gateway
        self._prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        """Load the gap detection prompt template."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Navigate from src/agents/skills/ → project root → prompts/
        prompt_path = os.path.abspath(
            os.path.join(current_dir, "..", "..", "..", "prompts", "gap_detector.txt")
        )
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"GapDetector: Prompt template not found at {prompt_path}")
            return ""

    def _get_llm(self) -> ILLMGateway:
        """Lazy-init LLM gateway."""
        if self._llm_gateway is None:
            from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
            provider = os.getenv("AI_PROVIDER", "Google Gemini")
            self._llm_gateway = LLMGatewayFactory.create(provider)
        return self._llm_gateway

    def _get_config(self) -> LLMConfig:
        """Fast-tier LLM config for classification."""
        return LLMConfig(
            provider=os.getenv("AI_PROVIDER", "Google Gemini"),
            model=os.getenv("AI_MODEL_FAST", "gemini-1.5-flash"),
            api_key=os.getenv("API_KEY", ""),
            temperature=0.0,
            max_tokens=500,
        )

    def _build_skill_summary(self, skills: Dict[str, SkillMetadata]) -> str:
        """Build a concise summary of available skills for the prompt."""
        lines = []
        for name, meta in skills.items():
            desc = meta.description if hasattr(meta, 'description') else str(meta)
            category = meta.category if hasattr(meta, 'category') else "general"
            lines.append(f"- {name} [{category}]: {desc}")
        return "\n".join(lines) if lines else "（無已註冊工具）"

    async def detect(
        self,
        user_message: str,
        registered_skills: Dict[str, SkillMetadata] = None,
        context: Dict[str, Any] = None,
    ) -> GapReport:
        """
        Analyze whether the user's intent falls outside current skill capabilities.
        分析使用者意圖是否超出現有 Skill 能力。

        Args:
            user_message: The user's text input
            registered_skills: Dict of skill name → SkillMetadata
            context: Additional conversation context

        Returns:
            GapReport with structured gap analysis results
        """
        # 1. Fast heuristic pre-filter: skip trivial messages
        stripped = user_message.strip().lower()
        if stripped in self.NON_GAP_PATTERNS or len(stripped) < 5:
            return GapReport(is_gap=False, reasoning="Trivial message, not a gap")

        # 2. Get available skills
        if registered_skills is None:
            self._skill_loader.discover_skills()
            registered_skills = self._skill_loader._metadata_cache

        skill_summary = self._build_skill_summary(registered_skills)

        # 3. Build prompt
        if not self._prompt_template:
            logger.warning("GapDetector: No prompt template, falling back to heuristic")
            return GapReport(is_gap=False, reasoning="Prompt template missing")

        prompt = (
            self._prompt_template
            .replace("{{skill_registry_summary}}", skill_summary)
            .replace("{{user_message}}", user_message)
        )

        # 4. Call Fast-tier LLM
        try:
            from src.utils.async_utils import to_thread

            llm = self._get_llm()
            config = self._get_config()
            messages = [
                Message(role="system", content="You are a JSON-only response agent."),
                Message(role="user", content=prompt),
            ]
            response_str = await to_thread(llm.chat, messages, config)

            # 5. Parse JSON response
            cleaned = response_str.replace("```json", "").replace("```", "").strip()
            if not cleaned.startswith("{"):
                start_idx = cleaned.find("{")
                if start_idx != -1:
                    cleaned = cleaned[start_idx:]

            data = json.loads(cleaned)

            return GapReport(
                is_gap=data.get("is_gap", False),
                suggested_skill_name=data.get("suggested_skill_name", ""),
                suggested_category=data.get("suggested_category", ""),
                reasoning=data.get("reasoning", ""),
                can_auto_scaffold=data.get("can_auto_scaffold", False),
                existing_similar=data.get("existing_similar", ""),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"GapDetector: Failed to parse LLM response: {e}")
            return GapReport(is_gap=False, reasoning=f"Parse error: {e}")
        except Exception as e:
            logger.error(f"GapDetector: Detection failed: {e}")
            return GapReport(is_gap=False, reasoning=f"Error: {e}")
