"""
Tests for GapDetector — Task 4A-4.
"""
import asyncio
import json
import os
import pytest
import sys
from unittest.mock import MagicMock, patch, AsyncMock

# Ensure project root is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.skills.gap_detector import GapDetector, GapReport
from src.agents.skills.skill_loader import SkillMetadata


def _make_mock_skills():
    """Create a minimal set of mock skills for testing."""
    return {
        "get_market_data": SkillMetadata(name="get_market_data", description="Fetches market data for a ticker"),
        "get_user_holdings": SkillMetadata(name="get_user_holdings", description="Gets user portfolio holdings"),
        "get_macro_summary": SkillMetadata(name="get_macro_summary", description="Gets macro economic indicators"),
        "run_momentum_analysis": SkillMetadata(name="run_momentum_analysis", description="Runs momentum/RSI/MACD analysis"),
        "search_web": SkillMetadata(name="search_web", description="Searches the web for information"),
    }


class TestGapReport:
    def test_dataclass_creation(self):
        report = GapReport(is_gap=True, suggested_skill_name="test_skill")
        assert report.is_gap is True
        assert report.suggested_skill_name == "test_skill"

    def test_to_dict(self):
        report = GapReport(is_gap=False, reasoning="No gap")
        d = report.to_dict()
        assert d["is_gap"] is False
        assert d["reasoning"] == "No gap"


class TestGapDetectorHeuristics:
    def test_trivial_message_skipped(self):
        """Short/trivial messages should NOT trigger gap detection."""
        detector = GapDetector()
        result = asyncio.get_event_loop().run_until_complete(
            detector.detect("嗯", _make_mock_skills())
        )
        assert result.is_gap is False
        assert "Trivial" in result.reasoning

    def test_greeting_skipped(self):
        detector = GapDetector()
        result = asyncio.get_event_loop().run_until_complete(
            detector.detect("你好", _make_mock_skills())
        )
        assert result.is_gap is False


class TestGapDetectorLLM:
    @patch("src.agents.skills.gap_detector.GapDetector._load_prompt", return_value="dummy prompt")
    @pytest.mark.asyncio
    async def test_gap_detected(self, mock_load):
        """When LLM reports a gap, GapReport should reflect it."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = json.dumps({
            "is_gap": True,
            "suggested_skill_name": "get_crypto_data",
            "suggested_category": "market_data",
            "reasoning": "需要加密貨幣數據源",
            "can_auto_scaffold": True,
            "existing_similar": "get_market_data"
        })

        detector = GapDetector(llm_gateway=mock_llm)
        result = await detector.detect("幫我查一下比特幣的價格是多少？", _make_mock_skills())
        assert result.is_gap is True
        assert result.suggested_skill_name == "get_crypto_data"
        assert result.existing_similar == "get_market_data"

    @patch("src.agents.skills.gap_detector.GapDetector._load_prompt", return_value="dummy prompt")
    @pytest.mark.asyncio
    async def test_no_gap(self, mock_load):
        """When LLM reports no gap, should return is_gap=False."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = json.dumps({
            "is_gap": False,
            "suggested_skill_name": "",
            "suggested_category": "",
            "reasoning": "可透過 get_market_data 取得",
            "can_auto_scaffold": False,
            "existing_similar": "get_market_data"
        })

        detector = GapDetector(llm_gateway=mock_llm)
        result = await detector.detect("NVDA 的股價是多少？", _make_mock_skills())
        assert result.is_gap is False

    @patch("src.agents.skills.gap_detector.GapDetector._load_prompt", return_value="dummy prompt")
    @pytest.mark.asyncio
    async def test_malformed_json_handled(self, mock_load):
        """Malformed LLM response should not crash, return is_gap=False."""
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "This is not JSON"

        detector = GapDetector(llm_gateway=mock_llm)
        result = await detector.detect("一個需要分析的長問題說明看看", _make_mock_skills())
        assert result.is_gap is False
        assert "Parse error" in result.reasoning or "Error" in result.reasoning


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
