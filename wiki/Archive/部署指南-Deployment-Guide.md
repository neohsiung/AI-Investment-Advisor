# 部署與維運指南 (Deployment & Operations Guide)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 部署與維運指南 (Deployment & Operations Guide)

> 返回 [[Home]]

本系統設計為在本地端 (MacBook Air M3) 常態性運作，使用 Docker 容器化技術確保環境一致性。

### 快速啟動 (Quick Start)

#### 1. 啟動服務
只需執行專案根目錄下的啟動腳本：
```bash
./start.sh
```
此腳本會自動：
1. 檢查 `.env` 設定 (SMTP, API Keys)。
2. 建置 Docker Image。
3. 以背景模式啟動 Dashboard 與 Scheduler 容器。

啟動後，請訪問：[http://localhost:8501](http://localhost:8501)

#### 2. 停止服務
```bash
./stop.sh
```
此腳本會優雅地停止所有容器。

### 系統監控 (Monitoring)

#### 查看日誌 (View Logs)
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

### CI/CD 與安全性
- 本專案已整合 `bandit` 進行靜態代碼掃描。詳見 [[Security-Audit-Report]]。
- 若需遷移至雲端資料庫，請參考 [[wiki/Archive/雲端資料庫遷移指南-Cloud-Database-Migration.md|Cloud Database Migration]]。

---

<a id="en"></a>

## 🇺🇸 Deployment & Operations Guide

> Back to [[Home]]

This system is designed to run consistently on a local environment (MacBook Air M3) using Docker containerization.

### Quick Start

#### 1. Start Services
Run the startup script in the project root:
```bash
./start.sh
```
This script automates:
1.  Checking `.env` configuration (SMTP, API Keys).
2.  Building Docker Images.
3.  Starting Dashboard and Scheduler containers in background mode.

Once started, access the dashboard at: [http://localhost:8501](http://localhost:8501)

#### 2. Stop Services
```bash
./stop.sh
```
This script gracefully stops all containers.

### Monitoring

#### View Logs
```bash
# View all logs and follow
docker compose logs -f

# View Scheduler only
docker compose logs -f scheduler

# View Dashboard only
docker compose logs -f dashboard
```

### Backup & Restore
-   **Data Location**: All databases and caches are stored in the `data/` directory.
-   **Backup**: Regularly copy `data/portfolio.db` and `data/cache.db`.
-   **Restore**: Stop services, overwrite files in `data/` with backups, and restart.

### CI/CD & Security
-   Integrated `bandit` for static code analysis. See [[Security-Audit-Report]].
-   For cloud database migration, refer to [[wiki/Archive/雲端資料庫遷移指南-Cloud-Database-Migration.md|Cloud Database Migration]].
