---
name: position_sizing
description: 計算適當的交易數量，考慮持有量、現金比例與風險閾值 (Calculate trade quantity considering holdings, cash ratio, and risk thresholds).
category: risk
tier: fast
input_schema:
  type: object
  properties:
    user_id: {type: string}
    ticker: {type: string}
    action: {type: string, enum: [BUY, SELL]}
    desired_quantity: {type: number}
    intent: {type: string, enum: [auto, full_close, partial_reduce]}
  required: [user_id, ticker, action]
output_schema:
  type: object
  properties:
    recommended_quantity: {type: number}
    actual_holding: {type: number}
    cash_ratio_before: {type: number}
---

# Position Sizing Skill

## 指令 (Instruction)
使用此技能計算特定標的與動作的推薦交易數量。它會考慮用戶當前持倉、可用現金與風險設定。

### Required Arguments for run_script:
Assistant: <tool_code>run_script(skill_name="position_sizing", args=["--user_id", "{{user_id}}", "--ticker", "AAPL", "--action", "BUY"])</tool_code>
