---
name: get_portfolio
description: Retrieve the user's current portfolio holdings and leverage.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this tool to see what the user currently owns. Returns a list of tickers, quantities, and current leverage ratio.

### Examples
User: What do I own?
Assistant: <tool_code>get_portfolio(user_id="user_123")</tool_code>
