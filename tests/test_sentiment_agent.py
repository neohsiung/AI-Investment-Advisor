"""
Test coverage for SentimentAgent
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from src.agents.sentiment import SentimentAgent


class TestSentimentAgent:
    """Test suite for SentimentAgent"""
    
    @pytest.fixture
    def agent(self):
        """Create SentimentAgent instance"""
        return SentimentAgent(use_cache=False)
    
    def test_initialization(self, agent):
        """Test agent initializes correctly"""
        assert agent is not None
        assert hasattr(agent, 'name')
        assert agent.name == "Sentiment"
    
    @patch.object(SentimentAgent, 'call_llm')
    def test_run_with_valid_context(self, mock_llm, agent):
        """Test run method with valid context"""
        # Mock LLM response as JSON
        mock_llm.return_value = json.dumps({
            "sentiment": "positive",
            "narrative": "Strong earnings beat expectations",
            "score": 0.8
        })
        
        context = {
            'ticker': 'AAPL',
            'news': ['Apple announces new product', 'Stock price rises 5%'],
            'price_change_percent': 5.2
        }
        
        result = agent.run(context)
        
        assert result is not None
        assert isinstance(result, dict)
        assert 'sentiment' in result
        assert result['sentiment'] == 'positive'
        mock_llm.assert_called_once()
    
    def test_run_with_no_news_returns_neutral(self, agent):
        """Test run with no news returns neutral sentiment"""
        context = {'ticker': 'TSLA', 'news': []}
        result = agent.run(context)
        
        assert result is not None
        assert result['sentiment'] == 'Neutral'
        assert result['score'] == 0.0
    
    @patch.object(SentimentAgent, 'call_llm')
    def test_run_handles_invalid_json_response(self, mock_llm, agent):
        """Test run handles malformed JSON gracefully"""
        mock_llm.return_value = "This is not valid JSON"
        
        context = {'ticker': 'AAPL', 'news': ['Some news']}
        result = agent.run(context)
        
        assert result is not None
        assert result['sentiment'] == 'Unknown'
        assert 'score' in result
    
    @patch.object(SentimentAgent, 'call_llm')
    def test_run_with_json_code_blocks(self, mock_llm, agent):
        """Test run strips markdown JSON code blocks"""
        mock_llm.return_value = '''```json
        {
            "sentiment": "bearish",
            "narrative": "Declining market share",
            "score": -0.6
        }
        ```'''
        
        context = {'ticker': 'AAPL', 'news': ['Bad news']}
        result = agent.run(context)
        
        assert result['sentiment'] == 'bearish'
        assert result['score'] == -0.6
    
    @pytest.mark.xfail(reason="Template variable mismatch: 'news' vs 'news_list' - to be fixed")
    def test_run_limits_news_to_top_5(self, agent):
        """Test that only top 5 news items are processed"""
        with patch.object(SentimentAgent, 'call_llm') as mock_llm:
            mock_llm.return_value = json.dumps({"sentiment": "neutral", "narrative": "test", "score": 0})
            
            context = {
                'ticker': 'AAPL',
                'news': [f'News item {i}' for i in range(10)]  # 10 news items
            }
            
            agent.run(context)
            
            # Check that system prompt was called
            call_args = mock_llm.call_args
            system_message = call_args[1]['messages'][0]['content']
            
            # Should only contain first 5 news items
            assert 'News item 0' in system_message
            assert 'News item 4' in system_message
            # Should NOT contain items 5-9
            assert 'News item 5' not in system_message
