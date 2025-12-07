# Clean Architecture 架構審查 (Clean Architecture Review)

> 返回 [[Home]]

## 總覽 (Overview)
本文件針對「AI 投資顧問 (AI Investment Advisor)」目前的程式碼庫，依據 Clean Architecture 原則 (Robert C. Martin) 進行分析。

## 現況分析 (Current State Analysis)
專案目前遵循「分層架構 (Layered Architecture)」結構如下：
- **表現層 (Presentation Layer)**: Streamlit 頁面 (`src/pages/*.py`, `src/dashboard.py`)。詳見 [[User-Guide]]。
- **服務層 (Service Layer)**: `src/services/*.py` (TransactionService, SettingsService)。
- **核心邏輯 / 使用案例 (Core Logic / Use Cases)**: `src/analytics.py`, `src/workflow.py`, `src/scheduler.py`。
- **基礎設施 / 資料存取 (Infrastructure / Data Access)**: `src/database.py`, `src/ingestor.py`, `src/agents/*.py`。詳見 [[Cloud-Database-Migration]] 以了解資料庫規劃。

### 優點 (Strengths)
- **UI 分離**: 頁面與邏輯分離。
- **服務抽象化**: `TransactionService` 與 `SettingsService` 抽象化了部分資料庫操作。
- **Agent 模組化**: 各個 Agent 封裝在繼承自 `BaseAgent` 的獨立類別中。詳見 [[AI-Agent-Swarm]]。

### 違規與改進機會 (Violations & Improvement Opportunities)

#### 1. 資料存取與業務邏輯耦合 (Coupling of Data Access and Business Logic)
- **問題**: 像 `TransactionService` 這樣的服務直接匯入 `get_db_connection` 並執行 SQL 查詢 (或使用 `pd.read_sql`)。
- **Clean Architecture 原則**: 使用案例 (Services) 應定義資料存取的介面 (抽象 Repository)。基礎設施 (DB) 應實作這些介面。
- **重構建議**: 建立 `src/repositories/transaction_repository.py` 來處理所有 SQL。`TransactionService` 應依賴於 `ITransactionRepository`。

#### 2. 硬編碼依賴 (Hardcoded Dependencies)
- **問題**: 服務通常在 `__init__` 或方法內部直接實例化依賴項目 (例如 `TransactionService` 內部實例化 `TradeIngestor`)。
- **Clean Architecture 原則**: 依賴注入 (Dependency Injection)。外部依賴應被注入到類別中。
- **重構建議**: 將依賴項目 (Repositories, 其他 Services) 傳入建構函式。

#### 3. 實體 vs 資料傳輸物件 (Entities vs DTOs)
- **問題**: 業務邏輯直接操作 Pandas DataFrames 或原始資料庫 Tuples。
- **Clean Architecture 原則**: 業務規則應操作與資料庫或 UI 無關的實體 (Domain Objects)。
- **重構建議**: 在 `src/domain/models.py` 中定義領域類別 (例如 `Transaction`, `PortfolioUser`)。

## 行動計畫 (Action Plan)

1.  **定義領域模型 (Define Domain Models)**: 建立 `src/domain` 用於核心實體。
2.  **抽象 Repository (Abstract Repositories)**: 建立 `src/interfaces` 用於定義 Repository 介面。
3.  **實作 Repository (Implement Repositories)**: 將 Service 或散落檔案中的 SQL 邏輯移至 `src/infrastructure/repositories`。
4.  **重構服務 (Refactor Services)**: 更新 Service 以透過依賴注入使用 Repository。
5.  **重構 UI (Refactor UI)**: 更新 Streamlit 頁面以呼叫 Service，絕不直接呼叫 DB。

## 效益 (Benefit)
- **可測試性 (Testability)**: 更容易為 Service 單元測試 Mock Repository。
- **靈活性 (Flexibility)**: 更容易切換資料庫後端 (例如 SQLite -> Postgres) 而不觸及業務邏輯。
- **可維護性 (Maintainability)**: 更清晰的邊界減少回歸風險。
