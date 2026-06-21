"""
Tests for NotificationValueAssessor (src/services/notification_value_assessor.py).
"""
import pytest
from unittest.mock import AsyncMock, patch
from src.services.notification_value_assessor import assess_notification_value, _call_llm_assessment


@pytest.mark.asyncio
async def test_assess_notification_valuable():
    with patch("src.services.notification_value_assessor._call_llm_assessment", AsyncMock(return_value="VALUABLE: actionable rebalancing recommendation")) as mock_call:
        should_send, reason = await assess_notification_value(
            title="Overweight Cash Alert",
            content="Cash ratio is 69%, please rebalance.",
            category="alert",
            user_id="test-user"
        )
        assert should_send is True
        assert "VALUABLE" in reason
        mock_call.assert_called_once()


@pytest.mark.asyncio
async def test_assess_notification_noise():
    with patch("src.services.notification_value_assessor._call_llm_assessment", AsyncMock(return_value="NOISE: vague hold recommendation")) as mock_call:
        should_send, reason = await assess_notification_value(
            title="No action required",
            content="Everything is fine, just hold.",
            category="report",
            user_id="test-user"
        )
        assert should_send is False
        assert "NOISE" in reason


@pytest.mark.asyncio
async def test_assess_notification_failure_fallback():
    # If LLM assessment fails, it should fallback to returning True (always send)
    with patch("src.services.notification_value_assessor._call_llm_assessment", AsyncMock(side_effect=Exception("LLM crash"))):
        should_send, reason = await assess_notification_value(
            title="Crash test",
            content="LLM will fail.",
            category="alert",
            user_id="test-user"
        )
        assert should_send is True
        assert "unavailable" in reason


@pytest.mark.asyncio
async def test_call_llm_assessment_success():
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = ("VALUABLE: test reason", 1)
    
    with patch("src.infrastructure.llm.budget_aware_model_router.BudgetAwareModelRouter.get_resilient_gateway", return_value=mock_pipeline):
        res = await _call_llm_assessment("System prompt", "User prompt", "test-user")
        assert res == "VALUABLE: test reason"
