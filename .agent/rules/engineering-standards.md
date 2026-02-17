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
