# Google OAuth 2.0 設定檢查清單 (GCP Auth Setup Guide)

為了啟用免費的 Google 登入功能，請依照以下步驟在您的 **Google Cloud Console** 中完成設定。

## 步驟 1：建立/選擇專案
1. 登入 [Google Cloud Console](https://console.cloud.google.com/)。
2. 點擊頂部專案選單，建立一個新專案 (例如：`Investment-Advisor-SaaS`) 或選擇現有專案。

## 步驟 2：配置 OAuth 同意畫面 (OAuth Consent Screen)
*這是使用者點擊登入後，Google 彈出的授權資訊頁面。*

1. 導覽至 **API 與服務 (APIs & Services)** > **OAuth 同意畫面 (OAuth consent screen)**。
2. **User Type**：選擇 **外部 (External)** (如果您希望任何人都能測試) 或 **內部** (如果您有 Google Workspace)。
3. 填寫必要資訊：
   - **應用程式名稱**：`AI Investment Advisor`
   - **使用者支援電子郵件**：您的 Email。
   - **開發者聯絡資訊**：您的 Email。
4. **範圍 (Scopes)**：點擊「新增或移除範圍」，勾選以下兩個最基本權限：
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
   - `openid`
5. 儲存並繼續。

## 步驟 3：建立 OAuth 2.0 客戶端 ID (Credentials)
1. 導覽至 **API 與服務** > **憑證 (Credentials)**。
2. 點擊 **建立憑證 (Create Credentials)** > **OAuth 客戶端 ID (OAuth client ID)**。
3. **應用程式類型**：選擇 **網頁應用程式 (Web application)**。
4. **名稱**：`Advisor Local Dev`
5. **已授權的重新導向 URI (Authorized redirect URIs)**：
   - **重要**：請精確輸入以下網址（本地開發用）：
     - `http://localhost:8000/api/v1/auth/google/callback`
6. 點擊 **建立**。

## 步驟 4：取得金鑰並更新 `.env`
建立後會彈出一個視窗包含 `Client ID` 和 `Client Secret`。請將它們複製並填入專案根目錄的 `.env` 檔案中：

```bash
# 認證設定 (Sprint 4 新增)
GOOGLE_CLIENT_ID=您的_CLIENT_ID_在這邊
GOOGLE_CLIENT_SECRET=您的_CLIENT_SECRET_在這邊
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
JWT_SECRET=請輸入一段隨機長字串作為簽名金鑰
```

> [!TIP]
> **常見問題**：如果看到 `redirect_uri_mismatch` 錯誤，通常是步驟 3 的網址拼錯（例如少了一個 `/` 或 `http` 誤填為 `https`）。
