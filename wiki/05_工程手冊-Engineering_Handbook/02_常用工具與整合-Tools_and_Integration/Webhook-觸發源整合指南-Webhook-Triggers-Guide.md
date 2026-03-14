# 事件驅動 Webhook 觸發源整合指南 (Event-Driven Webhook Triggers Guide)

本指南推薦 15 個適用於「AI 投資顧問」的高價值、低成本甚至免費的 Webhook 觸發來源。這些觸發源直接作為系統被動接收 (Inbound) 事件的來源，大幅降低 API 輪詢成本，並提升 Agent 對市場劇變的即時反應能力。

所有 Webhook 目標端點皆應設為 `https://<YOUR_ADVISOR_DOMAIN>/webhook/{source_id}`，並於 Header 中加入 `X-API-Key: <YOUR_API_KEY>`。

> [!IMPORTANT]
> **全域優先級評估 (Universal Prioritization)**: 透過 Webhook 傳入的事件不再預設 Bypass，而是強制經由 **Sentinel Agent** 進行優先級判定 (P0-P5)。除非判定為 **P0 (Critical)**，否則將根據優先級套用動態緩衝，以確保評議會 (Council) 具備足夠上下文進行高品質決策。

---

## 🟢 一、市場行情與技術面觸發 (Market & Technicals)

### 1. TradingView (首選技術面觸發)
- **價值**: 100% 自訂技術指標、趨勢線突破警報。將技術分析判斷外包給 TradingView 引擎，Agent 僅負責接手基本面決策。
- **設定**: 
  1. 建立警報 (Alert) 並勾選 Webhook URL。
  2. URL 填寫：`https://.../webhook/tradingview` (並於 Header 加入 `X-API-Key`)
  3. 訊息設定 (JSON)：`{"ticker": "{{ticker}}", "price": "{{close}}", "event": "MACD_Cross"}`

### 2. Polygon.io WebSocket (秒級即時行情)
- **價值**: 接收交易所即時逐筆成交 (Trades)、報價 (Quotes) 與 K 線 (Aggregates)。
- **設定**: 無須在 Dashboard 設定 Webhook，直接在系統設定中填入 `POLYGON_API_KEY`，系統會自動透過 `PolygonStreamClient` 建立 WebSocket 連線。

### 3. Alpaca Events (Trade Updates)
- **價值**: 接收實盤訂單成交狀態 (Fills, Rejects)，以觸發 Agent 進行資產重新平衡 (Rebalancing)。
- **設定**: Alpaca API -> Event Streams -> 綁定 Webhook。

### 4. TrendSpider
- **價值**: 基於 AI 的圖表型態辨識 (如頭肩頂、楔形突破) 警報。
- **設定**: 建立 Bot -> 新增 Webhook Action -> 映射對應 ticker。

---

## 🟡 二、新聞、情感與另類數據 (News & Sentiments)

### 5. Zapier - EDGAR SEC RSS (10-K / 10-Q)
- **價值**: 第一時間攔截上市公司的財報與重大事項提交。
- **設定**: Zapier 中選擇 RSS App -> 訂閱 SEC EDGAR Feed -> Action 選擇 Webhook POST 到 Advisor 系統。

### 6. Finnhub Earnings Surprises
- **價值**: 在財報公佈瞬間推送 EPS 與預期落差 (Surprise %)，直接喚醒 Fundamental Agent。
- **設定**: Finnhub Dashboard -> Webhooks -> 啟用 Earnings 事件。

### 7. Make.com - X (Twitter) 關鍵意見領袖
- **價值**: 監控 Jerome Powell (FED)、Elon Musk 等關鍵人物的推文過濾。
- **設定**: Make.com -> 綁定 X 帳號 -> 設定過濾器 (Filter) -> HTTP Request POST 至 Advisor。

### 8. Make.com - Reddit r/wallstreetbets
- **價值**: 爆紅迷因股 (Meme stocks) 的早期偵測與交易量預警。
- **設定**: Reddit API 監控新熱門貼文 -> 萃取 Ticker -> 送出 Webhook。

### 9. LunarCrush (加密貨幣專用)
- **價值**: 幣圈特有的社交聲量 (Social Volume) 暴增警報。
- **設定**: LunarCrush API -> Alerts -> Webhook Delivery。

### 10. Investing.com RSS (總經指標)
- **價值**: CPI、非農就業、FOMC 利率決策公佈後的第一時間快報。
- **設定**: 訂閱 Investing.com 的事件日曆 RSS (`https://www.investing.com/rss/news.rss`) -> Webhook POST 至 Advisor。注意需配置模擬瀏覽器的 User-Agent 以避免 403。

---

## 🟣 三、維運、系統與業務觸發 (Ops & Business)

### 11. GitHub Webhooks (Vibe Coding Trigger)
- **價值**: 監控策略代碼庫的 Push 或 Issue 建立，喚醒 Engineer Agent 處理 Bug。
- **設定**: GitHub Repo -> Settings -> Webhooks -> Payload URL (`/callback/github`)。

### 12. Sentry (系統異常攔截)
- **價值**: 當 Market Data API (如 FMP) 服務異常，觸發 Advisor 自動切換備援 (Fallback) 數據源。
- **設定**: Sentry Project -> Alerts -> Webhook Integration。

### 13. Typeform (投資人 KYC 與建檔)
- **價值**: 客戶填寫風險偏好問卷後，立刻觸發 Agent 建立客製化投資組合提案。
- **設定**: Typeform Dashboard -> Connect -> Webhooks。

### 14. Stripe (SaaS 訂閱與開通)
- **價值**: 客戶付費訂閱 AI 顧問服務後，立即初始化專屬的資料庫分區並觸發歡迎訊息。
- **設定**: Stripe Dashboard -> Developers -> Webhooks -> 監聽 `checkout.session.completed`。

### 15. IFTTT (券商報告轉發)
- **價值**: 將舊式券商 (無法提供 API) 發送的 PDF 研究報告 Email 自動轉發給 Advisor 進行 RAG 讀取。
- **設定**: IFTTT -> If Email received from (Broker) -> Make a web request (Webhook)。

---

## 🔵 四、免費自動化方案 (Free Automation Solutions)

### 16. n8n (首選開源方案 - Recommended)
- **價值**: 完全免費且可自主託管。支援抓取新聞、RSS、Email 並進行邏輯過濾。
- **URL**: `https://<你的域名>/webhook/n8n`
- **範本特性**: 
  - **Scalable RSS Polling**: 使用 `/webhook/rss-sources` 分離「來源配置」與「抓取邏輯」。n8n 動態獲取 30+ 來源併發處理，極易擴充。
  - **Robust XML Parsing**: 內建「Sanitize XML」節點自動修復非法 & 符號（如 S&P 500），確保解析不中斷。
  - **Auto Normalization**: 「Iterate Items」節點自動扁平化 RSS (item) 與 Atom (entry) 結構，解決 n8n 表達式中的 `$` 語法衝突。
  - **SEC Edgar (10-K)**: 使用 Atom 協定，內建 `Investment Advisor admin@gmail.com` 標準 UA 以符合 SEC 爬蟲規範。
  - **Econ Calendar**: 採用 Investing.com RSS，並配置 Chrome 122+ 模擬 Header。
- **設定步驟**:
  1. 在 n8n 中導入最新的 `n8n_workflow_template.json`。
  2. 確保 `Fetch RSS Sources` 節點指向 `http://investment_advisor_mcp:8000/webhook/rss-sources`。
  3. 配置 `X-API-Key` Header 進行安全驗證。

### 17. Make.com (原 Integromat)
- **價值**: 月額度高 (1,000 次)，適合複雜邏輯。
- **URL**: `https://<你的域名>/webhook/make`

### 18. Pipedream / IFTTT
- **價值**: 適合簡單的新聞轉發。
- **URL**: `/webhook/pipedream` 或 `/webhook/ifttt`
