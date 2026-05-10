"""
src/agents/swarm/swarm_orchestrator.py
=======================================
Backwards-compatibility shim.

SwarmOrchestrator was moved to src/agents/orchestration/swarm_orchestrator.py
as part of the v7.0 orchestration layer refactor.

This module re-exports everything from the new canonical location so that
existing tests and any third-party imports continue to work without changes.

DO NOT add new code here. Use the canonical module instead:
  src/agents/orchestration/swarm_orchestrator.py
"""
from src.agents.orchestration.swarm_orchestrator import SwarmOrchestrator  # noqa: F401
from src.repositories.agent_repository import AlchemyAgentRepository  # noqa: F401

__all__ = ["SwarmOrchestrator", "AlchemyAgentRepository"]
