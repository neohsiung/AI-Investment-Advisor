# 接續行動指南 (Next Steps)

為了確保專案能順利部署並運作，請參考以下步驟：

### 1. 設定 GitHub Secrets (CI/CD 自動化必備)
為了讓 GitHub Actions 能自動部署到您的 GCP 專案，請至 GitHub Repository 的 **Settings > Secrets and variables > Actions** 新增以下變數：
*   **`GCP_PROJECT_ID`**: 您的 Google Cloud Project ID。
*   **`GCP_SA_KEY`**: 具有 Cloud Run 管理員與 Artifact Registry 寫入權限的 Service Account JSON 金鑰內容。

---

### 📘 進階教學：多環境部署與金鑰申請

#### 一、如何申請 GCP Service Account Key (SA_KEY)

針對本專案的 Cloud Run 與 Artifact Registry 架構，請依照以下步驟申請專用的服務帳號：

1.  **進入 GCP Console**
    *   前往 [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)。
    *   確認上方選單已選取正確的專案。

2.  **建立服務帳號 (Create Service Account)**
    *   點擊上方 **+ CREATE SERVICE ACCOUNT**。
    *   **Service account name**: 輸入例如 `github-actions-deployer`。
    *   點擊 **CREATE AND CONTINUE**。

3.  **賦予權限 (Grant permissions)**
    請加入以下 **3 個角色**以符合最小權限原則：
    *   `Cloud Run Developer` (Cloud Run 開發人員): 允許部署與更新服務，但無法修改權限。
    *   `Service Account User` (服務帳號使用者): 允許模擬執行身分。
    *   `Artifact Registry Writer` (Artifact Registry 寫入者): 允許推送 Docker Image。
    *   點擊 **CONTINUE**，然後 **DONE**。

4.  **建立 JSON 金鑰**
    *   在列表中點擊剛建立的服務帳號 Email。
    *   進入上方 **KEYS** 分頁。
    *   點擊 **ADD KEY** > **Create new key**。
    *   選擇 **JSON**，點擊 **CREATE**。
    *   **請妥善保管下載的 `.json` 檔案。**

5.  **設定 GitHub Actions**
    *   複製 `.json` 檔案內容。
    *   前往 GitHub Repo > **Settings > Secrets and variables > Actions**。
    *   新增 Secret `GCP_SA_KEY`，並貼上內容。

---

### 🔥 關鍵步驟：首次部署後的權限設定 (One-Time Setup)

由於我們採用了最高安全標準 (機器人無權公開服務)，您需要**手動執行一次**以下設定，讓服務對外公開：

1.  **等待 CI/CD 首次部署成功**
    GitHub Actions 顯示部署成功，但 Cloud Run 網址顯示 `403 Forbidden`。

2.  **開啟公開存取 (只需做一次)**
    使用您的 **Admin 帳號** (在 Cloud Shell 或本機) 執行：
    ```bash
    # 將 <YOUR_PROJECT_ID> 替換為您的 GCP Project ID
    gcloud run services add-iam-policy-binding investment-dashboard \
      --region asia-east1 \
      --member="allUsers" \
      --role="roles/run.invoker" \
      --project=<YOUR_PROJECT_ID>
    ```
    *或在 GCP Console 點擊該服務 > "SECURITY" > "ADD MEMBER" > 輸入 `allUsers` > 選擇 Role `Cloud Run Invoker`。*

3.  **完成**
    之後 CI/CD 機器人每次更新程式碼時，這個「公開狀態」都會被保留。

---

#### 二、如何修改專案以支援多環境 (Dev / Staging / Prod)

目前專案僅有單一 `main` 分支對應生產環境 (Prod)。若要擴充為多環境架構，建議採取以下策略：

**1. 使用 GitHub Environments 管理參數**
GitHub 提供了 Environments 功能來隔離不同環境的 Secrets。

*   **設定步驟**:
    1.  至 GitHub Repo > Settings > Environments。
    2.  建立三個環境：`Development`, `Staging`, `Production`。
    3.  在每個環境中分別設定 Secrets (例如 `GCP_PROJECT_ID`, `GCP_SA_KEY`)。
        *   Dev 環境可以使用測試用的 GCP Project。
        *   Prod 環境使用正式的 GCP Project。

**2. 修改 CI/CD 流程 (`.github/workflows/ci-cd.yml`)**
將 workflow 修改為根據分支觸發不同環境的部署：

```yaml
on:
  push:
    branches: [ "main", "develop" ]

jobs:
  # ... 省略 test job ...

  deploy-dev:
    needs: test
    if: github.ref == 'refs/heads/develop'
    environment: Development  # 自動讀取 Dev 環境的 Secrets
    runs-on: ubuntu-latest
    steps:
      # ... 使用 ${{ secrets.GCP_SA_KEY }} 進行部署 ...
      # 部署至 Cloud Run Service: investment-advisor-dev

  deploy-prod:
    needs: test
    if: github.ref == 'refs/heads/main'
    environment: Production   # 自動讀取 Prod 環境的 Secrets
    runs-on: ubuntu-latest
    steps:
      # ... 使用 ${{ secrets.GCP_SA_KEY }} 進行部署 ...
      # 部署至 Cloud Run Service: investment-advisor (正式版)
```

**3. 應用程式層級的區隔**
*   **資料庫**: 利用環境變數 `DB_NAME` 或 `DB_HOST` 讓不同環境連接不同資料庫。
*   **API Keys**: 同樣透過 GitHub Environment Secrets 注入不同的 API Key (例如 Dev 環境使用免費版 API Key)。

---

### 2. 資料遷移 (Data Migration)
*(維持原有內容)*
若您是從本地 SQLite 遷移至雲端 PostgreSQL，請參考 `README.md` 中的 **Cloud Deployment & Data Migration Strategy** 章節。
您可以選擇：
*   **Remote Migration**: 透過 `cloud_sql_proxy` 從本地連線至雲端資料庫進行遷移。
*   **VM-based Migration**: 將 SQLite 檔案上傳至 VM 直接遷移。
指令範例：
```bash
# 本地執行遷移 (需設定 .env)
python3 scripts/migrate_data.py --source data/portfolio.db
```

### 3. 本地開發 (Local Development) & 監控
*(維持原有內容)*
*   啟動: `./start_local.sh`
*   Logs: `docker compose logs -f`
