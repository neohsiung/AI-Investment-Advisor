# 歷史文件存檔 (Archive)

本目錄存放已過時、被取代或參考價值的歷史文件。請勿將此處文件視為當前系統的真理來源 (Source of Truth)。

## 文件列表 (Documents)

- **[[wiki/Archive/雲端資料庫遷移指南-Cloud-Database-Migration.md|Cloud-Database-Migration]]**: 舊版雲端資料庫遷移指南。已整合至開發者指南。
- **[[wiki/Archive/功能規格_動態分析調度-Feature-Dynamic-Analysis-Dispatch.md|Feature-Dynamic-Analysis-Dispatch]]**: v3 核心功能原始規格草稿。已合併至 System Overview 與 Agent Swarm。
- **[[wiki/Archive/部署指南-Deployment-Guide.md|Deployment-Guide]]**: 舊版部署指南。已拆分為 Local/Cloud 兩個獨立文件。

## 程式碼存檔 (Code Archive)

位於專案根目錄的 `Archive/` 與 `scripts/Archive/`：

- **Root Scripts** (`Archive/root_scripts/`):
    - `deploy.sh`: 舊版 GCP 部署腳本 (v1)，已被 CI/CD 流程取代。
    - `setup_vm.sh`: 舊版 VM 初始化腳本，已被 Docker Compose 取代。
    - `setup_monitoring.sh`: 舊版監控設置，已被 Cloud Run Metrics 取代。

- **Utility Scripts** (`scripts/Archive/`):
    - `migrate_data.py`: 一次性使用的資料遷移腳本 (SQLite -> Postgres)。
    - `setup_cloud_sql.sh`: 初始設定 Cloud SQL 的腳本，僅需執行一次。

## 存檔原則
1. 當文件內容被新文件完全涵蓋時，移入此處。
2. 當功能被廢棄 (Deprecated) 或是一次性使用的腳本，移入各自的 Archive 資料夾。
3. 為了保持歷史脈絡，不建議直接刪除檔案。
