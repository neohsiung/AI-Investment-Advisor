---
name: investment-skill-learning
description: 每日投資技能學習系統的使用指南。指導 Agent 如何觸發學習、查詢技能、整併清理技能庫。
---

# Investment Skill Learning — 每日投資技能學習指南

> 本技能指導 Agent 如何使用「投資技能學習系統」，包括每日學習觸發、技能查詢、整併與清理。

## 適用時機 (When to Use)

- 需要觸發每日投資技能學習（通常由 n8n 自動觸發）
- 需要查詢現有投資技能庫（Agent 分析時調用）
- 需要手動傳入投資文章或 Podcast 逐字稿進行技能萃取
- 需要清理或整併技能庫

---

## 系統架構

```
n8n Schedule/RSS Trigger
    └─► POST /webhook/skill-learning
        └─► InvestmentSkillLearningService.run_daily_learning()
            ├── 1. 擷取內容 (Readwise / Podcast / 手動)
            ├── 2. LLM 萃取結構化技能
            ├── 3. 比對相似技能
            ├── 4. 合併或新增 (動態閾值)
            ├── 5. 調整合併閾值
            └── 6. 清理過時技能
```

## 來源類型

| 來源 | source_type | 觸發方式 |
|------|-------------|----------|
| Readwise | `highlight` | 每日排程自動 |
| Podcast | `podcast` | n8n RSS 監聽 → Groq Whisper |
| 文章 URL | `article` | 手動 webhook |

## 動態合併閾值

- 初始值: 70%
- 技能過多（token 消耗 > 預算）→ +5%（積極合併）
- 技能過少（< 5 個）→ -5%（傾向新增）
- 範圍: [30%, 95%]

## 相關檔案

- `src/services/investment_skill_learning_service.py` — 核心服務
- `src/agents/skills/investment_skill/` — Runtime Skill
- `src/agents/skills/registry.py` — 技能註冊
- `src/services/webhook_service.py` — Webhook 入口
