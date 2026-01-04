# 外部服務問題與解決方案 (External Service Issues & Solutions)

本文檔記錄了在開發與測試過程中遇到的外部服務不穩定問題，並提出建議的解決方案。

## 1. 網路搜尋 (Internet Search)

### 問題描述 (Issue)
- **錯誤訊息**: `RuntimeError: error sending request ... operation timed out`
- **發生頻率**: 高 (High)
- **原因**: 目前使用的 `duckduckgo_search` 套件是透過爬蟲方式模擬瀏覽器請求，容易受到 DuckDuckGo 的 Rate Limiting (速率限制) 或 IP 封鎖，導致回應超時或連線失敗，特別是在連續大量查詢時。

### 建議解決方案 (Proposed Solution)

#### A. Tavily API (推薦)
- **優點**: 專為 AI Agents 設計的搜尋 API，回應速度快，內建過濾與摘要功能，穩定性極高。
- **成本**: 提供免費額度 (每月 1000 次)，付費方案合理。
- **整合方式**: 建立 `TavilySearchService` 替換 `InternetSearchService`。

#### B. SerpApi / Google Custom Search
- **優點**: 直接獲取 Google 搜尋結果，資料準確。
- **缺點**: SerpApi 成本較高；Google Custom Search 設定繁瑣且配額有限。

#### C. 增加重試機制 (已實作 Temporary Fix)
- 目前已在 `InternetSearchService` 中加入 Retry (重試) 與 Backoff (延遲) 機制，並捕捉 Timeout 錯誤，避免單次失敗導致程式崩潰，但無法根本解決被封鎖的問題。

---

## 2. 市場數據 (Market Data)

### 問題描述 (Issue)
- **錯誤訊息**: `YFinance fetch_news error: 'NoneType' object has no attribute 'get'` / 不穩定的數據格式。
- **發生頻率**: 中 (Medium)
- **原因**: `yfinance` 是非官方的 Yahoo Finance 爬蟲套件。Yahoo Finance 的網頁與 API 結構經常變動，導致解析邏輯失效。
- **現狀**: 系統日誌顯示 `POLYGON_API_KEY not found` 與 `FMP_API_KEY not found`，因此系統自動降級 (Fallback) 使用 `yfinance`，導致穩定性不足。

### 建議解決方案 (Proposed Solution)

#### A. 使用官方付費 API (強烈推薦)
- **Financial Modeling Prep (FMP)**: 提供穩定的基本面數據與新聞，價格親民。
- **Polygon.io**: 股票報價與技術指標的首選，極度穩定。
- **行動**: 請在 `.env` 或資料庫設定中填入有效的 `FMP_API_KEY` 與 `POLYGON_API_KEY`。

#### B. 強化 YFinance 解析 (已實作 Temporary Fix)
- 目前已修正 `YFinanceProvider` 中的 `fetch_news` 方法，加入 Null Check (空值檢查) 以防止程式崩潰，但若 Yahoo 結構大幅改變，仍需手動維護。

---

## 3. LLM 框架 (DSPy)

### 問題描述 (Issue)
- **錯誤訊息**: `Failed to configure DSPy: module 'dspy' has no attribute 'OpenAI'`
- **原因**: `dspy` 套件版本更新頻繁且 API 變動大，當前環境安裝版本與程式碼預期不符。
- **解決方案**:
    - **短期**: 在 `AgentFactory` 加入強健的檢查邏輯 (`try-except` 與 `hasattr` )，確保若 DSPy 初始化失敗，不會影響其他 Agent 的運作。
    - **長期**: 鎖定 `requirements.txt` 中的 `dspy` 版本，或更新程式碼以適配最新版 API。

