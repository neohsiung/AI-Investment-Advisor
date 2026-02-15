# README Documentation Standards

## 目标 (Goal)
確保 `README.md` 作為項目入口文件，既符合項目內部的Wiki規範，又達到業界最佳實踐標準。

## 强制要求 (Mandatory Requirements)

### 1. 符合 Wiki 標準 (Wiki Standard Compliance)
引用: [`wiki/05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件規範-Wiki-Standard.md`](../wiki/05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件規範-Wiki-Standard.md)

- **版本紀錄 (Version History)**: 
  - 必須位於文件頂部 (Title之後)。
  - 格式必須包含 Date, Version, Description, Author。
- **雙語並列 (Bilingual)**:
  - 必須包含繁體中文 (Traditional Chinese) 與 英文 (English)。
  - **順序**: 繁體中文在上，英文在下。
  - 使用 `<a id="en"></a>` 錨點分隔。
- **代碼引用**: 使用 backticks (e.g., `` `Service` ``).

### 2. 業界最佳實踐 (Industry Best Practices)

- **項目標題與簡介 (Title & Description)**: 清晰說明項目用途與價值。
- **狀態徽章 (Badges)**: 顯示 Build Status, Version, License, Tech Stack (Python, Docker, etc.)。
- **核心功能 (Key Features)**: 使用表格或列表列出主要功能。
- **快速開始 (Quick Start)**: 提供最簡化的安裝與啟動指令 (One-liner is best)。
- **系統架構 (Architecture)**: 包含 Mermaid 圖表或架構圖連結。
- **文檔索引 (Documentation Index)**: 指向詳細 Wiki 文檔的連結。
- **授權與免責聲明 (License & Disclaimer)**: 明確的授權條款。

## 標準結構 (Standard Structure)

```markdown
# Project Name

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| ... | ... | ... | ... |

[Badges: CI, Python, Docker, License]

> **[繁體中文](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 專案概覽
- 簡介
- 核心能力 (Feature Table)
- 快速開始 (Code block)
- 系統架構 (Mermaid)
- 文檔索引 (Links to Wiki)
- 免責聲明

---

<a id="en"></a>

## 🇺🇸 Project Overview
- Introduction
- Key Features
- Quick Start
- Architecture
- Documentation
- Disclaimer
- License
```

## 檢查清單 (Checklist)

- [ ] 版本紀錄是否最新？(對應最新 Release/Milestone)
- [ ] 雙語內容是否同步？
- [ ] 安裝指令是否經過驗證可執行？
- [ ] 所有 Wiki 連結是否有效？
- [ ] 是否包含架構圖？
- [ ] 是否包含測試覆蓋率徽章 (如 > 75%)？

## 自動化檢查 (Automation)

此規則應整合至 `.agent/workflows/wiki-sync.md`，在 commit 前執行檢查。
