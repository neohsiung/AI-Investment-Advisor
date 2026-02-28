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
7. 視覺化指導原則 (Visual Documentation Rule): 所有技術相關的計畫 (Plan)、架構設計、操作手冊或規格文件，必須盡可能使用 Mermaid 語法提供對應的圖表 (包含流程圖 Flowcharts、循序圖 Sequence Diagrams、架構圖/類別圖 Class/Architecture Diagrams 等)。在寫入文件之前，必須驗證圖表結構與語法正確且能順利渲染，確保文件具備極高的可讀性與專業度。
8. 動態指標原則：所有系統閾值 (Thresholds) 必須是基於歷史數據計算的動態變數，或可經由復盤 (Experience Replay) 調整的參數，嚴禁使用寫死 (Hardcoded) 的定值。
9. 混合儲存原則 (Hybrid Strategy)：針對複雜行情計算與向量搜尋 (pgvector) 強制使用 Raw SQL (SQLAlchemy Core)；針對一般物件 (User, Settings) 與後台管理可選用 ORM。具體實施細節參見 `.agent/rules/engineering-standards.md`。
10. 資安唯一原則 (Safe-SQL-Only)：所有 Raw SQL 必須使用參數化查詢 (Parameterized Queries)，嚴禁使用字串拼接或 f-strings 組合 SQL 敘述。相關範例參見 `.agent/rules/engineering-standards.md`。
11. 基礎映像檔與資安審計原則 (Managed-Security-Base)：所有容器映像檔必須使用經過驗證的 Slim 或 Hardened Base Image (如 python:3.11-slim-bookworm)。強制定期執行依賴項版本與資安風險檢查，且生產環境嚴禁使用未鎖定版本 (Unpinned) 的套件。
12. 原子提交與文檔同步原則 (Atomic-Wiki-Sync)：嚴禁混合變更提交。必須遵循原子化提交 (Atomic Commits) 且確保 Wiki 文檔與代碼變更在同一週期內完成同步。**Agent 僅在使用者明確下達 commit 指令時才執行提交操作**。具體規範見 `git-commit-format.md` 與 `documentation-standards.md`。
13. 敏感資訊零容忍原則 (No-Hardcoded-Secrets)：嚴禁將任何 API 金鑰、資料庫密碼或個人敏感身分資訊 (PII) 硬編碼於代碼中，特別是 `src/data` 路徑下的模型與 Provider 定義。所有敏感配置必須透過環境變數或資料庫加密儲存區 (Settings) 讀取。
14. 工作流自動觸發原則 (Workflow Auto-Trigger)：以下工作流在符合條件時，Agent 必須**主動提議**執行（提示使用者確認），無需等待使用者下達 slash command：
    - `/walkthrough-wiki-sync`：當 Agent 完成含架構變更的 task 並產出 walkthrough 後，自動提議執行 Wiki 文檔同步。
    - `/test-coverage-check`：當使用者下達 `commit` 指令前，若本次變更涉及 `src/` 下的業務邏輯，自動提議執行覆蓋率檢查。
15. AI 輔助優先原則 (AI-Support First): 所有技術選型與架構部署設定 (如 Helm, IaC) 必須確保對 AI 代理人 (Agent) 擁有最高的代碼生成友善性，偏好聲明式 (Declarative) 的結構化語法與支援良好的生態系 (如 Next.js, Python, TypeScript)，以便 Agent 能夠精準重構。
16. 多雲可攜性原則 (Multi-Cloud Portability): 系統架構在設計與部署時，必須確保不被單一雲服務商獨家綁定 (No Vendor Lock-in)。透過採用 Kubernetes (K8s) 與標準化 Helm Charts，保證應用程式能在 GCP, AWS, Azure 等不同 PAAS 間無痛且低成本地搬遷。

---
*註：開發時請同時參考 `.agent/rules/` 下的 `engineering-standards.md`, `governance-standards.md`, `observability-standards.md` 與 `git-commit-format.md`。*