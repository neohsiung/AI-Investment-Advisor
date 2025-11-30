# AI 代理人集群規格 (AI Agent Swarm Specification)

本文件定義了組成「AI 投資決策委員會」的四位核心代理人及其協作模式。

## 1. 代理人架構 (Agent Architecture)

系統採用多代理人 (Multi-Agent) 架構，每個 Agent 擁有獨立的 System Prompt 與專屬工具。

### 1.1 角色定義

| 角色 | 代號 | 職責 | 關鍵指標/工具 |
| :--- | :--- | :--- | :--- |
| **Momentum Strategist** | `MOMENTUM` | 短期趨勢與技術分析 | RSI, MACD, MA, Vol (yfinance) |
| **Fundamental Analyst** | `FUNDAMENTAL` | 公司價值與財報分析 | Revenue, EPS, News (Alpha Vantage, Browser) |
| **Macro Economist** | `MACRO` | 總體經濟環境判斷 | Fed Rate, CPI, VIX (FRED API) |
| **Chief Investment Officer** | `CIO` | 最終決策與風險控管 | 整合上述報告, 槓桿水位 (Portfolio DB) |

## 2. 詳細規格

### 2.1 Momentum Agent
- **System Prompt**: `prompts/momentum_agent.txt`
- **輸入**: 股票代碼清單 (from DB/Watchlist)
- **分析邏輯**:
    - 計算 RSI(14): >70 超買, <30 超賣。
    - 判斷趨勢: Price > 20MA > 50MA (Bullish)。
- **輸出**: `signals/momentum_{date}.json` (包含 Signal: BUY/SELL/HOLD, Strength: 1-10)

### 2.2 Fundamental Agent
- **System Prompt**: `prompts/fundamental_agent.txt`
- **輸入**: 持倉前 5 大資產 + Watchlist
- **分析邏輯**:
    - 財報檢視: 營收與獲利成長 (YoY)。
    - 新聞摘要: 使用 Browser Tool 搜尋近期重大新聞。
- **輸出**: `reports/fundamental_{date}.md`

### 2.3 Macro Agent
- **System Prompt**: `prompts/macro_agent.txt`
- **輸入**: 無 (全市場通用)
- **分析邏輯**:
    - 殖利率曲線 (10Y-2Y) 是否倒掛?
    - VIX 是否過高 (>30)?
- **輸出**: `reports/macro_outlook_{date}.md` (Market Regime: Risk-On / Risk-Off)

### 2.4 CIO Agent
- **System Prompt**: `prompts/cio_agent.txt`
- **輸入**: Momentum Signals, Fundamental Report, Macro Outlook, Portfolio Leverage
- **決策邏輯**:
    - 若 Leverage > 2.0 -> 強制建議減碼 (Reduce)。
    - 若 Macro = Risk-Off -> 忽略 Momentum 的弱勢買訊。
    - 衝突解決: Fundamental (Long) vs Momentum (Short) -> 建議觀望或減碼。
- **輸出**: `Weekly_Advisory_{date}.md`

## 3. 工具整合 (Tool Integration)

### 3.1 外部 API
- **Alpha Vantage**: 用於獲取財報數據 (Fundamental)。
- **FRED (Federal Reserve Economic Data)**: 用於獲取總經數據 (Macro)。
- **yfinance**: 用於獲取歷史價格 (Momentum)。

### 3.2 內部工具
- **Database Access**: 讀取持倉與交易紀錄。
- **Browser Tool**: (模擬) 用於 RAG 新聞檢索。

## 4. 執行流程 (Workflow)
1. **Data Update**: 更新所有資產的最新價格 (Market Data)。
2. **Macro Analysis**: 執行 Macro Agent，產出市場定調。
3. **Asset Analysis**: 平行執行 Momentum 與 Fundamental Agent。
4. **Synthesis**: CIO Agent 讀取所有產出，生成最終週報。
