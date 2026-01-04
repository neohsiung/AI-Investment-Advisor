# 部署方案選擇 (Deployment Options)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 部署方案選擇

### 目標 (Goal)
提供靈活且彈性的部署架構，滿足不同階段 (開發測試 vs 生產環境) 與不同資源預算的需求。

### 為什麼 (Why)
- **開發效率**: 本地環境需快速啟動、零成本，適合快速迭代。
- **生產穩定**: 線上環境需高可用 (High Availability)、零維護 (Serverless) 與安全性。
- **成本控制**: 允許使用者根據流量與預算，自由切換算力與資料庫層級。

### 做了什麼 (What)
我們支援兩種主要的部署模式：

| 特性 | 方案 A: 本地輕量版 (Local SQLite) | 方案 B: 雲端企業版 (GCP Cloud Run) | 方案 C: 彈性擴展版 (K8s) |
| :--- | :--- | :--- | :--- |
| **適用場景** | 個人使用、開發測試、離線分析 | 團隊協作、長期運行、自動化排程 | 企業級應用、大規模集群 |
| **運算資源** | 本機 CPU/RAM | AWS/GCP Serverless 容器 | Kubernetes Cluster |
| **資料庫** | SQLite (`.db` 檔案) | Cloud SQL (PostgreSQL) 或 SQLite (Volume) | PostgreSQL (StatefulSet) |
| **成本** | $0 | 低 (依用量計費，有免費額度) | 高 (需負擔 Cluster 費用) |
| **設定難度** | 低 (Docker Compose 一鍵啟動) | 中 (需設定 GCP 專案與權限) | 高 (K8s Manifests) |

### 如何進行 (How)

#### 路徑 1: 我想快速試用，只在自己電腦跑
請參考 [[本地部署-Deployment-Local-SQLite]]。您只需要安裝 Docker，即可在一分鐘內啟動系統。

#### 路徑 2: 我需要 24/7 自動化監控與多裝置存取 (Serverless)
請參考 [[雲端部署-Deployment-GCP-CloudRun]]。這將引導您將容器部署至 Google Cloud Platform，並設定 HTTPS 與身分驗證。

#### 路徑 3: 我需要大規模彈性擴展 (Kubernetes)
使用 `start.sh --k8s` 部署至 Minikube 或 GKE。適合企業級應用。

#### 進階: 資料庫遷移
若您想從本地遷移至雲端，或反之，請參考 [[資料庫遷移-Database-Migration-Guide]]。

## 🔗 相關連結 (See Also)
- [本地部署指南 (Local)](wiki/03_開發者指南-Developer_Guide/本地部署-Deployment-Local-SQLite.md)
- [雲端部署指南 (Cloud Run)](wiki/03_開發者指南-Developer_Guide/雲端部署-Deployment-GCP-CloudRun.md)

---

<a id="en"></a>

## 🇺🇸 Deployment Options

### Goal
Provide flexible deployment architectures meeting different needs (Dev vs Prod) and budgets.

### Why
- **Dev Efficiency**: Local env needs fast startup, zero cost.
- **Prod Stability**: Online env needs High Availability (HA) and Security.
- **Cost Control**: Switch compute/database tiers based on budget.

### What
We support two main modes:

| Feature | Option A: Local Lightweight (SQLite) | Option B: Cloud Enterprise (GCP Cloud Run) | Option C: Scalable Cluster (K8s) |
| :--- | :--- | :--- | :--- |
| **Scenario** | Personal use, Dev/Test, Offline | Team collaboration, Long-running, Automation | Enterprise Scale |
| **Compute** | Local CPU/RAM | Serverless Container | Kubernetes Cluster |
| **Database** | SQLite (`.db` file) | Cloud SQL (PostgreSQL) | PostgreSQL (StatefulSet) |
| **Cost** | $0 | Low (Pay-as-you-go) | High (Cluster Cost) |
| **Difficulty** | Low (Docker Compose) | Medium (GCP Setup) | High (K8s Manifests) |

### How

#### Path 1: Quick Trial (Local)
See [[本地部署-Deployment-Local-SQLite]]. Requires Docker only. Up in 1 minute.

#### Path 2: 24/7 Automation (Serverless Cloud)
See [[雲端部署-Deployment-GCP-CloudRun]]. Deploy to Google Cloud Platform with HTTPS.

#### Path 3: Scalable Cluster (Kubernetes)
Run on Minikube or GKE using `start.sh --k8s` and manifests in `k8s/`. Ideal for enterprise scale.

#### Advanced: Migration
To move data between Local and Cloud, see [[資料庫遷移-Database-Migration-Guide]].
