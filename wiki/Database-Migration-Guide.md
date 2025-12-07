# 資料庫雙向遷移指南 (Bidirectional Database Migration)

> 返回 [[Home]] | 相關: [[Deployment-Options]]

本指南提供 SQLite (本地) 與 Cloud SQL (雲端) 之間的雙向資料遷移流程，讓您能自由切換部署環境。

## 情境 A: 上雲 (SQLite -> Cloud SQL)
**適用於**: 從本地開發環境遷移至生產環境。

### 1. 準備工作
- 確保本地 `data/portfolio.db` 資料完整。
- 已建立 Cloud SQL PostgreSQL 實例。

### 2. 使用 pgloader (推薦)
`pgloader` 能自動處理 Schema 轉換與資料匯入。

1.  **安裝**: `brew install pgloader`
2.  **設定**: 建立 `migrate.load` 檔案 (參考 repo 範例)。
3.  **執行**: `pgloader migrate.load`

### 3. 使用 CSV 中介 (手動)
若無法使用 pgloader，可透過「匯出 CSV -> 匯入」的方式：
1.  在本地 Dashboard 的 `Data Management` 頁面，使用 SQL 用戶端匯出 `transactions` 為 CSV。
2.  連線至 Cloud SQL，使用 `\COPY` 指令或透過 Dashboard 的 CSV Import 功能將資料匯入。

---

## 情境 B: 下雲 (Cloud SQL -> SQLite)
**適用於**: 備份數據、返回本地開發或降低成本。

由於 SQLite 不直接支援 PostgreSQL 格式，我們建議採用 **CSV 匯出/匯入法**。

### 1. 從 Cloud SQL 匯出資料
使用 `gcloud` 或 `psql` 將核心資料表匯出為 CSV。

```bash
# 匯出 Transactions
psql "host=[IP] user=[USER] dbname=portfolio" -c "\COPY (SELECT * FROM transactions) TO 'transactions_backup.csv' WITH CSV HEADER"

# 匯出 Cash Flows (若有)
psql ... -c "\COPY (SELECT * FROM cash_flows) TO 'cash_flows_backup.csv' WITH CSV HEADER"
```

### 2. 重置本地 SQLite
若要全新開始：
1.  停止本地服務。
2.  移除或更名舊的 `data/portfolio.db`。
3.  重新啟動服務 `./start.sh` (系統會自動初始化新的空 DB)。

### 3. 匯入資料
1.  開啟本地 Dashboard (`localhost:8501`)。
2.  前往 **Data Management** 頁面。
3.  使用 **CSV Import** 功能，上傳剛才匯出的 `transactions_backup.csv`。
4.  系統會自動重新計算所有持倉與績效。

## 資料驗證 (Validation)
無論是上雲或下雲，遷移後請務必檢查：
1.  **總資產價值 (NLV)**: 是否與遷移前一致？
2.  **持倉數量**: 股數是否正確？
3.  **歷史權益曲線**: 是否完整保留？

> **Tip**: 使用 Dashboard 的 "Overview" 截圖作為遷移前後的比對基準。
