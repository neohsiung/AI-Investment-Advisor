# 第三方服務設定 (3rd Party Services Setup)

> **[⬅️ Back to Developer Guide](README.md)**

本文件詳細說明如何申請與設定系統所需的外部服務 API (Polygon, FMP, FRED, Gemini)。
This document details how to apply for and configure external service APIs (Polygon, FMP, FRED, Gemini) required by the system.

## 1. 核心數據源 (Core Data Sources)

### 1.1 Polygon.io (Price Data)
*   **用途 (Usage)**: 主要股價數據源 (Primary Price Data Source) - WebSocket & HTTP.
*   **網址 (URL)**: [https://polygon.io/](https://polygon.io/)
*   **方案建議 (Recommendation)**:
    *   **Starter ($29/mo)**: 適合開發測試 (延遲 15 分鐘)。Suitable for dev/test (15 min delay).
    *   **Developer ($200/mo)**: 若需即時數據 (Real-time) 則需升級此方案。Required for Real-time data.
*   **申請步驟 (Application Steps)**:
    1. 註冊帳號 (Sign up).
    2. 至 Dashboard 獲取 API Key (Get API Key from Dashboard).
    3. 設定環境變數 (Set Env Var): `POLYGON_API_KEY`.

### 1.2 Financial Modeling Prep (FMP) (News & Fundamentals)
*   **用途 (Usage)**: 財報數據 (Financials), 新聞 (Stock News). 亦作為股價備援。
*   **網址 (URL)**: [https://site.financialmodelingprep.com/](https://site.financialmodelingprep.com/)
*   **方案建議 (Recommendation)**:
    *   **Starter ($19/mo)**: 足夠大部分財報與新聞需求。Sufficient for most financials & news needs.
*   **申請步驟 (Application Steps)**:
    1. 註冊帳號 (Sign up).
    2. 至 Dashboard 獲取 API Key (Get API Key from Dashboard).
    3. 設定環境變數 (Set Env Var): `FMP_API_KEY`.

### 1.4 Tavily (Search Service)
*   **用途 (Usage)**: 主要網路搜尋服務 (Primary Search Service)。
*   **網址 (URL)**: [https://tavily.com/](https://tavily.com/)
*   **方案建議 (Recommendation)**:
    *   **Free**: 每月 1000 次請求。1000 requests/mo.
*   **申請步驟 (Application Steps)**:
    1. 註冊帳號 (Sign up).
    2. 獲取 API Key.
    3. 設定環境變數 (Set Env Var): `TAVILY_API_KEY`.

## 2. 數據源策略 (Data Source Strategy)
為了確保系統穩定性與成本效益，每種資訊目標皆配置 **主要 (Primary)** 與 **備援 (Backup)** 數據源。

To ensure system stability and cost-efficiency, each information goal is assigned a **Primary** and a **Backup** source.

| 資訊目標 (Info Goal) | 主要來源 (Primary) | 備援來源 (Backup) | 考量 (Considerations) |
| :--- | :--- | :--- | :--- |
| **股價 (Price)** | **Polygon.io** (Paid) | **FMP / YF** | Polygon 延遲低且穩定；FMP/YFinance 作為備案。 |
| **搜尋 (Search)** | **Tavily** | **DuckDuckGo** | Tavily 提供結構化結果；DDG 作為無金鑰備援。 |
| **新聞 (News)** | **FMP** (Paid) | **Google/YF** | FMP 專注財經新聞。 |
| **總經 (Macro)** | **FRED** | **YFinance** | FRED 為官方數據源。 |

## 3. AI 模型與通訊相關 (AI & Communication)

### 3.1 Google Gemini / OpenRouter API
*   **用途 (Usage)**: 核心推理引擎 (Reasoning Engine)。
*   **設定環境變數**: `GOOGLE_API_KEY` 或 `OPENROUTER_API_KEY`.

### 3.2 MCP (Model Context Protocol)
*   **用途 (Usage)**: 提供微服務化的工具註冊與 Agent 間通訊 (Agent Mesh)。
*   **服務位址**: `MCP_SERVER_URL` (預設 http://mcp_server:8000)。

## 3. AI 模型服務 (AI Models)

### 2.1 Google Gemini API
*   **用途 (Usage)**: 長文本分析 (Stock Analysis), 語意理解 (Semantic Understanding)。
*   **網址 (URL)**: [https://aistudio.google.com/](https://aistudio.google.com/)
*   **方案 (Plan)**:
    *   **Free Service**: 適合開發測試 (有 Rate Limit)。Suitable for dev/test (Rate limited).
    *   **Pay-as-you-go**: 實際上線建議使用 (Gemini 1.5 Flash 極度便宜)。Recommended for production (Gemini 1.5 Flash is extremely cheap).
*   **申請步驟 (Application Steps)**:
    1. 在 Google AI Studio 建立專案 (Create project in Google AI Studio).
    2. 產生 API Key (Generate API Key).
    3. 設定環境變數 (Set Env Var): `GOOGLE_API_KEY`.

### 2.2 OpenAI API (備援 Backup)
*   **用途 (Usage)**: 當 Gemini 不可用時的備援 (Fallback when Gemini is unavailable)。
*   **網址 (URL)**: [https://platform.openai.com/](https://platform.openai.com/)
*   **申請步驟 (Application Steps)**:
    1. 註冊並綁定信用卡 (Sign up & Link Credit Card).
    2. 產生 API Key (Generate API Key).
    3. 設定環境變數 (Set Env Var): `OPENAI_API_KEY`.
## 4. AI 設定比較 (Configuration Strategy)

本系統採 **DB-First** 策略：
1.  **環境變數 (.env)**: 僅用於初始化 (Bootstrap) 或當作預設值 (Setup Default)。
2.  **系統設定 (GUI/DB)**: 運行期間優先使用資料庫中的設定。請透過 Web UI (`05_Settings`) 進行即時調整。

Environmental variables are mainly for bootstrapping. Runtime configuration is managed via the Web UI (`05_Settings`) and stored in the database.

## 3. 環境變數設定範例 (.env Example)

```bash
# SMTP Configuration (Required for Email Reports)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
EMAIL_RECIPIENT=recipient@example.com

# External Data APIs
POLYGON_API_KEY=your_polygon_api_key
FMP_API_KEY=your_fmp_api_key
FRED_API_KEY=your_fred_api_key_here

# AI Models (Unified)
# API_KEY=your_ai_api_key (Used for both Gemini & Factory Fallback)
# LLM_API_KEY=your_llm_api_key (Optional: Only if different from API_KEY)

# Search Service (Tavily Recommended)
TAVILY_API_KEY=your_tavily_api_key


# Google OAuth (Optional, for Web App)
# GOOGLE_CLIENT_SECRET_PATH=client_secret.json
# COOKIE_KEY=your_secret_cookie_key
# REDIRECT_URI=http://localhost:8501

```

## 4. 搜索服務 (Search Services)

### DuckDuckGo 替代方案
- **Tavily**: 一個專為開發者設計的搜索 API，提供乾淨的 JSON 結果，支援快速搜尋與過濾，免費層有每日 1000 次請求，付費層可提升配額與可靠性。
- **SerpAPI**: 支援 Google、Bing、Yahoo 等多種搜索引擎，返回結構化結果，適合需要高可靠性的商業應用（付費）。
- **Google Custom Search JSON API**: 官方 Google API，可靠但有每日 100 次免費配額，需設定搜尋引擎 ID。
- **Bing Web Search API (Azure Cognitive Services)**: 微軟提供的搜索服務，免費層每月 1000 次請求，支援 JSON 結構化回應。

這些服務相較於 DuckDuckGo 的非官方 HTML 抓取，提供更穩定的 API、速率限制管理以及結構化回應，減少超時與解析錯誤的風險。建議在 `src/services/search_service.py` 中將 `InternetSearchService` 換成上述任一服務的客戶端實作，並在環境變數中設定相應的 API 金鑰，例如 `TAVILY_API_KEY`、`SERPAPI_KEY` 等。
