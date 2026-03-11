# 架構總綱 (Architecture Blueprint)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-18 | v4.2 | **Refined Architecture Blueprint**: Consolidated Philosophy and Landscape. Documented Rule #8, #11, and #12 integration. | Neo |
| 2026-02-15 | v3.6 | **Milestone: 75% Coverage** + Leverage Engine & Channel Adapters. | Neo |
| 2024-01-04 | v1.0 | Initial Release. | Neo |

---

<a id="zh"></a>

## 🇹🇼 核心架構與設計哲學 (Core Architecture & Philosophies)

本文件定義了 AI Investment Advisor 的核心設計原則、系統全景與技術架構，旨在構建一個高透明度、具備自我演化能力且符合金融安全規範的 AI 代理系統。

### 1. 核心哲學 (Core Philosophies)

#### 1.1 整潔架構 (Clean Architecture)
遵守 **依賴規則 (Dependency Rule)**：源代碼依賴必須僅指向內部（Domain 層）。
- **領域層 (Domain)**: 純業務實體，不依賴框架。
- **應用層 (Service)**: 協調業務案例（Workflow）。
- **基礎設施層 (Infrastructure)**: 資料庫實作、API Providers。
- **適配層 (Adapter)**: UI (Streamlit) 與 API 入口 (FastAPI)。

#### 1.2 領域驅動設計 (Domain-Driven Design)
以「投資領域」為核心建模，使用 **通用語言 (Ubiquitous Language)**：
- **實體 (Entities)**: 如 `Position`, `Portfolio` 具備內生計算能力。
- **存儲庫 (Repositories)**: 隔離持久化細節，讓應用層專注於領域對象。

#### 1.3 規範驅動設計 (Spec-Driven Design)
「文檔即開發」，Wiki 作為開發藍圖。
1. 定義規格 (Sequence Diagram) -> 2. 實作介面 -> 3. 邏輯編寫 -> 4. 反饋校準。

---

### 2. 系統全景與 C4 模型 (System Landscape & C4)

#### 2.1 系統容器視角 (Container Diagram)
```mermaid
graph TD
    UI[""Dashboard (Streamlit")"] -->"|SQL| DB[""(Postgres DB")]
    UI -->"|HTTP| MCP_Serv["""MCP Microservice (FastAPI")"]
    Sch[""Scheduler (Daemon")"] -->"|Trigger| Agents["""Agent Swarm (7 Agents + Council")"]
    Agents -->"|Direct Call| Local["""Local Skills (Registry")"]
    Agents -->|HTTP| MCP_Serv
    MCP_Serv -->"|Financial Data| APIs[Polygon/FMP/FRED/Tavily]"
    Local -->|Search/Compute| APIs

    subgraph "Multi-Broker"
        BF[BrokerFactory] -->"ET[Etoro] & FU[Futu] & IK[IBKR]"
    end

    Agents -->|Orders| BF
    subgraph "Delivery"
        NS[NotificationService] -->"LNA[LINE Adapter] & MA[Email Adapter] & WA[Web Adapter]"
    end

    Agents -->|Results| NS
```

#### 2.2 六層智能作業系統模型 (6-Layer Agentic OS)
| 層次 | 角色 | 核心組件 | 說明 |
| :--- | :--- | :--- | :--- |
| **L1: 存取層** | I/O 正規化 | `ChannelAdapter` | **[v4.1 Async]** 非同步入口與 User UUID 映射。 |
| **L2: 控制層** | 並行與泳道 | `LaneManager` | Session 隔離與執行隊列管理。 |
| **L3: 認知層** | 執行環境 | `AgentRuntime` | Prompt 動態注入與 **Leverage Engine**。 |
| **L4: 記憶層** | 混合檢索 | `HybridMemory` | 結合 pgvector 與全文檢索。 |
| **L5: 互動層** | 回饋機制 | `A2A Protocol` | Agent 間的評分與衝突解決。 |
| **L6: 策略層** | 實施與交易 | `StrategyEngine` | 決策轉化為 Broker API 執行。 |

---

### 3. 先進機制與權衡 (Selection & Tradeoffs)

- **Webhook 架構變更**: LINE Webhook 指向 `mcp_server` (FastAPI) 以支持高併發與非同步處理，解決 Streamlit 執行緒阻塞問題。
- **PostgreSQL 原生化**: v4.0 全面採用 Postgres 以支援 `pgvector` 向量運算與高精度高頻計算（Rule #9）。
- **混合存儲 (Hybrid Strategy)**: 交易數據使用 Raw SQL 以追求極致性能；管理類實體使用 ORM 提升開發效率。
- **資安加固 (Rule #11)**: 使用 Hardened Base Image，落實「資安唯一原則 (Safe-SQL-Only)」。

---

<a id="en"></a>

## 🇺🇸 Architecture Blueprint

### 1. Philosophies
- **Clean Architecture & DDD**: Strict layer decoupling and domain-centric modeling.
- **Spec-Driven**: Iterative loops between Wiki specs and code execution.
- **Intelligence Tiering**: Parallel execution across Fast (Flash), Smart (Pro), and Advanced (Thinking) models.

### 2. Infrastructure
- **Agentic OS Model**: A 6-layer stack ensuring data-to-decision integrity.
- **Deployment**: Cloud-native (K8s/Cloud Run) with centralized MCP tool orchestration.

## 🔗 Bidirectional Links
- **Agents**: [Agentic Orchestration Specs](智能體調度與通訊規範-Agentic-Orchestration-Specs)
- **Data**: [Data & Memory Core Specs](數據與記憶核心架構-Data-Memory-Core-Specs)
- **Standard**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
