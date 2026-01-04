# Local Deployment Guide (SQLite)

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Local Deployment Guide (Docker)

### Goal
Quickly establish a full-featured dev/test environment on a local machine without cloud dependencies.

### Why
- **Privacy First**: Data stays local.
- **Fast Iteration**: Immediate preview after code changes.
- **Zero Cost**: Uses existing hardware.

## 🔗 See Also
- [Deployment Options](wiki/01_使用者手冊-User_Manual/Deployment-Options.md)
- [CLI Reference](wiki/03_開發者指南-Developer_Guide/命令行手冊-CLI-Reference.md)
- [Database Migration Guide](wiki/03_開發者指南-Developer_Guide/資料庫遷移-Database-Migration-Guide.md)

### Setup Steps

#### 1. Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Git](https://git-scm.com/)

#### 2. Download & Start
Terminal:
```bash
# 1. Clone
git clone https://github.com/neohsiung/AI-Investment-Advisor.git
cd AI-Investment-Advisor

# 2. Env Vars
cp .env.example .env

# 3. Start
./start.sh
```

#### 3. Verify
- Open `http://localhost:8501`.
- You should see the login screen.

#### 4. Stop & Maintenance
```bash
./stop.sh       # Stop services
./stop.sh       # Stop services
docker compose logs -f dashboard # View logs
```

---

<a id="traditional-chinese"></a>

## 🇹🇼 本地部署指南 (Local Docker)

### 目標 (Goal)
在使用者本地機器上快速建立一個全功能的開發與測試環境，無需任何雲端依賴。

### 為什麼 (Why)
- **隱私第一**: 所有數據僅存於本地，確保絕對隱私。
- **快速迭代**: 修改程式碼後可立即預覽，無需等待雲端 Build & Deploy。
- **零成本**: 使用既有硬體資源。

### 如何進行 (How)

#### 1. 前置需求 (Prerequisites)
- 安裝 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。
- 安裝 [Git](https://git-scm.com/)。

#### 2. 下載與啟動 (Download & Start)
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

#### 3. 驗證 (Verify)
- 瀏覽器打開 `http://localhost:8501`。
- 您應能看到 Streamlit 儀表板登入畫面。
- (本地模式預設可使用任意 Email 登入，或設定 OAuth 測試)。

#### 4. 停止與維護 (Stop & Maintain)
```bash
# 停止服務
./stop.sh

# 查看日誌
# 查看日誌
# 查看日誌
docker compose logs -f dashboard
```
