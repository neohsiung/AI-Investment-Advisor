"""
Tests for LLM settings error classes to improve coverage.
"""
import pytest
from src.services.llm_settings_errors import (
    LLMSettingsError,
    UnknownProviderCode,
    ProviderNotFound,
    ProviderDisabled,
    ProviderHasModelsError,
    ModelNotFound,
    DuplicateModel,
    ModelInUseError,
)


class TestLLMSettingsErrors:
    """Test all LLM settings error classes."""

    def test_llm_settings_error_base(self):
        err = LLMSettingsError("base error")
        assert str(err) == "base error"
        assert err.error_code == "LLM_SETTINGS_ERROR"
        assert isinstance(err, Exception)

    def test_unknown_provider_code(self):
        err = UnknownProviderCode("openai not found")
        assert err.error_code == "UNKNOWN_PROVIDER_CODE"
        assert isinstance(err, LLMSettingsError)

    def test_provider_not_found(self):
        err = ProviderNotFound("provider missing")
        assert err.error_code == "PROVIDER_NOT_FOUND"
        assert isinstance(err, LLMSettingsError)

    def test_provider_disabled(self):
        err = ProviderDisabled("provider is disabled")
        assert err.error_code == "PROVIDER_DISABLED"
        assert isinstance(err, LLMSettingsError)

    def test_provider_has_models_error(self):
        err = ProviderHasModelsError("prov-123", 5)
        assert err.error_code == "PROVIDER_HAS_MODELS"
        assert err.provider_id == "prov-123"
        assert err.models_count == 5
        assert "prov-123" in str(err)
        assert "5" in str(err)
        assert isinstance(err, LLMSettingsError)

    def test_provider_has_models_error_single_model(self):
        err = ProviderHasModelsError("prov-456", 1)
        assert err.models_count == 1
        assert "prov-456" in str(err)

    def test_model_not_found(self):
        err = ModelNotFound("model missing")
        assert err.error_code == "MODEL_NOT_FOUND"
        assert isinstance(err, LLMSettingsError)

    def test_duplicate_model(self):
        err = DuplicateModel("model already exists")
        assert err.error_code == "DUPLICATE_MODEL"
        assert isinstance(err, LLMSettingsError)

    def test_model_in_use_error(self):
        usages = {
            "tier_bindings": [{"tier": "fast", "id": "t1"}],
            "overrides": [{"agent": "cio", "id": "o1"}, {"agent": "risk", "id": "o2"}],
        }
        err = ModelInUseError("model-abc", usages)
        assert err.error_code == "MODEL_IN_USE"
        assert err.model_id == "model-abc"
        assert err.usages == usages
        # 3 total bindings
        assert "3" in str(err)
        assert "model-abc" in str(err)
        assert isinstance(err, LLMSettingsError)

    def test_model_in_use_error_empty_usages(self):
        err = ModelInUseError("model-xyz", {})
        assert err.model_id == "model-xyz"
        assert "0" in str(err)

    def test_model_in_use_error_single_usage(self):
        usages = {"tier_bindings": [{"tier": "slow"}]}
        err = ModelInUseError("model-001", usages)
        assert "1" in str(err)

    def test_errors_are_catchable_as_base(self):
        """All errors should be catchable as LLMSettingsError."""
        errors = [
            UnknownProviderCode("x"),
            ProviderNotFound("x"),
            ProviderDisabled("x"),
            ProviderHasModelsError("p", 1),
            ModelNotFound("x"),
            DuplicateModel("x"),
            ModelInUseError("m", {}),
        ]
        for err in errors:
            assert isinstance(err, LLMSettingsError)
            assert isinstance(err, Exception)

    def test_raise_and_catch_provider_has_models(self):
        with pytest.raises(ProviderHasModelsError) as exc_info:
            raise ProviderHasModelsError("prov-999", 3)
        assert exc_info.value.provider_id == "prov-999"
        assert exc_info.value.models_count == 3

    def test_raise_and_catch_model_in_use(self):
        usages = {"bindings": [{"id": "b1"}]}
        with pytest.raises(ModelInUseError) as exc_info:
            raise ModelInUseError("model-999", usages)
        assert exc_info.value.model_id == "model-999"
