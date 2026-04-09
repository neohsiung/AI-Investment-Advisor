---
name: investment_skill
description: Queries applicable investment skills based on current context.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to query applicable investment strategies and skills from the knowledge vault based on the current market context.
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "investment_skill"
- `args`: [
    "--user_id", "{{user_id}}",
    "--timeframe", "<short|medium|long>",
    "--market_regime", "<bull|bear|sideways>",
    "--industry", "<tech|finance|energy|...>",
    "--technique", "<momentum|value|growth|...>"
  ]

### Examples
User: What momentum strategies should I use for tech stocks?
Assistant: <tool_code>run_script(skill_name="investment_skill", args=["--user_id", "{{user_id}}", "--industry", "tech", "--technique", "momentum"])</tool_code>
