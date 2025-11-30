import pytest
from src.agents.momentum import MomentumAgent
from src.agents.fundamental import FundamentalAgent
from src.agents.macro import MacroAgent
from src.agents.cio import CIOAgent

def test_momentum_agent():
    agent = MomentumAgent()
    context = {"ticker": "TEST", "indicators": {"rsi": 50}}
    result = agent.run(context)
    assert isinstance(result, dict)
    assert "signal" in result

def test_fundamental_agent():
    agent = FundamentalAgent()
    context = {"ticker": "TEST", "metrics": {}, "news": []}
    result = agent.run(context)
    assert "Fundamental Analysis" in result

def test_macro_agent():
    agent = MacroAgent()
    context = {"yield_10y": 4.0, "yield_2y": 3.0, "vix": 20}
    result = agent.run(context)
    assert "Macro Outlook" in result

def test_cio_agent():
    agent = CIOAgent()
    context = {
        "macro_report": "Risk-On",
        "momentum_reports": [],
        "fundamental_reports": [],
        "leverage_ratio": 1.0
    }
    result = agent.run(context)
    assert "Weekly Advisory Report" in result
