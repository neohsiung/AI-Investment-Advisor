"""
Tests for discovery_parsers to improve coverage.
"""
import pytest
from src.infrastructure.llm.discovery_parsers import (
    parse_openai_models,
    parse_ollama_tags,
    parse_gemini_models,
    parse_anthropic_static,
    get_parser,
    PARSER_REGISTRY,
    _safe_int,
    _safe_float,
)
from src.domain.interfaces import DiscoveredModel


class TestSafeInt:
    def test_none_returns_none(self):
        assert _safe_int(None) is None

    def test_int_value(self):
        assert _safe_int(1024) == 1024

    def test_string_int(self):
        assert _safe_int("2048") == 2048

    def test_invalid_string_returns_none(self):
        assert _safe_int("not-a-number") is None

    def test_float_truncates(self):
        assert _safe_int(3.9) == 3


class TestSafeFloat:
    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_float_value(self):
        assert _safe_float(1.5) == 1.5

    def test_string_float(self):
        assert _safe_float("0.0000015") == pytest.approx(0.0000015)

    def test_invalid_string_returns_none(self):
        assert _safe_float("not-a-float") is None


class TestParseOpenAIModels:
    def test_empty_payload(self):
        result = parse_openai_models({})
        assert result == []

    def test_empty_data_list(self):
        result = parse_openai_models({"data": []})
        assert result == []

    def test_basic_model(self):
        payload = {
            "data": [
                {"id": "gpt-4.1-nano", "object": "model"}
            ]
        }
        result = parse_openai_models(payload)
        assert len(result) == 1
        assert result[0].model_code == "gpt-4.1-nano"
        assert result[0].display_name == "gpt-4.1-nano"

    def test_model_with_name_field(self):
        payload = {
            "data": [
                {"id": "gpt-4", "name": "GPT-4 Turbo", "object": "model"}
            ]
        }
        result = parse_openai_models(payload)
        assert result[0].display_name == "GPT-4 Turbo"

    def test_model_with_pricing(self):
        payload = {
            "data": [
                {
                    "id": "gpt-4",
                    "pricing": {"prompt": "0.000003", "completion": "0.000006"}
                }
            ]
        }
        result = parse_openai_models(payload)
        assert result[0].input_cost_per_1k == pytest.approx(0.003)
        assert result[0].output_cost_per_1k == pytest.approx(0.006)

    def test_model_with_context_window(self):
        payload = {
            "data": [
                {"id": "gpt-4", "context_length": 128000}
            ]
        }
        result = parse_openai_models(payload)
        assert result[0].context_window == 128000

    def test_skips_non_dict_items(self):
        payload = {"data": ["not-a-dict", {"id": "gpt-4"}]}
        result = parse_openai_models(payload)
        assert len(result) == 1

    def test_skips_items_without_id(self):
        payload = {"data": [{"object": "model"}]}
        result = parse_openai_models(payload)
        assert result == []

    def test_multiple_models(self):
        payload = {
            "data": [
                {"id": "gpt-4.1-nano"},
                {"id": "gpt-4.1"},
                {"id": "gpt-4.1-mini"},
            ]
        }
        result = parse_openai_models(payload)
        assert len(result) == 3

    def test_none_data_returns_empty(self):
        result = parse_openai_models({"data": None})
        assert result == []


class TestParseOllamaTags:
    def test_empty_payload(self):
        result = parse_ollama_tags({})
        assert result == []

    def test_basic_model(self):
        payload = {
            "models": [
                {"name": "qwen2.5:7b", "size": 4000000}
            ]
        }
        result = parse_ollama_tags(payload)
        assert len(result) == 1
        assert result[0].model_code == "qwen2.5:7b"
        assert result[0].input_cost_per_1k == 0.0
        assert result[0].output_cost_per_1k == 0.0

    def test_model_with_details(self):
        payload = {
            "models": [
                {
                    "name": "qwen2.5:7b",
                    "details": {
                        "family": "qwen2",
                        "parameter_size": "7.6B",
                        "context_length": 32768
                    }
                }
            ]
        }
        result = parse_ollama_tags(payload)
        assert result[0].context_window == 32768
        assert "qwen2" in result[0].display_name
        assert "7.6B" in result[0].display_name

    def test_model_capabilities_are_local(self):
        payload = {"models": [{"name": "llama3:8b"}]}
        result = parse_ollama_tags(payload)
        assert result[0].capabilities["local"] is True
        assert result[0].capabilities["tool_calling"] is True

    def test_skips_non_dict_items(self):
        payload = {"models": ["not-a-dict", {"name": "llama3"}]}
        result = parse_ollama_tags(payload)
        assert len(result) == 1

    def test_skips_items_without_name(self):
        payload = {"models": [{"size": 1000}]}
        result = parse_ollama_tags(payload)
        assert result == []


class TestParseGeminiModels:
    def test_empty_payload(self):
        result = parse_gemini_models({})
        assert result == []

    def test_basic_model(self):
        payload = {
            "models": [
                {
                    "name": "models/gemini-2.5-pro",
                    "displayName": "Gemini 2.5 Pro",
                    "inputTokenLimit": 1048576,
                    "supportedGenerationMethods": ["generateContent"]
                }
            ]
        }
        result = parse_gemini_models(payload)
        assert len(result) == 1
        assert result[0].model_code == "gemini-2.5-pro"
        assert result[0].display_name == "Gemini 2.5 Pro"
        assert result[0].context_window == 1048576

    def test_strips_models_prefix(self):
        payload = {
            "models": [{"name": "models/gemini-flash", "displayName": "Flash"}]
        }
        result = parse_gemini_models(payload)
        assert result[0].model_code == "gemini-flash"

    def test_model_without_prefix(self):
        payload = {
            "models": [{"name": "gemini-pro", "displayName": "Pro"}]
        }
        result = parse_gemini_models(payload)
        assert result[0].model_code == "gemini-pro"

    def test_skips_empty_model_code(self):
        payload = {"models": [{"name": "", "displayName": "Empty"}]}
        result = parse_gemini_models(payload)
        assert result == []

    def test_tool_calling_capability(self):
        payload = {
            "models": [
                {
                    "name": "models/gemini-pro",
                    "displayName": "Gemini Pro",
                    "supportedGenerationMethods": ["generateContent", "countTokens"]
                }
            ]
        }
        result = parse_gemini_models(payload)
        assert result[0].capabilities["tool_calling"] is True
        assert result[0].capabilities["streaming"] is True

    def test_skips_non_dict_items(self):
        payload = {"models": ["not-a-dict", {"name": "models/gemini-pro", "displayName": "Pro"}]}
        result = parse_gemini_models(payload)
        assert len(result) == 1


class TestParseAnthropicStatic:
    def test_returns_models(self):
        result = parse_anthropic_static()
        assert len(result) > 0

    def test_all_are_discovered_models(self):
        result = parse_anthropic_static()
        for m in result:
            assert isinstance(m, DiscoveredModel)

    def test_accepts_payload_argument(self):
        """payload is accepted but ignored."""
        result = parse_anthropic_static({"some": "data"})
        assert len(result) > 0

    def test_models_have_required_fields(self):
        result = parse_anthropic_static()
        for m in result:
            assert m.model_code
            assert m.display_name
            assert m.context_window is not None

    def test_claude_sonnet_present(self):
        result = parse_anthropic_static()
        codes = [m.model_code for m in result]
        assert any("claude" in c for c in codes)


class TestGetParser:
    def test_get_openai_parser(self):
        parser = get_parser("parse_openai_models")
        assert parser is parse_openai_models

    def test_get_ollama_parser(self):
        parser = get_parser("parse_ollama_tags")
        assert parser is parse_ollama_tags

    def test_get_gemini_parser(self):
        parser = get_parser("parse_gemini_models")
        assert parser is parse_gemini_models

    def test_get_anthropic_parser(self):
        parser = get_parser("parse_anthropic_static")
        assert parser is parse_anthropic_static

    def test_unknown_parser_raises_key_error(self):
        with pytest.raises(KeyError) as exc_info:
            get_parser("nonexistent_parser")
        assert "nonexistent_parser" in str(exc_info.value)

    def test_parser_registry_has_all_parsers(self):
        assert "parse_openai_models" in PARSER_REGISTRY
        assert "parse_ollama_tags" in PARSER_REGISTRY
        assert "parse_gemini_models" in PARSER_REGISTRY
        assert "parse_anthropic_static" in PARSER_REGISTRY
