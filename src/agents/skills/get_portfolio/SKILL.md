---
name: get_portfolio
description: 獲取當前持倉與帳戶摘要 (Fetch current holdings and account summary).
category: portfolio
tier: fast
input_schema:
  type: object
  properties:
    user_id: {type: string}
  required: [user_id]
output_schema:
  type: object
---

# Get Portfolio Skill

## 指令 (Instruction)
獲取用戶當前投資組合狀態、持倉摘要與最新槓桿資訊。

### Required Arguments for run_script:
Assistant: <tool_code>run_script(skill_name="get_portfolio", args=["--user_id", "{{user_id}}"])</tool_code>
