# AI Investment Advisor (v3.2)

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?style=for-the-badge&logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-Ready-326CE5.svg?style=for-the-badge&logo=kubernetes&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg?style=for-the-badge)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 專案概覽 (Project Overview)

**AI Investment Advisor** 是一個由 **自我修正 (Self-Correcting)** AI Agent 集群驅動的自動化投資顧問系統。它不僅僅是一個聊天機器人，而是模擬頂級對沖基金運作的**自主進化金融分析平台**。

本系統聘請了專業的 AI Agent (投資長、總經、基本面、動能) 進行 24/7 全天候市場分析，並設有 **HR Unit (人力資源部)** 利用 **DSPy** 技術持續監控並優化 Agent 的表現。

### 🔄 系統生命週期 (System Lifecycle)
> [!NOTE]
> 流程圖展示了從數據攝取到 AI 分析，再到自我優化的閉環過程。
> This diagram illustrates the closed-loop process from data ingestion to AI analysis and self-optimization.

```mermaid
graph LR
    A["數據攝取<br/>Data Ingest"] --> B["專家分析<br/>Expert Analysis"]
    B --> C["CIO 決策<br/>CIO Decision"]
    C --> D["績效反饋<br/>Performance Feedback"]
    D --> E["Prompt 優化<br/>Prompt Optimization"]
    E --> B
```

<details>
<summary><b>🌟 點擊查看核心功能 (Click to View Key Features)</b></summary>

| 功能模組 | 描述 |
| :--- | :--- |
| **🏆 量化反饋迴圈** | **Engineer Agent** 讀取績效指標 (Win Rate, Alpha) 與 CIO 反饋，利用 **DSPy** 自動重寫表現不佳 Agent 的 Prompt。 |
| **🏦 機構級角色設定** | **CIO (投資長)** 專注風險調整後報酬；**總經/基本面/動能/情緒** 分析師各司其職，擁有獨立數據管道。 |
| **🏗️ 現代化基礎架構** | 支援 **Kubernetes** 集群部署，採用 **Clean Architecture** (Factory, Repository, DI) 確保系統穩健性與可測試性。**測試覆蓋率 75%+**。 |
| **🔍 智慧搜尋引擎** | 整合 **Tavily API** 為主要搜尋引擎，DuckDuckGo 為備援，提供穩定的網路資訊檢索。 |
| **🧠 Agent Mesh 協議** | **MCP (Model Context Protocol)** 伺服器支援，實現跨 Agent 工具共享與 **HR 360 回饋** 機制。 |

</details>

### 🚀 快速開始 (Quick Start)

<details>
<summary><b>1. 下載與環境設定 (Download & Env Setup)</b></summary>

```bash
# 1. 下載專案
git clone https://github.com/neohsiung/AI-Investment-Advisor.git
cd AI-Investment-Advisor

# 2. 設定環境變數
cp .env.example .env  # 請在 .env 填入 API Keys (Google Gemini / OpenAI)
```
</details>

<details>
<summary><b>2. 啟動系統 (Launch System)</b></summary>

```bash
# 方式 A: Docker Compose (最推薦)
./start.sh

# 方式 B: Kubernetes (進階)
./start.sh --k8s
```
*系統啟動後，請訪問 Dashboard: [http://localhost:8501](http://localhost:8501)*
</details>

### 📚 文檔索引 (Documentation)

本專案擁有完整的文檔體系，位於 `wiki/` 目錄：

- **使用者手冊**:
    - [快速啟動與操作指南 (Quickstart & User Guide)](wiki/01_使用者手冊-User_Manual/快速啟動與操作指南-Quickstart-User-Guide.md)
- **產品規格**:
    - [產品演進藍圖 (Evolutionary Roadmap)](wiki/02_產品經理-Product_Managers/產品演進藍圖-Evolutionary-Roadmap.md)
    - [核心系統規格 (Core System Specs)](wiki/02_產品經理-Product_Managers/Specs/核心系統規格-Core-System-Specs.md)
- **開發者指南**:
    - [環境設定與本地開發 (Environment & Local Dev)](wiki/03_開發者指南-Developer_Guide/環境設定與本地開發-Environment-Local-Dev.md)
    - [服務層子系統詳解 (Service Layer Blueprints)](wiki/03_開發者指南-Developer_Guide/服務層開發指南-Service-Layer-Blueprints.md)
    - [前端架構與 UX 層 (Frontend & UX Layer)](wiki/03_開發者指南-Developer_Guide/前端架構與UX層-Frontend-UX-Layer.md)
    - [測試與外部服務整合 (Testing & External Services)](wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)
- **架構設計**:
    - [系統全景圖 (System Landscape)](wiki/04_架構觀點-Architect_Views/系統全景圖-System-Landscape.md)
    - [架構哲學 (Architectural Philosophies)](wiki/04_架構觀點-Architect_Views/架構哲學-Architectural-Philosophies.md)
    - [底層通信協議 (Agent Mesh Protocols)](wiki/04_架構觀點-Architect_Views/底層通信協議-Agent-Mesh-Protocols.md)
- **工程手冊**:
    - [研究與最佳實踐 (Research & Best Practices)](wiki/05_工程手冊-Engineering_Handbook/研究與最佳實踐-Research-Best-Practices.md)
    - [設計模式導讀 (Design Patterns Intro)](wiki/05_工程手冊-Engineering_Handbook/設計模式導讀-Design-Patterns-Intro.md)

### 🏗️ 系統架構 (Architecture)

```mermaid
graph TD
    User((User)) <-->|UI/Chat| DASH[Streamlit Dashboard]
    DASH <-->|Route| DISP[Dispatcher Agent]
    
    subgraph "Agent Swarm (v3.3)"
        CIO[CIO Agent]
        MACRO[Macro Strategist]
        FUND[Fundamental Analyst]
        SENT[Sentiment Analyst]
        
        CIO -->|IC Protocol| SWARM{Swarm}
        SWARM -->|Request| MACRO & FUND & SENT
        MACRO & FUND & SENT -->|Insights| CIO
        CIO -->|Decision| DB[(Database)]
    end
```

參閱詳細架構與協議：[代理人戰略協定 (Agent Swarm Protocol)](wiki/04_架構觀點-Architect_Views/代理人戰略協定-Agent-Swarm-Protocol.md)

---

<a id="en"></a>

## 🇺🇸 Project Overview

**AI Investment Advisor** is an advanced, automated quantitative investment system empowered by a **Self-Correcting Agent Swarm**. Simulating a **Billion-Dollar Hedge Fund**, it employs specialized AI Agents (CIO, Macro, Fundamental, Momentum) to perform global market research, while an **HR Unit** continuously monitors and optimizes their performance using **DSPy**.

This is not just a chatbot; it is an **autonomous financial analysis system capable of self-evolution**.

### 🌟 Key Features

| Feature Module | Description |
| :--- | :--- |
| **🏆 Quantitative Feedback Loop** | **Engineer Agent** reads performance metrics and CIO feedback, automatically rewriting Prompts for underperforming agents via **DSPy**. |
| **🏦 Institutional Personas** | **CIO** focuses on Risk-Adjusted Returns; **Macro/Fundamental/Momentum** analysts have dedicated data pipelines. |
| **🏗️ Modern Infrastructure** | **Kubernetes** ready, built with **Clean Architecture** (Factory, Repository, DI). **75%+ Test Coverage**. |
| **🔍 Intelligent Search** | Integrated **Tavily API** as primary search engine with DuckDuckGo fallback for reliable web research. |
| **🧠 Agent Mesh Protocol** | **MCP (Model Context Protocol)** server support enabling cross-agent tool sharing and **HR 360 Feedback**. |

### 🚀 Quick Start

#### 1. Clone Repository
```bash
git clone https://github.com/neohsiung/AI-Investment-Advisor.git
cd AI-Investment-Advisor
```

#### 2. Configure Environment
Copy the example config and add your API Keys.
```bash
cp .env.example .env
# vim .env
```

#### 3. Start System
```bash
# Option A: Docker Compose (Recommended)
./start.sh

# Option B: Kubernetes (Advanced)
./start.sh --k8s
```
*Access the Dashboard at: [http://localhost:8501](http://localhost:8501)*

### 📚 Documentation

Detailed documentation is available in the `wiki/` directory:

- **Getting Started**:
    - [Quickstart & User Guide](wiki/01_使用者手冊-User_Manual/快速啟動與操作指南-Quickstart-User-Guide.md)
- **Product Specs**:
    - [Evolutionary Roadmap](wiki/02_產品經理-Product_Managers/產品演進藍圖-Evolutionary-Roadmap.md)
    - [Core System Specs](wiki/02_產品經理-Product_Managers/Specs/核心系統規格-Core-System-Specs.md)
- **Developer Guide**:
    - [Environment & Local Dev](wiki/03_開發者指南-Developer_Guide/環境設定與本地開發-Environment-Local-Dev.md)
    - [Service Layer Blueprints](wiki/03_開發者指南-Developer_Guide/服務層開發指南-Service-Layer-Blueprints.md)
    - [Frontend & UX Layer](wiki/03_開發者指南-Developer_Guide/前端架構與UX層-Frontend-UX-Layer.md)
    - [Testing & External Services](wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)
- **Architecture & Engineering**:
    - [System Landscape](wiki/04_架構觀點-Architect_Views/系統全景圖-System-Landscape.md)
    - [Architectural Philosophies](wiki/04_架構觀點-Architect_Views/架構哲學-Architectural-Philosophies.md)
    - [Agent Mesh Protocols](wiki/04_架構觀點-Architect_Views/底層通信協議-Agent-Mesh-Protocols.md)
    - [Research & Best Practices](wiki/05_工程手冊-Engineering_Handbook/研究與最佳實踐-Research-Best-Practices.md)
    - [Design Patterns Intro](wiki/05_工程手冊-Engineering_Handbook/設計模式導讀-Design-Patterns-Intro.md)

### ⚠️ Disclaimer
**For Educational and Research Purposes Only.**
This software is a simulation of an investment system. It is not financial advice. Usage in real trading is at your own risk.

### 📄 License
MIT License.
