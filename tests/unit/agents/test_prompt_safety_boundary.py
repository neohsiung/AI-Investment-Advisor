"""
Prompt edits must not widen what an agent is permitted to do.

M6 makes system prompts editable through a browser, on a deployment wired to a
live eToro account. The safety argument is that a prompt changes what an agent
SAYS, never what it may DO: order placement passes through
RiskManager.check_constraints, which reads only settings — the trading gate, the
daily cap and the circuit breakers — and never reads prompt text.

These tests assert that argument structurally, so a future refactor cannot
quietly make a prompt influence a trading decision.

M6 讓系統提示詞可從瀏覽器編輯，而本部署接的是實盤 eToro 帳戶。
安全論證是：提示詞只改變代理「說什麼」，不改變它「能做什麼」——下單必須通過
RiskManager.check_constraints，而該方法只讀設定（交易開關、每日上限、斷路器），
從不讀取提示詞。以下測試以結構方式固定這個論證。
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest


class TestRiskManagerIgnoresPrompts:

    def test_risk_manager_source_contains_no_prompt_reference(self):
        """
        The whole module, not just one method: a helper that consulted a prompt
        would be just as dangerous as check_constraints doing it directly.
        檢查整個模組而非單一方法：某個輔助函式去讀提示詞的危險程度是一樣的。
        """
        src = Path("src/infrastructure/risk_manager.py").read_text()
        for needle in ("_load_prompt", "system_prompt", "custom_prompt",
                       "UserCustomPrompt", "prompt_path"):
            assert needle not in src, (
                f"risk_manager now references {needle!r} — a prompt must not be "
                "able to influence a trading constraint"
            )

    def test_check_constraints_gates_on_settings_only(self):
        from src.infrastructure.risk_manager import RiskManager

        src = inspect.getsource(RiskManager.check_constraints)
        # The gate it must consult.
        assert "ai_trading_enabled" in src
        # And nothing prompt-shaped.
        assert "prompt" not in src.lower()

    def test_order_path_calls_check_constraints(self):
        """
        If the order path stopped calling it, the constraints would be dead code
        and the safety argument above would be vacuous.
        若下單路徑不再呼叫它，上述安全論證就形同虛設。
        """
        src = Path("src/services/etoro_service.py").read_text()
        assert "risk_manager.check_constraints" in src

    def test_trading_gate_defaults_closed(self):
        """
        A missing ai_trading_enabled row must block, not permit. This defaulted to
        "true" before M4 — an absent setting authorised live order placement.
        缺少該設定列必須擋下而非放行；M4 之前預設為 "true"，等於授權真實下單。
        """
        from src.config.settings_schema import schema_default

        assert schema_default("ai_trading_enabled") is False


class TestTestRunDisablesTrading:

    def test_endpoint_forces_the_trading_gate_off(self):
        """
        POST /agents/{id}/test constructs a real agent with real credentials, so it
        pins ai_trading_enabled to false for the duration and restores it in a
        `finally` — including when the run raises.
        測試執行會建構真實代理並使用真實憑證，故期間強制關閉交易，
        並在 finally 還原（包含執行拋錯的情況）。
        """
        from src.api.v1.endpoints import agents as ep

        src = inspect.getsource(ep.test_run)
        assert '"ai_trading_enabled": False' in src, "test run does not disable trading"
        assert "finally:" in src, "the restore is not in a finally block"

    def test_endpoint_refuses_to_run_if_the_brake_cannot_be_applied(self):
        """Failing to disable trading must abort, not proceed unprotected."""
        from src.api.v1.endpoints import agents as ep

        src = inspect.getsource(ep.test_run)
        assert "refusing" in src.lower()
        assert "503" in src

    def test_endpoint_does_not_rely_on_paper_mode(self):
        """
        TRADING_MODE=paper is not a sandbox here: the eToro token has no demo
        permission, so paper mode makes every broker call return
        InsufficientPermissions — a hard failure rather than a safe degrade.
        paper 在本專案不是沙箱：token 無 demo 權限，會讓所有 broker 呼叫直接失敗。
        """
        from src.api.v1.endpoints import agents as ep

        src = inspect.getsource(ep.test_run)

        # Check behaviour, not vocabulary: the docstring legitimately MENTIONS
        # paper mode in order to explain why it is not used. What must not appear
        # is code that sets it.
        # 檢查行為而非字面：docstring 提到 paper 是為了說明「為何不用」，
        # 不得出現的是「設定它」的程式碼。
        code = "\n".join(
            line for line in src.splitlines()
            if not line.lstrip().startswith("#")
        )
        body = code.split('"""')[-1]  # everything after the docstring
        for forbidden in ('TRADING_MODE', '"paper"', "'paper'"):
            assert forbidden not in body, (
                f"the test run sets {forbidden} — paper mode is a hard failure "
                "here, not a sandbox; use ai_trading_enabled"
            )


class TestPromptStorageIsUserState:

    def test_saving_a_prompt_writes_to_the_database_not_the_manifest(self):
        """
        Prompt overrides are user state, so they live in `user_custom_prompts`.
        Writing them into the shipped manifest would mean a release that changes
        the default silently overwrites an operator's edit.
        提示詞覆寫屬使用者狀態，存於 user_custom_prompts；
        若寫入出貨 manifest，升級時預設值變更會靜默覆寫使用者的修改。
        """
        from src.api.v1.endpoints import agents as ep

        src = inspect.getsource(ep.save_prompt)
        assert "UserCustomPrompt" in src
        assert "write_text" not in src, "prompt saves must not write manifest files"

    def test_empty_prompt_is_rejected_rather_than_blanking_the_agent(self):
        from src.api.v1.endpoints import agents as ep

        src = inspect.getsource(ep.save_prompt)
        assert "400" in src
        assert "DELETE" in src, "the error should point at the explicit removal route"
