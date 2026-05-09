"""
src/agents/engineer.py
=======================
Backwards-compatibility shim.

SystemEngineerAgent was moved to src/agents/system_engineer_agent.py
as part of the v7.0 agent consolidation cleanup.

This module re-exports everything from the new canonical location so that
existing tests and any third-party imports continue to work without changes.

DO NOT add new code here. Use the canonical module instead:
  src/agents/system_engineer_agent.py
"""
from src.agents.system_engineer_agent import SystemEngineerAgent  # noqa: F401

__all__ = ["SystemEngineerAgent"]
