# Coding Standards & Best Practices

本專案遵循 **Google Python Style Guide** (繁體中文/英文 雙語規範)，並針對本專案的「混合儲存架構」進行特定擴充。

## 1. 核心風格規範 (Core Style Guide)

### 1.1 縮進與行寬 (Indentation & Line Length)
- **縮進**: 使用 **4 個空格** (儘管 Google 原生建議 2 個，但本專案為了與既有代碼一致，統一使用 4 個空格)。禁止使用 Tab。
- **行寬**: 每行建議不超過 **100 個字元** (Soft limit)，硬性限制為 120。

### 1.2 命名規範 (Naming Conventions)
- **類別 (Classes)**: `PascalCase` (e.g., `TransactionRepository`)
- **函式與變數 (Functions & Variables)**: `snake_case` (e.g., `calculate_net_equity`)
- **常量 (Constants)**: `UPPER_CASE_WITH_UNDERSCORES` (e.g., `MAX_RETRY_COUNT`)
- **模組與包 (Modules & Packages)**: `snake_case` (e.g., `data_ingestor.py`)

### 1.3 引用規範 (Imports)
- **規則**: 僅引用模組或包，不直接引用類別或函式 (特殊例外除外，如 `typing`)。
- **範例**: 
  - `import os` (正確)
  - `from datetime import datetime` (正確，常見例外)
  - `from src.data.models import User` (正確，實體類)
  - `from src.data import database` (推薦)

## 2. 註解與文檔 (Documentation & Comments)

### 2.1 雙語強制規範 (Bilingual Requirement)
- **規則**: 所有 Docstrings (類別/函式) 與程式碼中的關鍵註解 **必須** 同時包含 **英文** 與 **繁體中文**。
- **順序**: 英文在上，繁體中文在下。
- **格式 (Google Style)**:
  ```python
  def calculate_leverage(self, net_equity: float, loan: float) -> float:
      """
      Calculate the leverage ratio.
      計算槓桿比率。
      
      Args:
          net_equity (float): The net equity value. (淨權益價值)
          loan (float): The loan value. (貸款價值)
          
      Returns:
          float: The leverage ratio. (槓桿比率)
      """
  ```

### 2.2 類型提示 (Type Hinting)
- **規則**: 所有函式定義必須包含 Type Hints，使用 `src/mcp_service/` 代碼時必須通過 `mypy` 檢查。

## 3. 混合儲存架構規範 (Hybrid Storage Standards)

本專案採用 **Hybrid Strategy** (參見 `.agent/rules/core-philosophies.md` 第 9 條)。

### 3.1 ORM 使用準則 (SQLAlchemy ORM)
- **適用對象**: 管理類實體 (Users, Settings, EventLogs, Verifications)。
- **要求**: 
  - 必須繼承 `src.data.models.Base`。
  - 使用 `BaseRepository` 提供的 `session` 進行增刪改查。
  - 保持實體間的關係簡單，避免過度嵌套。

### 3.2 動態指標原則 (Rule #8)
- **規則**: 所有系統閾值 (Thresholds) 必須是基於歷史數據計算的動態變數，或可經由復盤 (Experience Replay) 調整的參數，嚴禁使用寫死 (Hardcoded) 的定值。
    - **實施細節**:
        - 優先使用 `SentinelService._calibrate_thresholds()` 進行統計校準。
        - 任何新增的監控邏輯必須在 `sentinel_thresholds` 表中註冊名稱。
        - 預設值僅作為 Seed 資料，正式運行時應依賴 DB 現狀。

### 3.3 Raw SQL 使用準則 (SQLAlchemy Core)
- **適用對象**: 效能敏感數據 (Transactions, Memory Embeddings, Snapshots)。
- **核心準則**: **Safe-SQL-Only** (參見本文第 4 節)。
- **理由**: 直接控制 SQL 以優化金融大數據計算與 `pgvector` 相似度搜尋。

## 4. 安全規範 (Security)

本專案遵循嚴格的資安準則，包含基礎映像檔硬化、憑證管理以及 SQL 注入防護。
- **具體規範**: 請參見 [security-standards.md](security-standards.md)。
- **核心原則**: 
    - **Safe-SQL-Only**: 所有 Raw SQL 必須參數化，嚴禁拼接。
    - **Managed-Security-Base**: 使用 hardened 基礎映像檔且非 root 執行。

## 5. 錯誤處理 (Error Handling)

- **規則**: 避免使用裸露的 `try-except` 或 `pass`。
- **最佳實踐**: 
  - 捕捉特定異常 (e.g., `sqlalchemy.exc.DBAPIError`)。
  - 在 catch block 中使用 `logger.error(..., exc_info=True)` 記錄堆疊訊息。
  - 對於資料庫操作，失敗時必須執行 `session.rollback()`。

## 6. 自動化與檢查 (Automation)

- **Linting**: 建議使用 `pylint` 並遵循 `Google` 配置。
- **Format**: 使用 `black` 配合 `--line-length 100`。
- **CI**: 提交前必須通過 `test-coverage-check` 流程，確保覆蓋率 > 70%。
