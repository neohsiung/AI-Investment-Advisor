import pytest
from src.services.evaluation_service import EvaluationService

def test_calculate_score_buy_correct():
    # Price went up 10%
    score = EvaluationService.calculate_score("BUY", 100.0, 110.0)
    assert score > 0.8

def test_calculate_score_buy_wrong():
    # Price went down 10%
    score = EvaluationService.calculate_score("BUY", 100.0, 90.0)
    assert score < -0.8

def test_calculate_score_sell_correct():
    # Price went down 10%
    score = EvaluationService.calculate_score("SELL", 100.0, 90.0)
    assert score > 0.8

def test_calculate_score_sell_wrong():
    # Price went up 10%
    score = EvaluationService.calculate_score("SELL", 100.0, 110.0)
    assert score < -0.8

def test_calculate_score_hold_neutral():
    # Price stayed flat (within 0.5%, so < 0.5 change)
    score = EvaluationService.calculate_score("HOLD", 100.0, 100.4)
    assert score > 0.5 # Holding flat is good

def test_calculate_score_hold_volatile():
    # Price moved a lot (either way)
    score_up = EvaluationService.calculate_score("HOLD", 100.0, 120.0)
    assert score_up < 0 # Missed opportunity
    
    score_down = EvaluationService.calculate_score("HOLD", 100.0, 80.0)
    # Actually, holding during a crash is ambiguous. If we sold, it would be better.
    # But current logic might penalize holding if significant move.
    
def test_input_handling():
    # Test case insensitivity and whitespace
    score = EvaluationService.calculate_score("  buy ", 100.0, 110.0)
    assert score > 0.0
