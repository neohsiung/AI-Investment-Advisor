"""
Unit Tests for EphemeralSandbox
================================
驗測微沙盒隔離執行器之執行結果、單元測試運行、網路阻斷防護與逾時終止機制。
"""
import pytest
from src.services.sandbox.ephemeral_sandbox import EphemeralSandbox


@pytest.fixture
def sandbox() -> EphemeralSandbox:
    return EphemeralSandbox(timeout_sec=2.0)


def test_sandbox_runs_valid_factor_and_test(sandbox: EphemeralSandbox):
    factor_code = """
import pandas as pd
import numpy as np

def calculate_sma(df: pd.DataFrame, window: int = 5) -> pd.Series:
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    return df["Close"].rolling(window=window).mean()
"""

    test_code = """
import pandas as pd
import numpy as np
from factor_module import calculate_sma

def test_sma_calculation():
    df = pd.DataFrame({"Close": [10.0, 20.0, 30.0, 40.0, 50.0]})
    sma = calculate_sma(df, window=3)
    assert len(sma) == 5
    assert np.isnan(sma.iloc[0])
    assert sma.iloc[2] == 20.0
    assert sma.iloc[4] == 40.0

def test_sma_empty():
    df = pd.DataFrame()
    res = calculate_sma(df)
    assert res.empty
"""

    result = sandbox.execute_and_verify(factor_code, test_code)
    assert result.passed is True
    assert result.return_code == 0
    assert result.execution_time_ms > 0
    assert result.error_type is None


def test_sandbox_catches_failing_test(sandbox: EphemeralSandbox):
    factor_code = """
def calculate_wrong() -> int:
    return 42
"""
    test_code = """
from factor_module import calculate_wrong

def test_will_fail():
    assert calculate_wrong() == 100
"""
    result = sandbox.execute_and_verify(factor_code, test_code)
    assert result.passed is False
    assert result.return_code != 0
    assert result.error_type == "TestFailure"


def test_sandbox_blocks_network_socket(sandbox: EphemeralSandbox):
    factor_code = """
def try_network():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    return s
"""
    test_code = """
import pytest
from factor_module import try_network

def test_network_is_blocked():
    with pytest.raises(PermissionError, match="Network access is strictly forbidden"):
        try_network()
"""
    result = sandbox.execute_and_verify(factor_code, test_code)
    assert result.passed is True
    assert result.return_code == 0


def test_sandbox_terminates_on_timeout(sandbox: EphemeralSandbox):
    factor_code = """
import time

def infinite_delay():
    time.sleep(5.0)
    return 1
"""
    test_code = """
from factor_module import infinite_delay

def test_timeout():
    infinite_delay()
"""
    # 設置超時 0.5s
    result = sandbox.execute_and_verify(factor_code, test_code, timeout_sec=0.5)
    assert result.passed is False
    assert result.error_type == "TimeoutExpired"
    assert "exceeded strict timeout" in result.error_message
