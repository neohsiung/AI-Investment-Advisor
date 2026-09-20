"""
End-to-End Behavior-Driven Development (BDD) Test Scenarios.
Aligned with wiki/05_Quality_Assurance/端到端行為驅動測試規格-BDD-E2E-Testing-Specs.md
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.infrastructure.llm.security_sanitizer import HighAssuranceSanitizer
from src.infrastructure.llm.audit_trail import ZeroKnowledgeAuditor
from src.infrastructure.llm.arbiter_client import ArbiterClient, ArbiterDecision
from src.services.cost_profile_service import COST_PROFILES, CostProfileService
from src.infrastructure.workflow.loader import list_workflows, load_workflow


class TestBddReflexArbiterHedging:
    """
    Feature: 市場黑天鵝事件之毫秒級條件裁決與避險
    """

    def test_bdd_scenario_extreme_volatility_triggers_p0_hedging(self):
        # ── Given ──
        # 市場指標 VIX >= 30 且標的即時回撤幅度超過 5%
        market_state = {
            "vix": 34.5,
            "drawdown": 0.072,
            "ticker": "TSLA",
            "relative_weight_delta": -0.05,
        }
        question_spec = {
            "question": "Is emergency hedging required?",
            "choices": ["P0", "P1", "P2", "P3"],
        }

        # ── When ──
        # Sentinel 哨兵調用 ArbiterClient 進行條件裁決
        auditor_mock = MagicMock()
        client = ArbiterClient(litellm_base_url="http://mock-litellm:4000", auditor=auditor_mock)

        mock_decision = ArbiterDecision(
            decision_id="dec_bdd_p0",
            domain="sentinel",
            choice="P0",
            confidence=0.98,
            is_escalated=False,
            tier="reflex",
            state_sha256="4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
            latency_ms=112.5,
        )

        with patch.object(client, "_call_reflex_api", return_value=mock_decision):
            import asyncio
            decision = asyncio.run(
                client.decide(
                    domain="sentinel",
                    state=market_state,
                    question_key="risk_action",
                    question_spec=question_spec,
                    confidence_threshold=0.96,
                )
            )

        # ── Then ──
        # 裁決結果為 P0，置信度 >= 0.96，未發生升級，且延遲符合毫秒級標準
        assert decision.choice == "P0"
        assert decision.confidence >= 0.96
        assert decision.is_escalated is False
        assert decision.tier == "reflex"

    def test_bdd_scenario_low_confidence_escalates_to_system2(self):
        # ── Given ──
        # 裁決結果之置信度落於邊界區間 (0.75 < 0.92)
        market_state = {"vix": 22.0, "drawdown": 0.02}
        question_spec = {"question": "Evaluate anomaly", "choices": ["P1", "P2"]}

        client = ArbiterClient(litellm_base_url="http://mock-litellm:4000")
        system2_mock_decision = ArbiterDecision(
            decision_id="dec_bdd_esc",
            domain="sentinel",
            choice="P1",
            confidence=0.90,
            is_escalated=True,
            tier="smart",
            state_sha256="4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
            latency_ms=1450.0,
        )

        # ── When ──
        # ArbiterClient 偵測到置信度未達自動平倉閾值 (0.92)
        with patch.object(client, "_call_reflex_api", return_value=None):
            with patch.object(client, "_escalate_to_system2", return_value=system2_mock_decision):
                import asyncio
                decision = asyncio.run(
                    client.decide(
                        domain="sentinel",
                        state=market_state,
                        question_key="action",
                        question_spec=question_spec,
                        confidence_threshold=0.92,
                    )
                )

        # ── Then ──
        # 系統自動升級至 System 2 (is_escalated = True)
        assert decision.is_escalated is True
        assert decision.tier == "smart"
        assert decision.choice == "P1"


class TestBddZeroLeakageSanitization:
    """
    Feature: 外部 LLM 請求之零資料外洩安全防護
    """

    def test_bdd_scenario_scrub_sensitive_financial_data(self):
        # ── Given ──
        # 原始狀態中包含真實帳號、現金餘額與 API 私鑰
        raw_state = {
            "account_id": "ACC_REAL_USER_9988",
            "portfolio_cash": 2500000.00,
            "total_balance": 3500000.00,
            "user_id": "usr_internal_admin",
            "api_token": "sk-" + "realSecretKeyThatMustBeScrubbed12345678",
            "vix": 28.5,
            "weight_delta": 0.0825,
            "prompt": "Investigate transaction with " + "sk-anotherSecretKey998877",
        }

        # ── When ──
        # 資料通過 HighAssuranceSanitizer
        sanitizer = HighAssuranceSanitizer()
        sanitized = sanitizer.sanitize(raw_state)

        # ── Then ──
        # 敏感識別欄位被徹底移除
        assert "account_id" not in sanitized
        assert "portfolio_cash" not in sanitized
        assert "total_balance" not in sanitized
        assert "user_id" not in sanitized

        # 數值特徵被保留且正規化
        assert sanitized["vix"] == 28.5
        assert sanitized["weight_delta"] == 0.0825

        # 機密金鑰被正則遮罩
        assert "[REDACTED_SECRET]" in sanitized["api_token"]
        assert ("sk-" + "realSecretKey") not in sanitized["api_token"]
        assert "[REDACTED_SECRET]" in sanitized["prompt"]

    def test_bdd_scenario_cryptographic_audit_trail_non_repudiation(self):
        # ── Given ──
        # 脫敏後之狀態字典
        sanitized_state = {"vix": 31.2, "drawdown": 0.055, "ticker": "SPY"}
        auditor = ZeroKnowledgeAuditor()

        # ── When ──
        # 記錄決策雜湊
        sha256_hash = auditor.record_decision(
            decision_id="dec_bdd_999",
            domain="sentinel",
            sanitized_state=sanitized_state,
            question_key="hedge",
            choice="P0",
            confidence=0.99,
        )

        # ── Then ──
        # 產出標準 64 位元不可篡改 SHA-256 雜湊
        assert len(sha256_hash) == 64
        import hashlib
        import json
        expected_hash = hashlib.sha256(
            json.dumps(sanitized_state, sort_keys=True).encode("utf-8")
        ).hexdigest()
        assert sha256_hash == expected_hash


class TestBddDeclarativeWorkflowDag:
    """
    Feature: 宣告式 YAML 工作流完整性與依賴拓撲
    """

    def test_bdd_scenario_all_workflows_form_valid_dags(self):
        # ── Given ──
        # 系統中的所有宣告式工作流檔案
        workflows = list_workflows()
        assert len(workflows) > 0, "At least one declarative workflow should exist"

        # ── When & Then ──
        # 每個工作流皆能正確解析出合法節點清單
        for wf_id in workflows:
            spec = load_workflow(wf_id)
            assert spec.id == wf_id
            assert len(spec.nodes) > 0, f"Workflow {wf_id} must have at least one node"

            # 驗證每個節點之輸入/輸出型別與結構
            for node in spec.nodes:
                assert node.name, f"Node in {wf_id} missing name"
                assert node.type in ("agent", "code"), f"Invalid node type in {wf_id}: {node.type}"
                assert isinstance(node.inputs, list)
                assert isinstance(node.outputs, list)


class TestBddCostProfilesGovernance:
    """
    Feature: 運算成本方案約束與階層調配
    """

    def test_bdd_scenario_cost_profiles_adhere_to_budget_limits(self):
        # ── Given ──
        # 系統預先定義的三大成本方案
        profiles = COST_PROFILES

        # ── When & Then ──
        # Frugal 方案必須具備低頻巡檢 (30 分鐘) 與最低預算配置
        frugal = profiles["frugal"]
        assert frugal["sentinel_tick_minute"] == "*/30"
        assert "ollama" in frugal["recommended_providers"]

        # Balanced 方案巡檢頻率為 15 分鐘 (推薦方案)
        balanced = profiles["balanced"]
        assert balanced["sentinel_tick_minute"] == "*/15"

        # Aggressive 方案巡檢頻率為 5 分鐘
        aggressive = profiles["aggressive"]
        assert aggressive["sentinel_tick_minute"] == "*/5"
