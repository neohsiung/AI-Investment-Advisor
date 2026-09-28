"""
Unit Tests for FactorSynthesizer & SynthesisOrchestrator
========================================================
驗測因子合成解析、AST 審計串接、剛性壓力測試與沙盒執行之閉環流程。
"""
import pytest
from src.services.code_synthesis.factor_synthesizer import (
    FactorSynthesizer,
    SynthesizedFactorCandidate,
)
from src.services.code_synthesis.synthesis_orchestrator import (
    SynthesisOrchestrator,
)
from src.services.code_synthesis.tdd_test_generator import MandatoryStressTestSuite


@pytest.fixture
def synthesizer() -> FactorSynthesizer:
    return FactorSynthesizer(user_id="test_user_001")


@pytest.fixture
def orchestrator() -> SynthesisOrchestrator:
    return SynthesisOrchestrator(user_id="test_user_001")


def test_factor_synthesizer_parses_json(synthesizer: FactorSynthesizer):
    sample_json = """
    ```json
    {
      "factor_name": "rsi_rebound_score",
      "description": "Calculates RSI oversold rebound momentum",
      "source_code": "def calculate_factor(df, p=None): return df['Close']",
      "test_code": "def test_foo(): pass",
      "parameters": {"rsi_period": 14},
      "target_regimes": ["VOLATILITY_PIVOT"]
    }
    ```
    """
    candidate = synthesizer._parse_response(sample_json, default_regime="NORMAL")
    assert candidate.factor_name == "rsi_rebound_score"
    assert candidate.parameters["rsi_period"] == 14
    assert candidate.target_regimes == ["VOLATILITY_PIVOT"]


def test_mandatory_stress_test_suite_generation():
    test_code = MandatoryStressTestSuite.generate_stress_test_code("calculate_factor")
    assert "test_stress_empty_dataframe" in test_code
    assert "test_stress_all_nan_dataframe" in test_code
    assert "test_stress_flash_crash_outlier" in test_code
    assert "test_stress_zero_variance_flatline" in test_code
    assert "test_stress_output_series_integrity" in test_code


def test_orchestrator_verifies_robust_factor(orchestrator: SynthesisOrchestrator):
    # Fully compliant factor that properly handles all 5 stress conditions
    valid_source = """
import numpy as np
import pandas as pd

def calculate_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:
    if df.empty or 'Close' not in df.columns:
        return pd.Series(dtype=float)
    params = params or {}
    window = int(params.get('window', 5))
    close = df['Close']
    mom = close - close.shift(window)
    std = close.rolling(window=window).std().replace(0, np.nan)
    norm = (mom / std).fillna(0.0)
    norm.index = df.index
    return norm
"""
    candidate = SynthesizedFactorCandidate(
        factor_name="test_robust_factor",
        description="Robust normalized momentum",
        source_code=valid_source,
        test_code="",
        parameters={"window": 5},
        target_regimes=["VOLATILITY_PIVOT"],
    )

    result = orchestrator.verify_candidate(candidate)
    assert result.passed is True
    assert result.ast_audit is not None
    assert result.ast_audit.passed is True
    assert result.sandbox_execution is not None
    assert result.sandbox_execution.passed is True
    assert len(result.rejection_reasons) == 0


def test_orchestrator_rejects_ast_violation(orchestrator: SynthesisOrchestrator):
    # Violates AST rules (imports os, calls system)
    bad_source = """
import os
import pandas as pd

def calculate_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:
    os.system("echo hacked")
    return pd.Series(dtype=float)
"""
    candidate = SynthesizedFactorCandidate(
        factor_name="malicious_factor",
        description="Tries to call os.system",
        source_code=bad_source,
        test_code="",
    )

    result = orchestrator.verify_candidate(candidate)
    assert result.passed is False
    assert result.ast_audit is not None
    assert result.ast_audit.passed is False
    assert any("Forbidden module import" in r for r in result.rejection_reasons)
    # Sandbox was NOT even executed because AST rejected it first
    assert result.sandbox_execution is None


def test_orchestrator_rejects_fragile_factor_failing_stress(orchestrator: SynthesisOrchestrator):
    # Fragile factor that crashes on empty DataFrame (KeyError)
    fragile_source = """
import numpy as np
import pandas as pd

def calculate_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:
    # Does not check df.empty or missing Close column!
    return df['Close'] * 2.0
"""
    candidate = SynthesizedFactorCandidate(
        factor_name="fragile_factor",
        description="Crashes on empty dataframe",
        source_code=fragile_source,
        test_code="",
    )

    result = orchestrator.verify_candidate(candidate)
    assert result.passed is False
    # AST passes because syntax and imports are allowed
    assert result.ast_audit.passed is True
    # But Sandbox stress test catches the failure!
    assert result.sandbox_execution.passed is False
    assert any("Sandbox verification failed" in r for r in result.rejection_reasons)
