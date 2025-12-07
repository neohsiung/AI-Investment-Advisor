# 部署方案選擇 (Deployment Options)

> 返回 [[Home]]

## 目標 (Goal)
提供靈活且彈性的部署架構，滿足不同階段 (開發測試 vs 生產環境) 與不同資源預算的需求。

## 為什麼 (Why)
- **開發效率**: 本地環境需快速啟動、零成本，適合快速迭代。
- **生產穩定**: 線上環境需高可用 (High Availability)、零維護 (Serverless) 與安全性。
- **成本控制**: 允許使用者根據流量與預算，自由切換算力與資料庫層級。

## 做了什麼 (What)
我們支援兩種主要的部署模式：

| 特性 | 方案 A: 本地輕量版 (Local SQLite) | 方案 B: 雲端企業版 (GCP Cloud Run) |
| :--- | :--- | :--- |
| **適用場景** | 個人使用、開發測試、離線分析 | 團隊協作、長期運行、自動化排程 |
| **運算資源** | 本機 CPU/RAM | AWS/GCP Serverless 容器 |
| **資料庫** | SQLite (`.db` 檔案) | Cloud SQL (PostgreSQL) 或 SQLite (Volume) |
| **成本** | $0 | 低 (依用量計費，有免費額度) |
| **設定難度** | 低 (Docker Compose 一鍵啟動) | 中 (需設定 GCP 專案與權限) |

## 如何進行 (How)

### 選擇您的路徑

#### 路徑 1: 我想快速試用，只在自己電腦跑
請參考 [[Deployment-Local-SQLite]]。您只需要安裝 Docker，即可在一分鐘內啟動系統。

#### 路徑 2: 我需要 24/7 自動化監控與多裝置存取
請參考 [[Deployment-GCP-CloudRun]]。這將引導您將容器部署至 Google Cloud Platform，並設定 HTTPS 與身分驗證。

#### 進階: 資料庫遷移
若您想從本地遷移至雲端，或反之，請參考 [[Database-Migration-Guide]]。
