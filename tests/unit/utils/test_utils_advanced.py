"""
Extended tests for utility functions.
測試工具函數。
"""
import pytest
from src.utils.format_utils import format_agent_output


class TestFormatUtils:
    
    def test_format_agent_output_with_sentiment_dict(self):
        """Test formatting sentiment output."""
        output = {
            "sentiment_score": 0.85,
            "sentiment_label": "Positive",
            "summary": "Market sentiment is bullish"
        }
        
        result = format_agent_output(output)
        
        assert "Score" in result
        assert "0.85" in result
        assert "Positive" in result
        assert "bullish" in result
    
    def test_format_agent_output_with_score_variant(self):
        """Test formatting with score instead of sentiment_score."""
        output = {
            "score": 0.75,
            "label": "Neutral",
            "summary": "Mixed signals"
        }
        
        result = format_agent_output(output)
        
        assert "Score" in result
        assert "0.75" in result
        assert "Neutral" in result
    
    def test_format_agent_output_with_valuation_dict(self):
        """Test formatting fundamental/valuation output."""
        output = {
            "valuation": "Undervalued",
            "thesis": "Strong fundamentals with low P/E ratio"
        }
        
        result = format_agent_output(output)
        
        assert "Valuation" in result
        assert "Undervalued" in result
        assert "Strong fundamentals" in result
    
    def test_format_agent_output_with_generic_dict(self):
        """Test formatting generic dictionary output."""
        output = {
            "price": "$150.00",
            "volume": "1.2M",
            "status": "Active"
        }
        
        result = format_agent_output(output)
        
        assert "price" in result
        assert "$150.00" in result
        assert "volume" in result
    
    def test_format_agent_output_with_string(self):
        """Test formatting plain string output."""
        output = "This is a plain text analysis."
        
        result = format_agent_output(output)
        
        assert result == output
    
    def test_format_agent_output_with_dict_string(self):
        """Test formatting dictionary represented as string."""
        output = "{'sentiment_score': 0.9, 'sentiment_label': 'Very Positive'}"
        
        result = format_agent_output(output)
        
        # Should parse and format as dict
        assert "Score" in result
        assert "0.9" in result
    
    def test_format_agent_output_with_invalid_string(self):
        """Test formatting invalid dict string."""
        output = "Not a valid dict: {'incomplete"
        
        result = format_agent_output(output)
        
        # Should return original string
        assert result == output
    
    def test_format_agent_output_with_none(self):
        """Test formatting None value."""
        output = None
        
        result = format_agent_output(output)
        
        assert result == "None"
    
    def test_format_agent_output_with_number(self):
        """Test formatting numeric output."""
        output = 42
        
        result = format_agent_output(output)
        
        assert result == "42"
    
    def test_format_agent_output_with_empty_dict(self):
        """Test formatting empty dictionary."""
        output = {}
        
        result = format_agent_output(output)
        
        assert result == ""
    
    def test_format_agent_output_with_nested_dict(self):
        """Test formatting nested dictionary."""
        output = {
            "analysis": {
                "score": 0.8,
                "details": "Good"
            }
        }
        
        result = format_agent_output(output)
        
        assert "analysis" in result
    
    def test_format_agent_output_with_list_value(self):
        """Test formatting dictionary with list value."""
        output = {
            "recommendations": ["BUY", "HOLD"],
            "reason": "Strong uptrend"
        }
        
        result = format_agent_output(output)
        
        assert "recommendations" in result
        assert "reason" in result
