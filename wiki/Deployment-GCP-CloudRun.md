# GCP Cloud Run 部署指南 (GCP Cloud Run Deployment)

> 返回 [[Deployment-Options]]

本方案適合需要 24/7 在線、多人存取或高可用性的生產環境。

## 架構說明 (Architecture)
- **運算**: Google Cloud Run (Serverless Container)。
- **資料庫**: Cloud SQL (PostgreSQL)。詳見 [[Database-Migration-Guide]]。
- **CI/CD**: GitHub Actions 自動化部署。

## 初始設定 (Initial Setup)

### 1. GCP 基礎建設
請參考 [[Database-Migration-Guide]] 內的步驟先建立 Cloud SQL 實例。

### 2. Service Account 設定 (CI/CD 必備)
為了讓 GitHub Actions 能自動部署，需申請一組 Service Account Key。

1.  **啟用 API**: Cloud Run Admin API, Artifact Registry API。
2.  **建立 Artifact Registry**: 建立 Docker Repo (名稱: `investment-advisor`, 地區: `asia-east1`)。
3.  **建立 Service Account**: 賦予以下角色：
    - `Cloud Run Developer`
    - `Service Account User`
    - `Artifact Registry Writer`
4.  **下載 JSON Key**: 下載後複製內容。
5.  **GitHub Secrets**: 到 Repo Settings > Secrets，新增 `GCP_SA_KEY` 與 `GCP_PROJECT_ID`。

### 3. 生產環境權限設定 (One-Time Setup)
首次部署後，Cloud Run 預設不公開。需手動開啟權限：
1.  前往 GCP Cloud Run Console。
2.  點擊服務 `investment-dashboard` > **PERMISSIONS**。
3.  新增 Principal `allUsers`，賦予角色 `Cloud Run Invoker`。
4.  儲存並允許公開存取。

## 雙向遷移 (Migration)
若您是從本地 SQLite 遷移過來，請務必閱讀 [[Database-Migration-Guide]] 完成資料遷移。

## 環境變數 (Environment Variables)
在 Cloud Run 中需設定以下變數以連線至 Cloud SQL：
- `DB_TYPE`: `postgres`
- `DB_HOST`: `/cloudsql/YOUR_CONNECTION_NAME`
- `DB_USER`: `postgres_user`
- `DB_PASS`: `YOUR_PASSWORD`
- `DB_NAME`: `portfolio`
