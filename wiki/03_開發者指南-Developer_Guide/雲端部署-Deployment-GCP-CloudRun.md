# GCP Cloud Run Deployment Guide

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


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

#### 4. Setup CI/CD Environment Variables (GitHub Secrets)
**IMPORTANT Update (2026-01-01):** The CI/CD pipeline is now **Zero-Cost by Default**.
- Automatic deployment on push is **DISABLED**.
- To deploy, you must manually trigger the workflow:
    1. Go to **Actions** tab in GitHub.
    2. Select **CI/CD Pipeline**.
    3. Click **Run workflow**.
    4. Check the box **Deploy to GCP (Prd)?** (set to `true`).
- This ensures you only pay for GCP resources when you explicitly intend to deploy.

The following secrets are automatically injected into Cloud Run by `ci-cd.yml`. Please configure them in your GitHub Repository Secrets:

| Category | Variable | Description |
|---|---|---|
| **AI** | `API_KEY` | API Key for Gemini or OpenAI. |
| | `AI_PROVIDER` | `Google Gemini`, `OpenAI`, or `OpenRouter`. |
| | `AI_MODEL_SMART` | High-reasoning model (e.g., `gemini-1.5-pro`). |
| | `AI_MODEL_FAST` | Low-cost/fast model (e.g., `gemini-1.5-flash`). |
| **DB** | `DB_TYPE` | Must be `postgres` for Cloud Run. |
| | `DB_HOST` | Cloud SQL IP address. |
| | `DB_USER` | Database username. |
| | `DB_PASS` | Database password. |
| | `DB_NAME` | Database name (e.g., `portfolio`). |
| **Auth** | `GOOGLE_CLIENT_SECRET_JSON` | Content of `client_secret.json`. |
| | `REDIRECT_URI` | Full URL of your Cloud Run service (e.g., `https://.../`). |

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
#### 4. 設定 CI/CD 環境變數 (GitHub Secrets)
**重要更新 (2026-01-01):** 目前 CI/CD 流程預設為 **零成本 (Zero-Cost)** 模式。
- `git push` **不會** 自動觸發部署。
- 若要部署至 GCP，必須手動觸發 Worklfow：
    1. 前往 GitHub 的 **Actions** 分頁。
    2. 選擇 **CI/CD Pipeline**。
    3. 點擊 **Run workflow**。
    4. 勾選 **Deploy to GCP (Prd)?** (設定為 `true`)。
- 此機制確保只有在您明確想要部署時，才會建立雲端資源並產生費用。

以下變數由 `ci-cd.yml` 自動注入到 Cloud Run。請在 GitHub Repository Secrets 中設定：

| 分類 (Category) | 變數名稱 (Variable) | 說明 (Description) |
|---|---|---|
| **AI** | `API_KEY` | Gemini 或 OpenAI 的 API Key。 |
| | `AI_PROVIDER` | AI 提供者 (如 `Google Gemini`, `OpenAI`, `OpenRouter`)。 |
| | `AI_MODEL_SMART` | 高推理能力模型 (例如 `gemini-1.5-pro`)，用於 CIO/總經分析。 |
| | `AI_MODEL_FAST` | 快速/低成本模型 (例如 `gemini-1.5-flash`)，用於動能分析/調度。 |
| **DB (資料庫)** | `DB_TYPE` | Cloud Run 環境必須設為 `postgres`。 |
| | `DB_HOST` | Cloud SQL 的 IP 位址。 |
| | `DB_USER` | 資料庫使用者名稱。 |
| | `DB_PASS` | 資料庫密碼。 |
| | `DB_NAME` | 資料庫名稱 (例如 `portfolio`)。 |
| Auth (驗證) | `GOOGLE_CLIENT_SECRET_JSON` | `client_secret.json` 檔案的完整內容。 |
| | `REDIRECT_URI` | Cloud Run 服務的完整網址 (例如 `https://.../`)。 |

#### 5. 資源清理 (Resource Teardown)
若需下線服務以停止計費，可使用專案提供的自動化腳本：

```bash
./scripts/gcp_teardown.sh
```

此腳本會刪除：
*   Cloud Run Service (`investment-dashboard`)
*   Cloud Run Jobs (`daily-check`, `weekly-report`, `monthly-refinement`)

**注意**：為防止資料遺失，腳本 **不會** 自動刪除 Cloud SQL 資料庫與 Artifact Registry 的映像檔。若確定不再需要，請手動刪除：

```bash
# 刪除資料庫
gcloud sql instances delete [INSTANCE_NAME]

# 刪除映像檔儲存庫
gcloud artifacts repositories delete investment-advisor --location=asia-east1
```

---

<a id="english-teardown"></a>

#### 5. Resource Teardown (Clean up)
To take the service offline and stop billing, use the provided script:

```bash
./scripts/gcp_teardown.sh
```

This script will delete:
*   Cloud Run Service (`investment-dashboard`)
*   Cloud Run Jobs (`daily-check`, `weekly-report`, `monthly-refinement`)

**Note**: To prevent data loss, the script does **NOT** delete the Cloud SQL database or Artifact Registry images. If you wish to delete them:

```bash
# Delete Cloud SQL
gcloud sql instances delete [INSTANCE_NAME]

# Delete Artifact Registry
gcloud artifacts repositories delete investment-advisor --location=asia-east1
```


