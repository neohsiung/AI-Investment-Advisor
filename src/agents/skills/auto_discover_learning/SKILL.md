---
name: auto_discover_learning
description: Trigger auto-discovery investment skill learning. 自動搜尋最佳投資文章並萃取為技能。
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to trigger the automatic discovery and learning of new investment skills from online articles or specified content.
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "auto_discover_learning"
- `args`: ["--user_id", "{{user_id}}"]

### Examples
User: Find new investment skills for me.
Assistant: <tool_code>run_script(skill_name="auto_discover_learning", args=["--user_id", "{{user_id}}"])</tool_code>
