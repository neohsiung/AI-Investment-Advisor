import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.nlp.intent_classifier import IntentClassifier

@pytest.fixture
def intent_classifier():
    with patch('src.agents.factory.AgentFactory.create_agent') as mock_factory:
        mock_agent = MagicMock()
        mock_factory.return_value = mock_agent
        ic = IntentClassifier()
        ic.agent = mock_agent
        return ic

def test_classify_approve_keyword(intent_classifier):
    # Setup: Keyword fallback
    intent = intent_classifier.classify("執行吧")
    
    assert intent == "APPROVE"
    intent_classifier.agent.run.assert_not_called()

def test_classify_reject_keyword(intent_classifier):
    # Setup: Keyword fallback
    intent = intent_classifier.classify("不執行")
    
    assert intent == "REJECT"
    intent_classifier.agent.run.assert_not_called()

def test_classify_llm_approve(intent_classifier):
    # Setup: LLM fallback
    intent_classifier.agent.run.return_value = "APPROVE"
    
    intent = intent_classifier.classify("我也覺得應該買進")
    
    assert intent == "APPROVE"
    intent_classifier.agent.run.assert_called()

def test_classify_llm_reject(intent_classifier):
    # Setup: LLM fallback
    intent_classifier.agent.run.return_value = "REJECT"
    
    intent = intent_classifier.classify("現在太危險了，先不要")
    
    assert intent == "REJECT"
    intent_classifier.agent.run.assert_called()

def test_classify_unknown(intent_classifier):
    # Setup: LLM returns nonsense
    intent_classifier.agent.run.return_value = "HELLO WORLD"
    
    intent = intent_classifier.classify("今天天氣如何？")
    
    assert intent == "UNKNOWN"

def test_classify_exception(intent_classifier):
    # Setup: Agent fails
    intent_classifier.agent.run.side_effect = Exception("Agent Error")
    
    intent = intent_classifier.classify("執行？")
    
    # Keyword fallback might handle it, but if we pass something without keywords:
    intent = intent_classifier.classify("幫我查氣象")
    
    assert intent == "UNKNOWN"
