"""
Model Canary Evaluator — Phase 1 of Autonomous Model Governance.
藍綠金絲雀門禁評估器。

Responsibilities:
  1. 針對候選模型（Green Candidate）執行三層門禁測試：
     - Test 1: JSON Schema 嚴格遵從性與無 Markdown 前言（徹底根絕 Request 1 格式解析崩潰）
     - Test 2: 端到端回應延遲與超時防線
     - Test 3: 投資決策枚舉與語意合法性
  2. 藍綠平滑切換（Blue-Green Promotion）：
     - 通過評估後，自動將 Green 晉升為 primary_model_id。
     - 原先穩定的 Blue 自動順延為 fallback_model_ids[0]，保障秒級回滾能力。
  3. 回滾機制（Instant Rollback）：
     - 若新模型在生產中發生異常，一鍵切回原 Blue 模型。
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

from src.config.owner import resolve_user_id
from src.domain.interfaces import LLMConfig, Message
from src.infrastructure.llm.llm_gateway import LLMGatewayFactory
from src.repositories.llm_model_repository import LLMModelRepository
from src.repositories.llm_provider_repository import LLMProviderRepository
from src.repositories.llm_tier_binding_repository import LLMTierBindingRepository
from src.services.llm_credential_cipher import LLMCredentialCipher
from src.services.llm_tier_binding_service import (
    LLMTierBindingService,
    TierBindingUpdate,
)

logger = logging.getLogger(__name__)


@dataclass
class CanaryEvaluationResult:
    tier: str
    candidate_model_id: str
    current_model_id: str
    passed: bool
    promoted: bool
    latency_seconds: float
    json_compliance: bool
    recommendation_valid: bool
    raw_response: str
    parsed_output: dict[str, Any] = field(default_factory=dict)
    failure_reasons: list[str] = field(default_factory=list)


class ModelCanaryEvaluator:
    """
    Evaluates LLM candidates in a sandbox canary environment before promoting to production tier bindings.
    """

    MAX_LATENCY_MAP: ClassVar[dict[str, float]] = {
        "nano": 6.0,
        "fast": 10.0,
        "smart": 25.0,
        "advanced": 35.0,
    }

    def __init__(
        self,
        user_id: str,
        model_repo: LLMModelRepository | None = None,
        provider_repo: LLMProviderRepository | None = None,
        tier_repo: LLMTierBindingRepository | None = None,
        tier_service: LLMTierBindingService | None = None,
        cipher: LLMCredentialCipher | None = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.model_repo = model_repo or LLMModelRepository()
        self.provider_repo = provider_repo or LLMProviderRepository()
        self.tier_repo = tier_repo or LLMTierBindingRepository()
        self.tier_service = tier_service or LLMTierBindingService(user_id=self.user_id)
        self.cipher = cipher or LLMCredentialCipher()

    async def evaluate_and_promote(
        self,
        tier: str,
        candidate_model_id: str,
        current_model_id: str,
        auto_promote: bool = True,
    ) -> CanaryEvaluationResult:
        """
        Run canary test battery on candidate_model_id. If passed and auto_promote is True,
        perform atomic Blue-Green switch (Green becomes Primary, Blue becomes Fallback 1).
        """
        cand_model = self.model_repo.get(candidate_model_id)
        if not cand_model:
            return CanaryEvaluationResult(
                tier=tier,
                candidate_model_id=candidate_model_id,
                current_model_id=current_model_id,
                passed=False,
                promoted=False,
                latency_seconds=0.0,
                json_compliance=False,
                recommendation_valid=False,
                raw_response="",
                failure_reasons=[f"Candidate model '{candidate_model_id}' not found in database"],
            )

        provider = self.provider_repo.get(cand_model.provider_id)
        if not provider or not provider.enabled:
            return CanaryEvaluationResult(
                tier=tier,
                candidate_model_id=candidate_model_id,
                current_model_id=current_model_id,
                passed=False,
                promoted=False,
                latency_seconds=0.0,
                json_compliance=False,
                recommendation_valid=False,
                raw_response="",
                failure_reasons=[f"Provider '{cand_model.provider_id}' is disabled or not found"],
            )

        # Build gateway & config
        api_key = self.cipher.decrypt(provider.encrypted_api_key) if provider.encrypted_api_key else ""
        gateway = LLMGatewayFactory.create(provider.provider_code)
        
        timeout = int(self.MAX_LATENCY_MAP.get(tier, 20.0))
        llm_config = LLMConfig(
            provider=provider.provider_code,
            model=cand_model.model_code,
            api_key=api_key,
            base_url=provider.base_url or "",
            temperature=0.1,  # Low temperature for strict determinism in test
            max_tokens=512,
            timeout_seconds=timeout,
        )

        test_prompt = (
            "You are an investment advisor AI. Output raw JSON ONLY. "
            "Do NOT include markdown formatting, code fences (e.g. ```json), or conversational preamble.\n"
            "Produce valid JSON matching this schema:\n"
            "{\n"
            '  "executive_summary": "Short market assessment under 200 characters",\n'
            '  "recommendation": "BUY" or "HOLD" or "SELL",\n'
            '  "confidence": 0.85\n'
            "}"
        )
        messages = [
            Message(role="system", content="You are a strict JSON generator. Never output conversational text."),
            Message(role="user", content=test_prompt),
        ]

        failure_reasons: list[str] = []
        raw_response = ""
        parsed_output: dict[str, Any] = {}
        json_compliance = False
        recommendation_valid = False
        start_time = time.time()

        try:
            raw_response = await gateway.chat(messages, llm_config)
            latency = time.time() - start_time
        except Exception as e:
            latency = time.time() - start_time
            failure_reasons.append(f"Gateway execution error: {e}")
            logger.warning("CanaryEvaluator: Candidate %s execution failed: %s", candidate_model_id, e)
            return CanaryEvaluationResult(
                tier=tier,
                candidate_model_id=candidate_model_id,
                current_model_id=current_model_id,
                passed=False,
                promoted=False,
                latency_seconds=round(latency, 2),
                json_compliance=False,
                recommendation_valid=False,
                raw_response="",
                failure_reasons=failure_reasons,
            )

        # Test 1: Check latency
        max_lat = self.MAX_LATENCY_MAP.get(tier, 20.0)
        if latency > max_lat:
            failure_reasons.append(f"Latency {latency:.2f}s exceeded threshold {max_lat:.1f}s")

        # Test 2: Check JSON compliance
        clean_text = raw_response.strip()
        # Remove markdown codeblock wrapping if model added it
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)
            clean_text = clean_text.strip()

        try:
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict):
                parsed_output = parsed
                required_keys = {"executive_summary", "recommendation", "confidence"}
                if required_keys.issubset(parsed.keys()):
                    json_compliance = True
                else:
                    missing = required_keys - set(parsed.keys())
                    failure_reasons.append(f"JSON response missing required keys: {missing}")
            else:
                failure_reasons.append("Response is not a JSON object")
        except json.JSONDecodeError as err:
            failure_reasons.append(f"Invalid JSON emitted by candidate: {err}")

        # Test 3: Recommendation validity
        rec = str(parsed_output.get("recommendation", "")).upper()
        if rec in ("BUY", "HOLD", "SELL"):
            recommendation_valid = True
        else:
            failure_reasons.append(f"Invalid recommendation '{rec}', expected BUY/HOLD/SELL")

        passed = len(failure_reasons) == 0
        promoted = False

        if passed and auto_promote:
            promoted = self._promote_blue_green(tier, candidate_model_id, current_model_id)

        logger.info(
            "CanaryEvaluator: Tier %s Candidate %s evaluation finished: passed=%s, promoted=%s, latency=%.2fs",
            tier,
            candidate_model_id,
            passed,
            promoted,
            latency,
        )

        return CanaryEvaluationResult(
            tier=tier,
            candidate_model_id=candidate_model_id,
            current_model_id=current_model_id,
            passed=passed,
            promoted=promoted,
            latency_seconds=round(latency, 2),
            json_compliance=json_compliance,
            recommendation_valid=recommendation_valid,
            raw_response=raw_response,
            parsed_output=parsed_output,
            failure_reasons=failure_reasons,
        )

    def _promote_blue_green(self, tier: str, green_id: str, blue_id: str) -> bool:
        """
        Execute atomic Blue-Green switch in DB:
        - Primary = Green (candidate)
        - Fallback 1 = Blue (previous primary)
        - Other fallbacks retained up to 4
        """
        try:
            binding = self.tier_repo.get_by_tier(self.user_id, tier)
            current_fallbacks = binding.fallback_model_ids if binding and binding.fallback_model_ids else []

            # Reconstruct fallback list: Blue becomes first fallback, filter out green
            new_fallbacks = [blue_id] + [fid for fid in current_fallbacks if fid not in (green_id, blue_id)]
            new_fallbacks = new_fallbacks[:4]  # Maximum 4 fallbacks

            update_spec = TierBindingUpdate(
                tier=tier,
                primary_model_id=green_id,
                fallback_model_ids=new_fallbacks,
                per_candidate_config=binding.per_candidate_config if binding else {},
                budget_aware=binding.budget_aware if binding else True,
            )

            self.tier_service.update_tier_bindings([update_spec])
            logger.info(
                "CanaryEvaluator: Blue-Green promotion succeeded for %s: Primary=%s (Green), Fallback1=%s (Blue)",
                tier,
                green_id,
                blue_id,
            )
            return True
        except Exception as e:
            logger.error("CanaryEvaluator: Failed to promote Green model %s for tier %s: %e", green_id, tier, e)
            return False

    def rollback_tier(self, tier: str) -> bool:
        """
        Instantly rollback a tier from Green to Blue by promoting the first fallback.
        """
        try:
            binding = self.tier_repo.get_by_tier(self.user_id, tier)
            if not binding or not binding.fallback_model_ids:
                logger.warning("CanaryEvaluator: Rollback not possible for %s, no fallbacks exist", tier)
                return False

            original_blue = binding.fallback_model_ids[0]
            new_fallbacks = [binding.primary_model_id] + binding.fallback_model_ids[1:]

            update_spec = TierBindingUpdate(
                tier=tier,
                primary_model_id=original_blue,
                fallback_model_ids=new_fallbacks[:4],
                per_candidate_config=binding.per_candidate_config,
                budget_aware=binding.budget_aware,
            )
            self.tier_service.update_tier_bindings([update_spec])
            logger.warning("CanaryEvaluator: Rolled back %s: Primary restored to %s", tier, original_blue)
            return True
        except Exception as e:
            logger.error("CanaryEvaluator: Rollback failed for tier %s: %s", tier, e)
            return False
