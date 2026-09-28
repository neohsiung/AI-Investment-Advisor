"""
Mandatory Stress Test Suite & TDD Generator for Autonomous Factors
===================================================================
針對 AI 自主生成的量化因子純函式，提供剛性強制注入的四大極端數據壓力測試矩陣：
1. 零長度空輸入 (Empty Data Stress)
2. 全 NaN/缺失值 (All NaNs Data Stress)
3. 極端閃崩/肥尾跳空 (Flash Crash Outlier Stress)
4. 零變異度死水盤 (Zero Variance Flatline Stress - 防除以零)
5. 索引與維度一致性 (Output Index & Series Shape Alignment)
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("TDDGenerator")


class MandatoryStressTestSuite:
    """
    Generates deterministic pytest test suites that subject candidate factor code
    to extreme market data anomalies and structural edge cases.
    """

    @classmethod
    def generate_stress_test_code(
        cls,
        factor_func_name: str = "calculate_factor",
        additional_test_code: Optional[str] = None,
    ) -> str:
        """
        Generate complete pytest module containing mandatory stress test cases.
        """
        base_stress_tests = f"""
import numpy as np
import pandas as pd
import pytest
from factor_module import {factor_func_name}

def _make_sample_df(n_rows: int = 30) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_rows, freq="D")
    base_price = 100.0 + np.cumsum(np.random.normal(0, 1, n_rows))
    return pd.DataFrame({{
        "Open": base_price,
        "High": base_price + 2.0,
        "Low": base_price - 2.0,
        "Close": base_price + 0.5,
        "Volume": np.random.randint(1000, 50000, n_rows),
    }}, index=dates)

def test_stress_empty_dataframe():
    \"\"\"1. Empty DataFrame Stress: Must safely return empty Series without crashing.\"\"\"
    df = pd.DataFrame()
    res = {factor_func_name}(df)
    assert isinstance(res, pd.Series), "Must return a pd.Series"
    assert res.empty or len(res) == 0, "Empty DataFrame must return empty Series"

def test_stress_all_nan_dataframe():
    \"\"\"2. All NaNs Stress: Must handle missing values cleanly without raising unhandled exceptions.\"\"\"
    dates = pd.date_range("2024-01-01", periods=20, freq="D")
    df = pd.DataFrame({{
        "Open": [np.nan] * 20,
        "High": [np.nan] * 20,
        "Low": [np.nan] * 20,
        "Close": [np.nan] * 20,
        "Volume": [np.nan] * 20,
    }}, index=dates)
    res = {factor_func_name}(df)
    assert isinstance(res, pd.Series)
    assert len(res) == len(df)

def test_stress_flash_crash_outlier():
    \"\"\"3. Flash Crash Outlier: Extreme +/- 50% jumps must not cause inf, overflow, or crash.\"\"\"
    df = _make_sample_df(50)
    # Inject sudden -50% flash crash on bar 25
    df.iloc[25, df.columns.get_loc("Close")] = df.iloc[24]["Close"] * 0.50
    # Inject sudden +100% surge on bar 35
    df.iloc[35, df.columns.get_loc("Close")] = df.iloc[34]["Close"] * 2.00
    res = {factor_func_name}(df)
    assert isinstance(res, pd.Series)
    assert len(res) == len(df)
    # Check no positive/negative infinity leaked through unhandled
    clean_vals = res.dropna()
    if not clean_vals.empty:
        assert not np.isinf(clean_vals).any(), "Factor output contains unhandled inf or -inf"

def test_stress_zero_variance_flatline():
    \"\"\"4. Zero Variance Flatline: Identical prices across 50 bars (must not divide by zero).\"\"\"
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame({{
        "Open": [100.0] * 50,
        "High": [100.0] * 50,
        "Low": [100.0] * 50,
        "Close": [100.0] * 50,
        "Volume": [1000] * 50,
    }}, index=dates)
    res = {factor_func_name}(df)
    assert isinstance(res, pd.Series)
    assert len(res) == len(df)
    clean_vals = res.dropna()
    if not clean_vals.empty:
        assert not np.isinf(clean_vals).any(), "Zero variance caused divide-by-zero inf"

def test_stress_output_series_integrity():
    \"\"\"5. Output Integrity: pd.Series output must match input index and length.\"\"\"
    df = _make_sample_df(40)
    res = {factor_func_name}(df)
    assert isinstance(res, pd.Series), "Return value must be a pd.Series"
    assert len(res) == len(df), f"Output length {{len(res)}} does not match input {{len(df)}}"
    assert res.index.equals(df.index), "Output index does not match input DataFrame index"
"""
        if additional_test_code and additional_test_code.strip():
            return f"{base_stress_tests}\n\n# --- Additional LLM Generated Tests ---\n{additional_test_code.strip()}\n"
        return base_stress_tests
