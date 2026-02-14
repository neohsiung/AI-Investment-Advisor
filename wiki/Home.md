# AI Investment Advisor Wiki

歡迎來到 AI Investment Advisor 的知識庫。本專案採用的規格驅動開發 (Spec-Driven Development) 確保了架構的高度一致性。
Welcome to the AI Investment Advisor knowledge base, built on Spec-Driven Development.

## 📚 導航 (Navigation)

### 01. 使用者手冊 (User Manual)
*   **[快速啟動與操作指南](快速啟動與操作指南-Quickstart-User-Guide)**: 安裝、部署與核心儀表板操作。

### 02. 產品規格 (Product Managers)
*   **[產品演進藍圖](產品演進藍圖-Evolutionary-Roadmap)**: v1 → v3.6 的研發歷程與 v4.0 Agent Swarm 願景。
*   **規格書 (Specs)**
    *   **[核心系統規格](核心系統規格-Core-System-Specs)**: 7 Agent Swarm、Multi-Broker 與 Leveraged NLV 解析。
    *   **[未來演進規格 (v4.0)](未來演進規格-Future-Roadmap-Specs)**: v4.0 Role × Multi-Agent (Agent Swarm Economy)。
*   **[OpenClaw 自動化規格](OpenClaw自動化規格-OpenClaw-Automation-Spec)**: Map-Reduce 全持倉併發分析。

### 03. 開發者指南 (Developer Guide)
*   **[環境設定與本地開發](環境設定與本地開發-Environment-Local-Dev)**: Python 環境建置與 CLI。
*   **[券商整合指南](券商整合指南-Broker-Integration-Guide)**: IBroker 介面、Etoro/Futu/IBKR 整合。
*   **[交易系統架構與 NLV 邏輯](交易系統架構-Trading-Architecture)**: 下單流程、RiskManager、雙重 NLV 核對。
*   **[服務層開發指南](服務層開發指南-Service-Layer-Blueprints)**: 27 個 Service 模組的設計與實現。
*   **[前端架構與 UX 層](前端架構與UX層-Frontend-UX-Layer)**: Streamlit 頁面、BasePage Template Method。
*   **[測試與外部服務整合](測試與外部服務整合-Testing-External-Services)**: 測試策略、API 設定、OAuth。
*   **[雲端部署 (GCP Cloud Run)](雲端部署-Deployment-GCP-CloudRun)**: 生產環境部署指南。

### 04. 架構觀點 (Architect View)
*   **[系統全景圖](系統全景圖-System-Landscape)**: 雲端拓撲與基礎設施。
*   **[架構哲學](架構哲學-Architectural-Philosophies)**: Clean Architecture、DDD、Spec-Driven。
*   **[底層通信協議 (Agent Mesh)](底層通信協議-Agent-Mesh-Protocols)**: MCP、JSON Schema、工具調用。
*   **[哨兵與評議會架構](哨兵與評議會架構-Sentinel-Council-Architecture)**: 7×24 監聽、碎形辯論。
*   **[任務規劃與執行引擎](任務規劃與執行引擎-Task-Planning-Engine)**: DAG 任務分解。
*   **[記憶系統與 Redis 架構](記憶系統與Redis架構-Memory-Redis-Architecture)**: 自適應壓縮記憶。

### 05. 工程手冊 (Engineering Handbook)
*   **規範 (Standards)**
    *   **[文件規範 (Wiki Standards)](文件規範-Wiki-Standard)**: 檔案禁止數字開頭，目錄強制數字排序。
    *   **[資料庫設計與代碼規範](資料庫設計與代碼規範-Database-Git-Standards)**: Schema、Commit 規範。
*   **設計模式深度庫 (Patterns)**
    *   **[設計模式導讀](設計模式導讀-Design-Patterns-Intro)**: 為什麼我們這樣寫程式？
    *   **[工廠模式](設計模式-工廠-Factory-Pattern)** · **[存儲庫模式](設計模式-存儲庫-Repository-Pattern)** · **[依賴注入](設計模式-依賴注入-DI-Pattern)** · **[樣板方法](設計模式-樣板方法-Template-Method)**

---

## 🆕 v3.6 重大更新 (Major Updates)

| 功能 | 說明 |
|---|---|
| **槓桿資產透明化** | 儀表板支援 Gross NLV / Net NLV 個別呈現，詳列每筆部位貸款金額。 |
| **文件與頁面規範** | `src/pages/` 與 `wiki/` 移除檔案數字前綴，強化 PascalCase 命名準則。 |
| **財務槓桿標準化** | 槓桿比率統一採 Gross Exposure / Net NLV (Financial Leverage) 計算。 |

---

---
