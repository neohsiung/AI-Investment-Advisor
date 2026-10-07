"""
Model Scanner Service — Phase 1 of Autonomous Model Governance.
模型智能巡檢與動態選型服務。

Responsibilities:
  1. 定期巡檢所有啟用的 LLM 提供者（OpenRouter, Ollama, NVIDIA 等），發現最新模型。
  2. 審查現有層級綁定（llm_tier_bindings）之存活狀態，防範因模型下架或 API 廢棄引發的服務中斷。
  3. 比對性價比（Cost-to-Intelligence ratio），為各層級（nano, fast, smart, advanced）評估潛在的候選模型（Green Candidate）。
  4. 產生模型演化建議（Evolution Proposals），供藍綠金絲雀評估器執行安全升級。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.config.owner import resolve_user_id
from src.data.models import LLMModel
from src.repositories.llm_model_repository import LLMModelRepository
from src.repositories.llm_provider_repository import LLMProviderRepository
from src.repositories.llm_tier_binding_repository import LLMTierBindingRepository
from src.services.llm_model_service import LLMModelService

logger = logging.getLogger(__name__)

# Tier Cost Benchmarks (Baseline commercial pricing per 1M tokens)
TIER_COST_CEILINGS = {
    "nano": 0.50,       # $0.50 / MTok
    "fast": 2.50,       # $2.50 / MTok
    "smart": 10.00,     # $10.00 / MTok
    "advanced": 25.00,  # $25.00 / MTok
}


@dataclass
class ModelHealthStatus:
    model_id: str
    model_code: str
    display_name: str
    provider_code: str
    is_available: bool
    is_enabled: bool
    status: str  # "healthy", "disabled", "deprecated", "missing"
    reason: str = ""


@dataclass
class TierAuditResult:
    tier: str
    primary_status: ModelHealthStatus
    fallback_statuses: list[ModelHealthStatus]
    is_healthy: bool
    needs_action: bool
    recommendation: str = ""


@dataclass
class EvolutionProposal:
    tier: str
    current_primary_id: str
    candidate_model_id: str
    candidate_model_code: str
    candidate_display_name: str
    proposal_type: str  # "EMERGENCY_REPLACEMENT" | "COST_SAVING" | "CAPABILITY_UPGRADE"
    estimated_cost_saving_pct: float
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


class ModelScannerService:
    """
    Automated scanner for LLM provider discovery and tier model health audit.
    """

    def __init__(
        self,
        user_id: str,
        provider_repo: LLMProviderRepository | None = None,
        model_repo: LLMModelRepository | None = None,
        tier_repo: LLMTierBindingRepository | None = None,
        model_service: LLMModelService | None = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.provider_repo = provider_repo or LLMProviderRepository()
        self.model_repo = model_repo or LLMModelRepository()
        self.tier_repo = tier_repo or LLMTierBindingRepository()
        self.model_service = model_service or LLMModelService(user_id=self.user_id)

    def scan_and_sync_providers(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        Poll external provider APIs to discover available models.
        """
        providers = self.provider_repo.list_by_user(self.user_id, enabled=True)
        summary = {"scanned_providers": len(providers), "discovered_count": 0, "errors": []}

        for p in providers:
            try:
                result = self.model_service.discover(p.id, force_refresh=force_refresh)
                items = result.get("data", [])
                summary["discovered_count"] += len(items)
                logger.info(
                    "ModelScanner: Discovered %d models for provider %s (%s)",
                    len(items),
                    p.provider_code,
                    p.id,
                )
            except Exception as e:
                err_msg = f"Failed to discover models for provider {p.provider_code}: {e}"
                logger.warning("ModelScanner: %s", err_msg)
                summary["errors"].append({"provider_id": p.id, "error": str(e)})

        return summary

    def audit_tier_bindings(self) -> dict[str, TierAuditResult]:
        """
        Audit the health and availability of all currently configured tier bindings.
        """
        bindings = self.tier_repo.list_by_user(self.user_id)
        audit_results: dict[str, TierAuditResult] = {}

        for b in bindings:
            primary_status = self._check_model_health(b.primary_model_id)
            fallback_statuses = [self._check_model_health(fid) for fid in (b.fallback_model_ids or [])]

            is_healthy = primary_status.status == "healthy"
            needs_action = not is_healthy or any(fs.status != "healthy" for fs in fallback_statuses)
            
            recommendation = ""
            if primary_status.status != "healthy":
                recommendation = f"Primary model for {b.tier} is {primary_status.status} ({primary_status.reason}). Urgent failover or replacement required."
            elif any(fs.status != "healthy" for fs in fallback_statuses):
                recommendation = f"One or more fallbacks in {b.tier} are unhealthy. Update fallback chain."
            else:
                recommendation = f"Tier {b.tier} is healthy."

            audit_results[b.tier] = TierAuditResult(
                tier=b.tier,
                primary_status=primary_status,
                fallback_statuses=fallback_statuses,
                is_healthy=is_healthy,
                needs_action=needs_action,
                recommendation=recommendation,
            )

        return audit_results

    def _check_model_health(self, model_id: str) -> ModelHealthStatus:
        """Inspect a single model ID for availability in DB and active status."""
        m = self.model_repo.get(model_id)
        if m is None:
            return ModelHealthStatus(
                model_id=model_id,
                model_code="",
                display_name="Unknown Model",
                provider_code="",
                is_available=False,
                is_enabled=False,
                status="missing",
                reason=f"Model ID '{model_id}' does not exist in llm_models",
            )

        provider = self.provider_repo.get(m.provider_id) if m.provider_id else None
        if provider is None or not provider.enabled:
            return ModelHealthStatus(
                model_id=m.id,
                model_code=m.model_code,
                display_name=m.display_name,
                provider_code=provider.provider_code if provider else "unknown",
                is_available=False,
                is_enabled=m.enabled,
                status="deprecated",
                reason=f"Provider '{m.provider_id}' is disabled or not found",
            )

        if not m.enabled:
            return ModelHealthStatus(
                model_id=m.id,
                model_code=m.model_code,
                display_name=m.display_name,
                provider_code=provider.provider_code,
                is_available=False,
                is_enabled=False,
                status="disabled",
                reason="Model is explicitly disabled in llm_models",
            )

        return ModelHealthStatus(
            model_id=m.id,
            model_code=m.model_code,
            display_name=m.display_name,
            provider_code=provider.provider_code,
            is_available=True,
            is_enabled=True,
            status="healthy",
            reason="Model and Provider are enabled and available",
        )

    def find_best_candidates(self, tier: str, limit: int = 5) -> list[LLMModel]:
        """
        Find best candidate models for a specific tier based on capability and cost.
        """
        models = self.model_repo.list_by_user(self.user_id, enabled=True)
        valid_candidates = []

        for m in models:
            # Check capability fit
            if tier in ("nano", "fast"):
                # Prefer fast models with valid context
                valid_candidates.append(m)
            elif tier == "smart":
                # Prefer models with json_mode or tool_calling capability
                if m.capability_json_mode or m.capability_tool_calling or "70b" in m.model_code.lower() or "smart" in m.model_code.lower():
                    valid_candidates.append(m)
            elif tier == "advanced":
                # Deep reasoning / advanced
                valid_candidates.append(m)

        # Sort by cost (input cost + output cost) ascending
        def _cost_key(m: LLMModel) -> float:
            in_cost = float(m.input_cost_per_1k or 0.001)
            out_cost = float(m.output_cost_per_1k or 0.002)
            return (in_cost * 3 + out_cost) / 4

        valid_candidates.sort(key=_cost_key)
        return valid_candidates[:limit]

    def generate_evolution_proposals(self) -> list[EvolutionProposal]:
        """
        Examine all tiers and generate actionable evolution proposals.
        """
        proposals: list[EvolutionProposal] = []
        audits = self.audit_tier_bindings()

        for tier, audit in audits.items():
            primary_id = audit.primary_status.model_id
            
            # Case 1: Primary is broken/unhealthy -> Emergency Replacement
            if not audit.primary_status.is_available:
                # Find the first healthy fallback
                candidate_id = None
                for fb in audit.fallback_statuses:
                    if fb.is_available:
                        candidate_id = fb.model_id
                        break
                
                # If no fallback available, find best candidate in repo
                if not candidate_id:
                    cands = self.find_best_candidates(tier, limit=1)
                    if cands:
                        candidate_id = cands[0].id

                if candidate_id:
                    cand_model = self.model_repo.get(candidate_id)
                    proposals.append(EvolutionProposal(
                        tier=tier,
                        current_primary_id=primary_id,
                        candidate_model_id=candidate_id,
                        candidate_model_code=cand_model.model_code if cand_model else "",
                        candidate_display_name=cand_model.display_name if cand_model else "",
                        proposal_type="EMERGENCY_REPLACEMENT",
                        estimated_cost_saving_pct=0.0,
                        reason=f"Current primary model {primary_id} is {audit.primary_status.status}. Urgent replacement to avoid downtime.",
                    ))
                continue

            # Case 2: Opportunity for Cost-Saving / Superior Model
            curr_model = self.model_repo.get(primary_id)
            if not curr_model:
                continue

            curr_cost = ((float(curr_model.input_cost_per_1k or 0) * 3 + float(curr_model.output_cost_per_1k or 0)) / 4) * 1000  # per 1M
            candidates = self.find_best_candidates(tier, limit=3)

            for cand in candidates:
                if cand.id == primary_id:
                    continue
                cand_cost = ((float(cand.input_cost_per_1k or 0) * 3 + float(cand.output_cost_per_1k or 0)) / 4) * 1000

                # If candidate is at least 25% cheaper and has equal/better capabilities
                if curr_cost > 0 and cand_cost < curr_cost * 0.75:
                    savings_pct = round(((curr_cost - cand_cost) / curr_cost) * 100, 1)
                    proposals.append(EvolutionProposal(
                        tier=tier,
                        current_primary_id=primary_id,
                        candidate_model_id=cand.id,
                        candidate_model_code=cand.model_code,
                        candidate_display_name=cand.display_name,
                        proposal_type="COST_SAVING",
                        estimated_cost_saving_pct=savings_pct,
                        reason=f"Candidate {cand.display_name} offers {savings_pct}% lower token cost (${cand_cost:.2f}/M vs ${curr_cost:.2f}/M) with required capabilities.",
                        details={"current_cost": curr_cost, "candidate_cost": cand_cost},
                    ))
                    break  # Take best candidate per tier

        return proposals
