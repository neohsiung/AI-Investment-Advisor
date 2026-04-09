---
name: get_historical_report
description: Fetch a historical investment report (e.g., last week's WeeklyWorkflow) to compare current signals and justify strategy adjustments.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to fetch previous investment reports (WeeklyWorkflow or DailyWorkflow). 
This is useful for comparing current market conditions with past analysis to justify strategy shifts.
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "get_historical_report"
- `args`: [
    "--user_id", "{{user_id}}",
    "--report_type", "<WeeklyWorkflow|DailyWorkflow>",
    "--weeks_ago", "<integer_default_1>"
  ]

### Examples
User: Show me last week's report.
Assistant: <tool_code>run_script(skill_name="get_historical_report", args=["--user_id", "{{user_id}}", "--report_type", "WeeklyWorkflow", "--weeks_ago", 1])</tool_code>
