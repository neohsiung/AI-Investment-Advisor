# AI Investment Advisor Wiki

歡迎來到 AI Investment Advisor 的知識庫。這裡收錄了所有關於本專案的文檔，從新手入門到架構設計。
Welcome to the AI Investment Advisor knowledge base. All project documentation is organized here.

## 📚 導航 (Navigation)

### 1. 新手入門 (User Manual)
*   **[使用手冊 (User Guide)](01_使用者手冊-User_Manual/使用手冊-User-Guide.md)**: 系統功能介紹與操作說明。
*   **[部署選項 (Deployment Options)](01_使用者手冊-User_Manual/部署選項-Deployment-Options.md)**: 選擇最適合你的部署方式 (Local vs Cloud)。
*   **[排程設定 (Cron Setup)](01_使用者手冊-User_Manual/排程設定-Cron-Setup.md)**: 如何設定自動化排程。

### 2. 產品規格 (Product Manager Corner)
*   **[產品藍圖 (Roadmap)](02_產品經理-Product_Managers/產品藍圖-Roadmap.md)**: 未來開發計畫與里程碑。
*   **[關鍵規格 (Specs)]**:
    *   [代理人規格 (Agent Specs)](02_產品經理-Product_Managers/Specs/代理人規格-Agent-Specs.md)
    *   [HR 協議 (HR Protocol)](02_產品經理-Product_Managers/Specs/HR協議-HR-Protocol.md)
    *   [資料層定義 (Data Layer)](02_產品經理-Product_Managers/Specs/資料層-Data-Layer.md)
    *   [分析層定義 (Analytics)](02_產品經理-Product_Managers/Specs/分析層-Analytics.md)
    *   [自適應系統 (Adaptive)](02_產品經理-Product_Managers/Specs/自適應系統-Adaptive-System.md)

### 3. 開發者指南 (Developer Guide)
*   **[環境設定 (Setup)](03_開發者指南-Developer_Guide/環境設定-Python-Environment-Setup.md)**: 如何搭建開發環境。
*   **[第三方服務 (3rd Party)](03_開發者指南-Developer_Guide/第三方服務設定-3rd-Party-Services-Setup.md)**: API Key 設定 (Tavily, Polygon, FMP, FRED)。
*   **[命令行手冊 (CLI)](03_開發者指南-Developer_Guide/命令行手冊-CLI-Reference.md)**: `src/cli.py` 指令大全。
*   **[測試指南 (Testing)](03_開發者指南-Developer_Guide/測試指南-Testing-Guide.md)**: 執行單元測試，**目前覆蓋率 75%+**。
*   **[雲端部署 (GCP)](03_開發者指南-Developer_Guide/雲端部署-Deployment-GCP-CloudRun.md)**: Google Cloud Run 部署教學。

### 4. 架構設計 (Architect View)
*   **[系統概觀 (Overview)](04_架構觀點-Architect_Views/系統概觀-System-Overview.md)**: 高層次架構圖與模組說明。
*   **[架構狀態 (Status)](04_架構觀點-Architect_Views/架構狀態-Architecture-Status.md)**: 目前系統的技術債與改進點。
*   **[Clean Architecture 審查](04_架構觀點-Architect_Views/架構檢視-Clean-Architecture-Review.md)**: DDD 合規性分析。

### 5. 工程手冊 (Engineering Handbook)
*   **[設計模式導讀 (Design Patterns)](05_工程手冊-Engineering_Handbook/設計模式導讀-Design-Patterns-Intro.md)**: 為什麼我們這樣寫程式？
    *   [工廠模式 (Factory)](05_工程手冊-Engineering_Handbook/設計模式-工廠模式-Factory-Pattern.md)
    *   [存儲庫模式 (Repository)](05_工程手冊-Engineering_Handbook/設計模式-存儲庫模式-Repository-Pattern.md)
    *   [依賴注入 (DI)](05_工程手冊-Engineering_Handbook/設計模式-依賴注入-Dependency-Injection.md)
    *   [樣板方法 (Template Method)](05_工程手冊-Engineering_Handbook/設計模式-樣板方法-Template-Method.md)

---

## 🆕 最新功能 (Latest Features - v3.2)

| 功能 | 說明 |
|---|---|
| **Tavily 搜尋整合** | 以 Tavily API 為主要搜尋引擎，DuckDuckGo 為備援 |
| **MCP 工具伺服器** | Agent Mesh 架構，跨 Agent 工具共享 |
| **HR 360 回饋** | Agent 間互評機制，追蹤表現 |
| **75% 測試覆蓋率** | 298+ 個自動測試 |

---
*Last Updated: 2026-01-04*

