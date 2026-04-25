"""
Unit tests for src/infrastructure/llm/discovery_parsers.py

Each parser receives a sample raw API response and must return a
normalised list of DiscoveredModel objects.
"""
import pytest
from src.infrastructure.llm.discovery_parsers import (
    parse_openai_models,
    parse_ollama_tags,
    parse_gemini_models,
    parse_anthropic_static,
    get_parser,
)
from src.domain.interfaces import DiscoveredModel


# ──────────────────────────────────────────────────────────────────────
# parse_openai_models
# ──────────────────────────────────────────────────────────────────────
OPENAI_SAMPLE = {
    "data": [
        {"id": "gpt-4.1-nano", "object": "model"},
        {"id": "gpt-4o", "object": "model", "context_length": 128000},
        {
            "id": "google/gemini-2.5-pro",
            "object": "model",
            "context_length": 1048576,
            "pricing": {"prompt": "0.00000125", "completion": "0.000005"},
        },
    ]
}


def test_parse_openai_models_basic():
    result = parse_openai_models(OPENAI_SAMPLE)
    assert len(result) == 3
    codes = [m.model_code for m in result]
    assert "gpt-4.1-nano" in codes
    assert "gpt-4o" in codes
    assert "google/gemini-2.5-pro" in codes


def test_parse_openai_models_context_window():
    result = parse_openai_models(OPENAI_SAMPLE)
    gpt4o = next(m for m in result if m.model_code == "gpt-4o")
    assert gpt4o.context_window == 128000


def test_parse_openai_models_pricing():
    result = parse_openai_models(OPENAI_SAMPLE)
    gemini = next(m for m in result if m.model_code == "google/gemini-2.5-pro")
    # pricing is per-token in OpenRouter; parser multiplies by 1000 → per-1k
    assert gemini.input_cost_per_1k == pytest.approx(0.00125, rel=1e-3)
    assert gemini.output_cost_per_1k == pytest.approx(0.005, rel=1e-3)


def test_parse_openai_models_empty():
    assert parse_openai_models({}) == []
    assert parse_openai_models({"data": []}) == []


def test_parse_openai_models_raw_preserved():
    result = parse_openai_models(OPENAI_SAMPLE)
    assert result[0].raw is not None


# ──────────────────────────────────────────────────────────────────────
# parse_ollama_tags
# ──────────────────────────────────────────────────────────────────────
OLLAMA_SAMPLE = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "size": 4730000000,
            "details": {
                "parameter_size": "7.6B",
                "family": "qwen2",
                "context_length": 32768,
            },
        },
        {
            "name": "qwen2.5:14b",
            "size": 9000000000,
            "details": {
                "parameter_size": "14.7B",
                "family": "qwen2",
            },
        },
        {"name": "nomic-embed-text:latest", "size": 274000000, "details": {}},
    ]
}


def test_parse_ollama_tags_count():
    result = parse_ollama_tags(OLLAMA_SAMPLE)
    assert len(result) == 3


def test_parse_ollama_tags_model_codes():
    result = parse_ollama_tags(OLLAMA_SAMPLE)
    codes = [m.model_code for m in result]
    assert "qwen2.5:7b" in codes
    assert "qwen2.5:14b" in codes


def test_parse_ollama_tags_context_window():
    result = parse_ollama_tags(OLLAMA_SAMPLE)
    qwen7b = next(m for m in result if m.model_code == "qwen2.5:7b")
    assert qwen7b.context_window == 32768


def test_parse_ollama_tags_free():
    result = parse_ollama_tags(OLLAMA_SAMPLE)
    for m in result:
        assert m.input_cost_per_1k == 0.0
        assert m.output_cost_per_1k == 0.0


def test_parse_ollama_tags_local_capability():
    result = parse_ollama_tags(OLLAMA_SAMPLE)
    for m in result:
        assert m.capabilities is not None
        assert m.capabilities["local"] is True


def test_parse_ollama_tags_empty():
    assert parse_ollama_tags({}) == []
    assert parse_ollama_tags({"models": []}) == []


# ──────────────────────────────────────────────────────────────────────
# parse_gemini_models
# ──────────────────────────────────────────────────────────────────────
GEMINI_SAMPLE = {
    "models": [
        {
            "name": "models/gemini-2.5-pro",
            "displayName": "Gemini 2.5 Pro",
            "inputTokenLimit": 1048576,
            "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        },
        {
            "name": "models/gemini-2.5-flash",
            "displayName": "Gemini 2.5 Flash",
            "inputTokenLimit": 1048576,
            "supportedGenerationMethods": ["generateContent"],
        },
        {
            "name": "models/text-embedding-004",
            "displayName": "Text Embedding 004",
            "inputTokenLimit": 2048,
            "supportedGenerationMethods": ["embedContent"],
        },
    ]
}


def test_parse_gemini_models_count():
    result = parse_gemini_models(GEMINI_SAMPLE)
    assert len(result) == 3


def test_parse_gemini_models_strips_prefix():
    result = parse_gemini_models(GEMINI_SAMPLE)
    codes = [m.model_code for m in result]
    assert "gemini-2.5-pro" in codes
    assert "gemini-2.5-flash" in codes
    # Should NOT contain "models/" prefix
    assert all(not c.startswith("models/") for c in codes)


def test_parse_gemini_models_context_window():
    result = parse_gemini_models(GEMINI_SAMPLE)
    pro = next(m for m in result if m.model_code == "gemini-2.5-pro")
    assert pro.context_window == 1048576


def test_parse_gemini_models_display_name():
    result = parse_gemini_models(GEMINI_SAMPLE)
    pro = next(m for m in result if m.model_code == "gemini-2.5-pro")
    assert pro.display_name == "Gemini 2.5 Pro"


def test_parse_gemini_models_empty():
    assert parse_gemini_models({}) == []


# ──────────────────────────────────────────────────────────────────────
# parse_anthropic_static
# ──────────────────────────────────────────────────────────────────────
def test_parse_anthropic_static_returns_list():
    result = parse_anthropic_static()
    assert isinstance(result, list)
    assert len(result) >= 2


def test_parse_anthropic_static_model_codes():
    result = parse_anthropic_static()
    codes = [m.model_code for m in result]
    # At least one claude model should be present
    assert any("claude" in c for c in codes)


def test_parse_anthropic_static_has_costs():
    result = parse_anthropic_static()
    for m in result:
        assert m.input_cost_per_1k is not None
        assert m.output_cost_per_1k is not None


def test_parse_anthropic_static_ignores_payload():
    # payload is accepted but ignored
    result1 = parse_anthropic_static(None)
    result2 = parse_anthropic_static({"unexpected": "data"})
    assert len(result1) == len(result2)


# ──────────────────────────────────────────────────────────────────────
# get_parser registry
# ──────────────────────────────────────────────────────────────────────
def test_get_parser_known():
    fn = get_parser("parse_openai_models")
    assert callable(fn)


def test_get_parser_unknown():
    with pytest.raises(KeyError, match="Unknown discovery_parser"):
        get_parser("nonexistent_parser")
