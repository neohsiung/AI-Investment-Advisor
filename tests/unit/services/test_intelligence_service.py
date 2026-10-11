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


def test_parse_llm_json_with_preamble_no_code_block(mock_settings_service):
    """Verify parser extracts JSON when LLM prefixes with prompt regurgitation without markdown blocks."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")
    raw_content = """We need to produce JSON with fields: executive_summary (≤250 Chinese characters), recommendation (specific action)...
{
  "executive_summary": "今日科技股因獲利了結回檔，債市殖利率小幅回落。",
  "recommendation": "適度獲利了結高估值部位，轉向低波動防守型資產。",
  "ai_note": "留意盤前 CPI 數據公布後的連鎖波動。",
  "sentiment_metrics": [
    {"label": "市場多頭動能", "score": 58, "trend": "down"},
    {"label": "避險需求", "score": 42, "trend": "up"},
    {"label": "波動風險", "score": 50, "trend": "stable"}
  ]
}
"""
    result = intel_service._parse_ai_response(raw_content)
    assert result is not None
    assert "今日科技股因獲利了結回檔" in result["executive_summary"]
    assert result["recommendation"] == "適度獲利了結高估值部位，轉向低波動防守型資產。"
    assert len(result["sentiment_metrics"]) == 3


def test_parse_llm_json_with_think_tags(mock_settings_service):
    """Verify parser strips <think> tags containing scratchpad drafts and extracts final code fence."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")
    raw_content = """<think>
We need to produce JSON with fields: executive_summary...
Drafting ideas: {"fake": 123}
</think>
```json
{
  "executive_summary": "聯準會多位官員發表演說，暗示降息步伐依據數據滾動調整。",
  "recommendation": "維持既有資產配置，靜待政策風向明朗。",
  "ai_note": "長端美債殖利率波動收斂。"
}
```
"""
    result = intel_service._parse_ai_response(raw_content)
    assert result is not None
    assert "聯準會多位官員" in result["executive_summary"]
    assert result["observation_window"] == "ACTIVE SESSION"
    assert len(result["sentiment_metrics"]) == 3  # Normalized fallback metrics


def test_parse_llm_json_with_trailing_commas(mock_settings_service):
    """Verify parser handles trailing commas gracefully."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")
    raw_content = """```json
{
  "executive_summary": "原油價格反彈提振能源板塊。",
  "recommendation": "增持抗通膨大宗商品配置。",
}
```"""
    result = intel_service._parse_ai_response(raw_content)
    assert result is not None
    assert "原油價格反彈" in result["executive_summary"]


def test_heuristic_regex_extract_corrupted_json(mock_settings_service):
    """Verify regex heuristic extractor recovers fields when JSON brackets are corrupted."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")
    raw_content = """Some text before...
executive_summary: "地緣衝突升溫導致避險情緒蔓延。",
recommendation: "提高現金儲備至20%以上以防極端外溢。",
Some footer notes...
"""
    result = intel_service._parse_ai_response(raw_content)
    assert result is not None
    assert "地緣衝突升溫" in result["executive_summary"]
    assert "提高現金儲備" in result["recommendation"]
    assert result["ai_note"] == "REGEX_HEURISTIC_RECOVERED"


def test_fallback_error_prevents_prompt_leakage(mock_settings_service):
    """Verify fallback does not leak raw prompt text when LLM outputs pure English rambling."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")
    pure_english_leak = "We need to produce JSON with fields: executive_summary (≤250 Chinese characters), recommendation (sp..."
    res = intel_service._fallback_error(content=pure_english_leak)
    assert "We need to produce" not in res["executive_summary"]
    assert "今日全球市場焦點持續輪動" in res["executive_summary"]
    assert res["recommendation"] == "維持既有防禦姿態與風險預算配置，靜待盤前關鍵數據公布。"


@pytest.mark.asyncio
async def test_get_positions_summary_async_with_broker_and_batch(mock_settings_service):
    """Verify _get_positions_summary_async aggregates active broker holdings and staged batch candidates."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")

    mock_broker = MagicMock()
    mock_p1 = MagicMock(symbol="AAPL.US")
    mock_p2 = MagicMock(symbol="NVDA.US")
    mock_p3 = MagicMock(symbol="TSM.US")
    mock_broker.get_positions = AsyncMock(return_value=[mock_p1, mock_p2, mock_p3])

    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=mock_broker), \
         patch("src.services.batch_cash_deployment_service.BatchCashDeploymentService.get_active_batch_number", new_callable=AsyncMock) as mock_active_batch, \
         patch("src.services.batch_cash_deployment_service.BatchCashDeploymentService.get_deployment_plan", new_callable=AsyncMock) as mock_plan:

        mock_active_batch.return_value = 2
        mock_plan.return_value = {
            "items": [
                {"ticker": "MSFT"},
                {"ticker": "MU"},
                {"ticker": "AMD"},
            ]
        }

        summary_text, focus_tickers = await intel_service._get_positions_summary_async()

        assert "【當前核心活躍持倉】AAPL, NVDA, TSM" in summary_text
        assert "【即將排程分批建倉標的 (第 2 批次)】MSFT, MU, AMD" in summary_text
        assert focus_tickers == ["AAPL", "NVDA", "TSM", "MSFT", "MU", "AMD"]


@pytest.mark.asyncio
async def test_get_positions_summary_async_fallback_to_db(mock_settings_service):
    """Verify _get_positions_summary_async falls back to DB active tickers when broker returns empty."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")

    with patch("src.services.broker_factory.BrokerFactory.get_broker", return_value=None), \
         patch("src.services.transaction_service.TransactionService.get_user_tickers", return_value=["NVDA", "TSM"]), \
         patch("src.services.batch_cash_deployment_service.BatchCashDeploymentService.get_active_batch_number", new_callable=AsyncMock) as mock_active_batch:

        mock_active_batch.return_value = 0

        summary_text, focus_tickers = await intel_service._get_positions_summary_async()

        assert "【當前核心活躍持倉】NVDA, TSM" in summary_text
        assert focus_tickers == ["NVDA", "TSM"]


@pytest.mark.asyncio
async def test_tavily_search_dynamic_queries_with_focus_tickers(mock_settings_service):
    """Verify _tavily_search constructs dynamic queries focusing on active and staged tickers."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")

    import httpx
    mock_resp = httpx.Response(200, json={"results": [{"title": "Tech Earnings", "content": "AI demand strong"}]})

    captured_queries = []

    async def mock_post(url, json=None):
        if json and "query" in json:
            captured_queries.append(json["query"])
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        results = await intel_service._tavily_search("test_key", focus_tickers=["AAPL", "NVDA", "TSM", "MSFT", "MU"])

        assert len(results) > 0
        assert any("AAPL NVDA TSM MSFT 科技股最新動態財報與產業分析" in q for q in captured_queries)
        assert any("美股半導體與 AI 算力供應鏈市場情緒" in q for q in captured_queries)


def test_get_positions_summary_sync_active_tickers(mock_settings_service):
    """Verify _get_positions_summary sync fallback prioritizes active tickers."""
    intel_service = IntelligenceService(settings_service=mock_settings_service, user_id="user_123")

    with patch("src.services.transaction_service.TransactionService.get_user_tickers", return_value=["AAPL", "TSM"]):
        summary = intel_service._get_positions_summary()
        assert "當前關鍵活躍持倉標的包括：AAPL, TSM" in summary


