# 架構哲學 (Architectural Philosophies)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 核心架構哲學 (Core Philosophies)

本專案不僅是一個 AI 投資助理，更是一個展示 **Clean Architecture**、**DDD** 與 **Spec-Driven Design** 整合實踐的技術範本。

### 1. 整潔架構 (Clean Architecture)
本專案嚴格遵守依賴規則：**源代碼依賴必須僅指向內部（Domain 層）**。

#### 1.1 分層結構 (Layering)
- **領域層 (Domain Layer)**: `src/domain/`。包含純業務實體（Dataclasses），不依賴任何外部框架或資料庫。
- **應用服務層 (Application/Service Layer)**: `src/services/`。負責協調領域模型與執行業務案例（UseCase），如 `WorkflowService`。
- **基礎設施層 (Infrastructure Layer)**: `src/data/` 與 `src/repositories/`。實作資料庫持久化、外部 API 橋接（Providers）等細節。
- **介面適配層 (Interface/Adapter Layer)**: `src/dashboard.py` 與 `src/mcp_service/`。處理與外部世界的互動（UI、API 入口）。

### 2. 領域驅動設計 (Domain-Driven Design)
我們以「投資領域」為核心進行建模，確保代碼語言與業務專家（PM/投資者）一致。

- **實體 (Entities)**: 如 `Position` 與 `Portfolio`，具備唯一標識與豐富的業務行為（屬性計算）。
- **存儲庫 (Repositories)**: 透過介面隔離持久化細節，讓應用層專注於處理領域對象的集合。
- **貧血模型預防**: 盡可能將邏輯保留在 `entities.py` 的 property 中（如 `unrealized_pnl`），而非全由 Service 計算。

### 3. 規範驅動設計 (Spec-Driven Design)
「文檔即開發」。本專案的 Wiki 不僅是筆記，更是開發的藍圖。

- **迭代流程**: 
    1. 在 Wiki 定義規格與 Sequence Diagram。
    2. 基於規格實作 `interfaces.py`。
    3. 實作業務邏輯並透過 [LLM 回饋循環](提示詞工程規範-Prompt-Engineering-Specs) 進行驗證。
    4. 更新 Wiki 反映實作中的優化點。

### 4. 智能分層與演化 (Intelligence Layering & Multi-Tier Architecture)
**理論**: 模仿 Kimi K2.5 的混合控制架構 + **Role × Multi-Tier Agents** 並行執行。
- **編排層 (Stateful Orchestrator)**: `CIOAgent` 負責任務拆解與資源調配，具備狀態記憶。
- **執行層 (Multi-Tier Sub-agents)**: 每個專責領域的 Sub-Agent 有 **3 個層級**，並行執行：
  - 🚀 **Advanced**: 關鍵決策、深度分析 (Claude Opus, Gemini Pro) - 高成本高質量
  - 🧠 **Smart**: 日常分析、平衡質量與速度 (GPT-4, Gemini Pro) - 中等成本
  - ⚡ **Fast**: 快速初篩、低風險探索 (Gemini Flash, GPT-3.5) - 低成本高速度
- **策略**: Fast tier 先行輸出初步結果，並行等待 Advanced tier 補充深度洞察，通過 voting/fusion 機制整合最終輸出。

### 5. 事件驅動演進 (Event-Driven Evolution)
- **主動監控**: 從「被動拉取 (Pull)」轉向「主動推送 (Push)」。`SentinelService` 實作了主動事件監聽，當 VIX 或持倉發生偏移時，主動喚醒慢想系統 (Council)。
- **外部整合**: 透過標準化的 Channel Adapters (參考 [研究與最佳實踐](研究與最佳實踐-Research-Best-Practices)) 整合 Webhook 觸發器。

### 6. 技術選型分析 (Selection Analysis)
- **為什麼選擇 Streamlit？**: 快速迭代 AI 互動介面，減少前端開發成本，專注於 Agent 邏輯。
- **為什麼選擇 SQLite 加載 Postgres 兼容？**: 本專案支援本地單機運行（SQLite）與雲端擴張（Postgres），透過 SQLAlchemy 展示了極高的可移植性。

---

<a id="en"></a>

## 🇺🇸 Architectural Philosophies

### 1. Clean Architecture
Strict adherence to the **Dependency Rule**: Source code dependencies always point inwards towards the Domain Layer.
- **Independence**: The UI, Database, and Frameworks are treated as pluggable details.

### 2. Domain-Driven Design (DDD)
The domain is the center of our universe.
- **Ubiquitous Language**: Using concepts like "Portfolio", "Rebalance", and "Momentum" across code and docs.
- **Decoupled Persistence**: Repositories provide a collection-like interface to storage.

### 3. Spec-Driven Design
The Wiki serves as the living contract between design and execution.
- **Design-First**: Architectural decisions are documented as ADRs before implementation.

### 4. Proactive Intelligence & Multi-Tier Execution
- **Event-Driven**: Transitioning from a reactive "User Poll" model to a proactive "Sentinel Alert" model.
- **Orchestrator-Multi-Tier Pattern**: Stateful Orchestrator (CIO) coordinates N Sub-Agents, each executing in **3 parallel tiers** (Advanced 🚀 /  Smart 🧠 / Fast ⚡) for optimal cost-quality balance. Fast tier provides quick initial results, Advanced tier adds depth, with voting/fusion mechanisms for final output.

## 🔗 Bidirectional Links
- **Architect View**: [System Landscape](系統全景圖-System-Landscape)
- **Engineering Handbook**: [Research & Best Practices](研究與最佳實踐-Research-Best-Practices)
- **PM Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
