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
from pathlib import Path
from typing import Dict, Optional, List

import yaml

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
    # default_model removed to enforce DB-only configuration
    cognitive_mapping: str = ""            # 認知科學對照

    @property
    def blended_cost_per_mtok(self) -> float:
        """Blended cost (3:1 input:output ratio)."""
        return (self.input_cost_per_mtok * 3 + self.output_cost_per_mtok) / 4

    def resolve_model(self, db_settings: Dict[str, str] = None) -> Optional[str]:
        """
        Resolve the actual model to use.
        Priority: DB setting (Only).
        Strictly prohibits env-var or hardcoded fallbacks.
        """
        db_settings = db_settings or {}
        # DB override
        if self.env_key in db_settings:
            val = db_settings[self.env_key]
            if val:
                return val.strip().strip('"').strip("'")
        
        # No fallback allowed
        return None


# ═══════════════════════════════════════════════════════
# Tier Definitions — loaded from config/llm_tiers.yaml
# ═══════════════════════════════════════════════════════
#
# This was a 54-line literal dict of four TierSpec constructions. The contents
# are data — display names, per-million-token prices, token ceilings — and those
# prices are what the budget router and cost dashboards compute against, so
# adjusting one meant editing Python and shipping an image.
#
# `DEFAULT_TIERS` keeps its name and its `Dict[str, TierSpec]` shape: it is read
# directly by `TierConfig.__init__`, `weekly_cost_review` and several tests.
# 原本是 54 行、四個 TierSpec 的字面 dict；內容純屬資料，且價格是預算路由與成本
# 報表的計算基礎。DEFAULT_TIERS 名稱與型別不變（多處直接讀取）。

TIERS_ENV = "LLM_TIERS_MANIFEST"
DEFAULT_TIERS_PATH = Path(__file__).resolve().parents[3] / "config" / "llm_tiers.yaml"


def tiers_manifest_path() -> Path:
    explicit = os.getenv(TIERS_ENV)
    return Path(explicit) if explicit else DEFAULT_TIERS_PATH


def _spec_from_dict(entry: Dict) -> TierSpec:
    return TierSpec(
        name=entry["name"],
        display_name=entry.get("display_name", entry["name"]),
        env_key=entry["env_key"],
        input_cost_per_mtok=float(entry.get("input_cost_per_mtok", 0.0)),
        output_cost_per_mtok=float(entry.get("output_cost_per_mtok", 0.0)),
        max_tokens=int(entry.get("max_tokens", 4096)),
        description=entry.get("description", ""),
        cognitive_mapping=entry.get("cognitive_mapping", ""),
    )


def load_tiers(path=None) -> Dict[str, TierSpec]:
    """
    Parse the tier manifest.

    Raises if the file is missing or yields no tiers. An empty tier table would
    make every `resolve()` fall through to "unknown tier" and route everything to
    whatever happened to be first — a silent, expensive misroute — so this is one
    of the few places where failing to start is the correct behaviour.
    檔案缺失或沒有任何 tier 時直接拋出：空的 tier 表會讓每次 resolve 落入「未知層級」
    並路由到恰好排在第一個的模型（靜默且昂貴的錯誤路由），因此此處啟動失敗才是正確行為。
    """
    tiers_path = Path(path) if path else tiers_manifest_path()
    if not tiers_path.exists():
        raise FileNotFoundError(f"LLM tier manifest not found at {tiers_path}")

    raw = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    specs: Dict[str, TierSpec] = {}
    for entry in raw.get("tiers") or []:
        try:
            spec = _spec_from_dict(entry)
        except Exception as exc:
            raise ValueError(f"Invalid tier entry {entry!r} in {tiers_path}: {exc}") from exc
        specs[spec.name] = spec

    if not specs:
        raise ValueError(f"No tiers defined in {tiers_path}")

    logger.info(f"TierConfig: loaded {len(specs)} tiers from {tiers_path}")
    return specs


DEFAULT_TIERS: Dict[str, TierSpec] = load_tiers()


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
        
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            chain = build_config_chain(tier=tier, user_id=user_id)
            if chain:
                model = chain[0].model_code
                logger.info(f"ModelRouter: {user_id} {tier} -> {model} (tier_bindings)")
                return model
        except Exception:
            pass

        model = self.tier_config.resolve(tier)
        logger.info(f"ModelRouter: {user_id} {tier} -> {model} (resolved)")
        return model or ""
    
    def get_all_models(self, user_id: str) -> Dict[str, str]:
        """Get all models for a user across all tiers."""
        return {
            tier: self.get_model(user_id, tier)
            for tier in ["nano", "fast", "smart", "advanced"]
        }
