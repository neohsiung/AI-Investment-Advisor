# AI Investment Advisor - Wiki (v3.0)

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Welcome to AI Investment Advisor v3.0

### **The "Billion-Dollar Hedge Fund" in Your Pocket**

**AI Investment Advisor** is an autonomous, self-correcting quantitative investment system. It simulates the organizational structure of a top-tier hedge fund, employing a team of specialized AI Agents to perform market research, technical analysis, and portfolio management.

### **Version 3.0: The Self-Correcting Loop**
The latest v3.0 release introduces a groundbreaking **Billion-Dollar Hedge Fund Architecture**, featuring:
*   **Self-Correction**: An "HR Unit" that monitors agent performance and optimizes their "thinking" (prompts) using DSPy.
*   **Specialized Roles**: A collaboration between CIO, Macro Strategist, Fundamental Analyst, Momentum Trader, and System Engineer agents.
*   **Clean Architecture**: Enterprise-grade code structure ensuring scalability and testability.

---

### **Navigation by Role**

Select the section that matches your role to get started:

#### **🚀 01_User_Manual (For Users)**
*Start here if you want to use the dashboard.*
*   [[User-Guide]]: **Read this first!** Comprehensive guide on Dashboard, Settings, and Reports.
*   [[Deployment-Options]]: How to run the app (Local Docker vs. Cloud).
*   [[Cron-Setup]]: Automating your investment reports via Cloud Scheduler.

#### **🎯 02_Product_Manager_Corner (For PMs)**
*Product specs, features, and future roadmap.*
*   [[Roadmap]]: Strategic milestones and v3.0 goals.
*   **Core Specifications**:
    *   [[03_agents]]: AI Agent Specs (CIO, Macro, Momentum, etc.).
    *   [[05_hr_protocol]]: **New!** The "Zombie Agent" detection and system health protocols.
    *   [[04_adaptive_system]]: Dynamic model switching logic & Tiering.
    *   [[02_analytics]]: Technical Analysis & indicators spec.
    *   [[01_data_layer]]: Database Schema & Data Ingestion spec.

#### **💻 03_Developer_Guide (For Developers)**
*Setup, coding standards, and internal APIs.*
*   **Getting Started**:
    *   [[Python-Environment-Setup]]: **New!** Python 3.11 setup & Conda guide.
    *   [[Deployment-Local-SQLite]]: Quick start for local development.
    *   [[Setup-External-Services]]: API Keys setup (Google, OpenRouter, FRED).
*   **References & Operations**:
    *   [[CLI-Reference]]: **New!** Master the `src/cli.py` command-line interface.
    *   [[Testing-Guide]]: Pytest standards, coverage requirements, and mocks.
    *   [[Database-Migration-Guide]]: Managing schema changes (SQLite/Postgres) with Alembic ideas.
    *   [[Deployment-GCP-CloudRun]]: Production deployment on Google Cloud.
    *   [[Google-OAuth-Setup]]: Configuring Google Authentication.

#### **🏗️ 04_Architect_View (For Architects)**
*System design, diagrams, and high-level decisions.*
*   [[System-Overview]]: **Updated!** The v3.0 Architecture Diagram (Clean Architecture + DSPy Loop).
*   [[AI-Agent-Swarm]]: Deep dive into the Agent Swarm collaboration mechanism.
*   [[Clean-Architecture-Review]]: The "Why" and "How" of the codebase refactoring.
*   [[Architecture-Status]]: Current system health and technical debt assessment.
*   [[System-Migration-Plan]]: Evolution from v1 to v3.0.
*   [[Security-Audit-Report]]: Vulnerability assessments and security best practices.

#### **🗄️ Archive**
*   [[Archive/README]]: Deprecated designs and legacy documentation.

---

<a id="traditional-chinese"></a>

## 🇹🇼 歡迎來到 AI 投資顧問 v3.0

### **口袋裡的「億萬級對沖基金」**

**AI Investment Advisor** 是一個具備自我修正能力的自動化量化投資系統。它模擬了頂級對沖基金的組織架構，聘請了一組專業的 AI Agent 團隊，全天候為您執行市場研究、技術分析與投資組合管理。

### **版本 3.0: 自我修正迴圈 (The Self-Correcting Loop)**
最新的 v3.0 版本引入了突破性的 **億萬級對沖基金架構 (Billion-Dollar Hedge Fund Architecture)**，特色包括：
*   **自我修正 (Self-Correction)**: 透過「人力資源部 (HR Unit)」監控 Agent 績效，並利用 DSPy 自動優化 Agent 的思考模式 (Prompts)。
*   **專業分工 (Specialized Roles)**: 模擬真實世界的投資長 (CIO)、總經策略師、基本面分析師、動能交易員與系統工程師的協作模式。
*   **整潔架構 (Clean Architecture)**: 採用企業級的程式碼架構，確保系統的擴充性與可測試性。

---

### **角色導航 (Navigation by Role)**

請根據您的角色選擇對應的專區：

#### **🚀 01_User_Manual (使用者手冊)**
*如果您是使用者，請從這裡開始。*
*   [[User-Guide]]: **必讀！** 按部就班教您使用儀表板、設定與查看報告。
*   [[Deployment-Options]]: 如何啟動系統 (本地 Docker 或雲端部署)。
*   [[Cron-Setup]]: 設定自動化投資報告排程 (Cloud Scheduler)。

#### **🎯 02_Product_Manager_Corner (產品經理專區)**
*產品規格、功能細節與未來藍圖。*
*   [[Roadmap]]: 專案的未來發展計畫與 v3.0 目標。
*   **核心規格 (Core Specs)**:
    *   [[03_agents]]: AI Agent 規格 (CIO, Macro, Momentum 等)。
    *   [[05_hr_protocol]]: **新功能！** 「殭屍 Agent」偵測與系統健康協議。
    *   [[04_adaptive_system]]: 動態模型切換與分級邏輯。
    *   [[02_analytics]]: 技術分析指標與計算邏輯。
    *   [[01_data_layer]]: 資料庫架構與數據攝取規格。

#### **💻 03_Developer_Guide (開發者指南)**
*環境架設、程式碼規範與 API 說明。*
*   **快速開始**:
    *   [[Python-Environment-Setup]]: **必讀！** Python 3.11 環境建置與 Conda 設定。
    *   [[Deployment-Local-SQLite]]: 本地開發快速啟動。
    *   [[Setup-External-Services]]: 外部服務 API (Google, OpenRouter, FRED) 設定。
*   **參考與運維**:
    *   [[CLI-Reference]]: **新功能！** `src/cli.py` 命令行工具完全指南。
    *   [[Testing-Guide]]: 測試執行標準與覆蓋率要求。
    *   [[Database-Migration-Guide]]: 資料庫遷移指南 (SQLite/Postgres)。
    *   [[Deployment-GCP-CloudRun]]: Google Cloud 生產環境部署。
    *   [[Google-OAuth-Setup]]: Google 登入驗證設定。

#### **🏗️ 04_Architect_View (架構師視角)**
*系統設計、架構圖與高層決策。*
*   [[System-Overview]]: **已更新！** v3.0 系統架構圖 (Clean Architecture + DSPy 迴圈)。
*   [[AI-Agent-Swarm]]: Agent 集群的協作機制詳解。
*   [[Clean-Architecture-Review]]: v3.0 重構的設計原則與理由。
*   [[Architecture-Status]]: 當前系統健康度與技術債評估。
*   [[System-Migration-Plan]]: 系統從 v1 到 v3.0 的演進計畫。
*   [[Security-Audit-Report]]: 安全性審計與防護建議。

#### **🗄️ Archive (歷史存檔)**
*   [[Archive/README]]: 過時文件與歷史決策索引。

---

> **Note**: This wiki is maintained by the AI Investment Advisor Team.
