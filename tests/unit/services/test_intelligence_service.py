"""
Unit tests for IntelligenceService.
驗證市場情報簡報生成、ResilientLLMPipeline 串接與過時 API Key 移除。
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.intelligence_service import IntelligenceService


@pytest.fixture
def mock_settings_service():
    service = MagicMock()
    service.get_setting.side_effect = lambda key, default=None: {
        "source_tavily_api_key": "tvly-test-12345",
        "openrouter_api_key": "sk-or-test",
        "AI_PROVIDER": "OpenRouter",
    }.get(key, default)
    return service


@pytest.mark.asyncio
async def test_compute_briefing_with_resilient_pipeline(mock_settings_service):
    """Verify compute_briefing uses ResilientLLMPipeline without needing legacy API_KEY."""
    mock_llm_json = json.dumps({
        "executive_summary": "市場表現平穩，科技股領漲，利率前景明確。",
        "recommendation": "維持現有核心持倉，持續關注動能指標。",
        "ai_note": "整體總經環境維持健康。",
        "observation_window": "ACTIVE SESSION",
        "sentiment_metrics": [
            {"label": "市場多頭動能", "score": 75, "trend": "up"},
            {"label": "避險需求", "score": 25, "trend": "stable"},
            {"label": "波動風險", "score": 35, "trend": "down"}
        ]
    })

    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")

    with patch("src.infrastructure.llm.llm_config_chain.build_config_chain") as mock_chain, \
         patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute", new_callable=AsyncMock) as mock_exec, \
         patch.object(intel_service, "_tavily_search", new_callable=AsyncMock) as mock_tavily:
        
        mock_chain.return_value = [MagicMock()]
        mock_exec.return_value = (mock_llm_json, [])
        mock_tavily.return_value = [{"title": "Fed Meeting", "content": "Rate cut imminent"}]

        briefing = await intel_service.compute_briefing()

        assert briefing is not None
        assert "市場表現平穩" in briefing["executive_summary"]
        assert briefing["recommendation"] == "維持現有核心持倉，持續關注動能指標。"
        assert len(briefing["sentiment_metrics"]) == 3
        assert mock_exec.await_count == 1


@pytest.mark.asyncio
async def test_compute_briefing_llm_failure_fallback(mock_settings_service):
    """Verify compute_briefing falls back gracefully when LLM fails without crashing."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")

    with patch("src.infrastructure.llm.llm_config_chain.build_config_chain", side_effect=Exception("LLM down")), \
         patch.object(intel_service, "_tavily_search", new_callable=AsyncMock) as mock_tavily:
        
        mock_tavily.return_value = []
        briefing = await intel_service.compute_briefing()

        assert briefing is not None
        assert "情報生成途中發生錯誤" in briefing["executive_summary"] or "AI 回傳內容為空" in briefing["executive_summary"]
        assert "self_evolution_summary" in briefing


@pytest.mark.asyncio
async def test_get_latest_briefing_cache(mock_settings_service):
    """Verify get_latest_briefing parses cached JSON properly."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")

    cached_data = {
        "executive_summary": "快取之情報摘要",
        "recommendation": "保持中性",
        "sentiment_metrics": []
    }
    mock_settings_service.get_setting.side_effect = lambda key, default=None: {
        "cached_intelligence_briefing": json.dumps(cached_data),
        "last_intelligence_timestamp": "2026-09-29 08:00:00",
    }.get(key, default)

    res = await intel_service.get_latest_briefing()
    assert res["executive_summary"] == "快取之情報摘要"
    assert "UPDATED: 2026-09-29 08:00:00" in res["observation_window"]
