import pytest
from src.services.evaluation_service import EvaluationService


@pytest.fixture
def service():
    """Default EvaluationService with default threshold."""
    return EvaluationService()


def test_calculate_score_buy_correct(service):
    # Price went up 10%
    score = service.calculate_score("BUY", 100.0, 110.0)
    assert score > 0.8


def test_calculate_score_buy_wrong(service):
    # Price went down 10%
    score = service.calculate_score("BUY", 100.0, 90.0)
    assert score < -0.8


def test_calculate_score_sell_correct(service):
    # Price went down 10%
    score = service.calculate_score("SELL", 100.0, 90.0)
    assert score > 0.8


def test_calculate_score_sell_wrong(service):
    # Price went up 10%
    score = service.calculate_score("SELL", 100.0, 110.0)
    assert score < -0.8


def test_calculate_score_hold_neutral(service):
    # Price stayed flat (within 0.5%, so < 0.5 change)
    score = service.calculate_score("HOLD", 100.0, 100.4)
    assert score > 0.5  # Holding flat is good


def test_calculate_score_hold_volatile(service):
    # Price moved a lot (either way)
    score_up = service.calculate_score("HOLD", 100.0, 120.0)
    assert score_up < 0  # Missed opportunity

    score_down = service.calculate_score("HOLD", 100.0, 80.0)
    # Actually, holding during a crash is ambiguous. If we sold, it would be better.
    # But current logic penalizes holding if significant move.
    assert score_down < 0


def test_input_handling(service):
    # Test case insensitivity and whitespace
    score = service.calculate_score("  buy ", 100.0, 110.0)
    assert score > 0.0


def test_custom_threshold():
    # Test that the threshold is configurable (Rule #8 compliance)
    # 測試閾值是否可配置（符合規則 #8）
    service = EvaluationService(flat_threshold=0.10)  # 10% threshold
    # 5% move should be NEUTRAL with 10% threshold
    score = service.calculate_score("BUY", 100.0, 105.0)
    assert score == 0.0
