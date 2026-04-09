---
name: etoro_trade
description: Execute trades on eToro and check trading status.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to place BUY or SELL orders on eToro, or to check the current trading system status (risk controls).
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "etoro_trade"
- `args`: [
    "--user_id", "{{user_id}}",
    "--action", "<BUY|SELL|STATUS>",
    "--ticker", "<ticker>",
    "--amount", "<float_usd>",
    "--leverage", "<int_default_1>",
    "--reason", "<string_reason>"
  ]

### Examples
User: Buy $100 of AAPL.
Assistant: <tool_code>run_script(skill_name="etoro_trade", args=["--user_id", "{{user_id}}", "--action", "BUY", "--ticker", "AAPL", "--amount", 100])</tool_code>

User: Is trading allowed right now?
Assistant: <tool_code>run_script(skill_name="etoro_trade", args=["--user_id", "{{user_id}}", "--action", "STATUS"])</tool_code>
