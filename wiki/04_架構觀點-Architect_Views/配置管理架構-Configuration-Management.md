# 配置管理架構 (Configuration Management Architecture)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-14 | v1.0 | Initial Release: DB-based Config & Security | Neo |

---

## 1. 核心概念 (Core Concepts)

為解決環境變數 (`.env`) 管理不便且需重啟容器的問題，系統實現了 **資料庫驅動的配置管理系統 (DB-Driven Configuration System)**。

To address the inflexibility of `.env` files and the need for restarts, we implemented a **DB-Driven Configuration System**.

### 1.1 設計目標 (Design Goals)
*   **動態性 (Dynamism)**: 修改設定後即時生效 (Hot-Reload)。
*   **安全性 (Security)**: API Key 等敏感資訊不應明文儲存於 Git 或 Dockerfile。
*   **使用者隔離 (User Isolation)**: 支援多租戶 (Multi-tenant) 的個人化設定。

## 2. 架構設計 (Architecture Design)

### 2.1 資料庫 Schema (Database Schema)

所有設定儲存於 SQLite `settings` 資料表：

All settings are stored in the SQLite `settings` table:

```sql
CREATE TABLE settings (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, key)
);
```

### 2.2 存取層 (Repository Layer)

使用 `SettingsRepository` 進行抽象化存取，支援 Singleton 模式與快取：

Access is abstracted via `SettingsRepository`, supporting Singleton pattern and caching:

```python
class SettingsRepository:
    def get(self, user_id, key, default=None): ...
    def set(self, user_id, key, value): ...
```

### 2.3 注入策略 (Injection Strategy)

服務 (Service) 初始化時，優先從資料庫讀取設定，若無則回退至環境變數 (Env Var Fallback)。

Services prioritize DB settings upon initialization, falling back to Environment Variables if DB settings are missing.

**Priority**: `DB Settings` > `Environment Variables` > `Hardcoded Defaults`

```python
# Pseudo-code Example
api_key = settings_repo.get(uid, "API_KEY") or os.getenv("API_KEY")
```

## 3. 安全性 (Security)

*   **API Key 加密**: 前端輸入框使用 `type="password"` 遮蔽。
*   **傳輸安全**: 建議在生產環境配合 HTTPS 使用。
*   **權限控制**: 設定僅限該 `user_id` 存取。

## 4. 遷移指南 (Migration Guide)

從 v3.4 升級至 v3.5 的開發者，建議將 `.env` 中的以下變數遷移至設定頁面：
*   `ETORO_API_KEY` / `ETORO_USER_KEY`
*   `OPENROUTER_API_KEY` / `GOOGLE_API_KEY`
*   `FUTU_HOST` / `IBKR_HOST`

---
### 參閱 (See Also)
*   [使用者手冊: 系統設定與金鑰管理](../01_使用者手冊-User_Manual/02_系統設定與金鑰管理-System-Configuration.md)
