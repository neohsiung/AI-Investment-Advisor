import pytest
from src.services.reporting_service import ReportingService

def test_generate_professional_html_basic():
    service = ReportingService()
    markdown = "# Title\nThis is a test."
    html = service.generate_professional_html(markdown, title="Test Report")
    
    assert "<title>Test Report</title>" in html
    assert "Test Report" in html
    assert "<h1" in html
    assert "This is a test." in html
    assert "投資有風險" in html  # Disclaimer check

def test_generate_professional_html_complex():
    service = ReportingService()
    markdown = """
## Analysis
| Asset | Price |
|-------|-------|
| BTC   | 70000 |

> Strategic note
"""
    html = service.generate_professional_html(markdown)
    
    assert "<table" in html
    assert "70000" in html
    assert "Strategic note" in html
    assert "<blockquote" in html

def test_generate_professional_html_error_handling():
    service = ReportingService()
    # Force an error by causing markdown conversion to fail (if possible) or mocking it
    from unittest.mock import patch
    with patch.object(service.md, "convert", side_effect=Exception("MD Fail")):
        html = service.generate_professional_html("# Fail")
        assert "Error generating report" in html
        assert "MD Fail" in html
