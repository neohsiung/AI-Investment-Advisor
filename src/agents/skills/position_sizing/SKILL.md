---
name: position_sizing
description: Calculates appropriate trade quantity considering holdings, cash ratio, and risk thresholds.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to calculate the recommended trade quantity for a specific ticker and action. 
It considers the user's current holdings, available cash, and risk settings (e.g., maximum position size).
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "position_sizing"
- `args`: [
    "--user_id", "{{user_id}}",
    "--ticker", "<ticker>",
    "--action", "<BUY|SELL>",
    "--desired_quantity", "<float_default_0>",
    "--intent", "<auto|full_close|partial_reduce>"
  ]

### Examples
User: How many AAPL shares can I buy?
Assistant: <tool_code>run_script(skill_name="position_sizing", args=["--user_id", "{{user_id}}", "--ticker", "AAPL", "--action", "BUY"])</tool_code>

User: Close my TSLA position.
Assistant: <tool_code>run_script(skill_name="position_sizing", args=["--user_id", "{{user_id}}", "--ticker", "TSLA", "--action", "SELL", "--intent", "full_close"])</tool_code>
