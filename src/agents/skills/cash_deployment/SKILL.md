---
name: cash_deployment
description: 分析閒置現金並提供部署建議 (Analyze idle cash and provide deployment suggestions).
category: analysis
tier: smart
input_schema:
  type: object
  properties:
    user_id: 
      type: string
      description: User ID context
  required: [user_id]
output_schema:
  type: object
  properties:
    status: {type: string}
    cash_ratio: {type: number}
    target_ratio: {type: number}
    excess_cash: {type: number}
    candidates: {type: array}
---

# Cash Deployment Skill

## 概述 (Overview)
此技能用於分析投資組合中的閒置現金。它檢索帳戶餘額，計算相對於目標現金比例的「超額現金」(Excess Cash)，並提供可部署這些資金的潛在候選標的。

## 指令 (Instruction)
使用此技能來獲取資金效率報告。
這是一個 CLI 工具，必須使用 `run_script` 執行。

### Required Arguments for run_script:
Assistant: <tool_code>run_script(skill_name="cash_deployment", args=["--user_id", "{{user_id}}"])</tool_code>

### 輸出結構 (Output Structure)
回傳一個 JSON 字串，包含：
- `status`: "balanced" | "overweight"
- `cash_ratio`: 當前現金比例 (0.0 - 1.0)
- `excess_cash`: 可部署金額 (USD)
- `candidates`: 建議部署的標的清單及理由
