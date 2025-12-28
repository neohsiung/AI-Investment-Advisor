# 使用手冊 (User Guide)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 使用者操作指南 (User Guide)

### 目標 (Goal)
引導使用者熟悉 AI 投資顧問儀表板的操作，從數據輸入到解讀 AI 分析報告，發揮系統最大價值。

### 為什麼 (Why)
- **降低學習門檻**: 系統功能繁多 (手動交易、CSV 匯入、報告設定)，需提供清晰指引。
- **避免操作錯誤**: 錯誤的數據輸入 (如買賣方向相反) 會導致分析結果嚴重失真。

### 做了什麼 (What)
本指南涵蓋三大核心功能模組：
1.  **總覽 (Dashboard Overview)**: 即時監控資產狀況。
2.  **數據管理 (Data Management)**: 記錄交易與維護資產。
3.  **設定與報告 (Settings & Reports)**: 調整 AI 參數與查看分析建議。

### 如何進行 (How)

#### 1. 總覽 (Overview)
登入後首頁即為總覽。
- **KPIs**: 關注 NLV (淨值)、Cash (現金) 與 Risk (槓桿比率)。
    - *Tips*: 若槓桿比率 > 1.5x，系統會顯示黃色警告；> 2.0x 顯示紅色危險。
- **資產配置**: 圓餅圖顯示各持倉佔比。
- **權益曲線**: 觀察資產隨時間的增長趨勢。

#### 2. 數據管理 (Data Management)
前往側邊欄的 **Data Management** 頁面。

- **匯入交易 (Import)**:
    - 支援 **Robinhood** / **IBKR** 的 CSV 匯出檔。
    - **簡易格式 (Simple)**: 選擇此選項後，可直接點擊 **「📥 下載匯入範本」** 按鈕取得標準 CSV 檔 (含範例資料)。
    - **備註欄位 (Note)**: 範本中包含 `note` 欄位供您填寫備註 (如交易策略或說明)，系統匯入時會自動忽略此欄位，不影響資料庫。
    - 上傳後系統自動去重並解析。
- **手動輸入 (Manual Entry)**:
    - 適用於零星交易或股息 (Dividend) 紀錄。
    - 必填：Ticker, Action (BUY/SELL), Quantity, Price。
- **資金管理 (Cash Management)**:
    - 紀錄入金 (Deposit) 與出金 (Withdraw) 以正確計算投資報酬率 (ROI)。
    - **操作**: 前往「手動輸入」分頁。
        - **Ticker**: 建議輸入 `USD` 或 `CASH` (系統無硬性限制，但統一代號方便管理)。
        - **Action**: 選擇 `DEPOSIT` (入金) 或 `WITHDRAW` (出金)。
        - **Quantity**: 輸入金額 (如 10000)。
        - **Price**: 輸入 `1`。
- **股息處理 (Dividend Handling)**:
    - **現金股息 (Cash Dividend)**: Action 設為 `DIVIDEND`，Quantity 設為總金額 (例如 50)，Price 設為 `1`。系統會增加您的現金餘額。
    - **股票股息 (Stock Dividend)**: Action 設為 `BUY`，Quantity 設為獲得股數 (例如 5)，Price 設為 `0` (或稅務成本)。系統會增加持倉數量並稀釋平均成本。
- **刪除/修正**: 可在「交易紀錄」Tab 刪除錯誤的條目。
- **槓桿/融資交易 (Margin Trading)**:
    - 系統會自動計算槓桿水位。
    - **操作**: 正常輸入 `BUY` 交易即可。當購買總額超過您的現金餘額時，現金會呈現負值 (代表融資欠款)，系統將自動更新槓桿比率 (Leverage Ratio)。
    - **不需要**額外紀錄融資借款動作。
    - **範例 (Example)**:
        - 假設您有 \$100 本金 (Deposit \$100)，想開 5 倍槓桿買入股票。
        - **步驟**: 直接紀錄 `BUY` 5 股，單價 \$100 (總值 \$500)。
        - **結果**:
            - 資產市值 (Market Value): \$500
            - 現金餘額 (Cash): \$100 - \$500 = **-\$400** (此即為融資金額)
            - 淨值 (Equity): \$500 + (-\$400) = \$100
            - 槓桿比率: \$500 / \$100 = **5.0x**

#### 2.4 顧問聊天室 (Advisor Chat)
- **功能**: 直接與 AI 投資顧問對話。
- **用法**:
    - 輸入問題，例如：「AAPL 最近技術面如何？」或「美股大盤現在安全嗎？」。
    - 系統會自動判斷並調用相應的專家 (動能、基本面、總經) 進行分析。

#### 2.5 系統設定 (System Settings)
- **API 設定**:
    - **模型分級 (Model Tiering)**: 您可以分別設定 `Smart Model` (用於深度分析) 與 `Fast Model` (用於快速篩選)。
    - **時區設定 (Timezone)**: 設定您偏好的 **顯示時區** (如 Asia/Taipei 或 US/Eastern)，這將影響所有報告與介面的時間顯示。預設為 Asia/Taipei。
- **排程設定**: 設定每日掃描與報告的時間。
- **報告試跑**: 手動觸發每週報告生成流程 (不發送郵件)。

#### 3. 設定與報告 (Settings & Reports)
- **AI 設定**:
    - 可切換模型 (e.g., Gemini-1.5-pro vs OpenRouter)。
    - 設定排程時間 (Daily/Weekly Check)。
- **查看報告**:
    - 每週排程結束後，報告會存入資料庫並發送 Email。
    - 可在 **Reports** 頁面回顧歷史報告。

### 4. 投資決策工作流 (Investment Decision Workflow)
本系統採用多階段的專業分工模式，模擬真實對沖基金的運作流程：

1.  **全局戰略 (Global Strategy)**:
    - 結合總體經濟 (Macro) 與您目前的持倉板塊分佈，決定本週的進攻方向 (Target Sectors)。
2.  **候選篩選 (Candidate Screening)**:
    - 基於戰略方向，初步篩選出 15 檔具備潛力的個股 (嚴格排除 ETF，專注於尋找 Alpha)。
3.  **深度研究 (Deep Research)**:
    - 對現有持倉 + 篩選出的候選股進行全面掃描。
    - **動能專家 (Momentum)**: 檢查技術面趨勢與支撐壓力。
    - **基本面專家 (Fundamental)**: 檢查財報數據與新聞情緒。
4.  **最終決策 (Final Decision)**:
    - 投資長 (CIO) 綜合所有研究報告，挑選 **Top 3-5** 精選標的，並生成最終的投資建議報告。

### 5. 常見問題 (FAQ)
- **Q: 為什麼我的損益顯示為 0？**
    - A: 請確認是否有正確輸入「買入」交易。若只有賣出或股息，無法計算成本基礎。
- **Q: AI 建議的股票去哪了？**
    - A: AI 建議會顯示在每週的 Email 報告與 Reports 頁面中，不會自動下單。

---

<a id="en"></a>

## 🇺🇸 User Guide

### Goal
Guide users to familiarize themselves with the AI Investment Advisor Dashboard, from data entry to interpreting AI analysis reports, maximizing system value.

### Key Sections
1.  **Dashboard Overview**: Real-time asset monitoring.
2.  **Data Management**: Transaction recording and asset maintenance.
3.  **Settings & Reports**: Adjusting AI parameters and viewing analysis.

### How-To Instructions

#### 1. Dashboard Overview
The homepage after login.
- **KPIs**: Monitor **NLV** (Net Liquidation Value), **Cash**, and **Risk** (Leverage Ratio).
    - *Tip*: Risk > 1.5x shows yellow warning; > 2.0x shows red danger.
- **Allocation**: Pie chart of current holdings.
- **Equity Curve**: Asset growth trend over time.

#### 2. Data Management
Navigate to **Data Management** in the sidebar.
- **Import**: Supports Robinhood / IBKR CSV files.
- **Manual Entry**: For manual trades or dividends. Requires Ticker, Action (BUY/SELL), Quantity, Price.
- **Cash Management**:
    - Record **DEPOSIT** or **WITHDRAW** to ensure accurate ROI.
    - Use Ticker `USD` or `CASH`, Quantiy `Amount`, Price `1`.
- **Margin Trading**:
    - Simply record `BUY` trades. If total cost > cash balance, cash becomes negative (representing margin loan). Leverage ratio updates automatically.

#### 3. Advisor Chat
- **Function**: Talk directly to the AI Advisor.
- **Usage**: Type questions like "How is AAPL's technicals?" or "Is the market safe?". The system routes it to the relevant expert (Momentum, Macro, etc.).

#### 4. System Settings
- **AI Configuration**:
    - **Model Tiering**: Configure `Smart Model` (Deep Analysis) vs `Fast Model` (Quick Screening).
    - **Timezone**: Set your preferred **Display Timezone** (e.g., Asia/Taipei or US/Eastern) for all reports and UI timestamps. Default is Asia/Taipei.
- **Schedule**: Set Daily/Weekly run times.
- **Dry Run**: Manually trigger a report generation (no email).

#### 5. Reports
- View historical weekly reports in the **Reports** page.
- AI suggestions are for reference only.
