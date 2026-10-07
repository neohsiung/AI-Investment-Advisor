"""
Unit tests for ModelScannerService and ModelCanaryEvaluator.
模型巡檢與藍綠金絲雀門禁測試套件。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.data.models import LLMModel, LLMProvider, LLMTierBinding
from src.services.model_canary_evaluator import ModelCanaryEvaluator
from src.services.model_scanner_service import ModelScannerService


@pytest.fixture
def mock_scanner_repos():
    provider_repo = MagicMock()
    model_repo = MagicMock()
    tier_repo = MagicMock()
    model_service = MagicMock()
    return provider_repo, model_repo, tier_repo, model_service


def test_scanner_audit_tier_bindings_healthy(mock_scanner_repos):
    p_repo, m_repo, t_repo, m_svc = mock_scanner_repos

    active_provider = LLMProvider(id="prov_1", provider_code="openrouter", enabled=True)
    primary_model = LLMModel(id="mod_primary", provider_id="prov_1", model_code="gpt-4o-mini", enabled=True, display_name="GPT 4o Mini")
    fb_model = LLMModel(id="mod_fb", provider_id="prov_1", model_code="llama-3.1-8b", enabled=True, display_name="Llama 3.1 8B")

    binding = LLMTierBinding(
        id="tb_fast",
        user_id="test_user",
        tier="fast",
        primary_model_id="mod_primary",
        fallback_model_ids=["mod_fb"],
    )

    t_repo.list_by_user.return_value = [binding]
    m_repo.get.side_effect = lambda mid: primary_model if mid == "mod_primary" else fb_model
    p_repo.get.return_value = active_provider

    scanner = ModelScannerService(
        user_id="test_user",
        provider_repo=p_repo,
        model_repo=m_repo,
        tier_repo=t_repo,
        model_service=m_svc,
    )

    audits = scanner.audit_tier_bindings()
    assert "fast" in audits
    assert audits["fast"].is_healthy is True
    assert audits["fast"].needs_action is False
    assert audits["fast"].primary_status.status == "healthy"


def test_scanner_audit_tier_bindings_detects_unhealthy_primary(mock_scanner_repos):
    p_repo, m_repo, t_repo, m_svc = mock_scanner_repos

    active_provider = LLMProvider(id="prov_1", provider_code="openrouter", enabled=True)
    # Primary model is disabled
    disabled_model = LLMModel(id="mod_disabled", provider_id="prov_1", model_code="old-model", enabled=False, display_name="Old Model")

    binding = LLMTierBinding(
        id="tb_fast",
        user_id="test_user",
        tier="fast",
        primary_model_id="mod_disabled",
        fallback_model_ids=[],
    )

    t_repo.list_by_user.return_value = [binding]
    m_repo.get.return_value = disabled_model
    p_repo.get.return_value = active_provider

    scanner = ModelScannerService(
        user_id="test_user",
        provider_repo=p_repo,
        model_repo=m_repo,
        tier_repo=t_repo,
        model_service=m_svc,
    )

    audits = scanner.audit_tier_bindings()
    assert audits["fast"].is_healthy is False
    assert audits["fast"].needs_action is True
    assert audits["fast"].primary_status.status == "disabled"


def test_scanner_proposes_cost_saving_evolution(mock_scanner_repos):
    p_repo, m_repo, t_repo, m_svc = mock_scanner_repos

    active_provider = LLMProvider(id="prov_1", provider_code="openrouter", enabled=True)
    # Expensive current model ($0.010 per 1k = $10/M)
    expensive_model = LLMModel(
        id="mod_expensive",
        provider_id="prov_1",
        model_code="claude-3-opus",
        display_name="Claude Opus",
        input_cost_per_1k=0.008,
        output_cost_per_1k=0.012,
        enabled=True,
    )
    # Cheaper candidate model ($0.002 per 1k = $2/M)
    cheap_candidate = LLMModel(
        id="mod_cheap",
        provider_id="prov_1",
        model_code="deepseek-v3",
        display_name="DeepSeek V3",
        input_cost_per_1k=0.001,
        output_cost_per_1k=0.003,
        enabled=True,
        capability_json_mode=True,
    )

    binding = LLMTierBinding(
        id="tb_smart",
        user_id="test_user",
        tier="smart",
        primary_model_id="mod_expensive",
        fallback_model_ids=[],
    )

    t_repo.list_by_user.return_value = [binding]
    m_repo.get.side_effect = lambda mid: expensive_model if mid == "mod_expensive" else cheap_candidate
    m_repo.list_by_user.return_value = [expensive_model, cheap_candidate]
    p_repo.get.return_value = active_provider

    scanner = ModelScannerService(
        user_id="test_user",
        provider_repo=p_repo,
        model_repo=m_repo,
        tier_repo=t_repo,
        model_service=m_svc,
    )

    proposals = scanner.generate_evolution_proposals()
    assert len(proposals) == 1
    assert proposals[0].tier == "smart"
    assert proposals[0].candidate_model_id == "mod_cheap"
    assert proposals[0].proposal_type == "COST_SAVING"
    assert proposals[0].estimated_cost_saving_pct > 50.0


@pytest.mark.asyncio
async def test_canary_evaluator_promotes_compliant_green_model():
    m_repo = MagicMock()
    p_repo = MagicMock()
    t_repo = MagicMock()
    t_svc = MagicMock()
    cipher = MagicMock()

    cipher.decrypt.return_value = "dummy-api-key"

    prov = LLMProvider(id="prov_1", user_id="test_user", provider_code="openrouter", display_name="OpenRouter", enabled=True, base_url="https://api.test")
    green_model = LLMModel(id="mod_green", provider_id="prov_1", model_code="green-candidate", enabled=True)
    blue_model = LLMModel(id="mod_blue", provider_id="prov_1", model_code="blue-primary", enabled=True)

    binding = LLMTierBinding(
        id="tb_fast",
        user_id="test_user",
        tier="fast",
        primary_model_id="mod_blue",
        fallback_model_ids=["mod_old_fb"],
    )

    m_repo.get.side_effect = lambda mid: green_model if mid == "mod_green" else blue_model
    p_repo.get.return_value = prov
    t_repo.get_by_tier.return_value = binding

    evaluator = ModelCanaryEvaluator(
        user_id="test_user",
        model_repo=m_repo,
        provider_repo=p_repo,
        tier_repo=t_repo,
        tier_service=t_svc,
        cipher=cipher,
    )

    valid_json_response = '{"executive_summary": "Market is strong with tech momentum.", "recommendation": "BUY", "confidence": 0.88}'
    mock_gateway = AsyncMock()
    mock_gateway.chat.return_value = valid_json_response

    with patch("src.services.model_canary_evaluator.LLMGatewayFactory.create", return_value=mock_gateway):
        result = await evaluator.evaluate_and_promote(
            tier="fast",
            candidate_model_id="mod_green",
            current_model_id="mod_blue",
            auto_promote=True,
        )

    assert result.passed is True
    assert result.promoted is True
    assert result.json_compliance is True
    assert result.recommendation_valid is True

    # 驗證 Blue-Green 晉升調用：Green 成為 Primary，Blue 降至首位 Fallback
    t_svc.update_tier_bindings.assert_called_once()
    updated_bindings = t_svc.update_tier_bindings.call_args[0][0]
    assert updated_bindings[0].primary_model_id == "mod_green"
    assert updated_bindings[0].fallback_model_ids[0] == "mod_blue"


@pytest.mark.asyncio
async def test_canary_evaluator_rejects_malformed_json_response():
    m_repo = MagicMock()
    p_repo = MagicMock()
    t_repo = MagicMock()
    t_svc = MagicMock()
    cipher = MagicMock()

    cipher.decrypt.return_value = "dummy-api-key"

    prov = LLMProvider(id="prov_1", user_id="test_user", provider_code="openrouter", display_name="OpenRouter", enabled=True, base_url="https://api.test")
    green_model = LLMModel(id="mod_green", provider_id="prov_1", model_code="broken-candidate", enabled=True)

    m_repo.get.return_value = green_model
    p_repo.get.return_value = prov

    evaluator = ModelCanaryEvaluator(
        user_id="test_user",
        model_repo=m_repo,
        provider_repo=p_repo,
        tier_repo=t_repo,
        tier_service=t_svc,
        cipher=cipher,
    )

    # 模擬常見的大語言模型前言報錯內容（類似 Request 1 中的解析錯誤）
    malformed_response = "We need to produce JSON with fields: executive_summary... but here is some plain text!"
    mock_gateway = AsyncMock()
    mock_gateway.chat.return_value = malformed_response

    with patch("src.services.model_canary_evaluator.LLMGatewayFactory.create", return_value=mock_gateway):
        result = await evaluator.evaluate_and_promote(
            tier="fast",
            candidate_model_id="mod_green",
            current_model_id="mod_blue",
            auto_promote=True,
        )

    assert result.passed is False
    assert result.promoted is False
    assert result.json_compliance is False
    assert any("Invalid JSON" in err for err in result.failure_reasons)
    t_svc.update_tier_bindings.assert_not_called()
