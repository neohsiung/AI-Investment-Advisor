---
name: get_market_data
description: Fetch quantitative market data for a ticker (Price, Volume, RSI, MACD).
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this skill to fetch technical and fundamental data for a specific stock ticker.
This skill is implemented as a CLI tool. You must use the generic `run_script` tool to execute it.

### Required Arguments for run_script:
- `skill_name`: "get_market_data"
- `args`: ["--user_id", "{{user_id}}", "--ticker", "<ticker_symbol>"]

### Examples
User: Check AAPL technicals.
Assistant: <tool_code>run_script(skill_name="get_market_data", args=["--user_id", "{{user_id}}", "--ticker", "AAPL"])</tool_code>
