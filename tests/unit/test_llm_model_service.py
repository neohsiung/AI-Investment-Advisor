"""
Unit tests for LLMModelService (src/services/llm_model_service.py).

Covers:
  - CRUD (create, update, delete)
  - discover (mock gateway, cache behaviour)
  - batch_import (dedup / skip existing)
  - delete blocked when model is in use (ModelInUseError)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.llm_model_service import LLMModelService
from src.services.llm_credential_cipher import LLMCredentialCipher
from src.services.llm_settings_errors import (
    DuplicateModel,
    ModelInUseError,
    ModelNotFound,
    ProviderDisabled,
    ProviderNotFound,
)
from src.domain.interfaces import DiscoveredModel


# ──────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────
USER_ID = "user-test-001"
PROVIDER_ID = "prov-001"
MODEL_ID = "model-001"


def _make_provider_row(enabled=True, provider_code="ollama"):
    row = MagicMock()
    row.id = PROVIDER_ID
    row.user_id = USER_ID
    row.provider_code = provider_code
    row.display_name = "Ollama (Local)"
    row.base_url = "http://localhost:11434/v1"
    row.encrypted_api_key = None
    row.enabled = enabled
    return row


def _make_model_row(
    model_id=MODEL_ID,
    model_code="qwen2.5:7b",
    display_name="Qwen 2.5 7B",
    enabled=True,
):
    row = MagicMock()
    row.id = model_id
    row.provider_id = PROVIDER_ID
    row.model_code = model_code
    row.display_name = display_name
    row.capability_tool_calling = True
    row.capability_vision = False
    row.capability_json_mode = True
    row.capability_streaming = True
    row.capability_embeddings = True
    row.context_window = 32768
    row.input_cost_per_1k = 0.0
    row.output_cost_per_1k = 0.0
    row.source = "manual"
    row.enabled = enabled
    row.notes = None
    return row


def _make_service(
    provider_row=None,
    model_rows=None,
    model_refs=None,
):
    provider_repo = MagicMock()
    model_repo = MagicMock()
    catalog = MagicMock()
    cipher = LLMCredentialCipher(key="")
    usages_service = MagicMock()

    provider_repo.get_for_user.return_value = provider_row
    provider_repo.get.return_value = provider_row
    provider_repo.list_by_provider.return_value = []

    model_repo.list_by_user.return_value = model_rows or []
    model_repo.list_by_provider.return_value = model_rows or []
    model_repo.get.return_value = model_rows[0] if model_rows else None
    model_repo.get_by_provider_and_code.return_value = None
    model_repo.create.return_value = MODEL_ID
    model_repo.batch_create.return_value = []
    model_repo.get_references.return_value = model_refs or {"tier_bindings": [], "agent_overrides": []}

    spec = MagicMock()
    spec.default_base_url = "http://localhost:11434/v1"
    spec.discovery_parser = "parse_ollama_tags"
    catalog.get.return_value = spec

    svc = LLMModelService(
        user_id=USER_ID,
        provider_repo=provider_repo,
        model_repo=model_repo,
        catalog=catalog,
        cipher=cipher,
        usages_service=usages_service,
    )
    return svc, provider_repo, model_repo, catalog


# ──────────────────────────────────────────────────────────────────────
# CRUD — list
# ──────────────────────────────────────────────────────────────────────
def test_list_returns_empty():
    svc, _, _, _ = _make_service(provider_row=_make_provider_row())
    result = svc.list()
    assert result == []


def test_list_by_provider_returns_models():
    prov = _make_provider_row()
    model = _make_model_row()
    svc, _, model_repo, _ = _make_service(provider_row=prov, model_rows=[model])
    model_repo.list_by_provider.return_value = [model]
    result = svc.list(provider_id=PROVIDER_ID)
    assert len(result) == 1
    assert result[0]["model_code"] == "qwen2.5:7b"


def test_list_provider_not_found_raises():
    svc, provider_repo, _, _ = _make_service()
    provider_repo.get_for_user.return_value = None
    with pytest.raises(ProviderNotFound):
        svc.list(provider_id="nonexistent")


# ──────────────────────────────────────────────────────────────────────
# CRUD — create
# ──────────────────────────────────────────────────────────────────────
def test_create_model_success():
    prov = _make_provider_row(enabled=True)
    model = _make_model_row()
    svc, _, model_repo, _ = _make_service(provider_row=prov, model_rows=[model])
    model_repo.get_by_provider_and_code.return_value = None  # no duplicate
    model_repo.get.return_value = model

    result = svc.create({
        "provider_id": PROVIDER_ID,
        "model_code": "qwen2.5:7b",
        "display_name": "Qwen 2.5 7B",
        "capabilities": {"tool_calling": True, "streaming": True},
    })
    model_repo.create.assert_called_once()
    assert result["model_code"] == "qwen2.5:7b"


def test_create_model_provider_not_found():
    svc, provider_repo, _, _ = _make_service()
    provider_repo.get_for_user.return_value = None
    with pytest.raises(ProviderNotFound):
        svc.create({"provider_id": "bad-id", "model_code": "x", "display_name": "X"})


def test_create_model_provider_disabled():
    prov = _make_provider_row(enabled=False)
    svc, _, _, _ = _make_service(provider_row=prov)
    with pytest.raises(ProviderDisabled):
        svc.create({
            "provider_id": PROVIDER_ID,
            "model_code": "qwen2.5:7b",
            "display_name": "Qwen 2.5 7B",
        })


def test_create_model_duplicate_raises():
    prov = _make_provider_row(enabled=True)
    existing = _make_model_row()
    svc, _, model_repo, _ = _make_service(provider_row=prov)
    model_repo.get_by_provider_and_code.return_value = existing  # already exists
    with pytest.raises(DuplicateModel):
        svc.create({
            "provider_id": PROVIDER_ID,
            "model_code": "qwen2.5:7b",
            "display_name": "Qwen 2.5 7B",
        })


# ──────────────────────────────────────────────────────────────────────
# CRUD — update
# ──────────────────────────────────────────────────────────────────────
def test_update_model_success():
    prov = _make_provider_row()
    model = _make_model_row()
    svc, _, model_repo, _ = _make_service(provider_row=prov, model_rows=[model])
    model_repo.update.return_value = model

    result = svc.update(MODEL_ID, {"display_name": "Qwen 7B Updated"})
    model_repo.update.assert_called_once()
    patch_arg = model_repo.update.call_args[0][1]
    assert patch_arg["display_name"] == "Qwen 7B Updated"


def test_update_ignores_provider_id_and_model_code():
    prov = _make_provider_row()
    model = _make_model_row()
    svc, _, model_repo, _ = _make_service(provider_row=prov, model_rows=[model])
    model_repo.update.return_value = model

    svc.update(MODEL_ID, {
        "display_name": "New Name",
        "provider_id": "should-be-ignored",
        "model_code": "should-be-ignored",
    })
    patch_arg = model_repo.update.call_args[0][1]
    assert "provider_id" not in patch_arg
    assert "model_code" not in patch_arg


def test_update_model_not_found():
    svc, _, model_repo, _ = _make_service()
    model_repo.get.return_value = None
    with pytest.raises(ModelNotFound):
        svc.update("nonexistent", {"display_name": "X"})


# ──────────────────────────────────────────────────────────────────────
# CRUD — delete
# ──────────────────────────────────────────────────────────────────────
def test_delete_model_success():
    prov = _make_provider_row()
    model = _make_model_row()
    svc, _, model_repo, _ = _make_service(
        provider_row=prov,
        model_rows=[model],
        model_refs={"tier_bindings": [], "agent_overrides": []},
    )
    svc.delete(MODEL_ID)
    model_repo.delete.assert_called_once_with(MODEL_ID)


def test_delete_model_in_use_raises():
    prov = _make_provider_row()
    model = _make_model_row()
    refs = {
        "tier_bindings": [{"tier": "nano", "role": "primary", "user_id": USER_ID}],
        "agent_overrides": [],
    }
    svc, _, _, _ = _make_service(provider_row=prov, model_rows=[model], model_refs=refs)
    with pytest.raises(ModelInUseError) as exc_info:
        svc.delete(MODEL_ID)
    assert exc_info.value.model_id == MODEL_ID
    assert len(exc_info.value.usages["tier_bindings"]) == 1


def test_delete_model_not_found():
    svc, _, model_repo, _ = _make_service()
    model_repo.get.return_value = None
    with pytest.raises(ModelNotFound):
        svc.delete("nonexistent")


# ──────────────────────────────────────────────────────────────────────
# discover
# ──────────────────────────────────────────────────────────────────────
DISCOVERED = [
    DiscoveredModel(model_code="qwen2.5:7b", display_name="Qwen 7B", input_cost_per_1k=0.0, output_cost_per_1k=0.0),
    DiscoveredModel(model_code="qwen2.5:14b", display_name="Qwen 14B", input_cost_per_1k=0.0, output_cost_per_1k=0.0),
]


@pytest.mark.asyncio
async def test_discover_calls_gateway_list_models():
    prov = _make_provider_row()
    svc, _, model_repo, catalog = _make_service(provider_row=prov)
    model_repo.list_by_provider.return_value = []

    mock_gateway = AsyncMock()
    mock_gateway.list_models = AsyncMock(return_value=DISCOVERED)
    catalog.build_gateway.return_value = mock_gateway

    # Clear in-memory cache to avoid cross-test pollution
    import src.services.llm_model_service as svc_module
    svc_module._discovery_cache.clear()

    result = await svc.discover(PROVIDER_ID, force_refresh=True)

    mock_gateway.list_models.assert_called_once()
    assert result["provider_id"] == PROVIDER_ID
    assert len(result["data"]) == 2


@pytest.mark.asyncio
async def test_discover_marks_already_imported():
    prov = _make_provider_row()
    existing_model = _make_model_row(model_code="qwen2.5:7b")
    svc, _, model_repo, catalog = _make_service(provider_row=prov)
    model_repo.list_by_provider.return_value = [existing_model]

    mock_gateway = AsyncMock()
    mock_gateway.list_models = AsyncMock(return_value=DISCOVERED)
    catalog.build_gateway.return_value = mock_gateway

    import src.services.llm_model_service as svc_module
    svc_module._discovery_cache.clear()

    result = await svc.discover(PROVIDER_ID, force_refresh=True)

    data = {item["model_code"]: item for item in result["data"]}
    assert data["qwen2.5:7b"]["already_imported"] is True
    assert data["qwen2.5:14b"]["already_imported"] is False


@pytest.mark.asyncio
async def test_discover_uses_cache_on_second_call():
    prov = _make_provider_row()
    svc, _, model_repo, catalog = _make_service(provider_row=prov)
    model_repo.list_by_provider.return_value = []

    mock_gateway = AsyncMock()
    mock_gateway.list_models = AsyncMock(return_value=DISCOVERED)
    catalog.build_gateway.return_value = mock_gateway

    import src.services.llm_model_service as svc_module
    svc_module._discovery_cache.clear()

    # First call — hits gateway
    await svc.discover(PROVIDER_ID, force_refresh=True)
    # Second call — should use cache (no force_refresh)
    result2 = await svc.discover(PROVIDER_ID, force_refresh=False)

    assert result2["cached"] is True
    # Gateway should only have been called once
    assert mock_gateway.list_models.call_count == 1


# ──────────────────────────────────────────────────────────────────────
# batch_import
# ──────────────────────────────────────────────────────────────────────
def test_batch_import_inserts_new_models():
    prov = _make_provider_row(enabled=True)
    svc, _, model_repo, _ = _make_service(provider_row=prov)
    model_repo.list_by_provider.return_value = []  # nothing existing
    new_model = _make_model_row(model_code="qwen2.5:14b")
    model_repo.batch_create.return_value = ["new-id-001"]
    model_repo.get.return_value = new_model

    result = svc.batch_import(PROVIDER_ID, [
        {"model_code": "qwen2.5:14b", "display_name": "Qwen 14B"},
    ])
    assert result["imported"] == 1
    assert result["skipped"] == 0


def test_batch_import_skips_existing():
    prov = _make_provider_row(enabled=True)
    existing = _make_model_row(model_code="qwen2.5:7b")
    svc, _, model_repo, _ = _make_service(provider_row=prov)
    model_repo.list_by_provider.return_value = [existing]
    model_repo.batch_create.return_value = []

    result = svc.batch_import(PROVIDER_ID, [
        {"model_code": "qwen2.5:7b", "display_name": "Qwen 7B"},
    ])
    assert result["imported"] == 0
    assert result["skipped"] == 1


def test_batch_import_mixed():
    prov = _make_provider_row(enabled=True)
    existing = _make_model_row(model_code="qwen2.5:7b")
    svc, _, model_repo, _ = _make_service(provider_row=prov)
    model_repo.list_by_provider.return_value = [existing]
    new_model = _make_model_row(model_code="qwen2.5:14b")
    model_repo.batch_create.return_value = ["new-id-001"]
    model_repo.get.return_value = new_model

    result = svc.batch_import(PROVIDER_ID, [
        {"model_code": "qwen2.5:7b", "display_name": "Qwen 7B"},   # skip
        {"model_code": "qwen2.5:14b", "display_name": "Qwen 14B"}, # import
    ])
    assert result["imported"] == 1
    assert result["skipped"] == 1


def test_batch_import_provider_disabled_raises():
    prov = _make_provider_row(enabled=False)
    svc, _, _, _ = _make_service(provider_row=prov)
    with pytest.raises(ProviderDisabled):
        svc.batch_import(PROVIDER_ID, [{"model_code": "x", "display_name": "X"}])
