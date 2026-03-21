# Position Sizing Skill

---
name: position_sizing
description: 計算適當的交易數量，考慮實際持倉、現金比例與風險閾值。
metadata:
  openclaw:
    os: [linux, darwin]
---

## Instruction

Use this skill **before executing any trade** to determine the appropriate quantity.
It queries the broker for actual holdings and account data, then calculates a safe trade quantity.

- **SELL**: Clamps quantity to actual holdings. Supports `full_close` / `partial_reduce` / `auto` intents.
- **BUY**: Clamps quantity to available cash and max single position percentage.
- Returns pre/post cash ratio estimates for impact evaluation.

### When to Use

- Before any BUY or SELL trade execution
- When ActionExtractor needs to determine quantity for a recommendation
- During emergency liquidation to get actual holding quantities

### Rules

1. **Always call this before `execute_order`** to avoid over-selling or over-buying
2. If `recommended_quantity` is 0, the Agent MUST skip the trade
3. For SELL: `intent=full_close` returns full holding; `intent=partial_reduce` returns min(desired, actual)
4. For BUY: quantity is clamped to `min(desired, available_cash, nlv * max_position_pct)`

### Examples

User: 幫我賣出 TSLA
Assistant: Let me first check the appropriate quantity.

```tool_code
position_sizing(ticker="TSLA", action="SELL", intent="full_close")
```

Result: `{ "recommended_quantity": 0.5, "actual_holding": 0.5, "reason": "Full close of TSLA position (0.5 units)" }`

User: 買入 100 美元的 NVDA
Assistant: Let me verify the sizing against portfolio limits.

```tool_code
position_sizing(ticker="NVDA", action="BUY", desired_quantity=100)
```

Result: `{ "recommended_quantity": 100, "actual_holding": 10, "reason": "Within limits (max position 10% of NLV)" }`
