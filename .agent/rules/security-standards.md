---
trigger: always_on
---

# 資安維護與基礎設施規範 (Security Maintenance & Infrastructure Standards)

本規範依據 **Rule #11 (Managed-Security-Base)** 制定，旨在確保 AI Agent 在開發與部署過程中維持專案的資安水位。

## 1. 基礎映像檔管理 (Base Image Management)
- **硬化基礎**: 必須使用 `python:3.11-slim-bookworm` 或經過驗證的 Slim 變體。
- **嚴禁使用**: `latest` 標籤、未鎖定版本的映像檔或未經驗證的第三方來源。
- **非 Root 執行**: 所有 Dockerfile 必須實做 `appuser` 並以其執行，禁止使用 `root`。

## 2. 依賴項安全性 (Dependency Security)
- **精確鎖定**: `requirements.txt` 必須使用 `==` 鎖定精確版本，嚴禁使用無限制的範圍 (如 `requests>=*`)。
- **強制審計**: 每次新增或更新套件時，必須執行 `bandit`, `safety` 或 `pip-audit` 檢查。
- **最小化原則**: 僅安裝執行所需的套件，移除所有不必要的測試型或編譯型依附項。

## 3. 憑證與機敏資料管理 (Secrets Management) - Rule #12
- **環境變數**: 敏感資訊 (API Key, Database URL, SMTP Credentials) 強制使用環境變數或專用的 Secret Manager。
- **嚴禁硬編碼**: 嚴禁在代碼、註釋或 Wiki 中出現任何明文憑證。
- **忽略規範**: 確保 `.gitignore` 和 `.dockerignore` 包含 `.env`, `*.pem`, `*.key` 等敏感檔案。

## 4. SQL 安全性 (SQL Security)
- **參數化查詢**: 所有 Raw SQL 必須使用參數化 (Parameterized Queries)，嚴禁使用 `f-string` 或字串拼接組合 SQL 敘述。
- **ORM 安全**: 對於非性能敏感的操作優先使用 ORM 提供的防注入機制。

## 5. 自動化工作流觸發 (Workflow Triggers)
- 在執行 `deploy` 或重大 `refactor` 前，Agent 應主動提示執行 `/security-audit` 工作流。

---
*註：違反此規範將直接導致 CI/CD 流程中斷。*
