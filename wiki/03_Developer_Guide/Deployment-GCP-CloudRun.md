# GCP Cloud Run Deployment Guide

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 GCP Cloud Run Deployment Guide

### Goal
Deploy the system to Google Cloud Platform (GCP) Cloud Run for a highly available, auto-scaling, secure Serverless environment.

### Why
- **NoOps**: No server/cluster management.
- **Pay-as-you-go**: Scale to zero when idle.
- **Security**: Built-in HTTPS and IAM.

### Deployment Steps

#### 1. Setup GCP
```bash
gcloud auth login
gcloud config set project [YOUR_PROJECT_ID]
```

#### 2. Deploy
```bash
gcloud run deploy portfolio-app \
    --source . \
    --platform managed \
    --region asia-east1 \
    --allow-unauthenticated \
    --set-env-vars DB_TYPE=postgres \
    --set-env-vars AI_PROVIDER=google \
    --set-env-vars AI_MODEL=gemini-1.5-pro \
    --set-env-vars API_KEY=[YOUR_KEY]
```

#### 3. Configure OAuth
Update **Authorized redirect URIs** in Google Cloud Console to point to your new Cloud Run URL.

---

<a id="traditional-chinese"></a>

## 🇹🇼 GCP Cloud Run 部署指南

### 目標 (Goal)
將系統部署至 Google Cloud Platform (GCP) 的 Cloud Run 服務，實現高可用、自動擴展且安全的 Serverless 運作環境。

### 為什麼 (Why)
- **免維運 (NoOps)**: 無需管理伺服器 (VM) 或 Kubernetes Cluster。
- **按需計費**: 無流量時縮減至 0，大幅降低閒置成本。
- **安全性**: 整合 IAM 權限管理與 HTTPS 自動憑證。

### 如何進行 (How)

#### 1. 初始化 GCP 環境 (Setup)
請先安裝 `gcloud` CLI 並登入：
```bash
gcloud auth login
gcloud config set project [YOUR_PROJECT_ID]
```

#### 2. 部署至 Cloud Run (Deploy)
推薦使用以下指令部署應用程式：

```bash
gcloud run deploy portfolio-app \
    --source . \
    --platform managed \
    --region asia-east1 \
    --allow-unauthenticated \
    --set-env-vars DB_TYPE=postgres \
    --set-env-vars AI_PROVIDER=google \
    --set-env-vars AI_MODEL=gemini-1.5-pro \
    --set-env-vars API_KEY=[YOUR_GEMINI_API_KEY]
```

#### 3. 設定 OAuth (Configure OAuth)
由於 Cloud Run 網址是動態生成的 (首次部署後)，您需要：
1. 更新 Google Cloud Console 中的 **Authorized redirect URIs**。
2. 或更新環境變數 `REDIRECT_URI` 指向 Cloud Run 網址。
請參閱 [[Google-OAuth-Setup]]。
