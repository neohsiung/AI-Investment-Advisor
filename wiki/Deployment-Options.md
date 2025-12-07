# 部署方案選擇 (Deployment Options)

> 返回 [[Home]]

本系統支援兩種主要部署模式，您可依據需求選擇最適合的方案。

## 方案比較 (Comparison)

| 特性 | [[Deployment-Local-SQLite]] | [[Deployment-GCP-CloudRun]] |
| :--- | :--- | :--- |
| **適用場景** | 個人使用、開發測試、零成本 | 多人協作、SaaS 營運、高可用性 |
| **資料庫** | SQLite (本地檔案) | Cloud SQL (PostgreSQL) |
| **運算資源** | 本地 Docker (MacBook/PC) | Google Cloud Run (Serverless) |
| **成本** | **$0** (Free) | **~$50/月** (視流量而定) |
| **資料遷移** | 需手動備份檔案 | 自動備份、可擴展 |
| **存取方式** | `localhost:8501` | 公網 URL (HTTPS) |

## 詳細指南 (Detailed Guides)

### 1. [[Deployment-Local-SQLite]]
適合單人開發者。數據儲存於本地 `data/portfolio.db`，透過 Docker Compose 一鍵啟動。

### 2. [[Deployment-GCP-CloudRun]]
適合生產環境。利用 GCP 的強大基礎設施，包含 CI/CD 自動化部署流程與 Cloud SQL 資料庫設定。
