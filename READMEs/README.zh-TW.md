# AI Investment Advisor

<p align="center">
  <a href="https://github.com/neohsiung/AI-Investment-Advisor"><img src="https://img.shields.io/github/stars/neohsiung/AI-Investment-Advisor?style=social" alt="Stars"></a>
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/network/members"><img src="https://img.shields.io/github/forks/neohsiung/AI-Investment-Advisor?style=social" alt="Forks"></a>
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/issues"><img src="https://img.shields.io/github/issues/neohsiung/AI-Investment-Advisor" alt="Issues"></a>
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/blob/main/LICENSE"><img src="https://img.shields.io/github/license/neohsiung/AI-Investment-Advisor" alt="License"></a>
</p>

<p align="center">
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/blob/main/README.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/blob/main/READMEs/README.ja-JP.md">日本語</a>
</p>

<p align="center">
  <img src="../assets/hero.png" alt="AI Investment Advisor" width="800" />
</p>

> [!WARNING]
> **非投資建議。接上有資金的券商帳戶，它會用真錢下單。** 只要設了真實券商憑證，軟體就會送出真實訂單。依「現狀」提供，不含任何保證，詳見 [LICENSE](../LICENSE) 與 [NOTICE](../NOTICE)。本專案的 `TRADING_MODE=paper` 不是模擬：eToro 的 token 沒有 demo 權限，所有券商呼叫都會以 `InsufficientPermissions` 失敗。安全的煞車是 `ai_trading_enabled=false` 與 `tradable_capital_pct=0`。接上有資金的帳戶之前，先讀過程式。

AI Investment Advisor 是自架的量化投資系統：多個 LLM agent 評估每一筆交易構想，由確定性的程式碼做決定，訂單可以送到 eToro 實盤帳戶。給想研究這類系統、願意自己承擔風險的開發者。

它能不能相對 SPY 賺到淨超額報酬，目前沒有證明。要看實際數字，查 `/api/v1/net-alpha` 和你自己的資料庫。

## 它做什麼

| 項目 | 做法 |
|:-----|:-----|
| 多 agent 辯論 | 一組 LLM agent 平行分析每檔標的，再由 CIO agent 裁決。名單定義在 [`config/workflows/single_ticker_council.yaml`](../config/workflows/single_ticker_council.yaml)。 |
| 評分 | 買進決策用加權組合評分，賣出另外評分。LLM 只能提案，決定由確定性的程式碼做。 |
| 市場狀態 | 三狀態隱馬可夫模型估計市場狀態，據此調整現金水位與目標 Beta。 |
| 尾部風險 | 用極值理論的 POT 與廣義 Pareto 分布外推 99.9% 的 VaR 與 CVaR。 |
| 風險引擎 | 波動度目標、相關性分群、機會成本門檻、分數 Kelly 部位，以及多因子 alpha 合成。 |
| 執行 | 對平均日成交量設流動性上限、隨機化 TWAP 與 VWAP 切單、實施落差歸因，以及線上校準 Almgren-Chriss 衝擊模型。 |
| 策略搜尋 | 在參數網格上做模擬退火，再用 walk-forward 做樣本外驗證。 |
| 影子帳本 | 獨立的紙上帳本記錄系統本來會怎麼做，拿來對照。 |
| 儀表板 | `/adaptive` 頁顯示五個維度的健康雷達，並標出每個數字的來源。缺資料就顯示缺資料。 |
| 安全 | 供應商金鑰用 Fernet 加密存放；追蹤資料經 OpenTelemetry 送到 SigNoz。 |

## 分層架構

### LLM 路由

呼叫分成四層：`nano`、`fast`、`smart`、`advanced`，由 `ResilientLLMPipeline` 解析。每一層背後用哪個模型，由設定頁的 tier 綁定決定，不寫在程式裡。

### 資料儲存

| 層級 | 引擎 | 用途 |
|:-----|:-----|:-----|
| Hot | Redis | 語意快取、速率限制、斷路器旗標 |
| Warm | PostgreSQL + pgvector | 交易紀錄、因子權重、向量 |
| Cold | 加密檔案、JSONL | 備份與 walk-forward 紀錄 |

## 技術棧

| 類別 | 技術 |
|:-----|:-----|
| 語言 | Python 3.10 與 3.11、TypeScript |
| 後端 | FastAPI、MCP、Celery Beat |
| 前端 | Next.js、React |
| AI | LiteLLM，模型由 tier 綁定決定 |
| 資料庫 | PostgreSQL + pgvector、Redis |
| 基礎設施 | Docker Compose、Nginx、SigNoz、OpenTelemetry |
| 券商 | eToro API、Interactive Brokers |
| 數據源 | Polygon、Tiingo、Finnhub、AlphaVantage、FMP、FRED、Tavily |
| 通知 | Telegram、Slack、Email |

版本號看 `pyproject.toml`、`uv.lock` 和 `frontend/package.json`。

## 快速開始

前置需求：Docker 與 Compose v2，空出約 4 GB 記憶體。Python、Node.js 只有本地開發才需要。

1. **安裝。**

   ```bash
   git clone https://github.com/neohsiung/AI-Investment-Advisor.git
   cd AI-Investment-Advisor
   ./install.sh
   ```

   `install.sh` 會檢查前置需求、產生金鑰、建置容器、套用 migration、套用安全預設值（`ai_trading_enabled` 預設為 false），最後才啟動排程（Celery worker 與 beat）。同一台機器已有這個專案的另一套 stack（同 compose 專案名、同容器名，或正式環境）時，安裝會**拒絕**。名字由 `.env` 的 `ADVISOR_PROJECT_NAME`、`ADVISOR_CONTAINER_PREFIX` 決定。

2. **填金鑰。** 開 [設定頁](http://127.0.0.1:8088/settings)，填 LLM 提供者的金鑰（安裝時已輸入就不用），有的話一併填資料源金鑰。金鑰加密存在資料庫，不放 `.env`。沒有 LLM 金鑰就產不出報告。
3. **拿到第一份報告。** 排程在週一到週五美東 17:00 產生報告。想現在就要：

   ```bash
   ./start.sh report
   ```

   幾分鐘後到 [報告頁](http://127.0.0.1:8088/reports) 看。
4. **保持交易關閉。** 讀過程式碼、決定要交易之前，維持 `ai_trading_enabled=false`。真實下單還需要券商金鑰與 `etoro_mode=real`。

開發環境（熱重載，獨立的 compose 專案 `advisor_dev`）：`docker compose up -d`，不會動到單機 stack。

單機 stack 的入口：

| 服務 | 網址 |
|:-----|:-----|
| 閘道 nginx，僅生產環境 | [http://127.0.0.1:8088](http://127.0.0.1:8088) |
| Next.js 儀表板 | [http://localhost:3001](http://localhost:3001) |
| FastAPI 與 MCP Server | [http://localhost:8000](http://localhost:8000)，dev 為 8001 |
| SigNoz APM，要用 `OBSERVABILITY=1 ./start.sh up` 啟動才有 | [http://127.0.0.1:8080](http://127.0.0.1:8080) |

dev 環境的 nginx 沒有對外發佈埠口，請直接連上面的前端與 API 埠口。閘道只存在於生產環境。

自架與維運說明見[文件索引](../docs/README.md)。

## 專案結構

```
AI-Investment-Advisor/
├── .agent/              # Agent 治理層：規則、技能、工作流
├── alembic/             # 資料庫遷移
├── config/              # 模型路由、工作流、角色定義、mission.yaml
├── docs/                # 文件
├── frontend/            # Next.js 儀表板
├── infra/               # Nginx 反向代理、SigNoz 設定
├── prompts/             # Agent 系統提示
├── scripts/             # 維運腳本：DB 初始化、部署、健康檢查
├── services/            # 微服務入口
├── src/                 # 核心 Python 套件
├── tests/               # 單元、整合、不變量測試
├── workspace/           # 多 agent 工作區
└── AGENTS.md            # AI 編碼助手的共用上下文
```

## 參與貢獻

1. Fork 此專案。
2. 建立分支，名稱用 `feat/…`、`fix/…` 或 `docs/…`。
3. 執行測試：`pytest tests/ -x --tb=short`。
4. 提交變更並開 Pull Request。

大的變更請先開 Issue 討論。完整規則見 [CONTRIBUTING.md](../CONTRIBUTING.md)。

## 授權與免責聲明

- 維護者：Litov。問題與資安回報寄 support@litov.app，見 [SECURITY.md](../SECURITY.md)。支援頁：<https://support.litov.app/>。
- 授權：[Apache License 2.0](../LICENSE)
- 免責聲明：本軟體分析金融市場，設了真實券商憑證就可能以真錢下單。非投資建議，依「現狀」提供，不含任何保證。詳見 [NOTICE](../NOTICE)。

Apache License 2.0，版權屬 Litov and contributors。
