---
name: get_portfolio
description: Retrieve the user's current portfolio holdings and leverage.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to retrieve the current portfolio status, holdings summary, and latest leverage for a user.
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "get_portfolio"
- `args`: ["--user_id", "{{user_id}}"]

### Examples
User: What are my current holdings?
Assistant: <tool_code>run_script(skill_name="get_portfolio", args=["--user_id", "{{user_id}}"])</tool_code>
