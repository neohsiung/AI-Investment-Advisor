---
name: investment_skill
description: 根據當前市場環境、時間框架與產業，查詢並推薦最適用的投資技能
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction

此工具用於查詢投資技能庫，根據當前市場環境回傳最適用的投資技能與策略建議。

技能庫中的技能來自每日自動學習的投資方法論文章與 Podcast，包含：
- **時間框架** (short_term / medium_term / long_term)
- **市場環境** (bull / bear / sideways / volatile)
- **產業** (tech / healthcare / financials / energy 等)
- **投資技術** (momentum / fundamental / macro / quantitative / sentiment / event_driven / value / growth / income / contrarian)

### 使用時機
- Agent 在執行投資分析時，需要根據當前環境選擇最適合的分析框架
- CIO Agent 在綜合各 Agent 意見時，需要參考適用的投資策略
- 當市場環境發生變化（如從 bull → bear），需要調整投資方法

### 參數
- `timeframe` (optional): 篩選特定時間框架的技能
- `market_regime` (optional): 篩選適用於特定市場環境的技能
- `industry` (optional): 篩選特定產業的技能
- `technique` (optional): 篩選特定投資技術的技能

所有參數皆為 optional，不輸入任何參數則回傳所有可用技能。

### Examples

User: 目前市場高波動，有什麼適合短線的策略？
Assistant: <tool_code>investment_skill(timeframe="short_term", market_regime="volatile")</tool_code>

User: 科技股基本面分析有哪些技能可以參考？
Assistant: <tool_code>investment_skill(industry="tech", technique="fundamental")</tool_code>

User: 列出所有可用的投資技能
Assistant: <tool_code>investment_skill()</tool_code>
