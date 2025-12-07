# Google OAuth 設定指南 (Google OAuth Setup)

> 返回 [[Deployment-GCP-CloudRun]] | 相關: [[System-Overview]]

## 目標 (Goal)
為系統啟用 Google 帳號登入功能，並保護應用程式僅供授權使用者存取，避免資料外洩。

## 為什麼 (Why)
- **安全性**: 取代簡易的密碼驗證，利用 Google 的強大安控機制 (2FA)。
- **便利性**: 使用者無需記憶額外帳號密碼 (SSO)。
- **SaaS 基礎**: 透過 Email 識別使用者身分，實現多租戶資料隔離。

## 做了什麼 (What)
- 整合 **OAuth 2.0** 授權流程。
- 使用 `streamlit-google-auth` 庫處理握手與 Token 交換。
- 使用 **Secret Manager** (雲端) 或 `.env` (本地) 安全管理憑證。

## 如何進行 (How)

### 1. 取得 Google 憑證 (Get Credentials)
1.  前往 [Google Cloud Console - Credentials](https://console.cloud.google.com/apis/credentials)。
2.  建立 **OAuth client ID** (Web application)。
3.  設定 **Authorized redirect URIs** (這是最容易錯誤的步驟，請精確設定):
    - 本地: `http://localhost:8501`
    - 雲端: `https://[YOUR-CLOUD-RUN-URL].run.app`
4.  下載 JSON 檔，重新命名為 `client_secret.json`。

### 2. 本地環境設定 (Local Setup)
將 `client_secret.json` 放入專案根目錄，並在 `.env` 設定：
```bash
GOOGLE_CLIENT_SECRET_PATH=client_secret.json
REDIRECT_URI=http://localhost:8501
COOKIE_KEY=[隨機亂數密鑰]
```

### 3. 雲端環境設定 (Cloud Setup) - 關鍵步驟！
由於資安考量，**絕對不要**將 `client_secret.json` push 到 git。

#### 方式 A: 使用 CLI (推薦，最穩健)
直接執行指令，讓 GCP 自動處理 Secret 新增與掛載：
```bash
gcloud run services update investment-dashboard \
  --region asia-east1 \
  --update-secrets=/app/secrets/client_secret.json=oauth-client-secret:latest \
  --update-env-vars="GOOGLE_CLIENT_SECRET_PATH=/app/secrets/client_secret.json"
```

#### 方式 B: 使用 Console UI (變通 - 檔案掛載)
若您堅持使用 UI 且找不到 "Target File" 欄位：
1.  Mount Volume 時，Secret 會預設使用其名稱作為檔名 (例如 `oauth-client-secret`)。
2.  請將環境變數 `GOOGLE_CLIENT_SECRET_PATH` 指向 `/app/secrets/oauth-client-secret` 即可。

#### 方式 C: 使用環境變數 (直接注入內容)
若您無法掛載檔案，可將 JSON 內容直接作為環境變數注入：
1.  在 Cloud Run 環境變數設定中，新增變數名為 `client_secret.json` (或 `GOOGLE_CLIENT_SECRET_JSON`)。
2.  將 `client_secret.json` 的**完整內容**貼入作為值。
3.  系統會自動偵測並解析該環境變數。

### 4. 驗證 (Verify)
開啟 App，看到 "Login with Google" 按鈕，點擊後能成功跳轉並返回，即設定完成。
