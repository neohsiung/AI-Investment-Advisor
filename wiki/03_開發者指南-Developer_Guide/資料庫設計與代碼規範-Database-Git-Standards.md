# 資料庫設計與代碼規範 (Database & Git Standards)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 資料庫設計與代碼規範 (v3.1)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，定義了系統持久層的物理設計、代碼風格與協作規範。

### 1. 資料庫物理設計 (Database Design)

#### 1.1 核心資料表詳解 (Table Definitions)

| 資料表 | 欄位 | 類型 | 描述與約束 |
| :--- | :--- | :--- | :--- |
| **`transactions`** | `id` | TEXT | PK, UUID。 |
| | `ticker` | TEXT | 股票代號 (e.g., AAPL)，不允許 NULL。 |
| | `action` | TEXT | 動作：`BUY`, `SELL`, `DIVIDEND`, `DEPOSIT`, `WITHDRAW`。 |
| | `quantity` | REAL | 數量，保留 4 位小數。 |
| | `price` | REAL | 執行價格，保留 4 位小數。 |
| | `amount` | REAL | 總金額 (Quantity * Price + Fees)。關鍵財務數據。 |
| **`daily_snapshots`** | `date` | TEXT | PK, 格式 `YYYY-MM-DD`。 |
| | `total_nlv` | REAL | 該日結算淨值。用於繪製 [績效曲線](快速啟動與操作指南-Quickstart-User-Guide)。 |
| | `leverage_ratio` | REAL | $TotalNominalValue / NLV$。超限觸發警告。 |

#### 1.2 非功能性要求 (NFR)
- **ACID 保證**: 所有外部 CSV 匯入必須使用 Transaction 封裝。任何一筆錯誤必須觸發 Full Rollback。
- **性能**: 定期針對 `date` 與 `user_id` 欄位建立 Index，確保 Dashboard 加載 < 5s。

### 2. 代碼規範 (Coding Best Practices)
本專案遵循業界最高標準：
- **Python 風格**: 遵循 [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)。
- **類型提示 (Type Hinting)**: 所有函式必須標註 `typing` 提示以利於 AI 生成與靜態檢查。
- **Docstrings**: 所有類別與方法必須提供 Google Style Docstrings (ZH/EN 雙語)。
- **安全規範**: 詳見 [底層通信協議](底層通信協議-Agent-Mesh-Protocols) 的 SQL 注入防護規範。

### 3. Git 協作與提交 (Git Standards)
- **提交規範**: 遵循 [Conventional Commits](https://www.conventionalcommits.org/)。
- **雙語要求**: 強制要求 `Subject` 為雙語，以便於全球協作團隊與各語系 AI 工程師理解。
    - **範例**: `feat(agent): add FredService for macro data | 新增 FredService 支持總經數據`

---

<a id="en"></a>

## 🇺🇸 Database & Git Standards

### 1. Database Specifications
- **Schema**: Detailed field definitions for `transactions`, `positions`, and `daily_snapshots`.
- **Integrity**: Mandatory use of transactions for all batch imports (ACID compliance).
- **Performance**: Indexing strategy focused on `date` and `user_id` for < 5s cold-load latency。

### 2. Code Quality
- **Standard**: [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).
- **Tooling**: Mandatory `bandit` for security and `typing` for static analysis.

### 3. Git Workflow
- **Commit Pattern**: Conventional Commits + Bilingual (EN|ZH) subjects.
- **Example**: `fix(auth): resolve Google OAuth token refresh | 修復 Google OAuth 憑證刷新問題`

## 🔗 Bidirectional Links
- **Architect View**: [System Landscape](系統全景圖-System-Landscape)
- **User Guide**: [Quickstart & User Guide](快速啟動與操作指南-Quickstart-User-Guide)
- **Tech Protocols**: [Agent Mesh Protocols](底層通信協議-Agent-Mesh-Protocols)
