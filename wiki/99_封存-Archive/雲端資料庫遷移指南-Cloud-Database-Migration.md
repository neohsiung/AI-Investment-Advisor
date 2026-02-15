# 雲端資料庫遷移指南 (Cloud Database Migration Guide)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 雲端資料庫遷移指南 (Cloud Database Migration Guide)

> 返回 [[Home]]

### 1. 技術選型: Cloud SQL (PostgreSQL) vs. AlloyDB

#### Cloud SQL for PostgreSQL
- **描述**: 全受管的 PostgreSQL 關聯式資料庫服務。
- **優點**:
    - **具成本效益**: 起始價格較低，足以應付大多數中小型資料集。
    - **標準 PostgreSQL**: 與標準 Postgres 工具和函式庫完全相容。
    - **維護**: 自動備份、修補與複寫。
- **缺點**: 相較於 AlloyDB，在處理大規模分析工作負載時擴展性有限。
- **建議**: 本專案的 **首選 (Primary Choice)**。對於個人/SaaS 投資顧問應用程式而言，它在成本、效能與管理之間取得了最佳平衡。

#### AlloyDB for PostgreSQL
- **描述**: 專為高要求企業工作負載打造的完全相容 PostgreSQL 服務。
- **建議**: 僅在使用者數 > 10,000 或百萬級交易資料列的即時分析成為瓶頸時才考慮。

---

### 2. 遷移策略 (SQLite -> Cloud SQL)

關於架構面的影響，請參考 [[Clean-Architecture-Review]]。

#### 先決條件 (Prerequisite)
1.  **GCP 專案**: 啟用中的 Google Cloud Project。
2.  **Cloud SQL 實例**: 已建立實例 (PostgreSQL 14/15)。
3.  **工具**: `gcloud`, `pgloader` (推薦) 或 `sqlite3` + `psql`。

#### 逐步指南 (Step-by-Step Guide)

##### 步驟 1: 準備本地資料 (Prepare Local Data)
確保您的本地 SQLite 資料庫是一致的。
```bash
# 先備份
cp data/portfolio.db data/portfolio_backup.db
```

##### 2: 建立 Cloud SQL 實例 (Create Cloud SQL Instance)
```bash
gcloud sql instances create portfolio-production \
    --database-version=POSTGRES_15 \
    --tier=db-custom-1-3840 \
    --region=asia-east1
```

##### 步驟 3: 建立資料庫與使用者 (Create Database & User)
```bash
gcloud sql databases create portfolio --instance=portfolio-production
gcloud sql users create postgres_user --instance=portfolio-production --password=[PASSWORD]
```

##### 步驟 4: 遷移 (選項 A: pgloader - 推薦)
`pgloader` 可以自動將 SQLite schema 轉換為 Postgres。

1.  **安裝 pgloader**: `brew install pgloader` (Mac) 或 `apt-get install pgloader` (Linux)。
2.  **建立命令檔案 (`migrate.load`)**:
    ```text
    load database
         from sqlite:///absolute/path/to/data/portfolio.db
         into postgresql://postgres_user:[PASSWORD]@[IP_ADDRESS]:5432/portfolio

    with include drop, create tables, create indexes, reset sequences

    set work_mem to '16MB', maintenance_work_mem to '512 MB';
    ```
3.  **執行遷移**:
    ```bash
    pgloader migrate.load
    ```

##### 步驟 5: 驗證資料 (Verify Data)
連線至 Cloud SQL 並查詢表格。
```bash
psql "host=[IP_ADDRESS] user=postgres_user dbname=portfolio sslmode=require"
# \dt
# SELECT count(*) FROM transactions;
```

##### 步驟 6: 更新應用程式設定 (Update Application Configuration)
更新 `src/database.py` (邏輯已相容) 以使用環境變數。

**在生產環境 (例如 Cloud Run / Docker) 設定環境變數:**
- `DB_TYPE`: `postgres`
- `DB_HOST`: `[IP_ADDRESS]` (或 Cloud Run 的 `/cloudsql/[INSTANCE_CONNECTION_NAME]`)
- `DB_USER`: `postgres_user`
- `DB_PASS`: `[PASSWORD]`
- `DB_NAME`: `portfolio`
- `DB_PORT`: `5432`

### 資安注意事項 (Security Note)
- 可參考 [[Security-Audit-Report]] 以了解更多關於連線安全的建議。
- **Cloud SQL Auth Proxy**: 使用 Auth Proxy 進行安全的本地連線，而非開放公用 IP。
- **VPC Peering**: 用於內部流量 (例如從 App Engine/Cloud Run 連線)。

---

<a id="en"></a>

## 🇺🇸 Cloud Database Migration Guide

> Back to [[Home]]

### 1. Technology Selection: Cloud SQL vs. AlloyDB

-   **Cloud SQL (Selected)**: Best balance of cost, performance, and management for our scale. Full PostgreSQL compatibility.
-   **AlloyDB**: Reserved for high-scale enterprise workloads (>10k users).

### 2. Migration Strategy (SQLite -> Cloud SQL)

Refer to [[Clean-Architecture-Review]] for architectural impacts.

#### Prerequisites
1.  GCP Project.
2.  Cloud SQL Instance (Postgres 14/15).
3.  Tools: `gcloud`, `pgloader`.

#### Step-by-Step

1.  **Backup**: `cp data/portfolio.db data/portfolio_backup.db`
2.  **Create Instance**: Use `gcloud sql instances create`.
3.  **Create DB/User**: Use `gcloud sql databases/users create`.
4.  **Migrate (pgloader)**: Use `pgloader` to convert SQLite schema/data to Postgres automatically.
5.  **Verify**: Check table counts via `psql`.
6.  **Update Config**: Set environment variables (`DB_TYPE`, `DB_HOST`, etc.) in production.

#### Security Note
-   See [[Security-Audit-Report]].
-   Use **Cloud SQL Auth Proxy** or **VPC Peering** for secure connections.
