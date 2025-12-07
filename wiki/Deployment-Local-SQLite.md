# 本地部署指南 (Local SQLite)

> 返回 [[Deployment-Options]]

## 目標 (Goal)
在使用者本地機器上快速建立一個全功能的開發與測試環境，無需任何雲端依賴。

## 為什麼 (Why)
- **隱私第一**: 所有數據僅存於本地，確保絕對隱私。
- **快速迭代**: 修改程式碼後可立即預覽，無需等待雲端 Build & Deploy。
- **零成本**: 使用既有硬體資源。

## 做了什麼 (What)
- 使用 **Docker Compose** 编排容器。
- 內建 **SQLite** 作為輕量化資料庫。
- 整合 **Streamlit** (UI) 與 **Schedule** (排程) 於同一服務或分離服務。

## 如何進行 (How)

### 1. 前置需求 (Prerequisites)
- 安裝 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。
- 安裝 [Git](https://git-scm.com/)。

### 2. 下載與啟動 (Download & Start)
打開終端機 (Terminal)，執行以下指令：

```bash
# 1. Clone 專案
git clone https://github.com/neohsiung/AI-Investment-Advisor.git
cd AI-Investment-Advisor

# 2. 建立環境變數檔 (可選)
# 若有 API Key，請填入 .env
cp .env.example .env

# 3. 啟動服務
./start.sh
```

### 3. 驗證 (Verify)
- 瀏覽器打開 `http://localhost:8501`。
- 您應能看到 Streamlit 儀表板登入畫面。
- (本地模式預設可使用任意 Email 登入，或設定 OAuth 測試)。

### 4. 停止與維護 (Stop & Maintain)
```bash
# 停止服務
./stop.sh

# 查看日誌
docker compose logs -f
```
