"""
LLM Tier Configuration — Multi-Tier Model Routing.
LLM 層級設定 — 多層模型路由。

Centralizes model tier definitions, pricing metadata, and selection
logic. Supports N-tier expansion beyond the original 3-tier (fast/smart/advanced).

Design rationale (from Artificial Analysis intelligence-efficiency curve):
  - Higher intelligence → higher cost per token
  - Key insight: 大腦越聰明，執行技能可以越慢越便宜
  - Budget: ~$20/week ≈ $2.86/day

Tier naming convention (cognitive mapping):
  - nano:     System 0 — 反射 (reflex)          → classification, routing
  - fast:     System 1 — 快思 (fast thinking)    → summarization, extraction
  - smart:    System 2 — 慢想 (slow thinking)    → analysis, reasoning
  - advanced: System 2+ — 深思 (deep thinking)   → complex strategy, CIO decisions

遵循規範:
  - 規範一 (Clean Architecture): 設定與邏輯分離
  - 規範四 (模組化設計): 新增 tier 只需加一行 config
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class TierSpec:
    """
    Specification for a single LLM tier.
    單一 LLM 層級的規格。
    """
    name: str                              # tier identifier
    display_name: str                      # human-readable
    env_key: str                           # env var for model override
    input_cost_per_mtok: float = 0.0       # $/million input tokens
    output_cost_per_mtok: float = 0.0      # $/million output tokens
    max_tokens: int = 4096                 # default max output tokens
    description: str = ""
    default_model: str = ""                # Fallback if DB and Env are missing
    cognitive_mapping: str = ""            # 認知科學對照

    @property
    def blended_cost_per_mtok(self) -> float:
        """Blended cost (3:1 input:output ratio)."""
        return (self.input_cost_per_mtok * 3 + self.output_cost_per_mtok) / 4

    def resolve_model(self, db_settings: Dict[str, str] = None) -> Optional[str]:
        """
        Resolve the actual model to use.
        Priority: DB setting > Env var > Default.
        """
        db_settings = db_settings or {}
        # DB override
        if self.env_key in db_settings:
            val = db_settings[self.env_key]
            if val:
                return val.strip().strip('"').strip("'")
        # Env override
        env_model = os.getenv(self.env_key)
        if env_model:
            return env_model.strip().strip('"').strip("'")
        # Default
        return self.default_model


# ═══════════════════════════════════════════════════════
# Tier Definitions (Recommended Models — March 2026)
# ═══════════════════════════════════════════════════════

# fmt: off
DEFAULT_TIERS: Dict[str, TierSpec] = {
    # ── Tier 0: Nano — 反射層 (Reflex) ─────────────────
    "nano": TierSpec(
        name="nano",
        display_name="Nano (反射)",
        env_key="AI_MODEL_NANO",
        input_cost_per_mtok=0.10,
        output_cost_per_mtok=0.40,
        max_tokens=512,
        description="Ultra-cheap reflex layer for classification & routing",
        default_model="google/gemini-2.0-flash-lite-preview-02-05",
        cognitive_mapping="System 0 — 反射 (Reflex): 不經思考的自動反應",
    ),

    # ── Tier 1: Fast — 快思層 (Fast Thinking) ──────────
    "fast": TierSpec(
        name="fast",
        display_name="Fast (高速)",
        env_key="AI_MODEL_FAST",
        input_cost_per_mtok=0.30,
        output_cost_per_mtok=2.50,
        max_tokens=2048,
        description="Low-latency balance for summary & sensory agents",
        default_model="google/gemini-2.0-flash-exp",
        cognitive_mapping="System 1 — 快思 (Fast Thinking): 直覺式快速處理",
    ),

    # ── Tier 2: Smart — 慢想層 (Slow Thinking) ─────────
    # 用途: 分析、推理、知識蒸餾、上下文對話、多步驟決策
    "smart": TierSpec(
        name="smart",
        display_name="Smart (慢想)",
        env_key="AI_MODEL_SMART",
        input_cost_per_mtok=1.25,
        output_cost_per_mtok=10.00,
        max_tokens=8192,
        description="Analytical layer for reasoning & multi-step decisions",
        default_model="google/gemini-2.0-pro-exp-02-05",
        cognitive_mapping="System 2 — 慢想 (Slow Thinking): 需要專注的分析性思考",
    ),

    # ── Tier 3: Advanced — 深思層 (Deep Thinking) ──────
    # Use for: CIO final decisions, wisdom crystallization (K→W),
    #          complex strategy, risk assessment with high stakes
    # 用途: CIO 最終決策、智慧結晶、複雜策略、高風險評估
    "advanced": TierSpec(
        name="advanced",
        display_name="Advanced (深思)",
        env_key="AI_MODEL_ADVANCED",
        input_cost_per_mtok=3.00,
        output_cost_per_mtok=15.00,
        max_tokens=8192,
        description="Deep reasoning for CIO decisions & complex strategy",
        default_model="anthropic/claude-3.5-sonnet:beta",
        cognitive_mapping="System 2+ — 深思 (Deep Thinking): 深度推理與戰略判斷",
    ),
}
# fmt: on


class TierConfig:
    """
    Central tier configuration manager.
    中央層級設定管理器。

    Usage:
        config = TierConfig()
        model = config.resolve("fast")
        spec = config.get_spec("smart")
        budget = config.estimate_daily_budget(call_counts)
    """

    def __init__(self, tiers: Dict[str, TierSpec] = None):
        self._tiers = tiers or DEFAULT_TIERS.copy()

    def resolve(self, tier_name: str, db_settings: Dict[str, str] = None) -> str:
        """Resolve tier name to actual model identifier."""
        spec = self._tiers.get(tier_name)
        if not spec:
            logger.warning(f"TierConfig: Unknown tier '{tier_name}', falling back to 'fast'")
            spec = self._tiers.get("fast", list(self._tiers.values())[0])
        return spec.resolve_model(db_settings)

    def get_spec(self, tier_name: str) -> Optional[TierSpec]:
        """Get full spec for a tier."""
        return self._tiers.get(tier_name)

    def list_tiers(self) -> List[TierSpec]:
        """List all tier specs in order (cheapest first)."""
        return sorted(
            self._tiers.values(),
            key=lambda t: t.blended_cost_per_mtok,
        )

    def estimate_daily_cost(self, call_counts: Dict[str, int], avg_tokens_per_call: int = 1500) -> float:
        """
        Estimate daily cost based on call counts per tier.
        根據每層的調用次數估算每日成本。

        Args:
            call_counts: {"nano": 50, "fast": 30, "smart": 10, "advanced": 2}
            avg_tokens_per_call: average total tokens (input + output) per call
        """
        total = 0.0
        for tier_name, count in call_counts.items():
            spec = self._tiers.get(tier_name)
            if spec:
                # Assume 3:1 input:output ratio
                cost = spec.blended_cost_per_mtok * (avg_tokens_per_call / 1_000_000) * count
                total += cost
        return total

    def recommend_tier(self, task_type: str) -> str:
        """
        Recommend a tier based on task type.
        根據任務類型推薦層級。
        """
        mapping = {
            # nano tasks
            "classify": "nano",
            "route": "nano",
            "intent": "nano",
            "yes_no": "nano",
            # fast tasks
            "summarize": "fast",
            "extract": "fast",
            "sentiment": "fast",
            "compact": "fast",
            "format": "fast",
            # smart tasks
            "analyze": "smart",
            "reason": "smart",
            "converse": "smart",
            "distill": "smart",
            "research": "smart",
            # advanced tasks
            "decide": "advanced",
            "strategy": "advanced",
            "crystallize": "advanced",
            "cio": "advanced",
        }
        return mapping.get(task_type.lower(), "fast")

    def print_budget_report(self, call_counts: Dict[str, int], avg_tokens: int = 1500) -> str:
        """Generate a human-readable budget report."""
        lines = ["## LLM 成本預估 (Cost Estimate)\n"]
        lines.append("| Tier | Model | Calls/Day | Cost/Day | Cost/Week |")
        lines.append("|------|-------|-----------|----------|-----------|")

        daily_total = 0.0
        for spec in self.list_tiers():
            count = call_counts.get(spec.name, 0)
            daily = spec.blended_cost_per_mtok * (avg_tokens / 1_000_000) * count
            daily_total += daily
            lines.append(
                f"| {spec.display_name} | `{spec.env_key}` | "
                f"{count} | ${daily:.4f} | ${daily * 7:.4f} |"
            )

        lines.append(f"| **Total** | — | — | **${daily_total:.4f}** | **${daily_total * 7:.4f}** |")
        lines.append(f"\n> Weekly budget: $20.00 | Estimated: ${daily_total * 7:.2f}")

        return "\n".join(lines)


class SettingsAwareModelRouter:
    """
    User-aware model router that fetches models from database settings.
    用戶感知的模型路由器，從資料庫設定中取得模型。
    
    Usage:
        router = SettingsAwareModelRouter(settings_repo)
        model = router.get_model(user_id, "fast")
        models = router.get_all_models(user_id)
    """
    
    def __init__(self, settings_repo=None):
        self.settings_repo = settings_repo
        self.tier_config = TierConfig()
    
    def get_model(self, user_id: str, tier: str) -> str:
        """
        Get the model for a specific tier and user.
        Priority: DB setting > Tier default
        """
        if not user_id:
            logger.warning("SettingsAwareModelRouter.get_model: user_id is empty")
            return self.tier_config.resolve(tier)
        
        try:
            if self.settings_repo:
                tier_key_map = {
                    "nano": "AI_MODEL_NANO",
                    "fast": "AI_MODEL_FAST",
                    "smart": "AI_MODEL_SMART",
                    "advanced": "AI_MODEL_ADVANCED"
                }
                db_key = tier_key_map.get(tier)
                if db_key:
                    # Use correct method signature: get(user_id, key, default)
                    db_model = self.settings_repo.get(user_id, db_key, None)
                    if db_model:
                        if isinstance(db_model, str):
                            db_model = db_model.strip().strip('"').strip("'")
                        logger.info(f"ModelRouter: {user_id} {tier} -> {db_model} (DB)")
                        return db_model
        except Exception as e:
            logger.warning(f"ModelRouter: Failed DB lookup {user_id}/{tier}: {e}")
        
        model = self.tier_config.resolve(tier)
        logger.info(f"ModelRouter: {user_id} {tier} -> {model} (resolved)")
        return model or ""
    
    def get_all_models(self, user_id: str) -> Dict[str, str]:
        """Get all models for a user across all tiers."""
        return {
            tier: self.get_model(user_id, tier)
            for tier in ["nano", "fast", "smart", "advanced"]
        }
