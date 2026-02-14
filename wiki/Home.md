# AI Investment Advisor Wiki

歡迎來到 AI Investment Advisor 的知識庫。這裡收錄了所有關於本專案的文檔，從新手入門到架構設計。
Welcome to the AI Investment Advisor knowledge base. All project documentation is organized here.

## 📚 導航 (Navigation)

*   **[首頁](Home)**

### 01. 使用者手冊 (User Manual)
*   **[快速啟動與操作指南 (Quickstart & User Guide)](快速啟動與操作指南-Quickstart-User-Guide)**: 安裝、部署與核心儀表板操作。

### 02. 產品規格 (Product Managers)
*   **[產品演進藍圖 (Evolutionary Roadmap)](產品演進藍圖-Evolutionary-Roadmap)**: v1 → v3.5 的研發歷程與 v4.0 Agent Swarm 願景。
*   **規格書 (Specs)**
    *   **[核心系統規格 (Core System Specs)](核心系統規格-Core-System-Specs)**: 7 Agent Swarm、Multi-Broker、Sentinel/Council 與資料層。
    *   **[未來演進規格 (Future Roadmap Specs)](未來演進規格-Future-Roadmap-Specs)**: v4.0 Role × Multi-Agent (Agent Swarm Economy)。
*   **[OpenClaw 自動化規格](OpenClaw自動化規格-OpenClaw-Automation-Spec)**: Map-Reduce 全持倉併發分析。

### 03. 開發者指南 (Developer Guide)
*   **[環境設定與本地開發 (Environment & Local Dev)](環境設定與本地開發-Environment-Local-Dev)**: Python 環境建置與 CLI。
*   **[券商整合指南 (Broker Integration)](券商整合指南-Broker-Integration-Guide)**: IBroker 介面、Etoro/Futu/IBKR 整合。
*   **[交易系統架構 (Trading Architecture)](交易系統架構-Trading-Architecture)**: 下單流程、RiskManager、Kill Switch。
*   **[服務層開發指南 (Service Layer)](服務層開發指南-Service-Layer-Blueprints)**: 27 個 Service 模組的設計與實現。
*   **[前端架構與 UX 層 (Frontend & UX)](前端架構與UX層-Frontend-UX-Layer)**: Streamlit 頁面、BasePage Template Method。
*   **[測試與外部服務整合 (Testing & External)](測試與外部服務整合-Testing-External-Services)**: 測試策略、API 設定、OAuth。
*   **[雲端部署 (GCP Cloud Run)](雲端部署-Deployment-GCP-CloudRun)**: 生產環境部署指南。

### 04. 架構觀點 (Architect View)
*   **[系統全景圖 (System Landscape)](系統全景圖-System-Landscape)**: 雲端拓撲與基礎設施。
*   **[架構哲學 (Architectural Philosophies)](架構哲學-Architectural-Philosophies)**: Clean Architecture、DDD、Spec-Driven。
*   **[前端與服務架構 (Frontend-Service)](前端與服務架構-Frontend-Service-Architecture)**: View-Service 模式。
*   **[資料與領域模型 (Data & Domain)](資料與領域模型-Data-Domain-Models)**: ER 圖、Schema。
*   **[底層通信協議 (Agent Mesh Protocols)](底層通信協議-Agent-Mesh-Protocols)**: MCP、JSON Schema、工具調用。
*   **[代理人戰略協定 (Agent Swarm Protocol)](代理人戰略協定-Agent-Swarm-Protocol)**: IC Protocol、Swarm 決策流程。
*   **[哨兵與評議會架構 (Sentinel & Council)](哨兵與評議會架構-Sentinel-Council-Architecture)**: 7×24 監聽、碎形辯論。
*   **[任務規劃與執行引擎 (Task Planning)](任務規劃與執行引擎-Task-Planning-Engine)**: DAG 任務分解。
*   **[記憶系統與 Redis 架構 (Memory & Redis)](記憶系統與Redis架構-Memory-Redis-Architecture)**: 自適應壓縮記憶。
*   **[OpenClaw 執行環境 (OpenClaw Runtime)](OpenClaw執行環境-OpenClaw-Runtime-Environment)**: Map-Reduce 併發。

### 05. 工程手冊 (Engineering Handbook)
*   **[提示詞工程規範 (Prompt Engineering)](提示詞工程規範-Prompt-Engineering-Specs)**: 指令設計原則。
*   **[研究與最佳實踐 (Research & Best Practices)](研究與最佳實踐-Research-Best-Practices)**: RAG、代理模式。
*   **規範 (Standards)**
    *   **[文件框架定義 (Document Frameworks)](文件框架定義-Document-Frameworks)**: 文檔結構標準。
    *   **[文件規範 (Wiki Standards)](文件規範-Wiki-Standard)**: 命名規範、雙語。
    *   **[資料庫設計與代碼規範 (DB & Git)](資料庫設計與代碼規範-Database-Git-Standards)**: Schema、Commit 規範。
*   **設計模式深度庫 (Patterns)**
    *   **[設計模式導讀](設計模式導讀-Design-Patterns-Intro)**: 為什麼我們這樣寫程式？
    *   **[工廠模式](設計模式-工廠-Factory-Pattern)** · **[存儲庫模式](設計模式-存儲庫-Repository-Pattern)** · **[依賴注入](設計模式-依賴注入-DI-Pattern)** · **[樣板方法](設計模式-樣板方法-Template-Method)**

---

## 🆕 最新功能 (Latest Features - v3.5)

| 功能 | 說明 |
|---|---|
| **7 Agent + Council** | CIO/Fundamental/Momentum/Macro/Sentiment/Risk/Engineer + 碎形辯論仲裁 |
| **多券商架構** | Etoro / Futu / IBKR 統一 IBroker 介面 + RiskManager |
| **哨兵與評議會** | 7×24 Sentinel 監聽 + Council Fractal Debate |
| **任務規劃引擎** | DAG 任務分解 + 動態模型路由 (Fast/Smart/Advanced) |
| **MCP 整合** | Polygon + FMP + FRED + Tavily 標準化工具 |
| **75%+ 測試覆蓋率** | 全面自動測試 |

---
