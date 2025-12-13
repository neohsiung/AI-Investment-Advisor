# Google OAuth 設定指南 (Google OAuth Setup)

> 返回 [[Deployment-GCP-CloudRun]] | 相關: [[System-Overview]]

## 1. 簡介 (Introduction)
本系統使用 Google OAuth 2.0 進行使用者登入驗證。為了在 Cloud Run 上正常運作，您必須提供 Google Cloud Credentials (`client_secret.json`) 與正確的 `REDIRECT_URI`。

---

## 2. 取得憑證 (Get Credentials) - 必備步驟
無論使用哪種部署方式，此前置步驟皆相同：

1.  前往 [Google Cloud Console - Credentials](https://console.cloud.google.com/apis/credentials)。
2.  建立 **OAuth client ID** (應用程式類型選擇 **Web application**)。
3.  **設定 Redirect URI** (非常重要！):
    - **本地測試**: `http://localhost:8501`
    - **正式環境**: `https://[您的CloudRun網址].run.app` (例如 `https://investment-app-xyz.run.app`)
      > *注意：若之後網址變更，請務必回來這裡更新。*
4.  下載 JSON 檔案，建議重新命名為 `client_secret.json`。

---

## 3. 設定方式推薦 (Setup Methods)

請依據您的需求選擇一種方式設定。

### 🥇 推薦方式 1: 使用環境變數 (最簡單、適合初學者)
直接將 JSON 內容貼入 Cloud Run 環境變數，無需處理檔案掛載。

1.  **開啟文字編輯器**，打開您下載的 `client_secret.json`。
2.  **複製**全部內容。
3.  前往 GCP Console > Cloud Run > 您的服務 > **編輯與部署新修訂版本**。
4.  切換到 **「變數與密鑰 (Variables & Secrets)」** 頁籤。
5.  新增環境變數：
    - **名稱 (Name)**: `client_secret.json` (或 `GOOGLE_CLIENT_SECRET_JSON`)
    - **值 (Value)**: `[貼上剛剛複製的完整 JSON 內容]`
6.  新增另一個環境變數：
    - **名稱**: `REDIRECT_URI`
    - **值**: `https://[您的CloudRun網址].run.app`
7.  **部署 (Deploy)**。

---

### 🥈 推薦方式 2: 使用 CLI 指令 (最穩健、適合自動化)
使用 `gcloud` 指令一次完成 Secret 上傳與部署，適合追求 Infrastructure as Code 的團隊。

```bash
# 1. 設定變數 (請替換為您的實際值)
SERVICE_NAME="investment-dashboard"
REGION="asia-east1"
REDIRECT_URL="https://[YOUR-SERVICE-URL].run.app"
SECRET_FILE_PATH="./client_secret.json"

# 2. 執行部署更新
gcloud run services update $SERVICE_NAME \
  --region $REGION \
  --update-secrets=/app/secrets/client_secret.json=oauth-client-secret:latest \
  --update-env-vars="GOOGLE_CLIENT_SECRET_PATH=/app/secrets/client_secret.json,REDIRECT_URI=$REDIRECT_URL"
```

---

### 🥉 方式 3: 使用 Secret Manager 檔案掛載 (進階)
若您習慣使用 GCP Console 的 Secret Manager 介面進行檔案掛載。

1.  將 `client_secret.json` 上傳至 GCP Secret Manager。
2.  在 Cloud Run 編輯頁面 > **Volumes** > 掛載該 Secret。
    - **Mount Path**: `/app/secrets`
3.  設定環境變數：
    - `GOOGLE_CLIENT_SECRET_PATH`: `/app/secrets/[Secret名稱]` (例如 `oauth-client-secret`)
    - `REDIRECT_URI`: `https://[您的CloudRun網址].run.app`

---

## 4. 本地開發 (Local Development)
在本地電腦執行時：
1.  將 `client_secret.json` 放在專案根目錄。
2.  在 `.env` 檔案中確認：
    ```bash
    REDIRECT_URI=http://localhost:8501
    COOKIE_KEY=[任意隨機字串]
    ```

---

## 5. 常見問題排除 (Troubleshooting)

### 🔴 錯誤 400: redirect_uri_mismatch
> **原因**: GCP Console 上設定的 URI 與程式實際送出的不一致。

**解決步驟**:
1.  查看錯誤訊息中的詳細資訊，找到 `redirect_uri=...` 後面的網址。
2.  注意網址**最後是否有斜線 `/`** (例如 `...run.app/`)。
3.  前往 [Google Cloud Console](https://console.cloud.google.com/apis/credentials)。
4.  將錯誤訊息中的網址，**完全一字不差**地加入到 **Authorized redirect URIs** 列表中。
5.  儲存後等待約 1-5 分鐘生效。

### 🔴 登入後被導向 localhost
> **原因**: Cloud Run 上缺少 `REDIRECT_URI` 環境變數。

**解決步驟**:
- 請參考「推薦方式 1」的步驟 6，補上 `REDIRECT_URI` 環境變數。
