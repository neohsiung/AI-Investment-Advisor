# AI Investment Advisor Wiki

歡迎來到 AI Investment Advisor 的知識庫。本專案採用的規格驅動開發 (Spec-Driven Development) 確保了架構的高度一致性。
Welcome to the AI Investment Advisor knowledge base, built on Spec-Driven Development.

## 📚 導航 (Navigation)

### 00. 規則規範 (Rules)
*   **[文件規範 (Wiki Standards)](文件規範-Wiki-Standard)**: 檔案禁止數字開頭，目錄強制數字排序。
*   **[資料庫設計與代碼規範](資料庫設計與代碼規範-Database-Git-Standards)**: Schema、Commit 規範。
*   **[文件框架定義](文件框架定義-Document-Frameworks)**: 各類文件標準結構。
*   **[資安管理與基礎映像檔規範](資安管理與基礎映像檔規範-Security-and-Base-Image-Standard)**: Security & Base Image.

### 01. 使用手冊 (User Manual)
*   **[快速啟動與操作指南](快速啟動與操作指南-Quickstart-User-Guide)**: 安裝、部署與核心儀表板操作。
*   **[系統設定與金鑰管理](系統設定與金鑰管理-System-Configuration)**: 環境變數與 API Key 設定。
*   **[互動頻道設定](互動頻道設定-Channel-Setup)**: LINE, Slack, Telegram 等全通路設定 Step-by-Step 指南。

### 02. 產品規格 (Product Managers)
*   **[產品演進藍圖](產品演進藍圖-Evolutionary-Roadmap)**: v1 → v4.0 願景。
*   **[核心系統規格 (v3.8)](核心系統規格-Core-System-Specs)**: 哨兵與評議會核心規格。
*   **[未來演進規格 (v4.0)](未來演進規格-Future-Roadmap-Specs)**: Agent Swarm Economy.

### 03. 開發者指南 (Developer Guide)
*   **[環境設定與本地開發](環境設定與本地開發-Environment-Local-Dev)**: Python 環境建置與 CLI。
*   **[券商整合指南](券商整合指南-Broker-Integration-Guide)**: IBroker 介面整合。
*   **[交易系統架構](交易系統架構-Trading-Architecture)**: 下單流程與 RiskManager。
*   **[服務層開發指南](服務層開發指南-Service-Layer-Blueprints)**: Service 模組設計。
*   **[測試與外部服務整合](測試與外部服務整合-Testing-External-Services)**: 測試策略與 API 設定。
*   **[前端架構與UX層](前端架構與UX層-Frontend-UX-Layer)**: Streamlit 與設計系統。
*   **[雲端部署](雲端部署-Deployment-GCP-CloudRun)**: GCP Cloud Run 部署流程。

### 04. 架構觀點 (Architect View)
*   **[系統全景圖](系統全景圖-System-Landscape)**: 雲端拓撲。
*   **[架構哲學](架構哲學-Architectural-Philosophies)**: Clean Architecture & DDD.
*   **[底層通信協議 (Agent Mesh)](底層通信協議-Agent-Mesh-Protocols)**: MCP & Tool Calling.
*   **[哨兵與評議會架構](哨兵與評議會架構-Sentinel-Council-Architecture)**: 碎形辯論機制。

### 05. 工程手冊 (Engineering Handbook)
*   **[設計模式導讀](設計模式導讀-Design-Patterns-Intro)**: 架構哲學之下的實作模式。
*   **01_設計模式-Patterns**
    *   **[工廠模式](設計模式-工廠-Factory-Pattern)** · **[存儲庫模式](設計模式-存儲庫-Repository-Pattern)** · **[依賴注入](設計模式-依賴注入-DI-Pattern)** · **[樣板方法](設計模式-樣板方法-Template-Method)**
*   **02_常用工具與整合-Tools_and_Integration**
    *   **[研究與最佳實踐](研究與最佳實踐-Research-Best-Practices)** · **[提示詞工程規範](提示詞工程規範-Prompt-Engineering-Specs)** · **[策略復盤與Alpha優化](策略復盤與Alpha優化-Strategic-Retrospective-Alpha-Optimization)**

---

*   **[99_封存-Archive](99_封存-Archive)**: 歷史版本。

---

## 🆕 最近更新 (Recent Updates)

| **v4.2** | **3-Tier Data Architecture** | **移除 SQLite**，確立 Redis (Hot) / Postgres (Warm) / Files (Cold) 三層架構。 |
| **v4.1** | **Wiki 重組** | 遵循 `文件規範-Wiki-Standard.md` 標準化目錄結構。 |
| **v3.8** | **Sentinel Refinement** | 智能警報去重 (24h Cool-down)、Omni-Channel 全通路修復。 |

---
