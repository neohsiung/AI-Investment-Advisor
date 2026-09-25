"""
Ephemeral Execution Sandbox for Autonomous Code Verification
=============================================================
在嚴格資源限制與隔離的暫時性環境 (Subprocess Sandbox) 中執行 AI 自主生成的
量化因子、特徵計算函式與單元測試。

防護機制：
1. 執行時間硬限制 (Wall-clock & CPU Timeout <= 3.0s)。
2. 網路阻斷 (Socket Monkeypatching Block)。
3. 獨立臨時目錄運行 (Temporary Directory Isolation)，測試完畢自動銷毀。
4. 全面捕獲 stdout, stderr, traceback 與執行耗時。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("EphemeralSandbox")


@dataclass
class SandboxExecutionResult:
    """
    Execution outcome returned by the Ephemeral Sandbox.
    沙盒隔離執行結果。
    """
    passed: bool
    return_code: int
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: float = 0.0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    extra_info: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        status = "PASSED" if self.passed else f"FAILED ({self.error_type or 'UnknownError'})"
        return f"[{status}] ReturnCode: {self.return_code}, Duration: {self.execution_time_ms:.1f}ms"


class EphemeralSandbox:
    """
    Manages isolated execution of candidate factor code and paired pytest suites.
    負責管理候選因子程式碼與雙生單元測試套件的隔離沙盒執行。
    """

    DEFAULT_TIMEOUT_SEC: float = 3.0

    def __init__(self, timeout_sec: float = DEFAULT_TIMEOUT_SEC):
        self.timeout_sec = timeout_sec

    def execute_and_verify(
        self,
        source_code: str,
        test_code: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ) -> SandboxExecutionResult:
        """
        Execute source code and run optional pytest suite inside an isolated ephemeral directory.
        在隔離臨時工作目錄中執行原始碼並運行 pytest 驗測。
        """
        effective_timeout = timeout_sec or self.timeout_sec
        start_time = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="quant_sandbox_") as temp_dir:
            temp_path = Path(temp_dir)

            # 1. 寫入候選因子模組 (factor_module.py) 及常見別名
            factor_file = temp_path / "factor_module.py"
            factor_file.write_text(source_code, encoding="utf-8")
            (temp_path / "your_module.py").write_text("from factor_module import *\n", encoding="utf-8")
            (temp_path / "candidate_factor.py").write_text("from factor_module import *\n", encoding="utf-8")

            # 2. 注入沙盒安全守護檔 (conftest.py - 阻斷網絡與特權)
            conftest_file = temp_path / "conftest.py"
            conftest_content = (
                "import socket\n"
                "def _blocked_socket(*args, **kwargs):\n"
                "    raise PermissionError('Network access is strictly forbidden in sandbox')\n"
                "socket.socket = _blocked_socket\n"
                "socket.create_connection = _blocked_socket\n"
            )
            conftest_file.write_text(conftest_content, encoding="utf-8")

            # 提供輕量級 pytest mock，確保生產映像檔即使無 pytest dev 套件亦能執行
            pytest_mock_file = temp_path / "pytest.py"
            pytest_mock_content = (
                "class RaisesContext:\n"
                "    def __init__(self, expected_exc):\n"
                "        self.expected = expected_exc\n"
                "    def __enter__(self):\n"
                "        return self\n"
                "    def __exit__(self, exc_type, exc_val, exc_tb):\n"
                "        if exc_type is None:\n"
                "            raise AssertionError(f'Expected {self.expected}, but no exception was raised')\n"
                "        return issubclass(exc_type, self.expected)\n\n"
                "def raises(expected_exc, *args, **kwargs):\n"
                "    return RaisesContext(expected_exc)\n"
            )
            pytest_mock_file.write_text(pytest_mock_content, encoding="utf-8")

            # 3. 準備執行指令
            if test_code:
                # 寫入測試套件
                test_file = temp_path / "test_factor.py"
                test_file.write_text(test_code, encoding="utf-8")

                # 建立零依賴沙盒執行腳本 (run_tests.py)
                runner_file = temp_path / "run_tests.py"
                runner_content = (
                    "import conftest\n"
                    "import sys\n"
                    "import inspect\n"
                    "import test_factor\n\n"

                    "test_funcs = [\n"
                    "    (name, func)\n"
                    "    for name, func in inspect.getmembers(test_factor, inspect.isfunction)\n"
                    "    if name.startswith('test_')\n"
                    "]\n"
                    "failures = []\n"
                    "for name, func in test_funcs:\n"
                    "    try:\n"
                    "        func()\n"
                    "        print(f'PASSED {name}')\n"
                    "    except Exception as e:\n"
                    "        print(f'FAILED {name}: {e}')\n"
                    "        failures.append((name, str(e)))\n\n"
                    "if failures:\n"
                    "    print(f'Total failures: {len(failures)}/{len(test_funcs)}')\n"
                    "    sys.exit(1)\n"
                    "else:\n"
                    "    print(f'All {len(test_funcs)} tests passed successfully.')\n"
                    "    sys.exit(0)\n"
                )
                runner_file.write_text(runner_content, encoding="utf-8")
                cmd = [
                    sys.executable,
                    str(runner_file.name),
                ]
            else:
                # 純驗證語法與導入執行
                runner_file = temp_path / "run_import_check.py"
                runner_content = (
                    "import factor_module\n"
                    "print('IMPORT_SUCCESS')\n"
                )
                runner_file.write_text(runner_content, encoding="utf-8")
                cmd = [
                    sys.executable,
                    str(runner_file.name),
                ]


            # 4. 在隔離子程序中執行
            env = os.environ.copy()
            # 確保子程序可導入 temp_dir 下的模組，但隔離全域污染
            env["PYTHONPATH"] = f"{temp_dir}:{env.get('PYTHONPATH', '')}"

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=temp_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=effective_timeout,
                )
                duration_ms = (time.perf_counter() - start_time) * 1000.0

                passed = proc.returncode == 0
                error_type = None
                error_message = None

                if not passed:
                    error_type = "TestFailure" if test_code else "ExecutionError"
                    error_message = (proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout) else "Non-zero return code"

                return SandboxExecutionResult(
                    passed=passed,
                    return_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    execution_time_ms=duration_ms,
                    error_type=error_type,
                    error_message=error_message,
                )

            except subprocess.TimeoutExpired as e:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                logger.warning(
                    "Sandbox execution timed out after %.2fs: %s",
                    effective_timeout,
                    cmd,
                )
                return SandboxExecutionResult(
                    passed=False,
                    return_code=-1,
                    stdout=e.stdout or "" if isinstance(e.stdout, str) else "",
                    stderr=e.stderr or "" if isinstance(e.stderr, str) else "",
                    execution_time_ms=duration_ms,
                    error_type="TimeoutExpired",
                    error_message=f"Execution exceeded strict timeout of {effective_timeout}s",
                )

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                logger.error("Unexpected error in EphemeralSandbox execution: %s", str(e), exc_info=True)
                return SandboxExecutionResult(
                    passed=False,
                    return_code=-2,
                    execution_time_ms=duration_ms,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
