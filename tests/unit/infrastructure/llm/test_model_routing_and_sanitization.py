"""
Unit tests for 2026 Model Routing, Rate-Limit Guard & Output Sanitization.
2026 模型路由、速率限制保護與輸出思維鏈清洗之單元測試。
"""
import asyncio
import json
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from src.utils.json_utils import repair_json, json_loads_safe
from src.infrastructure.llm.llm_gateway import NvidiaGateway
from src.domain.interfaces import LLMConfig, Message
from src.infrastructure.llm.tier_config import TierConfig, load_tiers


class TestJsonOutputSanitization:
    """Test thought tag stripping and robust JSON parsing for reasoning models (DeepSeek-R1)."""

    def test_strip_complete_think_tags(self):
        raw_output = """<think>
Here is my chain of thought.
Let's consider {"fake_json": "ignore this"}.
We should evaluate the risks.
</think>
```json
{
    "ticker": "AAPL",
    "score": 85.5,
    "decision": "BUY"
}
```"""
        cleaned = repair_json(raw_output)
        assert "<think>" not in cleaned
        assert "</think>" not in cleaned
        assert "fake_json" not in cleaned

        data = json_loads_safe(raw_output)
        assert data["ticker"] == "AAPL"
        assert data["score"] == 85.5
        assert data["decision"] == "BUY"

    def test_strip_multiline_unclosed_think_tag(self):
        """Handle truncated thought output gracefully."""
        raw_output = """<think>
Truncated thought without closing tag...
{"broken": true}"""
        cleaned = repair_json(raw_output)
        assert "<think>" not in cleaned
        assert cleaned == ""

    def test_pure_json_without_think_tags(self):
        raw_output = '{"status": "ok", "value": 123}'
        data = json_loads_safe(raw_output)
        assert data == {"status": "ok", "value": 123}


class TestNvidiaGatewayRateLimitGuard:
    """Test NvidiaGateway concurrency semaphore and rate limit detection."""

    def test_nvidia_gateway_semaphore_acquired(self):
        async def _run():
            gateway = NvidiaGateway()
            config = LLMConfig(provider="nvidia_nim", model="meta/llama-3.3-70b-instruct", api_key="test-key")
            messages = [Message(role="user", content="Hello")]

            # Mock super().chat to verify execution
            with patch("src.infrastructure.llm.llm_gateway.OpenAIGateway.chat", new_callable=AsyncMock) as mock_super_chat:
                mock_super_chat.return_value = "Hello from NIM"
                result = await gateway.chat(messages, config)
                assert result == "Hello from NIM"
                mock_super_chat.assert_awaited_once()

        asyncio.run(_run())

    def test_nvidia_gateway_429_warning_logged(self, caplog):
        async def _run():
            gateway = NvidiaGateway()
            config = LLMConfig(provider="nvidia_nim", model="meta/llama-3.3-70b-instruct", api_key="test-key")
            messages = [Message(role="user", content="Hello")]

            # Mock 429 response from upstream
            mock_response = httpx.Response(
                status_code=429,
                request=httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions"),
                text="Too Many Requests - Rate limit exceeded"
            )
            http_error = httpx.HTTPStatusError("429 Client Error", request=mock_response.request, response=mock_response)

            with patch("src.infrastructure.llm.llm_gateway.OpenAIGateway.chat", new_callable=AsyncMock, side_effect=http_error):
                with pytest.raises(httpx.HTTPStatusError) as exc_info:
                    await gateway.chat(messages, config)
                assert exc_info.value.response.status_code == 429
                assert "NIM 40 RPM rate limit hit" in caplog.text

        asyncio.run(_run())


class TestTierManifestIntegrity:
    """Test 2026 updated tier manifest and seed config."""

    def test_load_tiers_manifest(self):
        tiers = load_tiers()
        assert "nano" in tiers
        assert "fast" in tiers
        assert "smart" in tiers
        assert "advanced" in tiers

        # Verify 2026 economic constraints
        assert tiers["nano"].input_cost_per_mtok <= 0.20
        assert tiers["fast"].input_cost_per_mtok <= 0.50
        assert tiers["smart"].input_cost_per_mtok <= 2.00
        assert tiers["advanced"].input_cost_per_mtok <= 5.00

    def test_load_models_seed(self):
        seed_path = Path(__file__).resolve().parents[4] / "config" / "llm_models_seed.yaml"
        assert seed_path.exists()
        raw = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
        models = raw.get("models", [])
        assert len(models) >= 7

        provider_codes = {m["provider_code"] for m in models}
        assert "ollama" in provider_codes
        assert "nvidia_nim" in provider_codes
        assert "openrouter" in provider_codes

        model_codes = [m["model_code"] for m in models]
        assert "deepseek/deepseek-r1" in model_codes
        assert "meta/llama-3.3-70b-instruct" in model_codes
        assert "qwen2.5:7b" in model_codes

    def test_default_tier_chain_matches_seed_models(self):
        """Verify that all models in DEFAULT_TIER_CHAIN are defined in llm_models_seed.yaml."""
        from src.services.llm_onboarding_service import DEFAULT_TIER_CHAIN

        seed_path = Path(__file__).resolve().parents[4] / "config" / "llm_models_seed.yaml"
        raw = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
        seed_tuples = {(m["provider_code"], m["model_code"]) for m in raw.get("models", [])}

        for tier, chain in DEFAULT_TIER_CHAIN.items():
            for provider_code, model_code in chain:
                assert (provider_code, model_code) in seed_tuples, (
                    f"Tier '{tier}' references ({provider_code}, {model_code}) which is not in llm_models_seed.yaml"
                )
