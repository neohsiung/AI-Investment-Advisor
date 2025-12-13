# GCP Cloud Run 部署指南

> 返回 [[Deployment-Options]] | 相關: [[Google-OAuth-Setup]]

## 目標 (Goal)
將系統部署至 Google Cloud Platform (GCP) 的 Cloud Run 服務，實現高可用、自動擴展且安全的 Serverless 運作環境。

## 為什麼 (Why)
- **免維運 (NoOps)**: 無需管理伺服器 (VM) 或 Kubernetes Cluster。
- **按需計費**: 無流量時縮減至 0，大幅降低閒置成本。
- **安全性**: 整合 IAM 權限管理與 HTTPS 自動憑證。

## 做了什麼 (What)
- 將 Docker Image 推送至 **Google Artifact Registry**。
- 部署至 **Cloud Run**。
- (選用) 連結 **Cloud SQL** (PostgreSQL) 或掛載 **GCS Fuse**。
- 設定 **Secret Manager** 管理敏感憑證。

## 如何進行 (How)

### 1. 初始化 GCP 環境 (Setup)
請先安裝 `gcloud` CLI 並登入：
```bash
gcloud auth login
gcloud config set project [YOUR_PROJECT_ID]
```

### 2. 建立 Cloud SQL (Optional)
若要使用 PostgreSQL：
```bash
gcloud sql instances create portfolio-db --database-version=POSTGRES_15 --cpu=1 --memory=4GB --region=asia-east1
gcloud sql databases create portfolio --instance=portfolio-db
```

### 3. 部署至 Cloud Run (Deploy)
使用我們提供的 `gcloud run deploy` 指令或 Docker 部署。
推薦使用 Source Deploy：

```bash
gcloud run deploy investment-dashboard \
    --source . \
    --platform managed \
    --region asia-east1 \
    --allow-unauthenticated \
    --set-env-vars DB_TYPE=postgres,DB_HOST=/cloudsql/[PROJECT_ID]:asia-east1:portfolio-db,DB_USER=[USER],DB_PASS=[PASS],DB_NAME=portfolio
```

### 4. 設定 OAuth (Configure OAuth)
由於 Cloud Run 網址是動態生成的 (首次部署後)，您需要更新 OAuth 設定。
請參閱 [[Google-OAuth-Setup]] 進行憑證設定與環境變數掛載。

### 5. CI/CD 自動化 (Automation)
本專案包含 GitHub Actions workflow (`.github/workflows/deploy.yml`)。
只需在 GitHub Repository 的 Secrets 中設定 `GCP_SA_KEY`，即可在 Push main 分支時自動部署。
