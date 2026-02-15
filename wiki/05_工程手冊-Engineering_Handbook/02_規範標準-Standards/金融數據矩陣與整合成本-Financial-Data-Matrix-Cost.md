# 金融數據矩陣與整合成本 (Financial Data Matrix & Cost Analysis)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v1.5 | 嚴謹執行「一來源一 Runbook」循環，補齊所有 15+ 項目 | Antigravity |
| 2026-02-15 | v1.4 | 增加全來源 Runbook 與配置管理指南 | Antigravity |

---

<a id="zh"></a>

## 🇹🇼 金融數據源陣列 (v3.8)

本文件為系統「外部感知層」的 SOP。我們拒絕任何非官方 (Hack) 方式，確保穩定性。

### 1. 核心矩陣 (Core Matrix)

| 優先序 | 來源 | 類別 | 方法 | 優點 | 性價比 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **P0** | **Fred** | 總經 | REST | 權威指標 | 極高 |
| **P0** | **Finnhub** | 情緒 | REST | 情感分析強 | 高 |
| **P0** | **FMP** | 財報 | REST | 財報數據準 | 高 |
| **P1** | **Futu** | 交易/行情 | Gateway | 即時、支援交易 | 高 |
| **P1** | **Polygon** | 行情 | REST | 即時、期權數據 | 中 |
| **P1** | **Twelve Data** | 綜合 | REST | 全球覆蓋 | 高 |
| **P1** | **Yahoo** | 行情 | Library | 免費、搜尋強 | 極高 |
| **P1** | **Alpaca** | 交易 | SDK | 零佣金 API | 中 |
| **P2** | **Alpha Vantage**| 指標 | REST | 總經+情緒 | 中 |
| **P2** | **Tiingo** | 新聞 | REST | 內容乾淨、標籤強 | 高 |
| **P2** | **NewsAPI** | 新聞 | REST | 全球來源廣 | 低 |
| **P2** | **CryptoPanic** | 加密情緒 | REST | 幣圈聚合 | 高 |
| **P2** | **Alternative.me**| 市場恐懼 | REST | 指標化避險 | 高 |
| **P2** | **Whale Alert** | 大額異動 | Webhook | 鏈上預警 | 低 |
| **P2** | **Glassnode** | 鏈上總經 | REST | 週期分析 | 中 |

---

### 2. 詳細 Runbooks (Individual SOPs)

依據「一項目一 Runbook」原則循環列出：

#### [01] FRED (Macro Data)
- **描述**: 美國聯準會官方數據。
- **註冊**: [FRED API Key](https://fred.stlouisfed.org/docs/api/api_key.html) 申請。
- **配置**: `FRED_API_KEY`
- **驗證**: `curl "https://api.stlouisfed.org/fred/series?series_id=UNRATE&api_key=$FRED_API_KEY&file_type=json"`
- **代碼用途**: 監控失業率與利率，切換宏觀風控模型。

#### [02] Finnhub (Sentiment Scan)
- **描述**: 提供 AI 驅動的情緒分數與基本面。
- **註冊**: [Finnhub Token](https://finnhub.io/) 獲取。
- **配置**: `FINNHUB_API_KEY`
- **驗證**: `curl "https://finnhub.io/api/v1/news-sentiment?symbol=AAPL&token=$FINNHUB_API_KEY"`
- **代碼用途**: Sentinel System 1 情感過濾。

#### [03] FMP (Fundamental Depth)
- **描述**: 高精度財報數據。
- **註冊**: [FMP API](https://site.financialmodelingprep.com/developer/docs/)。
- **配置**: `FMP_API_KEY`
- **驗證**: `curl "https://financialmodelingprep.com/api/v4/score?symbol=AAPL&apikey=$FMP_API_KEY"`
- **代碼用途**: Fundamental Swarm 進行估值建模。

#### [04] Futu OpenAPI (Execution & L2)
- **描述**: 即時報價與港美股交易。
- **註冊**: 需開通富途帳戶，啟動 [FutuOpenD](https://openapi.futunn.com/)。
- **配置**: `FUTU_OPEND_IP`, `FUTU_OPEND_PORT`
- **驗證**: 本地運行 `telnet 127.0.0.1 11111`。
- **代碼用途**: 實盤報價獲取與訂單執行。

#### [05] Polygon.io (Option & Tick)
- **描述**: 美股即時逐筆數據。
- **註冊**: [Polygon 註冊](https://polygon.io/)。
- **配置**: `POLYGON_API_KEY`
- **驗證**: `curl "https://api.polygon.io/v2/last/trade/AAPL?apiKey=$POLYGON_API_KEY"`
- **代碼用途**: 即時監控盤中異動。

#### [06] Twelve Data (Global Quotes)
- **描述**: 全球股票、外匯。
- **註冊**: [Twelve Data](https://twelvedata.com/)。
- **配置**: `TWELVEDATA_API_KEY`
- **驗證**: `curl "https://api.twelvedata.com/quote?symbol=AAPL&apikey=$TWELVEDATA_API_KEY"`
- **代碼用途**: 跨市場資產關聯分析。

#### [07] Yahoo Finance (Search & History)
- **描述**: 最易獲取的歷史數據源。
- **註冊**: **無須 Key**。
- **配置**: 安裝 `yfinance` 庫。
- **驗證**: `python3 -c "import yfinance; print(yfinance.Ticker('TSLA').history(period='1d'))"`
- **代碼用途**: 歷史回測數據填充。

#### [08] Alpaca Markets (Trading API)
- **描述**: 零佣金 API 交易平台。
- **註冊**: [Alpaca Dashboard](https://alpaca.markets/)。
- **配置**: `ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`
- **驗證**: 使用 Alpaca Python SDK 測試。
- **代碼用途**: 美股算法交易執行。

#### [09] Alpha Vantage (Indicators)
- **描述**: 經整理的技術、總經與情感指標。
- **註冊**: [Alpha Vantage Key](https://www.alphavantage.co/)。
- **配置**: `ALPHA_VANTAGE_API_KEY`
- **驗證**: `curl "https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers=AAPL&apikey=$ALPHA_VANTAGE_API_KEY"`
- **代碼用途**: 市場體制分類 (Regime Classification)。

#### [10] Tiingo (Filtered News)
- **描述**: 高質量標籤化新聞。
- **註冊**: [Tiingo Console](https://api.tiingo.com/)。
- **配置**: `TIINGO_API_KEY`
- **驗證**: `curl "https://api.tiingo.com/tiingo/news?tickers=aapl&token=$TIINGO_API_KEY"`
- **代碼用途**: 新聞噪音過濾。

#### [11] NewsAPI.org (Global Pulse)
- **描述**: 綜合新聞搜索。
- **註冊**: [NewsAPI](https://newsapi.org/)。
- **配置**: `NEWS_API_KEY`
- **驗證**: `curl "https://newsapi.org/v2/everything?q=fed&apiKey=$NEWS_API_KEY"`
- **代碼用途**: 廣度事件掃描。

#### [12] CryptoPanic (Crypto Intel)
- **描述**: 幣圈情感聚合。
- **註冊**: [CryptoPanic API](https://cryptopanic.com/about/api/)。
- **配置**: `CRYPTOPANIC_API_KEY`
- **驗證**: `curl "https://cryptopanic.com/api/v1/posts/?auth_token=$CRYPTOPANIC_API_KEY"`
- **代碼用途**: 加密貨幣情感監控。

#### [13] Alternative.me (Market Fear)
- **描述**: 恐懼與貪婪指數。
- **註冊**: **公開 API**。
- **配置**: 系統端點對接。
- **驗證**: `curl "https://api.alternative.me/fng/"`
- **代碼用途**: 風險權重 (Risk Weighting) 調整。

#### [14] Whale Alert (On-chain Alerts)
- **描述**: 追蹤大鯨魚轉帳。
- **註冊**: [Whale Alert API](https://whale-alert.io/)。
- **配置**: `WHALE_ALERT_API_KEY`
- **驗證**: `curl "https://api.whale-alert.io/v1/status?api_key=$WHALE_ALERT_API_KEY"`
- **代碼用途**: 偵測市場潛在賣壓。

#### [15] Glassnode (On-chain Macro)
- **描述**: 鏈上宏觀指標。
- **註冊**: [Glassnode Studio](https://studio.glassnode.com/)。
- **配置**: `GLASSNODE_API_KEY`
- **驗證**: `curl -X GET "https://api.glassnode.com/v1/metrics/market/price_usd?a=BTC&api_key=$GLASSNODE_API_KEY"`
- **代碼用途**: 長周期牛熊判斷。

---

### 3. 配置與管理 (Configuration Management)

- **.env**: 系統啟動時讀取的靜態金鑰配置。
- **DB Settings**: 透過系統 UI 可動態更新金鑰，優先於 `.env` 生效。
- **檢查機制**: 每月應手動執行一次 Runbook 中的「驗證」指令，確保金鑰未過期。

---

<a id="en"></a>

## 🇺🇸 Financial Data Matrix (v3.8)

### 1. Loop-based Runbooks
Every one of the 15+ sources now has a dedicated, standardized Runbook entry containing:
- **Description**: Technical role.
- **Registration**: Official URL.
- **Config**: Variable mapping.
- **Verification**: `curl` command.

### 2. Implementation
Follow the numbered list [01]-[15] to complete your setup.

## 🔗 Bidirectional Links
- **Technical Standards**: [External Event Integration Guide](./外部事件整合指南-External-Event-Integration)
- **Architecture**: [System Landscape](../../04_架構觀點-Architect_Views/系統全景圖-System-Landscape)
