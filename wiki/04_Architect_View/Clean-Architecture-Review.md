# 架構檢討報告 (Clean Architecture Review)

> 返回 [[Home]] | 相關: [[System-Overview]]

## 目標 (Goal)
評估系統當前架構與 **Clean Architecture (整潔架構)** 原則的符合程度，識別技術債並提出重構計畫。

## 為什麼 (Why)
- **解耦依賴**: 避免 UI (Streamlit) 與業務邏輯 (Agents) 高度耦合，導致難以測試。
- **易於替換**: 未來若需更換資料庫 (SQLite -> Postgres) 或 UI 框架，核心邏輯不應受影響。
- **長期維護**: 清晰的分層架構有助於新成員理解程式碼。

## 做了什麼 (What)
我們對 `src/` 目錄下的核心模組進行了依賴性分析：
- **Entities (核心層)**: 定義交易、持倉等資料結構。
- **Use Cases (應用層)**: Workflow, Agents。
- **Interface Adapters (介面層)**: Dashboard, Ingestor。
- **Frameworks (框架層)**: Streamlit, SQLite driver.

## 如何進行 (How) - 改善計畫

### 1. 現狀分析 (Current State)
- ✅ **優點**: 模組分離清晰 (Agents, Services, Pages)。導入 `DatabaseManager` 與 `Services` 層封裝外部數據。
- ❌ **缺點**: UI 層 (`src/pages/*.py`) 仍包含直接 SQL 查詢 (`pd.read_sql`)，尚未完全導入 Repository Pattern。`workflow.py` 雖已支援 Event-Driven，但仍承擔部分調度細節。

### 2. 重構建議 (Refactoring Plan)

#### A. 引入 Repository Pattern
- **現狀**: 頁面直接寫 `SELECT * FROM transactions`.
- **目標**: 建立 `TransactionRepository` 介面。
    ```python
    class TransactionRepository(ABC):
        @abstractmethod
        def get_by_user(self, user_id): pass
    ```
- **效益**: 單元測試時可輕易 Mock 資料庫。

#### B. 依賴注入 (Dependency Injection)
- **現狀**: Service 內部直接 `new Database()`.
- **目標**: 透過建構子注入依賴。
    ```python
    service = PortfolioService(repo=SqliteTransactionRepo())
    ```

#### C. Use Case 封裝
- 將 `workflow.py` 的邏輯封裝為 `GenerateReportUseCase` 類別，使其可被 API 或 CLI 呼叫，不綁定特定入口。
