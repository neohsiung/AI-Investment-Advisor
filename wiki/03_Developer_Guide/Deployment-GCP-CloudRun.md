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
推薦使用以下指令部署應用程式：

```bash
gcloud run deploy portfolio-app \
    --source . \
    --platform managed \
    --region asia-east1 \
    --allow-unauthenticated \
    --set-env-vars DB_TYPE=postgres \
    --set-env-vars DB_USER=portfolio_user \
    --set-env-vars DB_PASS=[YOUR_PASSWORD] \
    --set-env-vars DB_NAME=portfolio \
    --set-env-vars DB_HOST=/cloudsql/[PROJECT_ID]:asia-east1:portfolio-prod \
    --set-env-vars AI_PROVIDER=google \
    --set-env-vars AI_MODEL=gemini-1.5-pro \
    --set-env-vars API_KEY=[YOUR_GEMINI_API_KEY]
```
*注意：`DB_PASS` 為您在執行 `setup_cloud_sql.sh` 時設定的密碼；`DB_HOST` 格式需完全符合 Script 輸出的 `Connection Name` (前綴 `/cloudsql/`)。*

### 4. 設定 OAuth (Configure OAuth)
由於 Cloud Run 網址是動態生成的 (首次部署後)，您需要：
1. 更新 Google Cloud Console 中的 **Authorized redirect URIs**。
2. 或更新環境變數 `REDIRECT_URI` 指向 Cloud Run 網址。
請參閱 [[Google-OAuth-Setup]]。

### 5. CI/CD 自動化 (Automation)
本專案包含 GitHub Actions workflow (`.github/workflows/deploy.yml`)。
只需在 GitHub Repository 的 Secrets 中設定 `GCP_SA_KEY`，即可在 Push main 分支時自動部署。
