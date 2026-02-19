# 工程實作標準 (Engineering Standards)

本文件統合了本專案在開發、測試與資安上的最高指導原則，確保代碼具備高質量、高安全性與高可維護性。

---

## 1. 代碼規範 (Coding Standards)

本專案遵循 **Google Python Style Guide**，並針對 AI Agent 與混合儲存場景進行擴充。

### 1.1 基本格式 (Basics)
- **縮進**: 統一使用 **4 個空格**。
- **行寬**: Soft limit 100, Hard limit 120。
- **雙語註解 (Bilingual Docs)**: 所有核心 Docstrings 必須包含 **英文 (上) 與 繁體中文 (下)**。

### 1.2 混合儲存策略 (Hybrid Strategy - Rule #9)
- **ORM Admin Layer**: 針對 `User`, `Settings`, `Logs` 等管理類實體，強制使用 **SQLAlchemy ORM** 以提升開發效率。
- **Raw SQL Performance Layer**: 針對 `Transactions`, `MarketData`, `pgvector` 等大數據或高效能場景，強制使用 **Raw SQL (SQLAlchemy Core)** 以利精確優化。

---

## 2. 測試規範 (Testing Standards)

### 2.1 測試金字塔 (Testing Pyramid)
- **單元測試 (Unit Tests)**: 佔比 70%。嚴禁出現網路、資料庫或文件 I/O，必須完全 Mock。
- **整合測試 (Integration Tests)**: 佔比 20%。驗證 Service 與 Repository 間的契約（可用 In-memory SQLite）。
- **端到端測試 (E2E Tests)**: 佔比 10%。僅針對核心 CLI/Workflow，模擬真實用戶行為。

### 2.3 環境確定性 (Environment Determinism)
- **環境隔離**: 單元測試嚴禁依賴主機或 CI 環境變數（如 `AI_PROVIDER`, `API_KEY`）。
- **強制 Patch**: 所有涉及環境變數的邏輯必須在測試中使用 `unittest.mock.patch.dict(os.environ, ...)` 進行明確模擬，確保測試在任何機器上執行的結果完全一致。

### 2.2 覆蓋率指標 (Coverage Targets)
- **總覆蓋率**: 強制 > 70%，目標 **> 75%**。
- **核心邏輯 (Services)**: 必須 > 80%。
- **錯誤處理**: 必須達到 100% 覆蓋。

---

## 3. 資安規範 (Security Standards - Rule #11)

### 3.1 基礎設施安全
- **基礎映像檔**: 必須使用 `python:3.11-slim-bookworm`。
- **非 Root 執行**: 所有容器內程序必須以 `appuser` 執行。
- **依賴鎖定**: 嚴禁在 `requirements.txt` 使用無版本號或 `latest` 標籤。

### 3.2 數據與 SQL 安全
- **Safe-SQL-Only (Rule #10)**: 所有 Raw SQL 必須使用參數化查詢，嚴禁字串拼接。
- **憑證管理**: 嚴禁硬編碼憑證，統一使用 `.env` 與隔離的 `secrets/` 目錄。

---

## 4. 專案組織與腳本管理 (Project Organization & Script Management)

為了保持工作區整潔並確保通性工具的可用性，必須遵循以下組織規範：

### 4.1 指令碼存放規範 (Script Locations)
- **`scripts/`**: 僅存放核心工具。包含部署 (Deployment)、維運/CI (Ops/CI) 及開發者設定 (Dev Setup)。
- **`Archive/scripts/`**: 存放一次性遷移 (Migration)、歷史修復 (Fixes) 及臨時診斷腳本。
- **`Archive/verifications/`**: 存放過往開發階段使用的 Ad-hoc 整合驗證腳本。

### 4.2 個人用腳本規範 (Personal Scripts & Gitignore)
- **命名約定**: 所有個人臨時用或開發中尚未成熟的腳本必須遵循以下命名模式以自動被 Git 排除：
    - `scripts/personal_*` (例如：`scripts/personal_test_api.py`)
    - `scripts/tmp_*`
    - `*_local.py`
- **通性工具**: 具備通用性且需於團隊/CI 間共享的工具（如 `run_full_verification.sh`, `seed_data.py`）嚴禁使用上述個人命名模式，且必須由 Git 追蹤。
