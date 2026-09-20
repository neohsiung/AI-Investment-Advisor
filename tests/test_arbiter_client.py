"""
Unit tests for ArbiterClient, HighAssuranceSanitizer, and ZeroKnowledgeAuditor.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.infrastructure.llm.security_sanitizer import HighAssuranceSanitizer
from src.infrastructure.llm.audit_trail import ZeroKnowledgeAuditor
from src.infrastructure.llm.arbiter_client import ArbiterClient, ArbiterDecision


class TestSecuritySanitizer:
    def test_sanitizer_filters_financial_keys_and_secrets(self):
        sanitizer = HighAssuranceSanitizer()
        raw_state = {
            "account_id": "ACC_99882233",
            "portfolio_cash": 125000.50,
            "vix": 24.5,
            "weight_delta": 0.05234,
            "api_token": "sk-" + "1234567890abcdef1234567890",
            "message": "User with " + "sk-abcdef1234567890abcdef1234" + " wanted to buy",
            "nested": {
                "user_id": "user_456",
                "safe_val": "ok"
            }
        }

        sanitized = sanitizer.sanitize(raw_state)

        # 1. 確保敏感金鑰與帳號已徹底移除
        assert "account_id" not in sanitized
        assert "portfolio_cash" not in sanitized
        assert "user_id" not in sanitized["nested"]
        assert sanitized["nested"]["safe_val"] == "ok"

        # 2. 確保數值特徵已正規化保留
        assert sanitized["vix"] == 24.5
        assert sanitized["weight_delta"] == 0.0523

        # 3. 確保字串內金鑰被遮蔽
        assert "[REDACTED_SECRET]" in sanitized["api_token"]
        assert ("sk-" + "1234") not in sanitized["api_token"]
        assert "[REDACTED_SECRET]" in sanitized["message"]


class TestZeroKnowledgeAuditor:
    def test_auditor_records_sha256_hash(self):
        mock_logger = MagicMock()
        auditor = ZeroKnowledgeAuditor(log_channel=mock_logger)

        state = {"vix": 25.0, "drawdown": 0.04}
        state_hash = auditor.record_decision(
            decision_id="dec_001",
            domain="sentinel",
            sanitized_state=state,
            question_key="action",
            choice="P1",
            confidence=0.96,
            is_escalated=False,
            tier="reflex",
            latency_ms=120.5
        )

        assert len(state_hash) == 64  # SHA256 hex length
        mock_logger.info.assert_called_once()
        log_content = mock_logger.info.call_args[0][0]
        assert "dec_001" in log_content
        assert state_hash in log_content
        assert "P1" in log_content


@pytest.mark.asyncio
class TestArbiterClient:
    async def test_reflex_success_high_confidence(self):
        client = ArbiterClient(litellm_base_url="http://mock-litellm:4000")

        mock_response_data = {
            "results": {
                "hedging_priority": {
                    "answer": "P0",
                    "confidence": 0.96,
                    "probabilities": {"P0": 0.96, "P1": 0.04}
                }
            },
            "latency_ms": 85.0
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            decision = await client.decide(
                domain="sentinel",
                state={"vix": 38.0, "account_id": "SECRET"},
                question_key="hedging_priority",
                question_spec={"type": "choice", "instructions": "Assess priority"},
                confidence_threshold=0.92
            )

            assert decision.choice == "P0"
            assert decision.confidence == 0.96
            assert decision.is_escalated is False
            assert decision.tier == "reflex"
            assert decision.state_hash is not None

    async def test_low_confidence_triggers_system2_escalation(self):
        mock_gateway = MagicMock()
        mock_gateway.chat = AsyncMock(return_value='{"choice": "P1", "rationale": "Elevated risk"}')

        client = ArbiterClient(
            litellm_base_url="http://mock-litellm:4000",
            llm_gateway=mock_gateway
        )

        # 模擬 Jev 回傳低信心度 (0.75 < 0.92)
        mock_response_data = {
            "results": {
                "hedging_priority": {
                    "answer": "P2",
                    "confidence": 0.75
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            decision = await client.decide(
                domain="sentinel",
                state={"vix": 22.0},
                question_key="hedging_priority",
                question_spec={"type": "choice", "instructions": "Assess priority"},
                confidence_threshold=0.92,
                system2_fallback_prompt="Detailed market context for hedging"
            )

            assert decision.is_escalated is True
            assert decision.tier == "smart_deliberator"
            assert decision.choice == "P1"
            assert mock_gateway.chat.called

    async def test_circuit_breaker_tripping_and_fallback(self):
        client = ArbiterClient(
            litellm_base_url="http://mock-litellm:4000",
            failure_threshold=2,
            circuit_recovery_time_sec=10.0
        )

        # 模擬連續 2 次網路異常
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.ConnectError("Connection refused")

            # 第一次失敗 -> 進入 fallback
            d1 = await client.decide(
                domain="test",
                state={"x": 1},
                question_key="q",
                question_spec={},
                deterministic_default="FALLBACK_1"
            )
            assert d1.choice == "FALLBACK_1"
            assert client._circuit_state == "CLOSED"
            assert client._failure_count == 1

            # 第二次失敗 -> 達到 threshold，觸發 OPEN 熔斷
            d2 = await client.decide(
                domain="test",
                state={"x": 2},
                question_key="q",
                question_spec={},
                deterministic_default="FALLBACK_2"
            )
            assert d2.choice == "FALLBACK_2"
            assert client._circuit_state == "OPEN"

            # 第三次呼叫 -> 斷路器直接短路，不發出 HTTP 請求
            mock_post.reset_mock()
            d3 = await client.decide(
                domain="test",
                state={"x": 3},
                question_key="q",
                question_spec={},
                deterministic_default="FALLBACK_3"
            )
            assert d3.choice == "FALLBACK_3"
            mock_post.assert_not_called()  # 驗證未發出網路連線
