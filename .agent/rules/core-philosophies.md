---
trigger: always_on
---

遵守以下事項
1. 整潔架構 (Clean Architecture)
2. 領域驅動設計 (Domain-Driven Design)
3. 規範驅動設計 (Spec-Driven Design)
4. 模組化設計：所有開發必須模組化，確保具備良好的可單元測試性 (Unit Testability) 與整合測試性 (Integration Testability)
5. 測試覆蓋率 > 70%，包含正反向情境 (CI 標準 65%)
6. 若有較佳的 Design Pattern 則可以進行重構 (Refactor)
7. 所有 Plan 根據技術有關的依照內容要提供給我流程圖 / 循序圖 / 架構圖 / 設計原則
8. 動態指標原則：所有系統閾值 (Thresholds) 必須是基於歷史數據計算的動態變數，或可經由復盤 (Experience Replay) 調整的參數，嚴禁使用寫死 (Hardcoded) 的定值。
9. 混合儲存原則 (Hybrid Strategy)：針對複雜行情計算與向量搜尋 (pgvector) 強制使用 Raw SQL (SQLAlchemy Core)；針對一般物件 (User, Settings) 與後台管理可選用 ORM。具體實施細節參見 `.agent/rules/engineering-standards.md`。
10. 資安唯一原則 (Safe-SQL-Only)：所有 Raw SQL 必須使用參數化查詢 (Parameterized Queries)，嚴禁使用字串拼接或 f-strings 組合 SQL 敘述。相關範例參見 `.agent/rules/engineering-standards.md`。
11. 基礎映像檔與資安審計原則 (Managed-Security-Base)：所有容器映像檔必須使用經過驗證的 Slim 或 Hardened Base Image (如 python:3.11-slim-bookworm)。強制定期執行依賴項版本與資安風險檢查，且生產環境嚴禁使用未鎖定版本 (Unpinned) 的套件。
12. 原子提交與文檔同步原則 (Atomic-Wiki-Sync)：嚴禁混合變更提交。必須遵循原子化提交 (Atomic Commits) 且確保 Wiki 文檔與代碼變更在同一週期內完成同步。**Agent 僅在使用者明確下達 commit 指令時才執行提交操作**。具體規範見 `git-commit-format.md` 與 `documentation-standards.md`。
13. 敏感資訊零容忍原則 (No-Hardcoded-Secrets)：嚴禁將任何 API 金鑰、資料庫密碼或個人敏感身分資訊 (PII) 硬編碼於代碼中，特別是 `src/data` 路徑下的模型與 Provider 定義。所有敏感配置必須透過環境變數或資料庫加密儲存區 (Settings) 讀取。

---
*註：開發時請同時參考 `.agent/rules/` 下的 `security-standards.md`, `coding-standards.md` 與 `testing-standards.md`。*