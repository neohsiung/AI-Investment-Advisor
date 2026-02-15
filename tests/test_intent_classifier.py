import pytest
from unittest.mock import MagicMock, patch
from src.infrastructure.nlp.intent_classifier import IntentClassifier

@pytest.fixture
def mock_agent():
    return MagicMock()

def test_intent_classifier_approve(mock_agent):
    with patch("src.infrastructure.nlp.intent_classifier.AgentFactory.create_agent") as mock_create:
        mock_agent.run.return_value = "APPROVE"
        mock_create.return_value = mock_agent
        
        classifier = IntentClassifier()
        result = classifier.classify("Yes, execute the trade")
        assert result == "APPROVE"

def test_intent_classifier_reject(mock_agent):
    with patch("src.infrastructure.nlp.intent_classifier.AgentFactory.create_agent") as mock_create:
        mock_agent.run.return_value = "REJECT"
        mock_create.return_value = mock_agent
        
        classifier = IntentClassifier()
        result = classifier.classify("No, cancel it")
        assert result == "REJECT"

def test_intent_classifier_keywords():
    # Test direct keyword pre-checks without LLM
    classifier = IntentClassifier()
    with patch.object(classifier, 'agent') as mock_agent:
        assert classifier.classify("執行") == "APPROVE"
        assert classifier.classify("不執行") == "REJECT"
        assert classifier.classify("取消") == "REJECT"
        mock_agent.run.assert_not_called()

def test_intent_classifier_exception(mock_agent):
    with patch("src.infrastructure.nlp.intent_classifier.AgentFactory.create_agent") as mock_create:
        mock_create.return_value = mock_agent
        classifier = IntentClassifier()
        
        # Test exception during run, not init
        mock_agent.run.side_effect = Exception("LLM Error")
        result = classifier.classify("Approve")
        assert result == "UNKNOWN"
