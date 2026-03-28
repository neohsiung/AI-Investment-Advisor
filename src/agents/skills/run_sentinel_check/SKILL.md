---
name: run_sentinel_check
description: 執行 Sentinel 即時市場巡邏與風險掃描
---

# Run Sentinel Check

觸發 Sentinel 巡邏，執行即時的市場風險掃描與異常偵測。

## When to Use

- 使用者詢問「現在市場有什麼風險？」「需要注意什麼？」
- Heartbeat tick 觸發的例行巡邏
- 外部事件（webhook）觸發的即時評估

## Output Format

返回 Sentinel 掃描結果摘要。
