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

### 3. 本地開發與運行 (Development & Execution)

#### 3.1 命令行工具註冊表 (CLI Registry)
系統核心邏輯可透過 `python src/cli.py` 觸發。

| 指令模式 | 參數示例 | 說明 |
| :--- | :--- | :--- |
| **Daily Workflow** | `--mode daily --user_id <ID>` | 執行每日收盤後的動能分析與快照。 |
| **Weekly Workflow**| `--mode weekly --user_id <ID>` | 執行每週總經分析與完整週報發送。 |
| **Backtest** | `--mode backtest --ticker AAPL` | 在本地執行 30 天標的回測模擬。 |
| **Optimize** | `--mode optimize` | 啟動 DSPy 優化流程 (Engineer Agent 核心)。 |
| **Scheduler** | `--mode scheduler` | 啟動守護進程，自動按時執行任務。 |

#### 3.2 自動化腳本清單 (Automation Scripts)
腳本存放於 `scripts/` 目錄，用於生產維護與部署。

- **`run_daily_check.sh`**: 封裝了 `cli.py` 的每日檢測與日誌輸出，用於 Cron Job。
- **`deploy_k8s.sh`**: 執行 `kubectl apply` 與 Secret 注入，實現 K8s 自動化。
- **`seed_user.py`**: 快速在資料庫中建立初始用戶與 API 金鑰設置。
- **`inspect_db.py`**: 診斷工具，快速查看 `transactions` 與 `holdings` 的一致性。

### 2. 環境變數手冊 (Environment Variable Glossary)
核心邏輯詳見 [資料庫設計與代碼規範](資料庫設計與代碼規範-Database-Git-Standards)。

| 變數名稱 | 類型 | 說明 |
| :--- | :--- | :--- |
| `GOOGLE_API_KEY` | Secret | Gemini 1.5 系列推理金鑰。 |
| `POLYGON_API_KEY` | Secret | Polygon.io 金鑰，用於獲取無限次數的即時行與歷史數據。 |
| `FMP_API_KEY` | Secret | Financial Modeling Prep 金鑰，用於獲取財報與新聞。 |
| `DISPLAY_TIMEZONE`| Enum | 系統顯示時區 (預設 `Asia/Taipei`)。 |
| `DB_TYPE` | Enum | `sqlite` 或 `postgres`。預設 `sqlite`。 |
| `DB_PATH` | Path | SQLite 檔案路徑。例：`data/portfolio.db`。 |
| `LOG_LEVEL` | Enum | `DEBUG`, `INFO`, `WARNING`, `ERROR`。 |
| `RISK_KEYWORDS_WEIGHTS` | JSON | **(v3.6)** 風險關鍵字權重配置，通常存儲於資料庫。 |
| `CHANNEL_CONFIG` | JSON | **(v3.6)** 通道適配器配置 (Email/LINE/Web)，通常存儲於資料庫。 |

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
| `Timezone Mismatch` | 系統時間與排程時間不符。 | 確保 `DISPLAY_TIMEZONE` 已設為您的本地時區並重新啟動 Scheduler。 |

---

<a id="en"></a>

## 🇺🇸 Environment & Local Dev

### 1. Installation
- **Python 3.11**: Mandatory for async support.
- **Docker**: Optional but recommended for microservice deployments.

### 2. Secrets Management
Define all keys in `.env`. Security defaults are detailed in [Agent Mesh Protocols](底層通信協議-Agent-Mesh-Protocols).
- `TAVILY_API_KEY`: High-precision search.
- `POLYGON_API_KEY`: Primary market data source.
- `FMP_API_KEY`: Fundamental and financial news source.
- `FRED_API_KEY`: Macro trends.
- `DISPLAY_TIMEZONE`: User-interface timezone (Default: `Asia/Taipei`).
- `RISK_KEYWORDS_WEIGHTS`: (v3.6) DB-driven risk weights.
- `CHANNEL_CONFIG`: (v3.6) Channel adapter settings.

### 3. Troubleshooting
- **API Key issues**: Check for trailing spaces in `.env`.
- **Latency**: Ensure stable internet; the primary search service has a 10s timeout policy.

## 🔗 Bidirectional Links
- **Standards**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
- **User Guide**: [Quickstart & User Guide](快速啟動與操作指南-Quickstart-User-Guide)
