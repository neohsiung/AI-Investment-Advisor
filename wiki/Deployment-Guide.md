# 部署與維運指南 (Deployment & Operations Guide)

> 返回 [[Home]]

本系統設計為在本地端 (MacBook Air M3) 常態性運作，使用 Docker 容器化技術確保環境一致性。

## 快速啟動 (Quick Start)

### 1. 啟動服務
只需執行專案根目錄下的啟動腳本：
```bash
./start.sh
```
此腳本會自動：
1. 檢查 `.env` 設定 (SMTP, API Keys)。
2. 建置 Docker Image。
3. 以背景模式啟動 Dashboard 與 Scheduler 容器。

啟動後，請訪問：[http://localhost:8501](http://localhost:8501)

### 2. 停止服務
```bash
./stop.sh
```
此腳本會優雅地停止所有容器。

## 系統監控 (Monitoring)

### 查看日誌 (View Logs)
```bash
# 查看所有服務日誌並持續追蹤
docker compose logs -f

# 僅查看 Scheduler (排程任務)
docker compose logs -f scheduler

# 僅查看 Dashboard (網頁介面)
docker compose logs -f dashboard
```

### 備份與還原 (Backup & Restore)
- **數據位置**: 所有資料庫與快取皆儲存於 `data/` 目錄。
- **備份**: 定期複製 `data/portfolio.db` 與 `data/cache.db`。
- **還原**: 停止服務後，將備份檔案覆蓋回 `data/` 目錄，再重新啟動。

## CI/CD 與安全性
- 本專案已整合 `bandit` 進行靜態代碼掃描。詳見 [[Security-Audit-Report]]。
- 若需遷移至雲端資料庫，請參考 [[Cloud-Database-Migration]]。
