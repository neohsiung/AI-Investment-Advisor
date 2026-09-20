"""
One provider list, one tier table (M7-5).

Three registries used to hold the same provider mapping and disagree:

  1. `ProviderCatalog` — read config/llm_providers.yaml.
  2. `LLMGatewayFactory._REGISTRY` — a literal dict of 13 spellings over 6
     classes, with no `groq`. `settings_schema.yaml` offers "Groq" in the
     AI_PROVIDER enum, so picking the provider the UI advertised raised
     "Unsupported LLM provider: 'Groq'".
  3. `llm_config_chain._GATEWAY_REGISTRY` — the same list again, plus
     `try: from ... import GroqGateway / except ImportError: pass` for Groq and
     Anthropic. Neither class has ever existed, so both excepts always fired and
     `build_config_chain` dropped every groq/anthropic candidate from every chain
     with a WARNING — the silent-drop failure the file's own 2026-08-12
     nvidia_nim note describes, still live for two more providers.

The load-bearing assertion here is the regression table: every spelling the old
hardcoded dict accepted must still resolve to the same gateway class. A refactor
that quietly stopped accepting `"Google Gemini"` would not fail anywhere near
the change — it would surface as an agent that cannot build its gateway.

本檔的關鍵斷言是回歸對照表：舊硬編字典接受的每個拼法都必須解析到同一個 gateway 類別。
"""
from pathlib import Path

import pytest
import yaml

from src.infrastructure.llm.llm_gateway import (
    GeminiGateway,
    LLMGatewayFactory,
    MockLLMGateway,
    NvidiaGateway,
    OllamaGateway,
    OpenAIGateway,
    OpenRouterGateway,
)
from src.infrastructure.llm.provider_catalog import get_provider_catalog

REPO = Path(__file__).resolve().parents[4]
PROVIDERS_YAML = REPO / "config" / "llm_providers.yaml"
GATEWAY_SRC = REPO / "src" / "infrastructure" / "llm" / "llm_gateway.py"
CHAIN_SRC = REPO / "src" / "infrastructure" / "llm" / "llm_config_chain.py"

# Exactly the dict that used to live in llm_gateway.py.
LEGACY_REGISTRY = {
    "OpenRouter": OpenRouterGateway,
    "openrouter": OpenRouterGateway,
    "Google Gemini": GeminiGateway,
    "google_gemini": GeminiGateway,
    "gemini": GeminiGateway,
    "OpenAI": OpenAIGateway,
    "openai": OpenAIGateway,
    "Ollama": OllamaGateway,
    "ollama": OllamaGateway,
    "Nvidia": NvidiaGateway,
    "nvidia": NvidiaGateway,
    "NVIDIA": NvidiaGateway,
    "mock": MockLLMGateway,
}


def _code_without_comments(path: Path) -> str:
    return "\n".join(
        line for line in path.read_text().splitlines()
        if not line.strip().startswith("#")
    )


class TestNoRegression:

    @pytest.mark.parametrize("spelling,expected", sorted(
        LEGACY_REGISTRY.items(), key=lambda kv: kv[0]
    ))
    def test_every_legacy_spelling_still_resolves(self, spelling, expected):
        assert isinstance(LLMGatewayFactory.create(spelling), expected)

    def test_an_unknown_provider_still_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMGatewayFactory.create("NotAProvider")

    def test_the_error_lists_what_is_supported(self):
        """The message is how an operator finds the right spelling."""
        with pytest.raises(ValueError) as exc:
            LLMGatewayFactory.create("nope")
        assert "OpenRouter" in str(exc.value)


class TestTheSilentlyDroppedProviders:

    @pytest.mark.parametrize("spelling", ["Groq", "groq", "Anthropic", "anthropic"])
    def test_they_resolve_now(self, spelling):
        """
        Both are OpenAI-compatible, which config/llm_providers.yaml already said;
        the registries just never read it.
        兩者皆為 OpenAI 相容（YAML 早已如此宣告），只是註冊表從未讀取。
        """
        assert isinstance(LLMGatewayFactory.create(spelling), OpenAIGateway)

    def test_the_config_chain_registry_has_them_too(self):
        from src.infrastructure.llm.llm_config_chain import _get_gateway_registry

        registry = _get_gateway_registry()
        assert registry.get("groq") is OpenAIGateway
        assert registry.get("anthropic") is OpenAIGateway

    def test_no_try_import_of_a_class_that_does_not_exist(self):
        """
        `except (ImportError, AttributeError): pass` around an import of a
        never-existing class is indistinguishable from an optional dependency
        being absent, which is why this went unnoticed.

        Checked over the AST rather than the text: this module's own docstrings
        quote the deleted code, and so does the docstring in the file under test.
        以 AST 檢查而非文字比對：本檔與受測檔的 docstring 都引用了被刪除的程式碼。
        """
        import ast

        imported = set()
        for node in ast.walk(ast.parse(CHAIN_SRC.read_text())):
            if isinstance(node, ast.ImportFrom):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        assert "GroqGateway" not in imported
        assert "AnthropicGateway" not in imported

    def test_neither_class_actually_exists(self):
        """Documents why the excepts always fired — this is not a missing extra."""
        import src.infrastructure.llm.llm_gateway as gw

        assert not hasattr(gw, "GroqGateway")
        assert not hasattr(gw, "AnthropicGateway")

    def test_the_ai_provider_enum_only_offers_providers_that_resolve(self):
        """
        The original defect in user-visible terms: the settings enum offered a
        provider the factory refused.
        原始缺陷的使用者可見形式：設定選單提供了工廠會拒絕的供應商。
        """
        schema = yaml.safe_load((REPO / "config" / "settings_schema.yaml").read_text())
        field = [s for s in schema["settings"] if s["key"] == "AI_PROVIDER"][0]
        unresolvable = []
        for option in field.get("enum") or []:
            try:
                LLMGatewayFactory.create(option)
            except ValueError:
                unresolvable.append(option)
        assert unresolvable == [], f"offered but not buildable: {unresolvable}"


class TestManifestIsTheSource:

    def test_the_factory_no_longer_hardcodes_the_map(self):
        code = _code_without_comments(GATEWAY_SRC)
        assert '"Google Gemini": GeminiGateway' not in code
        assert '"google_gemini"' not in code

    def test_the_chain_no_longer_hardcodes_the_map(self):
        code = _code_without_comments(CHAIN_SRC)
        assert '"nvidia_nim": NvidiaGateway' not in code
        assert '"openrouter": OpenRouterGateway' not in code

    def test_both_registries_agree_on_every_provider_code(self):
        """Divergence between these two is the bug class this milestone closes."""
        from src.infrastructure.llm.llm_config_chain import _get_gateway_registry

        chain = _get_gateway_registry()
        for code, cls in chain.items():
            if code in LLMGatewayFactory._REGISTRY:
                assert LLMGatewayFactory._REGISTRY[code] is cls, code

    def test_every_declared_provider_can_be_built(self):
        catalog = get_provider_catalog(force_reload=True)
        for code in catalog.codes():
            assert catalog.build_gateway(code) is not None, code

    def test_gateway_classes_must_subclass_the_interface(self):
        """The check that makes a dotted `gateway_class:` in YAML safe to import."""
        from src.domain.interfaces import ILLMGateway

        for cls in get_provider_catalog().gateway_map().values():
            assert issubclass(cls, ILLMGateway)

    def test_mock_is_not_selectable_from_the_manifest(self):
        """A test double must not appear in the operator-facing provider list."""
        raw = yaml.safe_load(PROVIDERS_YAML.read_text())
        assert "mock" not in {p["provider_code"] for p in raw["providers"]}
        # but it stays available to code
        assert isinstance(LLMGatewayFactory.create("mock"), MockLLMGateway)

    def test_an_explicit_registration_survives_the_lazy_load(self):
        """
        `register()` predates the catalog and had no users; if a later lazy load
        overwrote it, an override would silently stop applying.
        register() 若被之後的延遲載入蓋掉，覆寫會靜默失效。
        """
        LLMGatewayFactory._REGISTRY.clear()
        LLMGatewayFactory._registry_loaded = False
        try:
            LLMGatewayFactory.register("OpenRouter", MockLLMGateway)
            assert isinstance(LLMGatewayFactory.create("OpenRouter"), MockLLMGateway)
        finally:
            LLMGatewayFactory._REGISTRY.clear()
            LLMGatewayFactory._registry_loaded = False
        assert isinstance(LLMGatewayFactory.create("OpenRouter"), OpenRouterGateway)


class TestLiveProviderCodesResolve:

    def test_every_alias_in_the_manifest_resolves_to_a_class(self):
        catalog = get_provider_catalog()
        raw = yaml.safe_load(PROVIDERS_YAML.read_text())
        mapping = catalog.gateway_map()
        for provider in raw["providers"]:
            for alias in [provider["provider_code"], *(provider.get("aliases") or [])]:
                assert alias in mapping, alias

    def test_both_nvidia_spellings_are_declared(self):
        """
        The 2026-08-12 incident: the DB uses provider_code 'nvidia_nim' while the
        registry had only 'nvidia', so every NIM-backed candidate was dropped
        from every chain. Keeping both is what prevents the repeat.
        DB 使用 'nvidia_nim' 而註冊表只有 'nvidia'，導致所有 NIM 候選被剔除。
        """
        mapping = get_provider_catalog().gateway_map()
        assert mapping["nvidia"] is NvidiaGateway
        assert mapping["nvidia_nim"] is NvidiaGateway
