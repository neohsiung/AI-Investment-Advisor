# AI Investment Advisor Wiki

歡迎來到 AI Investment Advisor 的知識庫。本專案採用的規格驅動開發 (Spec-Driven Development) 確保了架構的高度一致性。
Welcome to the AI Investment Advisor knowledge base, built on Spec-Driven Development.

## 📚 導航 (Navigation)

### 00. 規則規範 (Rules)
*   **[文件規範 (Wiki Standards)](00_規則規範-Rules/文件規範-Wiki-Standard.md)**: 檔案禁止數字開頭，目錄強制數字排序。
*   **[資料庫設計與代碼規範](00_規則規範-Rules/資料庫設計與代碼規範-Database-Git-Standards.md)**: Schema、Commit 規範。
*   **[文件框架定義](00_規則規範-Rules/文件框架定義-Document-Frameworks.md)**: 各類文件標準結構。
*   **[資安管理與基礎映像檔規範](00_規則規範-Rules/資安管理與基礎映像檔規範-Security-and-Base-Image-Standard.md)**: Security & Base Image.

### 01. 使用手冊 (User Manual)
*   **[快速啟動與操作指南](01_使用手冊-User_Manual/快速啟動與操作指南-Quickstart-User-Guide.md)**: 安裝、部署與核心儀表板操作。
*   **[系統設定與金鑰管理](01_使用手冊-User_Manual/系統設定與金鑰管理-System-Configuration.md)**: 環境變數與 API Key 設定。
*   **[互動頻道設定](01_使用手冊-User_Manual/互動頻道設定-Channel-Setup.md)**: LINE, Slack, Telegram 等全通路設定 Step-by-Step 指南。

### 02. 產品規格 (Product Managers)
*   **[產品演進藍圖](02_產品經理-Product_Managers/01_規格書-Specs/產品演進藍圖-Evolutionary-Roadmap.md)**: v1 → v4.0 願景。
*   **[核心系統規格 (v3.8)](02_產品經理-Product_Managers/01_規格書-Specs/核心系統規格-Core-System-Specs.md)**: 哨兵與評議會核心規格。
*   **[未來演進規格 (v4.0)](02_產品經理-Product_Managers/01_規格書-Specs/未來演進規格-Future-Roadmap-Specs.md)**: Agent Swarm Economy.

### 03. 開發者指南 (Developer Guide)
*   **[環境設定與本地開發](03_開發者指南-Developer_Guide/環境設定與本地開發-Environment-Local-Dev.md)**: Python 環境建置與 CLI。
*   **[券商整合指南](03_開發者指南-Developer_Guide/券商整合指南-Broker-Integration-Guide.md)**: IBroker 介面整合。
*   **[交易系統架構](03_開發者指南-Developer_Guide/交易系統架構-Trading-Architecture.md)**: 下單流程與 RiskManager。
*   **[服務層開發指南](03_開發者指南-Developer_Guide/服務層開發指南-Service-Layer-Blueprints.md)**: Service 模組設計。
*   **[測試與外部服務整合](03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)**: 測試策略與 API 設定。
*   **[前端架構與UX層](03_開發者指南-Developer_Guide/前端架構與UX層-Frontend-UX-Layer.md)**: Streamlit 與設計系統。
*   **[雲端部署](03_開發者指南-Developer_Guide/雲端部署-Deployment-GCP-CloudRun.md)**: GCP Cloud Run 部署流程。

### 04. 架構觀點 (Architect View)
*   **[系統全景圖](04_架構觀點-Architect_Views/系統全景圖-System-Landscape.md)**: 雲端拓撲。
*   **[架構哲學](04_架構觀點-Architect_Views/架構哲學-Architectural-Philosophies.md)**: Clean Architecture & DDD.
*   **[底層通信協議 (Agent Mesh)](04_架構觀點-Architect_Views/底層通信協議-Agent-Mesh-Protocols.md)**: MCP & Tool Calling.
*   **[哨兵與評議會架構](04_架構觀點-Architect_Views/哨兵與評議會架構-Sentinel-Council-Architecture.md)**: 碎形辯論機制。

### 05. 工程手冊 (Engineering Handbook)
*   **[設計模式導讀](05_工程手冊-Engineering_Handbook/02_常用工具與整合-Tools_and_Integration/設計模式導讀-Design-Patterns-Intro.md)**: 架構哲學之下的實作模式。
*   **01_設計模式-Patterns**
    *   **[工廠模式](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-工廠-Factory-Pattern.md)** · **[存儲庫模式](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-存儲庫-Repository-Pattern.md)** · **[依賴注入](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-依賴注入-DI-Pattern.md)** · **[樣板方法](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-樣板方法-Template-Method.md)**
*   **02_常用工具與整合-Tools_and_Integration**
    *   **[研究與最佳實踐](05_工程手冊-Engineering_Handbook/02_常用工具與整合-Tools_and_Integration/研究與最佳實踐-Research-Best-Practices.md)** · **[提示詞工程規範](05_工程手冊-Engineering_Handbook/02_常用工具與整合-Tools_and_Integration/提示詞工程規範-Prompt-Engineering-Specs.md)** · **[策略復盤與Alpha優化](05_工程手冊-Engineering_Handbook/02_常用工具與整合-Tools_and_Integration/策略復盤與Alpha優化-Strategic-Retrospective-Alpha-Optimization.md)**

---

*   **[99_封存-Archive](99_封存-Archive)**: 歷史版本。

---

## 🆕 最近更新 (Recent Updates)

| **v4.2** | **3-Tier Data Architecture** | **移除 SQLite**，確立 Redis (Hot) / Postgres (Warm) / Files (Cold) 三層架構。 |
| **v4.1** | **Wiki 重組** | 遵循 `文件規範-Wiki-Standard.md` 標準化目錄結構。 |
| **v3.8** | **Sentinel Refinement** | 智能警報去重 (24h Cool-down)、Omni-Channel 全通路修復。 |

---
