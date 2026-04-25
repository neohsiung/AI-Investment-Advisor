"""
Unit tests for LLMProviderService (src/services/llm_provider_service.py).

Covers:
  - CRUD operations (create, update, delete)
  - API key encryption / decryption / masking
  - test_connection (mock Gateway.ping)
  - delete blocked when models exist (ProviderHasModelsError)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.services.llm_provider_service import LLMProviderService
from src.services.llm_credential_cipher import LLMCredentialCipher
from src.services.llm_settings_errors import (
    ProviderHasModelsError,
    ProviderNotFound,
    UnknownProviderCode,
)
from src.domain.interfaces import PingResult


# ──────────────────────────────────────────────────────────────────────
# Helpers / Fixtures
# ──────────────────────────────────────────────────────────────────────
USER_ID = "user-test-001"
PROVIDER_ID = "prov-001"


def _make_provider_row(
    provider_id=PROVIDER_ID,
    provider_code="ollama",
    display_name="Ollama (Local)",
    base_url="http://localhost:11434/v1",
    encrypted_api_key=None,
    enabled=True,
    health_status=None,
    health_detail=None,
    last_checked_at=None,
):
    row = MagicMock()
    row.id = provider_id
    row.user_id = USER_ID
    row.provider_code = provider_code
    row.display_name = display_name
    row.base_url = base_url
    row.encrypted_api_key = encrypted_api_key
    row.enabled = enabled
    row.extra_config = {}
    row.health_status = health_status
    row.health_detail = health_detail
    row.last_checked_at = last_checked_at
    return row


def _make_service(
    provider_rows=None,
    model_count=0,
    catalog_codes=None,
):
    """Build a LLMProviderService with mocked dependencies."""
    provider_repo = MagicMock()
    model_repo = MagicMock()
    catalog = MagicMock()
    cipher = LLMCredentialCipher(key="")  # fallback mode (no Fernet key)
    usages_service = MagicMock()

    # Default: list returns empty
    provider_repo.list_by_user.return_value = provider_rows or []
    provider_repo.get.return_value = provider_rows[0] if provider_rows else None
    provider_repo.get_for_user.return_value = provider_rows[0] if provider_rows else None
    provider_repo.count_models.return_value = model_count
    provider_repo.create.return_value = PROVIDER_ID
    provider_repo.update.return_value = provider_rows[0] if provider_rows else None

    # Catalog
    catalog.codes.return_value = catalog_codes or ["ollama", "openai", "openrouter", "gemini", "anthropic", "groq"]
    spec = MagicMock()
    spec.default_base_url = "http://localhost:11434/v1"
    spec.default_capabilities.tool_calling = True
    spec.default_capabilities.streaming = True
    spec.default_capabilities.vision = False
    spec.default_capabilities.json_mode = True
    spec.default_capabilities.embeddings = True
    spec.default_capabilities.local = True
    catalog.get.return_value = spec

    svc = LLMProviderService(
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
def test_list_returns_empty_when_no_providers():
    svc, _, _, _ = _make_service()
    result = svc.list()
    assert result == []


def test_list_returns_serialized_providers():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row])
    provider_repo.count_models.return_value = 3
    result = svc.list()
    assert len(result) == 1
    assert result[0]["id"] == PROVIDER_ID
    assert result[0]["provider_code"] == "ollama"
    assert result[0]["model_count"] == 3


# ──────────────────────────────────────────────────────────────────────
# CRUD — create
# ──────────────────────────────────────────────────────────────────────
def test_create_valid_provider():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row])
    result = svc.create({
        "provider_code": "ollama",
        "display_name": "Ollama (Local)",
        "base_url": "http://localhost:11434/v1",
        "api_key": None,
        "enabled": True,
    })
    provider_repo.create.assert_called_once()
    assert result["id"] == PROVIDER_ID


def test_create_unknown_provider_code_raises():
    svc, _, _, _ = _make_service()
    with pytest.raises(UnknownProviderCode):
        svc.create({
            "provider_code": "nonexistent_provider",
            "display_name": "Bad Provider",
        })


def test_create_encrypts_api_key():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row])
    svc.create({
        "provider_code": "openai",
        "display_name": "OpenAI",
        "api_key": "sk-test-key-12345",
    })
    call_kwargs = provider_repo.create.call_args
    payload = call_kwargs[0][1]  # second positional arg is the payload dict
    # The stored key must NOT be the plaintext
    assert payload.get("encrypted_api_key") != "sk-test-key-12345"
    # But it must be decryptable
    decrypted = svc.cipher.decrypt(payload.get("encrypted_api_key"))
    assert decrypted == "sk-test-key-12345"


# ──────────────────────────────────────────────────────────────────────
# CRUD — update
# ──────────────────────────────────────────────────────────────────────
def test_update_display_name():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row])
    svc.update(PROVIDER_ID, {"display_name": "Ollama (GPU Box)"})
    provider_repo.update.assert_called_once()
    patch_arg = provider_repo.update.call_args[0][1]
    assert patch_arg["display_name"] == "Ollama (GPU Box)"


def test_update_api_key_none_leaves_unchanged():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row])
    svc.update(PROVIDER_ID, {"api_key": None})
    patch_arg = provider_repo.update.call_args[0][1]
    assert "encrypted_api_key" not in patch_arg


def test_update_api_key_empty_string_clears():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row])
    svc.update(PROVIDER_ID, {"api_key": ""})
    patch_arg = provider_repo.update.call_args[0][1]
    assert patch_arg["encrypted_api_key"] is None


def test_update_api_key_string_encrypts():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row])
    svc.update(PROVIDER_ID, {"api_key": "new-secret-key"})
    patch_arg = provider_repo.update.call_args[0][1]
    assert patch_arg["encrypted_api_key"] != "new-secret-key"
    assert svc.cipher.decrypt(patch_arg["encrypted_api_key"]) == "new-secret-key"


def test_update_not_found_raises():
    svc, provider_repo, _, _ = _make_service()
    provider_repo.get_for_user.return_value = None
    with pytest.raises(ProviderNotFound):
        svc.update("nonexistent-id", {"display_name": "X"})


# ──────────────────────────────────────────────────────────────────────
# CRUD — delete
# ──────────────────────────────────────────────────────────────────────
def test_delete_success_when_no_models():
    row = _make_provider_row()
    svc, provider_repo, _, _ = _make_service(provider_rows=[row], model_count=0)
    svc.delete(PROVIDER_ID)
    provider_repo.delete.assert_called_once_with(PROVIDER_ID)


def test_delete_raises_when_models_exist():
    row = _make_provider_row()
    svc, _, _, _ = _make_service(provider_rows=[row], model_count=3)
    with pytest.raises(ProviderHasModelsError) as exc_info:
        svc.delete(PROVIDER_ID)
    assert exc_info.value.models_count == 3


def test_delete_not_found_raises():
    svc, provider_repo, _, _ = _make_service()
    provider_repo.get_for_user.return_value = None
    with pytest.raises(ProviderNotFound):
        svc.delete("nonexistent-id")


# ──────────────────────────────────────────────────────────────────────
# Encryption / Decryption / Masking
# ──────────────────────────────────────────────────────────────────────
def test_cipher_encrypt_decrypt_roundtrip():
    cipher = LLMCredentialCipher(key="")  # fallback mode
    plaintext = "sk-or-v1-abc123xyz"
    encrypted = cipher.encrypt(plaintext)
    assert encrypted != plaintext
    assert cipher.decrypt(encrypted) == plaintext


def test_cipher_mask_shows_partial():
    cipher = LLMCredentialCipher(key="")
    plaintext = "sk-or-v1-abc123xyz"
    encrypted = cipher.encrypt(plaintext)
    masked = cipher.mask(encrypted)
    assert masked is not None
    assert "****" in masked
    # Should show last 4 chars of plaintext
    assert plaintext[-4:] in masked


def test_cipher_none_passthrough():
    cipher = LLMCredentialCipher(key="")
    assert cipher.encrypt(None) is None
    assert cipher.decrypt(None) is None
    assert cipher.mask(None) is None


def test_cipher_empty_string_passthrough():
    cipher = LLMCredentialCipher(key="")
    assert cipher.encrypt("") == ""
    assert cipher.decrypt("") == ""
    assert cipher.mask("") == ""


# ──────────────────────────────────────────────────────────────────────
# test_connection
# ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_test_connection_success():
    row = _make_provider_row()
    svc, provider_repo, _, catalog = _make_service(provider_rows=[row])

    mock_gateway = AsyncMock()
    mock_gateway.ping = AsyncMock(return_value=PingResult(
        ok=True, latency_ms=42.0, detail={"available_models": 2}
    ))
    catalog.build_gateway.return_value = mock_gateway

    result = await svc.test_connection(PROVIDER_ID)

    assert result["ok"] is True
    assert result["latency_ms"] == 42.0
    assert result["error"] is None
    # Should persist health_status
    provider_repo.update.assert_called()
    update_patch = provider_repo.update.call_args[0][1]
    assert update_patch["health_status"] == "ok"


@pytest.mark.asyncio
async def test_test_connection_failure():
    row = _make_provider_row()
    svc, provider_repo, _, catalog = _make_service(provider_rows=[row])

    mock_gateway = AsyncMock()
    mock_gateway.ping = AsyncMock(return_value=PingResult(
        ok=False, latency_ms=2000.0, error="Connection refused"
    ))
    catalog.build_gateway.return_value = mock_gateway

    result = await svc.test_connection(PROVIDER_ID)

    assert result["ok"] is False
    assert "Connection refused" in result["error"]
    update_patch = provider_repo.update.call_args[0][1]
    assert update_patch["health_status"] == "error"


@pytest.mark.asyncio
async def test_test_connection_not_implemented_graceful():
    row = _make_provider_row()
    svc, provider_repo, _, catalog = _make_service(provider_rows=[row])

    mock_gateway = AsyncMock()
    mock_gateway.ping = AsyncMock(side_effect=NotImplementedError("no ping"))
    catalog.build_gateway.return_value = mock_gateway

    result = await svc.test_connection(PROVIDER_ID)

    assert result["ok"] is False
    assert "not implement" in result["error"].lower()
    update_patch = provider_repo.update.call_args[0][1]
    assert update_patch["health_status"] == "unknown"


@pytest.mark.asyncio
async def test_test_connection_not_found_raises():
    svc, provider_repo, _, _ = _make_service()
    provider_repo.get_for_user.return_value = None
    with pytest.raises(ProviderNotFound):
        await svc.test_connection("nonexistent-id")
