"""
Unit Tests for ASTSecurityAuditor
=================================
驗測 AST 靜態語法審計器之安全性、白名單過濾、終止性保證與 Constraint #0 防護。
"""
import pytest
from src.services.sandbox.ast_security_auditor import ASTSecurityAuditor


@pytest.fixture
def auditor() -> ASTSecurityAuditor:
    return ASTSecurityAuditor()


def test_valid_pure_factor_code_passes(auditor: ASTSecurityAuditor):
    code = """
import numpy as np
import pandas as pd

def calculate_momentum_factor(df: pd.DataFrame, window: int = 14) -> pd.Series:
    \"\"\"Calculate pure momentum factor.\"\"\"
    if df.empty or "Close" not in df.columns:
        return pd.Series(dtype=float)
    close = df["Close"]
    return (close / close.shift(window) - 1.0).fillna(0.0)
"""
    result = auditor.audit(code)
    assert result.passed is True
    assert len(result.violations) == 0
    assert "calculate_momentum_factor" in result.metrics["functions"]
    assert len(result.ast_hash) == 64


def test_forbidden_module_imports_blocked(auditor: ASTSecurityAuditor):
    forbidden_snippets = [
        "import os\ndef test() -> None: pass",
        "import sys\ndef test() -> None: pass",
        "import subprocess\ndef test() -> None: pass",
        "import requests\ndef test() -> None: pass",
        "from socket import socket\ndef test() -> None: pass",
        "import urllib.request\ndef test() -> None: pass",
    ]
    for code in forbidden_snippets:
        result = auditor.audit(code)
        assert result.passed is False
        assert any("Forbidden module import" in v for v in result.violations)


def test_forbidden_calls_blocked(auditor: ASTSecurityAuditor):
    forbidden_snippets = [
        "def test() -> None:\n    open('test.txt', 'w')",
        "def test() -> None:\n    eval('2 + 2')",
        "def test() -> None:\n    exec('x = 1')",
        "def test() -> None:\n    globals()['a'] = 1",
        "def test() -> None:\n    __import__('os')",
    ]
    for code in forbidden_snippets:
        result = auditor.audit(code)
        assert result.passed is False
        assert any("Forbidden function call" in v for v in result.violations)


def test_forbidden_attributes_and_reflection_blocked(auditor: ASTSecurityAuditor):
    code = """
def exploit() -> None:
    x = ().__class__.__bases__[0].__subclasses__()
"""
    result = auditor.audit(code)
    assert result.passed is False
    assert any("Forbidden attribute" in v for v in result.violations)


def test_while_loops_blocked(auditor: ASTSecurityAuditor):
    code = """
def infinite_loop() -> None:
    while True:
        pass
"""
    result = auditor.audit(code)
    assert result.passed is False
    assert any("'while' loops are strictly forbidden" in v for v in result.violations)


def test_nested_loops_depth_limit(auditor: ASTSecurityAuditor):
    code = """
def deep_loops() -> None:
    for i in range(10):
        for j in range(10):
            for k in range(10):
                pass
"""
    result = auditor.audit(code)
    assert result.passed is False
    assert any("Nested loop depth" in v for v in result.violations)


def test_recursion_blocked(auditor: ASTSecurityAuditor):
    code = """
def recursive_calc(n: int) -> int:
    if n <= 1:
        return 1
    return n * recursive_calc(n - 1)
"""
    result = auditor.audit(code)
    assert result.passed is False
    assert any("Self-recursion detected" in v for v in result.violations)


def test_fail_silent_swallowed_exception_blocked(auditor: ASTSecurityAuditor):
    code = """
def swallowed_error() -> None:
    try:
        x = 1 / 0
    except:
        pass
"""
    result = auditor.audit(code)
    assert result.passed is False
    assert any("Constraint #0" in v for v in result.violations)


def test_syntax_error_handled_gracefully(auditor: ASTSecurityAuditor):
    code = "def broken( -> None: pass"
    result = auditor.audit(code)
    assert result.passed is False
    assert any("Python SyntaxError" in v for v in result.violations)
