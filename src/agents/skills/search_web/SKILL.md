---
name: search_web
description: Search the internet for financial news, reports, and data.
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
Use this tool to search for real-time information, news, or specific data points that are not in your internal memory.
Preferred queries should be specific.

### Examples
User: What is the current price of NVDA?
Assistant: <tool_code>search_web(query="NVDA stock price live")</tool_code>

User: Find recent news about TSLA.
Assistant: <tool_code>search_web(query="TSLA latest news")</tool_code>
