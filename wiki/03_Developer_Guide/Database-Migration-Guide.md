# 資料庫遷移指南 (Database Migration Guide)

> 返回 [[Deployment-Options]]

## 目標 (Goal)
提供一套安全、可靠的流程，讓使用者能在不同環境 (Local SQLite, Cloud SQL, Cloud Volume) 之間無縫遷移數據。

## 為什麼 (Why)
- **環境切換**: 從開發轉入生產環境，或從雲端備份回本地分析。
- **技術升級**: 從 SQLite 升級至效能更好的 PostgreSQL。
- **災難復原**: 在系統故障時還原數據。

## 做了什麼 (What)
本指南涵蓋三種主要的遷移路徑：
1.  **SQLite -> Cloud SQL (PostgreSQL)**: 上雲升級。
2.  **Cloud SQL -> SQLite**: 下雲備份。
3.  **Local SQLite -> Cloud SQLite**: 雲端掛載。

## 如何進行 (How)

### 情境 A: 上雲 (SQLite -> Cloud SQL)
*推薦工具: `pgloader`*

1.  **準備**: 確認本地 `portfolio.db` 完整。
2.  **轉換**: 建立 `migrate.load` 腳本，描述 SQLite 到 PostgreSQL 的欄位對應。
3.  **執行**:
    ```bash
    pgloader migrate.load
    ```
4.  **驗證**: 檢查 Cloud SQL 中的 `transactions` 筆數是否一致。

### 情境 B: 下雲 (Cloud SQL -> SQLite)
*推薦方式: CSV 中轉*

1.  **匯出**: 使用 `psql` 或 GCP Console 匯出 `transactions` 表格為 CSV。
    ```sql
    \COPY (SELECT * FROM transactions) TO 'backup.csv' WITH CSV HEADER
    ```
2.  **初始化**: 在本地啟動一個乾淨的 `portfolio.db`。
3.  **匯入**: 使用 Dashboard 的 [Data Management] -> [CSV Import] 功能匯入備份檔。

### 情境 C: 雲端 SQLite (Local -> Cloud Volume)
*適用於: 想用 Cloud Run 但不想付 Cloud SQL 費用的用戶*

1.  **上傳**: 將 `portfolio.db` 上傳至 **Google Cloud Storage (GCS)**。
    ```bash
    gcloud storage cp data/portfolio.db gs://[YOUR_BUCKET]/portfolio.db
    ```
2.  **掛載**: 在 Cloud Run 中使用 GCS Fuse 掛載 Bucket 到 `/app/data`。
3.  **設定**: 確保應用程式讀取路徑正確。

---
> **資料驗證重點**: 遷移後務必核對 **NLV (淨值)** 與 **ROI** 是否與原環境一致。
