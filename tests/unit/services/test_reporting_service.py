import pytest
from src.services.reporting_service import ReportingService

def test_generate_professional_html_basic():
    service = ReportingService()
    markdown_content = """# Market Analysis
## Summary
* Bullish on tech.
* Bearish on energy.

| Asset | Signal |
|-------|--------|
| NVDA  | BUY    |
"""
    title = "Weekly Strategic Report"
    html_output = service.generate_professional_html(markdown_content, title=title)
    
    assert "<title>Weekly Strategic Report</title>" in html_output
    assert "Market Analysis" in html_output
    assert "Bullish on tech" in html_output
    assert "NVDA" in html_output
    assert "投資有風險" in html_output  # Chinese disclaimer
    assert "style=" in html_output  # Ensure styling is applied

def test_generate_professional_html_error_handling():
    service = ReportingService()
    # Mocking self.md.convert to raise an exception
    original_convert = service.md.convert
    service.md.convert = lambda x: 1/0  # Raise ZeroDivisionError
    
    markdown_content = "# Test"
    html_output = service.generate_professional_html(markdown_content)
    
    assert "Error generating report" in html_output
    assert "division by zero" in html_output
    
    # Restore original convert for other tests if any
    service.md.convert = original_convert
