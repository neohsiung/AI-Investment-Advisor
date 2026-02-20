---
name: swarm-orchestration-pattern
description: Defines the architecture and asyncio implementation patterns for the Role x Multi-Tier Agent Swarm (Fast, Smart, Advanced). Use this when building or modifying SwarmOrchestrator or Sub-Agents.
---

# Agent Swarm Orchestration Guidelines

## When to use this skill
- Implementing the 3-Tier agent execution (Fast, Smart, Advanced).
- Writing `asyncio.gather` logic for parallel LLM API calls.
- Modifying `SwarmOrchestrator` or `WorkflowService`.

## How to use it

### 1. Fan-out Architecture
Always split tasks into the three defined tiers based on the requirement:
- **Fast Tier**: Quick checks, risk scanning, sentiment snapshot. (Low complexity, high speed).
- **Smart Tier**: Standard logic, synthesis, specific domain tasks. (Balanced).
- **Advanced Tier**: Deep reasoning, "Knowledge Graph" traversal, complex strategy. (High latency, high cost).

### 2. Concurrency Control
- Use `asyncio.gather` to run tiers in parallel where possible.
- Wrap calls in `asyncio.Semaphore` if hitting APU limits.

#### Example Pattern
```python
import asyncio

async def run_swarm(self, task_context):
    results = await asyncio.gather(
        self.fast_agent.run(task_context),
        self.smart_agent.run(task_context),
        self.advanced_agent.run(task_context),
        return_exceptions=True
    )
    return self.fuse_results(results)
```

### 3. Fusion Logic (Fan-in)
- Implement a **Fusion Strategy** to combine results.
- **Graceful Degradation**: If `Fast` agent fails (or timeouts), the system should still proceed with `Smart`/`Advanced` results (or vice versa).
- **Conflict Resolution**: Define strict rules. E.g., if `RiskAgent` (Fast) says "Critical Danger", it overrides `FundamentalAgent` (Advanced) "Buy" signal unless the Advanced agent explicitly addresses the risk.

### 4. Error Handling
- Use `return_exceptions=True` in `gather` to prevent one failure from crashing the whole swarm.
- Log all sub-agent failures distinctly.
