"""
Unit tests for LLMModelLifecycleService and Blue-Green Canary Evolution.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.llm_model_lifecycle_service import (
    LLMModelLifecycleService,
    ScanModelReport,
)
from src.data.models import (
    LLMModel,
    LLMProvider,
    LLMTierBinding,
    LLMBlueGreenDeployment,
)


@pytest.fixture
def mock_repos():
    provider_repo = MagicMock()
    model_repo = MagicMock()
    tier_repo = MagicMock()
    model_service = MagicMock()
    tier_service = MagicMock()
    return provider_repo, model_repo, tier_repo, model_service, tier_service


@pytest.mark.asyncio
async def test_scan_and_evolve_models_discovery_and_import(mock_repos):
    """驗證模型自動探索與批次匯入流程"""
    p_repo, m_repo, t_repo, m_svc, t_svc = mock_repos

    # 模擬 1 個啟用中的 Provider
    active_prov = LLMProvider(id="prov_1", provider_code="nvidia_nim", enabled=True)
    p_repo.list_by_user.return_value = [active_prov]

    # 模擬 discovery 回傳未匯入的新模型
    m_svc.discover = AsyncMock(return_value={
        "data": [
            {"model_code": "new-fast-model", "already_imported": False, "display_name": "New Fast"},
            {"model_code": "existing-model", "already_imported": True, "display_name": "Existing"},
        ]
    })
    m_svc.batch_import.return_value = {"imported": 1, "skipped": 1}

    # 模擬空 Tier 綁定
    t_repo.list_by_user.return_value = []

    service = LLMModelLifecycleService(
        user_id="test_user",
        provider_repo=p_repo,
        model_repo=m_repo,
        tier_repo=t_repo,
        model_service=m_svc,
        tier_service=t_svc,
    )

    report: ScanModelReport = await service.scan_and_evolve_models()

    assert report.discovered_count == 2
    assert report.new_imported_count == 1
    m_svc.batch_import.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_deprecates_retired_models(mock_repos):
    """驗證退役/下架模型（如 deepseek-v4-flash）被自動停用"""
    p_repo, m_repo, t_repo, m_svc, t_svc = mock_repos
    p_repo.list_by_user.return_value = []

    # 模擬 Tier 引用了一個退役模型
    retired_model = LLMModel(
        id="mod_retired",
        provider_id="prov_1",
        model_code="deepseek-ai/deepseek-v4-flash",
        enabled=True,
    )
    binding = LLMTierBinding(
        id="tb_1",
        user_id="test_user",
        tier="fast",
        primary_model_id="mod_retired",
        fallback_model_ids=[],
    )
    t_repo.list_by_user.return_value = [binding]
    m_repo.get.return_value = retired_model

    service = LLMModelLifecycleService(
        user_id="test_user",
        provider_repo=p_repo,
        model_repo=m_repo,
        tier_repo=t_repo,
        model_service=m_svc,
        tier_service=t_svc,
    )

    report = ScanModelReport()
    await service._health_check_active_models(report)

    assert report.deprecated_count == 1
    m_repo.update.assert_called_once_with(
        "mod_retired",
        {"enabled": False, "notes": "Auto-disabled: Retired/Deprecated model"}
    )


@pytest.mark.asyncio
async def test_blue_green_promotion_when_green_saves_cost(mock_repos):
    """驗證性價比更高的 Green 模型通過基準驗證後被安全晉升，且 Blue 被降級為首位備援"""
    p_repo, m_repo, t_repo, m_svc, t_svc = mock_repos

    # Blue 是收費模型 ($0.005)
    blue_model = LLMModel(
        id="mod_blue",
        provider_id="prov_paid",
        model_code="openrouter/expensive-model",
        input_cost_per_1k=0.003,
        output_cost_per_1k=0.002,
        enabled=True,
    )
    # Green 是同等級免費模型 ($0.0)
    green_model = LLMModel(
        id="mod_green",
        provider_id="prov_free",
        model_code="nvidia_nim/free-lightning-model",
        input_cost_per_1k=0.0,
        output_cost_per_1k=0.0,
        enabled=True,
    )

    binding = LLMTierBinding(
        id="tb_fast",
        user_id="test_user",
        tier="fast",
        primary_model_id="mod_blue",
        fallback_model_ids=["mod_old_fb"],
    )

    m_repo.get.side_effect = lambda mid: blue_model if mid == "mod_blue" else green_model
    m_repo.list_by_user.return_value = [blue_model, green_model]
    t_repo.list_by_user.return_value = [binding]

    service = LLMModelLifecycleService(
        user_id="test_user",
        provider_repo=p_repo,
        model_repo=m_repo,
        tier_repo=t_repo,
        model_service=m_svc,
        tier_service=t_svc,
    )

    # 模擬基準測試通過
    benchmark_res = {
        "blue_latency_ms": 2000.0,
        "green_latency_ms": 1200.0,
        "blue_success_rate": 1.0,
        "green_success_rate": 1.0,
        "blue_cost": 0.005,
        "green_cost": 0.0,
        "cost_saving_pct": 100.0,
        "is_eligible_for_promotion": True,
        "notes": "Green verified healthy and cost-effective",
    }
    service._run_canary_benchmark = AsyncMock(return_value=benchmark_res)
    service._external_session = MagicMock()

    report = ScanModelReport()
    await service._evaluate_and_evolve_tiers(report)

    assert report.evaluated_blue_green == 1
    assert report.promoted_count == 1

    # 驗證晉升時呼叫了 update_tier_bindings
    t_svc.update_tier_bindings.assert_called_once()
    called_update = t_svc.update_tier_bindings.call_args[0][0][0]
    assert called_update.tier == "fast"
    assert called_update.primary_model_id == "mod_green"
    # 原 Blue 必須退到 Fallback 的第一位
    assert called_update.fallback_model_ids[0] == "mod_blue"
