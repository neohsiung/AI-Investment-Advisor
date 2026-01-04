# Database Migration Guide

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Database Migration Guide

### Goal
Provide a reliable process to migrate data seamlessly between environments (Local SQLite, Cloud SQL, Cloud Volume).

### Why
- **Environment Switch**: Dev to Prod.
- **Upgrade**: SQLite to PostgreSQL.
- **Disaster Recovery**: Restore from backups.

### Pathways

#### Path A: To Cloud (SQLite -> Cloud SQL)
*Tool: `pgloader`*

1.  **Prepare**: Backup local `portfolio.db`.
2.  **Convert**: Create `migrate.load` script.
3.  **Run**: `pgloader migrate.load`
4.  **Verify**: Check row counts.

#### Path B: From Cloud (Cloud SQL -> SQLite)
*Method: CSV*

1.  **Export**: Export `transactions` table to CSV via GCP Console or `psql`.
2.  **Init**: Start clean `portfolio.db` locally.
3.  **Import**: Use Dashboard [Data Management] -> [CSV Import].

#### Path C: Cloud SQLite (Local -> Cloud Volume)
*For: Cloud Run without Cloud SQL.*

1.  **Upload**: `gcloud storage cp data/portfolio.db gs://[BUCKET]/`
2.  **Mount**: Use GCS Fuse in Cloud Run.

---

<a id="traditional-chinese"></a>

## 🇹🇼 資料庫遷移指南 (Database Migration Guide)

### 目標 (Goal)
提供一套安全、可靠的流程，讓使用者能在不同環境 (Local SQLite, Cloud SQL, Cloud Volume) 之間無縫遷移數據。

### 為什麼 (Why)
- **環境切換**: 從開發轉入生產環境，或從雲端備份回本地分析。
- **技術升級**: 從 SQLite 升級至效能更好的 PostgreSQL。
- **災難復原**: 在系統故障時還原數據。

### 如何進行 (How)

#### 情境 A: 上雲 (SQLite -> Cloud SQL)
*推薦工具: `pgloader`*

1.  **準備**: 確認本地 `portfolio.db` 完整。
2.  **轉換**: 建立 `migrate.load` 腳本，描述 SQLite 到 PostgreSQL 的欄位對應。
3.  **執行**:
    ```bash
    pgloader migrate.load
    ```
4.  **驗證**: 檢查 Cloud SQL 中的 `transactions` 筆數是否一致。

#### 情境 B: 下雲 (Cloud SQL -> SQLite)
*推薦方式: CSV 中轉*

1.  **匯出**: 使用 `psql` 或 GCP Console 匯出 `transactions` 表格為 CSV。
    ```sql
    \COPY (SELECT * FROM transactions) TO 'backup.csv' WITH CSV HEADER
    ```
2.  **初始化**: 在本地啟動一個乾淨的 `portfolio.db`。
3.  **匯入**: 使用 Dashboard 的 [Data Management] -> [CSV Import] 功能匯入備份檔。

#### 情境 C: 雲端 SQLite (Local -> Cloud Volume)
*適用於: 想用 Cloud Run 但不想付 Cloud SQL 費用的用戶*

1.  **上傳**: 將 `portfolio.db` 上傳至 **Google Cloud Storage (GCS)**。
    ```bash
    gcloud storage cp data/portfolio.db gs://[YOUR_BUCKET]/portfolio.db
    ```
2.  **掛載**: 在 Cloud Run 中使用 GCS Fuse 掛載 Bucket 到 `/app/data`。
3.  **設定**: 確保應用程式讀取路徑正確。

---
> **資料驗證重點**: 遷移後務必核對 **NLV (淨值)** 與 **ROI** 是否與原環境一致。
