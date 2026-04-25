---
name: etoro_trade
description: 執行 eToro 交易指令或查詢狀態 (Execute eToro trades or check status).
category: trading
tier: smart
input_schema:
  type: object
  properties:
    user_id: {type: string}
    action: {type: string, enum: [BUY, SELL, STATUS]}
    ticker: {type: string}
    amount: {type: number}
    quantity: {type: number}
  required: [user_id, action]
output_schema:
  type: object
---

# eToro Trade Skill

## 指令 (Instruction)
在 eToro 下單，或檢查目前交易系統狀態。

### Required Arguments for run_script:
Assistant: <tool_code>run_script(skill_name="etoro_trade", args=["--user_id", "{{user_id}}", "--action", "BUY", "--ticker", "AAPL", "--amount", 100])</tool_code>
