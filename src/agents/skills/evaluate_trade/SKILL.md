---
name: evaluate_trade
description: 評估並執行交易指令 (Evaluate and execute a trade order with risk checks)
---

# Evaluate Trade

評估交易指令的可行性，通過風控檢查後執行。

## When to Use

- Workflow 產出 Actionable Orders 後的執行步驟
- 使用者在頻道要求執行特定交易（需經 Approval 流程）
- Sentinel 觸發的防禦性交易

## Important

此 skill 涉及資金操作，在 Channel 場景中應先觸發 Approval 流程而非直接執行。
