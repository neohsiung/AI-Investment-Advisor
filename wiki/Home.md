# AI Investment Advisor Wiki

歡迎來到 AI Investment Advisor 的知識庫。本專案採用的規格驅動開發 (Spec-Driven Development) 確保了架構的高度一致性。
Welcome to the AI Investment Advisor knowledge base, built on Spec-Driven Development.

## 📚 導航 (Navigation)

### 01. 使用者手冊 (User Manual)
*   **[快速啟動與操作指南](01_使用者手冊-User_Manual/快速啟動與操作指南-Quickstart-User-Guide.md)**: 安裝、部署與核心儀表板操作。
*   **[系統設定與金鑰管理](01_使用者手冊-User_Manual/系統設定與金鑰管理-System-Configuration.md)**: 環境變數與 API Key 設定。
*   **[互動頻道設定](01_使用者手冊-User_Manual/互動頻道設定-Channel-Setup.md)**: LINE, Slack, Telegram 等全通路設定 Step-by-Step 指南。

### 02. 產品規格 (Product Managers)
*   **[產品演進藍圖](02_產品經理-Product_Managers/產品演進藍圖-Evolutionary-Roadmap.md)**: v1 → v3.6 的研發歷程與 v4.0 Agent Swarm 願景。
*   **01_規格書-Specs**
    *   **[核心系統規格 (v3.8)](02_產品經理-Product_Managers/01_規格書-Specs/核心系統規格-Core-System-Specs.md)**: 含 7 Agent Swarm、Sentinel Refinement、Channel Verification 與 Multi-Tier Agent 架構。
    *   **[未來演進規格 (v4.0)](02_產品經理-Product_Managers/01_規格書-Specs/未來演進規格-Future-Roadmap-Specs.md)**: v4.0 Role × Multi-Agent (Agent Swarm Economy) 與自動化特性。

### 03. 開發者指南 (Developer Guide)
*   **[環境設定與本地開發](03_開發者指南-Developer_Guide/環境設定與本地開發-Environment-Local-Dev.md)**: Python 環境建置與 CLI。
*   **[券商整合指南](03_開發者指南-Developer_Guide/券商整合指南-Broker-Integration-Guide.md)**: IBroker 介面、Etoro/Futu/IBKR 整合。
*   **[交易系統架構與 NLV 邏輯](03_開發者指南-Developer_Guide/交易系統架構-Trading-Architecture.md)**: 下單流程、RiskManager、雙重 NLV 核對。
*   **[服務層開發指南](03_開發者指南-Developer_Guide/服務層開發指南-Service-Layer-Blueprints.md)**: 27 個 Service 模組的設計與實現。
*   **[前端架構與 UX 層](03_開發者指南-Developer_Guide/前端架構與UX層-Frontend-UX-Layer.md)**: Streamlit 頁面、BasePage Template Method。
*   **[測試與外部服務整合](03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)**: 測試策略、API 設定、OAuth。
*   **[雲端部署 (GCP Cloud Run)](03_開發者指南-Developer_Guide/雲端部署-Deployment-GCP-CloudRun.md)**: 生產環境部署指南。

### 04. 架構觀點 (Architect View)
*   **[系統全景圖](04_架構觀點-Architect_Views/系統全景圖-System-Landscape.md)**: 雲端拓撲與基礎設施。
*   **[架構哲學](04_架構觀點-Architect_Views/架構哲學-Architectural-Philosophies.md)**: Clean Architecture、DDD、Spec-Driven。
*   **[底層通信協議 (Agent Mesh)](04_架構觀點-Architect_Views/底層通信協議-Agent-Mesh-Protocols.md)**: MCP、JSON Schema、工具調用。
*   **[哨兵與評議會架構](04_架構觀點-Architect_Views/哨兵與評議會架構-Sentinel-Council-Architecture.md)**: 7×24 監聽、碎形辯論。
*   **[任務規劃與執行引擎](04_架構觀點-Architect_Views/任務規劃與執行引擎-Task-Planning-Engine.md)**: DAG 任務分解。
*   **[記憶系統與 Redis 架構](04_架構觀點-Architect_Views/記憶系統與Redis架構-Memory-Redis-Architecture.md)**: 自適應壓縮記憶。
*   **[資料與領域模型](04_架構觀點-Architect_Views/資料與領域模型-Data-Domain-Models.md)**: Schema 與 Entity 定義。
*   **[配置管理架構](04_架構觀點-Architect_Views/配置管理架構-Configuration-Management.md)**: 動態參數與環境變數。

### 05. 工程手冊 (Engineering Handbook)
*   **[文件規範 (Wiki Standards)](05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件規範-Wiki-Standard.md)**: 檔案禁止數字開頭，目錄強制數字排序。
*   **[資料庫設計與代碼規範](05_工程手冊-Engineering_Handbook/02_規範標準-Standards/資料庫設計與代碼規範-Database-Git-Standards.md)**: Schema、Commit 規範。
*   **[文件框架定義](05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件框架定義-Document-Frameworks.md)**: 各類文件標準結構。
*   **01_設計模式-Patterns**
    *   **[設計模式導讀](05_工程手冊-Engineering_Handbook/設計模式導讀-Design-Patterns-Intro.md)**: 為什麼我們這樣寫程式？
    *   **[工廠模式](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-工廠-Factory-Pattern.md)** · **[存儲庫模式](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-存儲庫-Repository-Pattern.md)** · **[依賴注入](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-依賴注入-DI-Pattern.md)** · **[樣板方法](05_工程手冊-Engineering_Handbook/01_設計模式-Patterns/設計模式-樣板方法-Template-Method.md)**
*   **[99_封存-Archive](99_封存-Archive/README.md)**: 歷史版本與舊型規格存檔。

---

## 🆕 最近更新 (Recent Updates)

| 版本 | 功能 | 說明 |
|---|---|---|
| **v3.8** | **Sentinel Refinement** | 智能警報去重 (24h Cool-down)、Omni-Channel 全通路修復。 |
| **v3.7** | **Multi-Tier Swarm** | 雙層模型路由 (Fast/Smart)、Channel Verification (Interactive Test)。 |
| **v3.6** | **槓桿資產透明化** | 儀表板支援 Gross NLV / Net NLV 個別呈現，詳列每筆部位貸款金額。 |
| **v3.5** | **Sentinel Hub** | 4D Multi-Trigger 監控、加權新聞風險評分。 |

---
