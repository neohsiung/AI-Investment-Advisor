"""
Code Synthesis & Autonomous Verification Package
================================================
提供量化因子與策略程式碼自主合成、雙生 TDD 測試生成與閉環自我修復 (Self-Healing) 機制。
"""
from src.services.code_synthesis.factor_synthesizer import (
    FactorSynthesizer,
    SynthesizedFactorCandidate,
)
from src.services.code_synthesis.synthesis_orchestrator import (
    SynthesisOrchestrator,
    SynthesisResult,
)
from src.services.code_synthesis.tdd_test_generator import (
    MandatoryStressTestSuite,
)

__all__ = [
    "FactorSynthesizer",
    "SynthesizedFactorCandidate",
    "SynthesisOrchestrator",
    "SynthesisResult",
    "MandatoryStressTestSuite",
]
