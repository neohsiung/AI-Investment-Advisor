# Clean Architecture Review

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 架構檢討報告 (Clean Architecture Review)

### 目標 (Goal)
評估系統當前架構與 **Clean Architecture (整潔架構)** 原則的符合程度，識別技術債並提出重構計畫。

### 為什麼 (Why)
- **解耦依賴**: 避免 UI (Streamlit) 與業務邏輯 (Agents) 高度耦合，導致難以測試。
- **易於替換**: 未來若需更換資料庫 (SQLite -> Postgres) 或 UI 框架，核心邏輯不應受影響。
- **長期維護**: 清晰的分層架構有助於新成員理解程式碼。

### 做了什麼 (What)
我們對 `src/` 目錄下的核心模組進行了依賴性分析：
- **Entities (核心層)**: 定義交易、持倉等資料結構。
- **Use Cases (應用層)**: Workflow, Agents。
- **Interface Adapters (介面層)**: Dashboard, Ingestor。
- **Frameworks (框架層)**: Streamlit, SQLite driver.

### 如何進行 (How) - 改善計畫

#### 1. 現狀分析 (Current State)
- ✅ **優點**: 模組分離清晰 (Agents, Services, Pages)。導入 `DatabaseManager` 與 `Services` 層封裝外部數據。
- ❌ **缺點**: 部分 UI 層仍包含直接 SQL 查詢，但 `AnalyticsService` 已完全重構為 Clean Architecture。

#### 2. 重構建議 (Refactoring Plan)

**A. 引入 Repository Pattern**
- **狀態**: ✅ 已完成 (Transactions/Analytics)
- **目標**: 建立 `TransactionRepository` 介面。
- **效益**: 單元測試時可輕易 Mock 資料庫。

**B. 依賴注入 (Dependency Injection)**
- **狀態**: ✅ 已完成 (Analytics Service)
- **目標**: 透過建構子注入依賴。
- **範例**: `service = PortfolioService(repo=SqliteTransactionRepo())`

**C. Use Case 封裝**
- 將 `workflow.py` 的邏輯封裝為 `GenerateReportUseCase` 類別，使其可被 API 或 CLI 呼叫，不綁定特定入口。

---

<a id="en"></a>

## 🇺🇸 Clean Architecture Review

### Goal
Evaluate adherence to **Clean Architecture** principles, identify technical debt, and propose refactoring plans.

### Why
- **Decoupling**: Avoid coupling UI (Streamlit) with Business Logic (Agents).
- **Replaceability**: Ease future DB/UI swaps.
- **Maintainability**: Clear layering for new devs.

### Analysis (What)
Analyzed `src/` dependencies:
- **Entities**: Core data structures.
- **Use Cases**: Workflows, Agents.
- **Adapters**: Dashboard, Ingestor.
- **Frameworks**: Streamlit, SQLite.

### Plan (How)

#### 1. Current State
- ✅ **Pros**: Clear module separation (Agents/Services). `DatabaseManager` allows some decoupling.
- ❌ **Cons**: Some UI layer pages still have direct SQL, but `AnalyticsService` is physically decoupled via Repository Pattern.

#### 2. Refactoring Plan

**A. Repository Pattern**
- **Status**: ✅ Completed (Transactions/Analytics)
- **Goal**: Create `TransactionRepository` interface.
- **Benefit**: Easier mocking for unit tests.

**B. Dependency Injection**
- **Status**: ✅ Completed (Analytics Service)
- **Goal**: Inject repos into Services via constructor.

**C. Use Case Encapsulation**
- **Goal**: Wrap `workflow.py` logic into `GenerateReportUseCase`.
