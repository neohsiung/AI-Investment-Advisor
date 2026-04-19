"""
Tests for ProviderSpec and ProviderCapabilities to improve coverage.
"""
import pytest
from src.infrastructure.llm.provider_spec import (
    ProviderCapabilities,
    ProviderSpec,
)


class TestProviderCapabilities:
    """Test ProviderCapabilities dataclass."""

    def test_default_values(self):
        caps = ProviderCapabilities()
        assert caps.tool_calling is False
        assert caps.streaming is True
        assert caps.vision is False
        assert caps.json_mode is False
        assert caps.embeddings is False
        assert caps.local is False

    def test_custom_values(self):
        caps = ProviderCapabilities(
            tool_calling=True,
            streaming=True,
            vision=True,
            json_mode=True,
            embeddings=True,
            local=True,
        )
        assert caps.tool_calling is True
        assert caps.vision is True
        assert caps.json_mode is True
        assert caps.embeddings is True
        assert caps.local is True

    def test_frozen_immutable(self):
        """ProviderCapabilities is frozen — cannot be modified."""
        caps = ProviderCapabilities()
        with pytest.raises((AttributeError, TypeError)):
            caps.tool_calling = True  # type: ignore

    def test_equality(self):
        caps1 = ProviderCapabilities(tool_calling=True)
        caps2 = ProviderCapabilities(tool_calling=True)
        assert caps1 == caps2

    def test_inequality(self):
        caps1 = ProviderCapabilities(tool_calling=True)
        caps2 = ProviderCapabilities(tool_calling=False)
        assert caps1 != caps2


class TestProviderSpec:
    """Test ProviderSpec dataclass."""

    def _make_spec(self, **kwargs):
        defaults = {
            "provider_code": "openrouter",
            "display_name": "OpenRouter",
            "gateway_class": "src.infrastructure.llm.llm_gateway.OpenRouterGateway",
            "default_base_url": "https://openrouter.ai/api/v1",
            "auth_type": "bearer",
        }
        defaults.update(kwargs)
        return ProviderSpec(**defaults)

    def test_basic_creation(self):
        spec = self._make_spec()
        assert spec.provider_code == "openrouter"
        assert spec.display_name == "OpenRouter"
        assert spec.auth_type == "bearer"

    def test_default_optional_fields(self):
        spec = self._make_spec()
        assert spec.api_key_env is None
        assert spec.models_endpoint is None
        assert spec.discovery_parser == "parse_openai_models"
        assert spec.pricing_source is None
        assert spec.healthcheck_endpoint is None
        assert spec.notes == ""

    def test_default_capabilities(self):
        spec = self._make_spec()
        assert isinstance(spec.default_capabilities, ProviderCapabilities)
        assert spec.default_capabilities.streaming is True

    def test_custom_capabilities(self):
        caps = ProviderCapabilities(tool_calling=True, vision=True)
        spec = self._make_spec(default_capabilities=caps)
        assert spec.default_capabilities.tool_calling is True
        assert spec.default_capabilities.vision is True

    def test_with_all_fields(self):
        caps = ProviderCapabilities(tool_calling=True, streaming=True)
        spec = ProviderSpec(
            provider_code="gemini",
            display_name="Google Gemini",
            gateway_class="src.infrastructure.llm.llm_gateway.GeminiGateway",
            default_base_url="https://generativelanguage.googleapis.com",
            auth_type="api_key_query",
            api_key_env="GEMINI_API_KEY",
            models_endpoint="/v1beta/models",
            discovery_parser="parse_gemini_models",
            pricing_source="static",
            healthcheck_endpoint="/v1beta/models",
            default_capabilities=caps,
            notes="Google Gemini provider",
        )
        assert spec.provider_code == "gemini"
        assert spec.api_key_env == "GEMINI_API_KEY"
        assert spec.discovery_parser == "parse_gemini_models"
        assert spec.notes == "Google Gemini provider"

    def test_frozen_immutable(self):
        """ProviderSpec is frozen — cannot be modified."""
        spec = self._make_spec()
        with pytest.raises((AttributeError, TypeError)):
            spec.provider_code = "other"  # type: ignore

    def test_equality(self):
        spec1 = self._make_spec()
        spec2 = self._make_spec()
        assert spec1 == spec2

    def test_auth_type_none(self):
        spec = self._make_spec(auth_type="none")
        assert spec.auth_type == "none"

    def test_auth_type_custom(self):
        spec = self._make_spec(auth_type="custom")
        assert spec.auth_type == "custom"

    def test_ollama_spec(self):
        """Test a local Ollama provider spec."""
        caps = ProviderCapabilities(local=True, tool_calling=True)
        spec = ProviderSpec(
            provider_code="ollama",
            display_name="Ollama (Local)",
            gateway_class="src.infrastructure.llm.llm_gateway.OllamaGateway",
            default_base_url="http://localhost:11434",
            auth_type="none",
            models_endpoint="/api/tags",
            discovery_parser="parse_ollama_tags",
            pricing_source="zero",
            default_capabilities=caps,
        )
        assert spec.provider_code == "ollama"
        assert spec.default_capabilities.local is True
        assert spec.pricing_source == "zero"
