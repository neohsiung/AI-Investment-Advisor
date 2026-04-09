---
name: financial_modeling_prep
description: Query financial sector performance, stock peers, and company profiles.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to retrieve high-level financial data including market sector performance (useful for sector rotation), competitor/peer stocks, and fundamental company profiles.
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "financial_modeling_prep"
- `args`: [
    "--action", "<sector_performance|peers|profile>",
    "--ticker", "<optional_ticker_for_peers_or_profile>"
  ]

### Examples
User: How are different sectors performing?
Assistant: <tool_code>run_script(skill_name="financial_modeling_prep", args=["--action", "sector_performance"])</tool_code>

User: Who are the competitors of AAPL?
Assistant: <tool_code>run_script(skill_name="financial_modeling_prep", args=["--action", "peers", "--ticker", "AAPL"])</tool_code>
