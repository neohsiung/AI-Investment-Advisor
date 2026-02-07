---
name: get_market_data
description: Fetch quantitative market data for a ticker (Price, Volume, RSI, MACD).
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this tool to get technical and fundamental data for a specific stock ticker.
This returns a JSON object with price, changes, and key indicators.

### Examples
User: Check AAPL technicals.
Assistant: <tool_code>get_market_data(ticker="AAPL")</tool_code>
