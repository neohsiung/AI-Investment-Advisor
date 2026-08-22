# AI Investment Advisor

> 🧠 自主量化投資平台 — 7 智能體集群碎形辯論、三層 LLM 路由、自動化 eToro 交易。

<p align="center">
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/stargazers"><img src="https://img.shields.io/github/stars/neohsiung/AI-Investment-Advisor?style=social" alt="Stars"></a>
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
  <img src="../assets/hero.png" alt="AI Investment Advisor — 7-Agent Swarm 自主量化投資平台" width="800" />
</p>

---

> [!WARNING]
> **非投資建議，真金交易風險自負。** 本軟體為自主交易系統，若配置真實券商憑證將以真實資金下單。依「現狀」提供，不含任何保證（詳見 [LICENSE](../LICENSE) / [NOTICE](../NOTICE)）。請務必先以 paper/demo 模式運行並理解程式邏輯後，再連接有實際資金的券商帳戶。

## 📌 這是什麼？

**你的投資組合有多久沒被重新審視了？**

AI Investment Advisor 模仿頂級對沖基金的決策架構。一位 **CIO Agent（首席投資官）** 將投資問題拆解，分派給 **7 位專業子智能體**，透過獨創的 **碎形辯論 (Fractal Debate)** 演算法消除模型幻覺，並產出可執行的投資組合決策 — 全程自動透過 eToro API 執行交易。

> **消除幻覺的辯論 > 單一模型的猜測。**

---

## ✨ 核心功能

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🧬 碎形辯論</h3>
      <p>多智能體對抗式推理，消除單一模型幻覺，提升決策可解釋性。</p>
    </td>
    <td width="50%" valign="top">
      <h3>🦅 10D 哨兵雷達</h3>
      <p>VIX、價格、新聞、宏觀經濟、配置漂移 — 自主全維度風險監控。</p>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>⚡ 自動對沖</h3>
      <p>毫秒級精度的倉位清算，透過 eToro API 全自動執行。</p>
    </td>
    <td width="50%" valign="top">
      <h3>🧠 OpenClaw 架構</h3>
      <p>每位 Agent 具備獨立的 WAL（預寫日誌），防止上下文溢出遺忘。</p>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>📊 混合 RAG 檢索</h3>
      <p>BM25 + 時間衰減語義搜索，基於 pgvector + Redis 實現。</p>
    </td>
    <td width="50%" valign="top">
      <h3>🔐 Fernet 加密</h3>
      <p>所有 API 金鑰以 <code>LLMCredentialCipher</code> 加密存儲。</p>
    </td>
  </tr>
</table>

---

## 📐 分層架構

### 三層 AI 路由

| 層級 | 用途 | 模型範例 |
|:-----|:-----|:---------|
| **Advanced 🚀** | 深度分析、CIO 決策 | GPT-4o, Claude 3.5 Sonnet |
| **Smart 🧠** | 辯論、推理、分類 | Gemini 1.5 Pro |
| **Fast ⚡** | 格式化、篩選、萃取 | GPT-4o-mini, Ollama 本地 |

### 三層資料存儲

| 層級 | 引擎 | 用途 |
|:-----|:-----|:-----|
| **Hot 🔥** | Redis | 語義緩存、即時狀態 |
| **Warm ☀️** | PostgreSQL + pgvector | 結構化紀錄、向量搜索 |
| **Cold ❄️** | 檔案系統 | 原始報告、歷史回測 |

---

## 🛠️ 技術棧

| 類別 | 技術 |
|:-----|:-----|
| **語言** | Python 3.11, TypeScript |
| **後端** | FastAPI, MCP (Model Context Protocol), Celery |
| **前端** | Next.js 15 (App Router), Streamlit (舊版) |
| **AI/ML** | LiteLLM, DSPy, OpenAI / Gemini / Claude / Ollama 多模型 |
| **資料庫** | PostgreSQL 16 + pgvector, Redis, SQLite (開發) |
| **基礎設施** | Docker Compose, Nginx, SigNoz, OpenTelemetry 1.39 |
| **交易** | eToro API（自動化碎股交易） |
| **數據源** | Polygon, Tiingo, Finnhub, AlphaVantage, FMP, FRED, TAVILY |
| **通知** | Telegram, LINE, Email (SMTP) |

---

## 🚀 快速開始

### 前置需求

- Docker & Docker Compose
- Python 3.10+（本地開發）
- Node.js 20+（前端開發）

### 啟動

```bash
# 1. 複製並設定
git clone https://github.com/neohsiung/AI-Investment-Advisor.git
cd AI-Investment-Advisor
cp .env.example .env
# 編輯 .env — 設定 APP_SECRET_KEY 和 LLM_CREDENTIAL_KEY

# 2. 一鍵啟動所有服務
./start.sh
```

| 服務 | 網址 |
|:-----|:-----|
| 閘道 (nginx，僅生產環境) | [http://127.0.0.1:8088](http://127.0.0.1:8088) |
| Next.js 儀表板 | [http://localhost:3001](http://localhost:3001) |
| FastAPI / MCP Server | [http://localhost:8000](http://localhost:8000)（dev 為 8001）|
| SigNoz APM | [http://127.0.0.1:8080](http://127.0.0.1:8080) |

> dev 環境的 nginx 沒有對外發佈埠口，請直接連上方的前端與 API 埠口；
> 閘道只存在於生產環境。

---

## 📁 專案結構

```
AI-Investment-Advisor/
├── .agent/              # Agent 治理層（規則、技能、工作流）
├── alembic/             # 資料庫遷移（PostgreSQL）
├── config/              # 模型路由、LLM 種子數據、角色定義
├── frontend/            # Next.js 15 儀表板（TypeScript）
├── infra/               # Nginx 反向代理、SigNoz 觀測配置
├── prompts/             # Agent 系統提示（CIO、Sentinel、子智能體）
├── scripts/             # 維運：DB 初始化、部署、健康檢查
├── services/            # 微服務入口
│   ├── mcp_server/      #   FastAPI + MCP 伺服器（主後端）
│   ├── notification/    #   Telegram / LINE / Email 服務
│   └── scheduler/       #   Celery Beat 排程器
├── src/                 # 核心 Python 套件
│   ├── agents/          #   Agent 定義 + 技能（eToro 交易、研究）
│   ├── services/        #   業務邏輯服務
│   └── workflow/        #   日/週工作流編排器
├── tests/               # 單元、整合、端到端測試
├── workspace/           # 多智能體工作區（WAL、身份、記憶）
└── AGENTS.md            # AI 編碼助手統一上下文
```

---

## 🤝 參與貢獻

歡迎貢獻！以下是參與方式：

1. Fork 此專案
2. 建立功能分支 (`git checkout -b feature/my-feature`)
3. 執行測試 (`pytest tests/ -x --tb=short`)
4. 提交變更並開啟 Pull Request

重大變更請先開 Issue 討論方案。

---

## 📄 授權與免責聲明

- **授權**: [Apache License 2.0](../LICENSE)
- **免責聲明**: 本軟體可自主分析市場，若配置真實券商憑證可能以真實資金下單。非投資建議，依「現狀」提供不含任何保證。詳見 [NOTICE](../NOTICE)。

---

<p align="center">Built with ❤️ for Modern Quantitative Investing</p>
