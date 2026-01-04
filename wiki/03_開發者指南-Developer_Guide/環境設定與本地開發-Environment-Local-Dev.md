# 環境設定與本地開發 (Environment & Local Dev)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 環境設定與本地開發指南 (v3.1)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，引導開發者從零開始建置專業的開發環境。

### 1. 快速啟動 (Quick Start)

#### 1.1 傳統 Python 環境 (推薦)
建議使用 **Python 3.11** 以確保非同步套件兼容性。
```bash
# 建立環境 (以 Conda 為例)
conda create -n ai-advisor python=3.11 -y
conda activate ai-advisor

# 安裝依賴 (含 Linting 與測試工具)
pip install -r requirements.txt
```

#### 1.2 Docker 容器化開發
```bash
# 啟動包含所有服務的開發環境
docker-compose up --build
```

### 2. 環境變數手冊 (Environment Variable Glossary)
核心邏輯詳見 [資料庫設計與代碼規範](資料庫設計與代碼規範-Database-Git-Standards)。

| 變數名稱 | 類型 | 說明 |
| :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Secret | Gemini 1.5 系列推理金鑰。 |
| `DB_TYPE` | Enum | `sqlite` 或 `postgres`。預設 `sqlite`。 |
| `DB_PATH` | Path | SQLite 檔案路徑。例：`data/portfolio.db`。 |
| `LOG_LEVEL` | Enum | `DEBUG`, `INFO`, `WARNING`, `ERROR`。 |

### 3. 操作手冊與 CLI (CLI Handbook)
`src/cli.py` 封裝了所有自動化任務：
- **生成報告**: `python src/cli.py --mode daily --user_id <email>`
- **回測模擬**: `python src/cli.py --mode backtest --ticker AAPL`

### 4. 疑難排解 (Troubleshooting)

| 問題 | 可能原因 | 解決方法 |
| :--- | :--- | :--- |
| `SSL Certificate Error` | MacOS 預設證書失效。 | 執行 `/Applications/Python 3.11/Install Certificates.command`。 |
| `Database is locked` | 多個行程同時寫入 SQLite。 | 確保僅有一個 CLI 排程器在運行。 |
| `ModuleNotFoundError` | 虛擬環境未正確激活。 | 執行 `export PYTHONPATH=$PYTHONPATH:$(pwd)`。 |

---

<a id="en"></a>

## 🇺🇸 Environment & Local Dev

### 1. Installation
- **Python 3.11**: Mandatory for async support.
- **Docker**: Optional but recommended for microservice deployments.

### 2. Secrets Management
Define all keys in `.env`. Security defaults are detailed in [Agent Mesh Protocols](底層通信協議-Agent-Mesh-Protocols).
- `TAVILY_API_KEY`: High-precision search.
- `FRED_API_KEY`: Macro trends.

### 3. Troubleshooting
- **API Key issues**: Check for trailing spaces in `.env`.
- **Latency**: Ensure stable internet; the primary search service has a 10s timeout policy.

## 🔗 Bidirectional Links
- **Standards**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
- **User Guide**: [Quickstart & User Guide](快速啟動與操作指南-Quickstart-User-Guide)
