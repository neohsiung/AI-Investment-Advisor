# AI Investment Advisor Wiki

歡迎來到 AI Investment Advisor 的知識庫。這裡收錄了所有關於本專案的文檔，從新手入門到架構設計。
Welcome to the AI Investment Advisor knowledge base. All project documentation is organized here.

## 📚 導航 (Navigation)

*   **[首頁](Home)**
*   **[文件規範 (Wiki Standards)](文件規範-Wiki-Standard)**

### 01. 使用者手冊 (User Manual)
*   **[快速啟動與操作指南 (Quickstart & User Guide)](快速啟動與操作指南-Quickstart-User-Guide)**: 涵蓋安裝、部署與核心儀表板操作。

### 02. 產品規格 (Product Managers)
*   **[產品演進藍圖 (Evolutionary Roadmap)](產品演進藍圖-Evolutionary-Roadmap)**: 從 v1 到 v5 的研發歷程與願景。
*   **深度規格 (Specs)**
    *   **[核心系統規格 (Core System Specs)](核心系統規格-Core-System-Specs)**: Agent Swarm、HR 協議與資料層詳解。
    *   **[未來演進規格 (Future Roadmap Specs)](未來演進規格-Future-Roadmap-Specs)**: v3.3 危機自動駕駛與 v4.0 家族辦公室計畫。

### 03. 開發者指南 (Developer Guide)
*   **[環境設定與本地開發 (Environment & Local Dev)](環境設定與本地開發-Environment-Local-Dev)**: Python 環境建置與 CLI 使用手冊。
*   **[服務層子系統詳解 (Service Layer Blueprints)](服務層開發指南-Service-Layer-Blueprints)**: 深入探賦服務層的設計與實現。
*   **[前端架構與 UX 層 (Frontend & UX Layer)](前端架構與UX層-Frontend-UX-Layer)**: Streamlit 管理、狀態同步與用戶體驗流程。
*   **[測試與外部服務整合 (Testing & External Services)](測試與外部服務整合-Testing-External-Services)**: 測試策略、第三方 API 設定 (Tavily, Polygon) 與 OAuth 配置。
*   **[雲端部署 (GCP Cloud Run)](雲端部署-Deployment-GCP-CloudRun)**: 生產環境部署指南。

### 04. 架構觀點 (Architect View)
*   **[系統全景圖 (System Landscape)](系統全景圖-System-Landscape)**: 雙部門架構、雲端拓撲與 Infrastructure 註冊表。
*   **[架構哲學 (Architectural Philosophies)](架構哲學-Architectural-Philosophies)**: Clean Architecture、DDD 與 Spec-Driven Design 的實踐。
*   **[資料與領域模型 (Data & Domain Models)](資料與領域模型-Data-Domain-Models)**: 實體關係圖、SQL Schema 與數據流動路徑。
*   **[底層通信協議 (Agent Mesh Protocols)](底層通信協議-Agent-Mesh-Protocols)**: MCP 微服務、JSON Schema 與工具調用生命週期。

### 05. 工程手冊 (Engineering Handbook)
*   **[提示詞工程規範 (Prompt Engineering Specs)](提示詞工程規範-Prompt-Engineering-Specs)**: 提示詞設計原則與最佳實踐。
*   **[研究與最佳實踐 (Research & Best Practices)](研究與最佳實踐-Research-Best-Practices)**: 行業標準、代理模式與 RAG 研究。
*   **規範 (Standards)**
    *   **[文件框架定義 (Document Frameworks)](文件框架定義-Document-Frameworks)**: 跨角色文檔結構標準。
    *   **[資料庫設計與代碼規範 (Database & Git Standards)](資料庫設計與代碼規範-Database-Git-Standards)**: Schema 定義、遷移路徑與雙語 Commit 規範。
*   **設計模式深度庫 (Patterns)**
    *   **[設計模式導讀 (Design Patterns Intro)](設計模式導讀-Design-Patterns-Intro)**: 為什麼我們這樣寫程式？
    *   **[工廠模式 (Factory Pattern)](設計模式-工廠-Factory-Pattern)**
    *   **[存儲庫模式 (Repository Pattern)](設計模式-存儲庫-Repository-Pattern)**
    *   **[依賴注入 (DI Pattern)](設計模式-依賴注入-DI-Pattern)**
    *   **[樣板方法模式 (Template Method)](設計模式-樣板方法-Template-Method)**

---

## 🆕 最新功能 (Latest Features - v3.2)

| 功能 | 說明 |
|---|---|
| **Tavily 搜尋整合** | 以 Tavily API 為主要搜尋引擎，DuckDuckGo 為備援 |
| **MCP 工具伺服器** | Agent Mesh 架構，跨 Agent 工具共享 |
| **HR 360 回饋** | Agent 間互評機制，追蹤表現 |
| **75% 測試覆蓋率** | 298+ 個自動測試 |

---

