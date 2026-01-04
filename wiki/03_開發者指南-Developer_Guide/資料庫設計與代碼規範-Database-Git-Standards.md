# 資料庫設計與代碼規範 (Database & Git Standards)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 資料庫設計與代碼規範

本文件定義了核心資料模型、遷移流程以及 Git 協作規範。

### 1. 資料庫架構 (Database Schema)
系統支援 SQLite 與 PostgreSQL。核心表格包含：
- **`users`**: 使用者驗證元資料。
- **`transactions`**: 買賣、股息與入金紀錄。
- **`positions`**: 基於交易計算出的即時持倉。
- **`recommendations`**: Agent 生成的買賣訊號與歷史績效 (`outcome_score`)。
- **`agent_states`**: 快取機制，存放 Context Hash 與最後輸出以節省 Token。
- **`event_logs`**: 系統匯流排驗證日誌。

### 2. 資料庫遷移 (Migration)
- **本地 -> 雲端 (SQLite -> Postgres)**: 推薦使用 `pgloader` 工具配合 `.load` 腳本。
- **雲端 -> 本地 (Postgres -> SQLite)**: 推薦先匯出 `transactions` 為 CSV，再使用 Dashboard 的匯入功能。

### 3. 代碼提交規範 (Git Commit Standard)
本專案採用 **Conventional Commits** 並強制執行**雙語**說明。
- **格式**: `<type>(<scope>): <English Subject> | <中文主旨>`
- **常見類型**: 
    - `feat`: 新增功能 ✨
    - `fix`: 修復 Bug 🐛
    - `refactor`: 重構代碼 🔨
    - `docs`: 修改文件 📚
- **範例**: `feat(market): implement Fred API | 實作 Fred API 串接`

---

<a id="en"></a>

## 🇺🇸 Database & Git Standards

### 1. Database Schema
- **Entities**: `users`, `transactions`, `positions`, `recommendations`.
- **Caching**: `agent_states` stores SHA256 hashes of input context to minimize costs.
- **Audit**: `event_logs` and `scheduler_logs` for traceability.

### 2. Migration Guide
- **SQLite to Cloud SQL**: Use `pgloader`.
- **Cloud to Local**: CSV export/import via Data Management page.

### 3. Git Commit Standard
- **Bilingual Required**: `type(scope): English | 中文`.
- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`.
- **Example**: `fix(auth): resolve oauth redirect loop | 修復 OAuth 重新導向無窮迴圈`

## 🔗 See Also
- [Environment & Local Dev](wiki/03_開發者指南-Developer_Guide/環境設定與本地開發-Environment-Local-Dev.md)
- [Testing & External Services](wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)
