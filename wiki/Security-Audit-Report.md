# 安全性稽核報告 (Security Audit Report)

> 返回 [[Home]]

**日期:** 2025-12-06
**狀態:** 通過 (含建議事項)

## 1. 摘要 (Summary)
本次稽核針對程式碼庫的相依套件漏洞、SQL 注入風險、指令注入風險與機密管理進行了檢查。

**整體風險等級:** 低 (Low)

## 2. 發現 (Findings)

### 2.1 相依套件 (Dependencies)
- **行動**: 已將 `bandit` 加入 `requirements.txt` 以進行持續性靜態安全性分析。
- **建議**: 參見 [[Deployment-Guide]]，在 CI/CD 流程中執行 `bandit -r src/`。

### 2.2 SQL 注入 (SQL Injection)
- **元件**: `src/database.py`, `src/services/`, `src/pages/3_Data_Management.py`
- **狀態**: **已修復 / 安全**
- **分析**:
    - 應用程式在 Service Layer 使用參數化查詢。
    - **修復應用**: `src/pages/3_Data_Management.py` 現在針對資料瀏覽器的 Table Name 實作了白名單機制，防止 SQL 注入。

### 2.3 指令注入 (Command Injection)
- **元件**: `src/pages/4_Settings.py`, `src/scheduler.py`
- **狀態**: **已修復 / 安全**
- **分析**:
    - 程式碼使用 `subprocess.Popen` 並傳入嚴格的參數列表。
    - **修復應用**: 將明確的 "python3" 字串替換為 `sys.executable`，確保使用正確的虛擬環境解釋器，緩解路徑劫持風險 (Bandit B607)。

### 2.4 硬編碼機密 (Hardcoded Secrets)
- **元件**: 原始碼 (`src/`)
- **狀態**: **安全**
- **分析**:
    - 未在 `*.py` 檔案中發現硬編碼的 API Key (OpenAI, Gemini)。
    - 系統依賴 `.env` 變數或資料庫設定 (`settings` table) 來管理憑證。
    - `.env` 已正確加入 `.gitignore`。

## 3. 建議 (Recommendations)
1.  **CI/CD 整合**: 在 GitHub Actions 中新增執行 `bandit` 的步驟。
2.  **機密管理**: 確保包含真實 API Key 的 `portfolio.db` 不被提交 (注意: `data/*.db` 已被 gitignored)。
