# 本地 SQLite 部署指南 (Local SQLite Deployment)

> 返回 [[Deployment-Options]]

本方案適合個人開發者或希望將數據完全保留在本地端的使用者。

## 系統需求 (Prerequisites)
- Docker Desktop (已安裝並啟動)
- Git

## 快速啟動 (Quick Start)

### 1. 取得程式碼
```bash
git clone https://github.com/YOUR_REPO/investment-advisor.git
cd investment-advisor
```

### 2. 設定環境變數
系統已包含 `.env.example`，啟動腳本會自動為您處理，但若需啟用 Email 通知，請手動編輯 `.env`：
```bash
cp .env.example .env
nano .env
# 填入 SMTP_USER, SMTP_PASSWORD 等資訊 (選填)
```

### 3. 一鍵啟動
執行啟動腳本：
```bash
./start.sh
```
此腳本會自檢環境、建置 Docker Image 並啟動服務。

### 4. 訪問服務
- **Dashboard**: [http://localhost:8501](http://localhost:8501)
- **Scheduler**: 在背景運行，自動執行每週報告。

---

## 維運管理 (Operations)

### 查看日誌
```bash
docker compose logs -f
```

### 停止服務
```bash
./stop.sh
```

### 資料備份
所有資料皆位於 `data/` 目錄：
- `data/portfolio.db`: 核心資料庫 (交易、持倉)。
- `data/cache.db`: AI 分析快取。
- `data/app.log`: 系統日誌。

**備份方式**: 定期複製整個 `data/` 資料夾即可。

## 下一步
- 若希望遷移至雲端，請參考 [[Database-Migration-Guide]]。
