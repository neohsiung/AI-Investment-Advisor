# 接續行動指南 (Next Steps)

為了確保專案能順利部署並運作，請參考以下步驟：

### 1. 設定 GitHub Secrets (CI/CD 自動化必備)
為了讓 GitHub Actions 能自動部署到您的 GCP 專案，請至 GitHub Repository 的 **Settings > Secrets and variables > Actions** 新增以下變數：
*   **`GCP_PROJECT_ID`**: 您的 Google Cloud Project ID。
*   **`GCP_SA_KEY`**: 具有 Cloud Run 管理員與 Artifact Registry 寫入權限的 Service Account JSON 金鑰內容。

### 2. 準備 GCP 環境
請確保您的 GCP 專案已啟用以下服務，並建立儲存庫：
*   **啟用 API**: Cloud Run API, Artifact Registry API, Cloud Scheduler API。
*   **建立 Artifact Registry**: 建立一個 Docker Repository (名稱預設為 `investment-advisor`，若不同請修改 `.github/workflows/ci-cd.yml` 中的 `REPOSITORY` 變數)。

### 3. 部署與驗證
完成上述設定後，您只需將目前的程式碼推送到 `main` 分支：
```bash
git add .
git commit -m "feat: add tests, refactor scheduler for cloud run jobs, setup ci/cd"
git push origin main
```
這將會觸發 CI/CD 流程：
1.  **CI**: 自動執行 `pytest` 確保測試覆蓋率 > 80%。
2.  **CD**: 自動建置 Docker Image 並部署 Dashboard (Cloud Run Service) 與排程任務 (Cloud Run Jobs)。

### 4. 設定排程觸發器 (一次性)
部署完成後，請執行 `deploy.sh` 腳本 (或手動設定 Cloud Scheduler) 來定期觸發 Cloud Run Jobs：
```bash
chmod +x deploy.sh
./deploy.sh
```
*(請記得先修改 `deploy.sh` 內的 `PROJECT_ID` 等變數)*

### 5. 本地開發注意事項
若您需要在本地執行測試，由於 `yfinance` 依賴的 `multitasking` 套件在 Python 3.8 有相容性問題，請執行以下指令修復（您已完成此步驟）：
```bash
pip install "multitasking<0.0.12"
pytest
```
