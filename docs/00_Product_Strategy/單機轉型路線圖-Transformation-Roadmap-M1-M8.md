---
title: 單機轉型路線圖 (Transformation Roadmap M1-M8)
description: 記錄 AI Investment Advisor 從多租戶 SaaS 原型全面轉型為單機低代碼自架平台之 14 項核心任務里程碑與交付成果。
tags: [roadmap, transformation, milestones, low-code, self-hosting]
---

# 單機轉型路線圖 (Single-Box Transformation Roadmap M1–M8)

> **導航跳轉 (Navigation)**: [Wiki 首頁 (Home)](../Home.md) | [產品需求規格總綱](./產品需求規格總綱-PRD-Master-System-Specs.md) | [單機自架手冊](../06_SRE_Observability/單機自架手冊-Self-Hosting-Guide.md)

### 版本紀錄 (Version History)
| 日期 (Date) | 版本 (Version) | 變更說明 (Description) | 作者 (Author) |
| :--- | :--- | :--- | :--- |
| 2026-09-20 | v1.1.0 | 整併至 Wiki 產品策略目錄，記錄 14 項轉型任務 100% 驗收完成成果 | Antigravity |
| 2026-09-20 | v1.0.0 | 初版 M1~M8 轉型任務總表 | Core Team |

---

### 角色導引 (Persona Guide)
- **目標受眾 (Target Audience)**: 👑 **產品總監 / 技術主管 (Product Lead / Tech Lead)**
- **閱讀時間 (Reading Time)**: 約 4~5 分鐘 (Approx. 4-5 mins)
- **文件目的 (Purpose)**: 綜述 14 項工程改造任務之驗收成果、前後架構對比與里程碑進展。

---

## 🇹🇼 繁體中文 (Traditional Chinese)

### 1. 任務交付總表 (Master Task Status)

全階段共計 14 項核心任務，現已 **100% 全數實作完畢並完成全系統驗收**：

| 任務編號 | 里程碑 (Milestone) | 核心目標與交付成果 | 狀態 | 核心檔案與模組 |
| :---: | :--- | :--- | :---: | :--- |
| **M1** | 租戶收斂 | 單一擁有者收斂 (`OWNER_ID`)，消除多租戶競爭問題 | ✔ 完成 | `src/config/owner.py` |
| **M2** | 認證安全 | Loopback 免密認證、`ADMIN_TOKEN` 與 `:8080` 隔離 | ✔ 完成 | `src/api/v1/dependencies.py` |
| **M3** | 系統瘦身 | 移除荒廢容器、移轉排程至 Celery Beat | ✔ 完成 | `docker-compose.prod.yml` |
| **M4** | 設定架構 | 宣告式設定註冊表 (`settings_schema.yaml`) 與動態表單 | ✔ 完成 | `config/settings_schema.yaml` |
| **M5** | 工作流 DAG | 宣告式 Workflow DAG 與動態視覺化頁面 (`/workflows`) | ✔ 完成 | `config/workflows/*.yaml` |
| **M6-1** | Agent 解析器 | 統一 Markdown Frontmatter 解析器 | ✔ 完成 | `src/utils/frontmatter.py` |
| **M6-2** | Agent 註冊表 | Agent 提示詞清單化 (`config/agents/*.md`) | ✔ 完成 | `config/agents/*.md` |
| **M7-1** | 外掛註冊表 | 共用外掛抽象註冊表與驗證機制 | ✔ 完成 | `src/plugins/registry.py` |
| **M7-2** | 資料來源註冊 | 宣告式行情與總經資料來源註冊清單 | ✔ 完成 | `config/data_providers.yaml` |
| **M7-3** | 通知管道註冊 | 宣告式通知管道註冊表與 Discord/Telegram/Line 轉接器 | ✔ 完成 | `config/channels.yaml` |
| **M7-4** | 工具清單註冊 | MCP 工具與本地工具宣告式註冊表 | ✔ 完成 | `config/tools.yaml` |
| **M7-5** | LLM Gateway | 單一來源 LLM Gateway 提供商與階層動態綁定 | ✔ 完成 | `config/llm_tiers.yaml` |
| **M7-6** | Skills 規格化 | 技能規格收斂為 `SKILL.md`，支援意圖路由 | ✔ 完成 | `src/agents/skills/*/SKILL.md` |
| **M7-7** | 外掛中心介面 | 前端外掛中心 (`/extensions`) 與全系統整合 | ✔ 完成 | `frontend/src/app/extensions/` |
| **M8** | 開箱即用運維 | 一鍵安裝腳本 (`install.sh`)、三大成本方案與自架手冊 | ✔ 完成 | `install.sh`, `start.sh` |

---

## 🇬🇧 English

### 1. Transformation Overview
The platform transitioned from a legacy multi-tenant SaaS architecture to a streamlined, single-box, low-code autonomous system. All 14 engineering milestones across M1 to M8 are successfully implemented, verified, and active in production.

---

### 參考資源 (References)
- **相關規劃文檔 (Related Documents)**:
  - [Wiki 首頁 (Home)](../Home.md)
  - [產品需求規格總綱 (Master PRD)](./產品需求規格總綱-PRD-Master-System-Specs.md)
  - [單機自架手冊](../06_SRE_Observability/單機自架手冊-Self-Hosting-Guide.md)
  - [端到端行為驅動測試規格 (BDD Specs)](../05_Quality_Assurance/端到端行為驅動測試規格-BDD-E2E-Testing-Specs.md)
- **專案交付代碼 (Code Assets)**:
  - 一鍵安裝腳本: [install.sh](../../install.sh)
  - 宣告式設定目錄: [config/](../../config/)
