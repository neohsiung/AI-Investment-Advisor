# Google OAuth Setup Guide

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Google OAuth Setup Guide

### 1. Introduction
This system uses Google OAuth 2.0 for authentication. You must provide `client_secret.json` and a correct `REDIRECT_URI`.

### 2. Get Credentials (Required)
1.  Go to [Google Cloud Console - Credentials](https://console.cloud.google.com/apis/credentials).
2.  Create **OAuth client ID** (Type: **Web application**).
3.  **Set Redirect URI**:
    - **Local**: `http://localhost:8501`
    - **Cloud**: `https://[YOUR-SERVICE-URL].run.app`
4.  Download JSON as `client_secret.json`.

### 3. Setup Method

#### Method 1: Environment Variables (Recommended for Simple Setup)
Copy JSON content into Cloud Run Env Var `client_secret.json`.

#### Method 2: CLI (Recommended for Automation)
Use `gcloud run services update` with `--update-secrets` or `--update-env-vars`.

### 4. Local Development
Place `client_secret.json` in root and set `REDIRECT_URI=http://localhost:8501` in `.env`.

### 5. Troubleshooting
- **Error 400 redirect_uri_mismatch**: The URL in Console must MATCH EXACTLY what the app sends (trailing slash matters).
- **Looping at login**: Missing `REDIRECT_URI` env var in Cloud Run.

---

<a id="traditional-chinese"></a>

## 🇹🇼 Google OAuth 設定指南 (Google OAuth Setup)

### 1. 簡介 (Introduction)
本系統使用 Google OAuth 2.0 進行使用者登入驗證。為了在 Cloud Run 上正常運作，您必須提供 Google Cloud Credentials (`client_secret.json`) 與正確的 `REDIRECT_URI`。

### 2. 取得憑證 (Get Credentials) - 必備步驟
無論使用哪種部署方式，此前置步驟皆相同：

1.  前往 [Google Cloud Console - Credentials](https://console.cloud.google.com/apis/credentials)。
2.  建立 **OAuth client ID** (應用程式類型選擇 **Web application**)。
3.  **設定 Redirect URI** (非常重要！):
    - **本地測試**: `http://localhost:8501`
    - **正式環境**: `https://[您的CloudRun網址].run.app` (例如 `https://investment-app-xyz.run.app`)
      > *注意：若之後網址變更，請務必回來這裡更新。*
4.  下載 JSON 檔案，建議重新命名為 `client_secret.json`。

### 3. 設定方式推薦 (Setup Methods)

#### 🥇 推薦方式 1: 使用環境變數 (最簡單、適合初學者)
直接將 JSON 內容貼入 Cloud Run 環境變數 (`client_secret.json`)，無需處理檔案掛載。

#### 🥈 推薦方式 2: 使用 CLI 指令 (最穩健、適合自動化)
使用 `gcloud` 指令一次完成 Secret 上傳與部署。

### 4. 本地開發 (Local Development)
在本地電腦執行時：
1.  將 `client_secret.json` 放在專案根目錄。
2.  在 `.env` 檔案中確認 `REDIRECT_URI=http://localhost:8501`。

### 5. 常見問題排除 (Troubleshooting)

- **🔴 錯誤 400: redirect_uri_mismatch**
    - **原因**: GCP Console 上設定的 URI 與程式實際送出的不一致 (注意斜線 `/`)。
    - **解法**: 複製錯誤訊息中的網址，加入 Console 的允許清單。

- **🔴 登入後被導向 localhost**
    - **原因**: Cloud Run 上缺少 `REDIRECT_URI` 環境變數。
    - **解法**: 補上該變數指向 Cloud Run 網址。
