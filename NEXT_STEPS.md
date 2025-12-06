# 接續行動指南 (Next Steps)

為了確保專案能順利部署並運作，請參考以下步驟：

### 1. 設定 GitHub Secrets (CI/CD 自動化必備)
為了讓 GitHub Actions 能自動部署到您的 GCP 專案，請至 GitHub Repository 的 **Settings > Secrets and variables > Actions** 新增以下變數：
*   **`GCP_PROJECT_ID`**: 您的 Google Cloud Project ID。
*   **`GCP_SA_KEY`**: 具有 Cloud Run 管理員與 Artifact Registry 寫入權限的 Service Account JSON 金鑰內容。

### 2. 資料遷移 (Data Migration)
若您是從本地 SQLite 遷移至雲端 PostgreSQL，請參考 `README.md` 中的 **Cloud Deployment & Data Migration Strategy** 章節。
您可以選擇：
*   **Remote Migration**: 透過 `cloud_sql_proxy` 從本地連線至雲端資料庫進行遷移。
*   **VM-based Migration**: 將 SQLite 檔案上傳至 VM 直接遷移。
指令範例：
```bash
# 本地執行遷移 (需設定 .env)
python3 scripts/migrate_data.py --source data/portfolio.db
```

### 3. 部署與驗證 (Deployment)
目前程式碼已通過測試 (Coverage > 70%) 並且重構完畢。
請執行以下指令將變更推送至 `main` 分支以觸發 CI/CD：
```bash
git add .
git commit -m "release: finalize database extraction, cloud migration scripts, and test coverage > 70%"
git push origin main
```

流程說明：
1.  **CI**: 自動執行 `pytest` 確保測試覆蓋率達標。
2.  **CD**: 自動建置 Docker Image 並部署 Dashboard 與 Cron Jobs。

### 4. 本地開發 (Local Development)
若需在本地開發測試，請使用輔助腳本：
```bash
./start_local.sh
```
此腳本會自動建立虛擬環境並安裝相依套件。
若遇到 `yfinance` 相容性問題，請確保 `multitasking<0.0.12` (已在 requirements.txt 中)。

### 5. 監控與維運
*   **GCP Cloud Monitoring**: 請依據 `setup_monitoring.sh` 設定 Uptime Check。
*   **Logs**: 使用 `docker compose logs -f` (本地) 或 GCP Logs Explorer (雲端) 查看排程執行狀況。
