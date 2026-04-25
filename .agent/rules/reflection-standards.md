# Cognitive Governance: Reflection & Self-Healing Standards

These standards define the requirements for autonomous self-healing (reflection) operations within the agent system.

## 1. Observability (Metadata Tagging)

All LLM calls initiated as part of a reflection/self-healing cycle **MUST** be tagged with metadata for budget and performance auditing.

- **Agent Name**: Use the calling agent's name (e.g., `AgentLoop`, `SkillRouter`).
- **Tag**: Always include `"tag": "reflection"`.
- **Context**: Include relevant context such as `"tool": "tool_name"` or `"skill": "skill_name"`.


Example Implementation:
```python
llm = await LoggingLLMGateway(
    inner=raw_llm,
    agent_name="AgentLoop",
    tier="smart",
    user_id=user_id,
    metadata={"tag": "reflection", "tool": tool_name}
)
```

## 2. Emergency Mode (Budget-Aware Prompting)

To maintain system autonomy during budget constraints, the system switches to **Emergency Mode** when the weekly budget exceeds the `BUDGET_SOFT_LIMIT`.

### 2.1 Trigger Condition
- If `router.is_budget_critical(user_id)` returns `True`.

### 2.2 Prompt Behavior
- **Standard Mode**: Use `ReflectionPrompt.build()`. Provides rich context and double-checks (Simplified dual-language).
- **Emergency Mode**: Use `ReflectionPrompt.build_compressed()`. Provides minimal JSON-only instructions for logic extraction (English only).

## 3. Performance Metrics

Every reflection event (whether it results from an error or a timeout) must be recorded using `EvolutionMetrics`.

Required Fields:

- `tool_name`: The tool that failed.
- `error_type`: The exception class or type string.
- `action`: The corrective action recommended by the LLM (e.g., `fix_args`, `retry`).
- `success`: Boolean indicating if the reflection process itself completed successfully.
- `duration_ms`: Time taken for the reflection call.

## 4. Log Auditing

Metrics are persisted to `evolution_metrics.jsonl`. This log is the source of truth for the **Self-Healing Report** generated in phase transitions.

- **Success Rate**: Aim for >80% effective fixes in non-critical mode.
- **Cost Ratio**: Reflection costs should not exceed 20% of total weekly LLM spending.
