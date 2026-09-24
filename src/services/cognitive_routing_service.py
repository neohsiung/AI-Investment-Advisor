"""
CognitiveRoutingService — 議題導向之多階層認知模型路由服務。
Cognitive Routing Service — Issue-based multi-tier model routing and Reflex (Jev) dispatcher.

Core Philosophy:
- Maps quantitative platform issues (intent routing, sentinel checks, news filtering, etc.)
  to optimal LLM tiers (reflex, fast, smart, advanced).
- Leverages TypeSafe Jev 1.13 (<70ms, non-generative, $0.042/MTok) for Level 0 micro-decisions.
- Transparent semantic escalation to Fast/Smart tiers when confidence is below threshold.
- Zero-fail-silent compliance (Constraint #0).
"""

from __future__ import annotations

import os
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.domain.cognitive_issue_type import CognitiveIssueType, IssueRoutingSpec
from src.infrastructure.llm.arbiter_client import ArbiterClient, ArbiterDecision
from src.repositories.settings_repository import ISettingsRepository, AlchemySettingsRepository

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "issue_tier_routing.yaml"


class CognitiveRoutingService:
    """
    Service for resolving issue-to-tier mappings and dispatching Reflex decisions.
    """

    _cached_defaults: Optional[Dict[str, IssueRoutingSpec]] = None

    def __init__(
        self,
        settings_repo: Optional[ISettingsRepository] = None,
        arbiter_client: Optional[ArbiterClient] = None,
        config_path: Optional[Path] = None,
    ):
        self._settings_repo = settings_repo
        self._arbiter_client = arbiter_client
        self.config_path = config_path or CONFIG_PATH

    @property
    def settings_repo(self) -> Optional[ISettingsRepository]:
        if self._settings_repo is None:
            try:
                self._settings_repo = AlchemySettingsRepository()
            except Exception as e:
                logger.debug(f"CognitiveRouting: DB settings repo unavailable ({e}), using memory-only defaults")
        return self._settings_repo

    @property
    def arbiter_client(self) -> ArbiterClient:
        if self._arbiter_client is None:
            self._arbiter_client = ArbiterClient()
        return self._arbiter_client

    @classmethod
    def load_defaults(cls, config_path: Optional[Path] = None) -> Dict[str, IssueRoutingSpec]:
        """Load default routing specifications from YAML."""
        path = config_path or CONFIG_PATH
        if not path.exists():
            logger.warning(f"CognitiveRouting: Config file not found at {path}, using hardcoded baseline")
            return cls._baseline_defaults()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            routes = data.get("routing", [])
            result = {}
            for item in routes:
                spec = IssueRoutingSpec(**item)
                result[spec.issue_type] = spec
            return result
        except Exception as e:
            logger.error(f"CognitiveRouting: Failed to parse {path}: {e}")
            return cls._baseline_defaults()

    @classmethod
    def _baseline_defaults(cls) -> Dict[str, IssueRoutingSpec]:
        """Hardcoded baseline fallback in case config file is unreadable."""
        return {
            CognitiveIssueType.INTENT_ROUTING.value: IssueRoutingSpec(
                issue_type=CognitiveIssueType.INTENT_ROUTING.value,
                default_tier="reflex",
                confidence_threshold=0.88,
                fallback_tier="fast",
                is_reflex_eligible=True,
                description="User intent classification",
            ),
            CognitiveIssueType.NEWS_RELEVANCE.value: IssueRoutingSpec(
                issue_type=CognitiveIssueType.NEWS_RELEVANCE.value,
                default_tier="reflex",
                confidence_threshold=0.90,
                fallback_tier="fast",
                is_reflex_eligible=True,
                description="Binary news relevance",
            ),
            CognitiveIssueType.SENTINEL_BREACH.value: IssueRoutingSpec(
                issue_type=CognitiveIssueType.SENTINEL_BREACH.value,
                default_tier="reflex",
                confidence_threshold=0.92,
                fallback_tier="smart",
                is_reflex_eligible=True,
                description="Sentinel breach checks",
            ),
            CognitiveIssueType.EVENT_PRIORITIZATION.value: IssueRoutingSpec(
                issue_type=CognitiveIssueType.EVENT_PRIORITIZATION.value,
                default_tier="reflex",
                confidence_threshold=0.90,
                fallback_tier="smart",
                is_reflex_eligible=True,
                description="Event priority tiering",
            ),
        }

    def _get_defaults(self) -> Dict[str, IssueRoutingSpec]:
        if CognitiveRoutingService._cached_defaults is None:
            CognitiveRoutingService._cached_defaults = self.load_defaults(self.config_path)
        return CognitiveRoutingService._cached_defaults

    def get_routing_spec(
        self,
        issue_type: str | CognitiveIssueType,
        user_id: Optional[str] = None
    ) -> IssueRoutingSpec:
        """
        Get the effective routing spec for an issue type, applying tenant-specific overrides.
        """
        key = issue_type.value if isinstance(issue_type, CognitiveIssueType) else str(issue_type).strip().lower()
        defaults = self._get_defaults()
        spec = defaults.get(key)

        if not spec:
            # Fallback for unrecognized issue types
            logger.warning(f"CognitiveRouting: Unknown issue_type '{key}', defaulting to fast tier")
            return IssueRoutingSpec(
                issue_type=key,
                default_tier="fast",
                fallback_tier="smart",
                confidence_threshold=0.80,
                description="Unregistered issue type",
            )

        # Apply tenant-specific overrides from Settings table
        if user_id:
            try:
                overrides_raw = self.settings_repo.get(user_id, "issue_tier_overrides", default=None)
                if overrides_raw:
                    overrides = json.loads(overrides_raw) if isinstance(overrides_raw, str) else overrides_raw
                    if isinstance(overrides, dict) and key in overrides:
                        user_override = overrides[key]
                        updated_dict = spec.model_dump()
                        updated_dict.update(user_override)
                        return IssueRoutingSpec(**updated_dict)
            except Exception as e:
                logger.warning(f"CognitiveRouting: Failed to load user overrides for {user_id}: {e}")

        return spec

    def get_tier_for_issue(
        self,
        issue_type: str | CognitiveIssueType,
        user_id: Optional[str] = None
    ) -> str:
        """
        Return the optimal model tier (reflex, fast, smart, advanced) for the given issue.
        """
        spec = self.get_routing_spec(issue_type, user_id=user_id)
        return spec.default_tier

    def should_use_reflex(
        self,
        issue_type: str | CognitiveIssueType,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Determine if this issue should be processed via TypeSafe Jev (Reflex Tier).
        """
        spec = self.get_routing_spec(issue_type, user_id=user_id)
        return spec.is_reflex_eligible and spec.default_tier == "reflex"

    def list_all_routing_specs(self, user_id: Optional[str] = None) -> List[IssueRoutingSpec]:
        """
        List all configured routing specs with user overrides applied.
        """
        defaults = self._get_defaults()
        results = []
        for key in defaults.keys():
            results.append(self.get_routing_spec(key, user_id=user_id))
        return results

    def update_issue_override(
        self,
        user_id: str,
        issue_type: str | CognitiveIssueType,
        updates: Dict[str, Any]
    ) -> IssueRoutingSpec:
        """
        Set a tenant-specific routing override for an issue type.
        """
        key = issue_type.value if isinstance(issue_type, CognitiveIssueType) else str(issue_type).strip().lower()
        current_overrides_raw = self.settings_repo.get(user_id, "issue_tier_overrides", default="{}")
        current_overrides = (
            json.loads(current_overrides_raw)
            if isinstance(current_overrides_raw, str)
            else current_overrides_raw or {}
        )

        current_overrides[key] = updates
        self.settings_repo.set(user_id, "issue_tier_overrides", json.dumps(current_overrides))

        return self.get_routing_spec(key, user_id=user_id)

    async def evaluate_reflex_issue(
        self,
        issue_type: str | CognitiveIssueType,
        domain: str,
        state: Dict[str, Any],
        question_key: str,
        question_spec: Dict[str, Any],
        system2_fallback_prompt: str,
        deterministic_default: Any,
        user_id: Optional[str] = None,
    ) -> ArbiterDecision:
        """
        Dispatch a conditional decision to Jev (Reflex Tier), handling automatic escalation if confidence is low.
        """
        spec = self.get_routing_spec(issue_type, user_id=user_id)

        return await self.arbiter_client.decide(
            domain=domain,
            state=state,
            question_key=question_key,
            question_spec=question_spec,
            confidence_threshold=spec.confidence_threshold,
            system2_fallback_prompt=system2_fallback_prompt,
            deterministic_default=deterministic_default,
            timeout_ms=spec.timeout_ms,
        )
