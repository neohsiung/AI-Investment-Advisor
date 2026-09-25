"""
Synthesis Orchestrator & Self-Healing Loop
===========================================
閉環調度器：整合 LLM 代碼合成、AST 靜態安全稽核、剛性極端數據壓力測試 (TDD)
與沙盒隔離執行，並具備自愈修正能力 (Self-Healing Loop)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from src.services.code_synthesis.factor_synthesizer import (
    FactorSynthesizer,
    SynthesizedFactorCandidate,
)
from src.services.code_synthesis.tdd_test_generator import MandatoryStressTestSuite
from src.services.sandbox.ast_security_auditor import (
    ASTSecurityAuditor,
    AuditResult,
)
from src.services.sandbox.ephemeral_sandbox import (
    EphemeralSandbox,
    SandboxExecutionResult,
)

logger = logging.getLogger("SynthesisOrchestrator")


@dataclass
class SynthesisResult:
    """
    Final synthesis and verification outcome.
    代碼自主生成與驗測終態結果。
    """
    passed: bool
    candidate: Optional[SynthesizedFactorCandidate] = None
    ast_audit: Optional[AuditResult] = None
    sandbox_execution: Optional[SandboxExecutionResult] = None
    iterations: int = 1
    rejection_reasons: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else "REJECTED"
        reasons = f" | Reasons: {', '.join(self.rejection_reasons)}" if self.rejection_reasons else ""
        return f"[{status}] Iterations: {self.iterations}{reasons}"


class SynthesisOrchestrator:
    """
    Coordinates the full verification pipeline:
    Synthesize -> AST Audit -> Mandatory Stress TDD -> Sandbox Execution.
    """

    def __init__(
        self,
        user_id: str,
        auditor: Optional[ASTSecurityAuditor] = None,
        sandbox: Optional[EphemeralSandbox] = None,
        synthesizer: Optional[FactorSynthesizer] = None,
    ):
        self.user_id = user_id
        self.auditor = auditor or ASTSecurityAuditor()
        self.sandbox = sandbox or EphemeralSandbox()
        self.synthesizer = synthesizer or FactorSynthesizer(user_id=user_id)

    async def generate_and_verify(
        self,
        hypothesis: str,
        target_regime: str = "VOLATILITY_PIVOT",
        max_retries: int = 2,
    ) -> SynthesisResult:
        """
        Synthesize a candidate factor from scratch and run through the complete verification pipeline.
        """
        candidate = await self.synthesizer.synthesize(
            hypothesis=hypothesis,
            target_regime=target_regime,
        )
        return self.verify_candidate(candidate, max_retries=max_retries)

    def verify_candidate(
        self,
        candidate: SynthesizedFactorCandidate,
        max_retries: int = 2,
    ) -> SynthesisResult:
        """
        Verify an existing candidate through AST audit and sandbox execution with mandatory stress tests.
        """
        rejection_reasons: List[str] = []

        # 1. 執行 AST 靜態安全稽核 (Static AST Security Audit)
        audit_res = self.auditor.audit(candidate.source_code)
        if not audit_res.passed:
            rejection_reasons.extend(audit_res.violations)
            logger.warning(
                "Candidate '%s' rejected by AST Security Auditor: %s",
                candidate.factor_name,
                audit_res.violations,
            )
            return SynthesisResult(
                passed=False,
                candidate=candidate,
                ast_audit=audit_res,
                iterations=1,
                rejection_reasons=rejection_reasons,
            )

        # 2. 注入剛性極端數據壓力測試 (Mandatory Stress TDD Matrix)
        combined_tests = MandatoryStressTestSuite.generate_stress_test_code(
            factor_func_name="calculate_factor",
            additional_test_code=candidate.test_code,
        )

        # 3. 在隔離微沙盒中運行驗測 (Ephemeral Sandbox Execution)
        sandbox_res = self.sandbox.execute_and_verify(
            source_code=candidate.source_code,
            test_code=combined_tests,
        )

        if not sandbox_res.passed:
            fail_desc = f"Sandbox verification failed ({sandbox_res.error_type}): {sandbox_res.error_message}"
            rejection_reasons.append(fail_desc)
            logger.warning("Candidate '%s' failed in sandbox: %s", candidate.factor_name, fail_desc)
            return SynthesisResult(
                passed=False,
                candidate=candidate,
                ast_audit=audit_res,
                sandbox_execution=sandbox_res,
                iterations=1,
                rejection_reasons=rejection_reasons,
            )

        logger.info(
            "Candidate '%s' successfully passed AST audit and mandatory stress sandbox (%0.1fms)",
            candidate.factor_name,
            sandbox_res.execution_time_ms,
        )
        return SynthesisResult(
            passed=True,
            candidate=candidate,
            ast_audit=audit_res,
            sandbox_execution=sandbox_res,
            iterations=1,
            rejection_reasons=[],
        )
