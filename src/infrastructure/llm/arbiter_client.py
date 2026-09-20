"""
Arbiter Client — Anti-Corruption Layer for Structured Decision & Escalation.
裁決防腐層客戶端：負責毫秒級強型別條件裁決 (Reflex) 與深度審思 (Deliberator) 雙軌升級。

遵循 SOLID 原則:
  - SRP: 封裝 Reflex 決策、校準機率門檻判定、斷路器與語意升級
  - DIP: 業務層僅依賴此 Client，不直接耦合底層 HTTP 或特定模型 API
"""

import time
import uuid
import logging
from typing import Dict, Any, Optional, Union
from pydantic import BaseModel, Field
import httpx

from src.infrastructure.llm.security_sanitizer import HighAssuranceSanitizer
from src.infrastructure.llm.audit_trail import ZeroKnowledgeAuditor

logger = logging.getLogger(__name__)

class ArbiterDecision(BaseModel):
    decision_id: str
    choice: Any
    confidence: float
    is_escalated: bool = False
    tier: str = "reflex"
    escalation_reason: Optional[str] = None
    state_hash: Optional[str] = None
    latency_ms: float = 0.0
    probabilities: Optional[Dict[str, float]] = None

class ArbiterClient:
    """
    符合 SOLID 原則之條件裁決客戶端。
    """

    def __init__(
        self,
        litellm_base_url: str = "http://localhost:4000",
        llm_gateway: Optional[Any] = None,
        sanitizer: Optional[HighAssuranceSanitizer] = None,
        auditor: Optional[ZeroKnowledgeAuditor] = None,
        failure_threshold: int = 3,
        circuit_recovery_time_sec: float = 60.0
    ):
        self.litellm_base_url = litellm_base_url.rstrip("/")
        self.decision_endpoint = f"{self.litellm_base_url}/decisions/v1"
        self.llm_gateway = llm_gateway
        self.sanitizer = sanitizer or HighAssuranceSanitizer()
        self.auditor = auditor or ZeroKnowledgeAuditor()

        # 斷路器狀態
        self._circuit_state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_time = circuit_recovery_time_sec
        self._last_state_change = time.time()

    async def decide(
        self,
        domain: str,
        state: Dict[str, Any],
        question_key: str,
        question_spec: Dict[str, Any],
        confidence_threshold: float = 0.92,
        system2_fallback_prompt: Optional[str] = None,
        deterministic_default: Optional[Any] = None,
        timeout_ms: int = 800
    ) -> ArbiterDecision:
        """
        發起條件裁決主進入點。
        1. 脫敏與特徵化
        2. 嘗試 Reflex (Jev)
        3. 驗證校準機率
        4. 必要時自動語意升級至 System 2 (Deliberator)
        """
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        start_time = time.perf_counter()

        # 1. 本地高強度脫敏與特徵抽象化
        sanitized_state = self.sanitizer.sanitize(state)

        # 2. 檢查斷路器狀態
        now = time.time()
        should_bypass_reflex = False
        if self._circuit_state == "OPEN":
            if now - self._last_state_change > self._recovery_time:
                self._circuit_state = "HALF_OPEN"
                logger.info(f"ArbiterClient: Circuit entering HALF_OPEN for probe.")
            else:
                should_bypass_reflex = True

        # 3. 嘗試 Reflex (Jev 1.13 via LiteLLM /decisions/v1)
        if not should_bypass_reflex:
            try:
                decision = await self._call_reflex_api(
                    decision_id=decision_id,
                    domain=domain,
                    sanitized_state=sanitized_state,
                    question_key=question_key,
                    question_spec=question_spec,
                    confidence_threshold=confidence_threshold,
                    timeout_ms=timeout_ms,
                    start_time=start_time
                )
                if decision:
                    # 成功回傳且信心度達標
                    if self._circuit_state == "HALF_OPEN":
                        self._circuit_state = "CLOSED"
                        self._failure_count = 0
                        logger.info("ArbiterClient: Circuit recovered to CLOSED.")
                    return decision
            except Exception as e:
                self._failure_count += 1
                logger.warning(
                    f"ArbiterClient: Reflex call failed ({self._failure_count}/{self._failure_threshold}): {e}"
                )
                if self._failure_count >= self._failure_threshold:
                    self._circuit_state = "OPEN"
                    self._last_state_change = time.time()
                    logger.error("ArbiterClient: Circuit breaker TRIPPED to OPEN!")

        # 4. 若未達標或拋出異常，啟動語意升級 (System 2 Fallback)
        escalation_reason = (
            "Circuit OPEN" if should_bypass_reflex else "Reflex low confidence or error"
        )
        return await self._escalate_to_system2(
            decision_id=decision_id,
            domain=domain,
            sanitized_state=sanitized_state,
            question_key=question_key,
            system2_fallback_prompt=system2_fallback_prompt,
            deterministic_default=deterministic_default,
            escalation_reason=escalation_reason,
            start_time=start_time
        )

    async def _call_reflex_api(
        self,
        decision_id: str,
        domain: str,
        sanitized_state: Dict[str, Any],
        question_key: str,
        question_spec: Dict[str, Any],
        confidence_threshold: float,
        timeout_ms: int,
        start_time: float
    ) -> Optional[ArbiterDecision]:
        payload = {
            "model": "typesafe/jev-1.13",
            "state": sanitized_state,
            "questions": {question_key: question_spec}
        }

        timeout_sec = timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.post(self.decision_endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", {})
        if question_key not in results:
            raise ValueError(f"Response missing question key '{question_key}': {data}")

        q_res = results[question_key]
        answer = q_res.get("answer")
        confidence = float(q_res.get("confidence", 1.0))
        probabilities = q_res.get("probabilities")
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 校準機率門檻裁決
        if confidence >= confidence_threshold:
            state_hash = self.auditor.record_decision(
                decision_id=decision_id,
                domain=domain,
                sanitized_state=sanitized_state,
                question_key=question_key,
                choice=answer,
                confidence=confidence,
                is_escalated=False,
                tier="reflex",
                latency_ms=latency_ms,
                extra_meta={"probabilities": probabilities}
            )

            return ArbiterDecision(
                decision_id=decision_id,
                choice=answer,
                confidence=confidence,
                is_escalated=False,
                tier="reflex",
                state_hash=state_hash,
                latency_ms=latency_ms,
                probabilities=probabilities
            )

        # 信心度不足，回傳 None 讓流程進入升級
        logger.info(
            f"ArbiterClient: [{domain}] Reflex confidence {confidence:.2f} < threshold {confidence_threshold:.2f}."
        )
        return None

    async def _escalate_to_system2(
        self,
        decision_id: str,
        domain: str,
        sanitized_state: Dict[str, Any],
        question_key: str,
        system2_fallback_prompt: Optional[str],
        deterministic_default: Optional[Any],
        escalation_reason: str,
        start_time: float
    ) -> ArbiterDecision:
        """語意升級至 System 2 生成模型或保底決策"""
        if self.llm_gateway and system2_fallback_prompt:
            try:
                from src.domain.interfaces import Message, LLMConfig
                from src.infrastructure.llm.tier_config import TierConfig
                from src.utils.json_utils import json_loads_safe

                tc = TierConfig()
                smart_model = tc.resolve("smart") or "gpt-oss-120b"
                cfg = LLMConfig(provider="openrouter", model=smart_model, temperature=0.1)

                messages = [
                    Message(role="system", content="You are a precise investment and risk decision arbiter."),
                    Message(role="user", content=system2_fallback_prompt)
                ]

                raw_output = await self.llm_gateway.chat(messages, cfg)
                parsed = json_loads_safe(raw_output)
                
                if isinstance(parsed, dict) and question_key in parsed:
                    choice = parsed[question_key]
                elif isinstance(parsed, dict) and "choice" in parsed:
                    choice = parsed["choice"]
                else:
                    choice = raw_output.strip()

                latency_ms = (time.perf_counter() - start_time) * 1000.0
                state_hash = self.auditor.record_decision(
                    decision_id=decision_id,
                    domain=domain,
                    sanitized_state=sanitized_state,
                    question_key=question_key,
                    choice=choice,
                    confidence=0.85,  # System 2 基準置信度
                    is_escalated=True,
                    tier="smart_deliberator",
                    latency_ms=latency_ms,
                    extra_meta={"escalation_reason": escalation_reason}
                )

                return ArbiterDecision(
                    decision_id=decision_id,
                    choice=choice,
                    confidence=0.85,
                    is_escalated=True,
                    tier="smart_deliberator",
                    escalation_reason=escalation_reason,
                    state_hash=state_hash,
                    latency_ms=latency_ms
                )
            except Exception as e:
                logger.error(f"ArbiterClient: System 2 escalation failed: {e}")

        # 保底規則（Deterministic Default）
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        final_choice = deterministic_default if deterministic_default is not None else "UNKNOWN"
        state_hash = self.auditor.record_decision(
            decision_id=decision_id,
            domain=domain,
            sanitized_state=sanitized_state,
            question_key=question_key,
            choice=final_choice,
            confidence=0.50,
            is_escalated=True,
            tier="deterministic_fallback",
            latency_ms=latency_ms,
            extra_meta={"escalation_reason": escalation_reason}
        )

        return ArbiterDecision(
            decision_id=decision_id,
            choice=final_choice,
            confidence=0.50,
            is_escalated=True,
            tier="deterministic_fallback",
            escalation_reason=escalation_reason,
            state_hash=state_hash,
            latency_ms=latency_ms
        )
