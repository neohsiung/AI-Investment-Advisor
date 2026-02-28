# Multi-Agent Workspace

This directory contains the independent brains for the 9 agents in the AI Investment Advisor platform.
Each agent has its own directory containing its identity, state (WAL), and long-term memory, ensuring strict role-level isolation.

## Directory Structure
- `IDENTITY.md`: The agent's core persona, system prompts, and unchangeable constraints.
- `SOUL.md`: Deeper characteristics, decision-making biases, and learning styles.
- `MEMORY.md`: Long-term persistent memory (user preferences, past mistakes learned).
- `HEARTBEAT.md`: (For Active Agents) The checklist of tasks to run during periodic awakenings.
- `STATE.md`: The WAL (Write-Ahead Logging) for the agent to reconstruct thought processes after context flush.
