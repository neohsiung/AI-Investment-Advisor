---
name: auto_discover_learning
description: 自動搜尋網路上最佳投資策略文章，萃取為結構化投資技能。當無外部內容輸入時，Agent 可主動調用。
---

# Auto-Discover Learning — 自主學習技能

> 當沒有外部內容 (Readwise / Podcast / 手動文章) 時，Agent 主動從網路搜尋高品質投資文章並自動學習。

## 適用時機 (When to Use)

- 每日排程觸發時，Readwise 無新畫線且無 Podcast 內容
- Agent 想要主動擴充投資技能庫
- 用戶手動要求 Agent 學習特定主題

## 運作流程

```text
觸發 (n8n 排程 or Agent 主動)
    └─► InvestmentSkillLearningService.run_daily_learning()
        ├── 1. 檢查外部 content
        ├── 2. Readwise fallback
        └── 3. Auto-Discovery fallback ← 本技能
            ├── SearchService.search() (Tavily)
            ├── 隨機選擇搜尋關鍵字 (多樣性)
            ├── 取得搜尋結果摘要
            └── 進入既有 skill extraction 流程
```

## 搜尋關鍵字池 (自動輪換)

| 類別 | 範例查詢 |
| --- | --- |
| 價值投資 | `value investing strategy analysis` |
| 動量交易 | `momentum trading strategy breakdown` |
| 宏觀策略 | `macro investing approach current market` |
| 風險管理 | `portfolio risk management technique` |
| 逆勢投資 | `contrarian investing strategy guide` |
| AI 成長 | `growth investing in AI and technology` |

## 相關檔案

- `src/services/investment_skill_learning_service.py` — `_auto_discover_content()`
- `src/services/search_service.py` — Tavily 搜尋整合
- `src/agents/skills/auto_discover_learning/` — 本技能
