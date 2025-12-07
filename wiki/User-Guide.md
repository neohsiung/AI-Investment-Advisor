# 使用者操作手冊 (User Guide)

> 返回 [[Home]]

## 儀表板功能 (Dashboard)

### 1. 總覽 (Overview)
- **KPIs**: 顯示淨清算價值 (NLV), 現金餘額, 槓桿比率與總 ROI。
- **資產配置**: 圓餅圖顯示各標的佔比。
- **持倉列表**: 即時計算每個持倉的現價、市值與未實現損益。

### 2. 績效追蹤 (Performance)
- **權益曲線 (Equity Curve)**: 追蹤每日資產淨值變化。
- **投入 vs 現值**: 比較總投入成本 (Invested Capital) 與當前市場價值。

### 3. 分析報告 (Reports)
- **歷史報告**: 下拉選單檢視過去的 AI 投資建議報告 (Markdown 格式)。
- **每週週報**: 系統每週六自動生成完整分析。

## 數據管理 (Data Management)

### CSV 匯入
1. 前往「Data Management」頁面。
2. 選擇 Broker (Robinhood, IBKR, Simple)。
3. 上傳 CSV 檔案。
4. 系統會自動解析並寫入資料庫，同時更新當日績效。

### 手動交易 (Manual Entry)
- 支援手動輸入 Ticker, Date, Action (BUY/SELL), Quantity, Price 與 Fees。
- 新增後立即反映於持倉與現金餘額。

## 系統設定 (Settings)

### AI 模型設定
- **Provider**: 支援 Google Gemini, OpenRouter, OpenAI。
- **Model**: 可動態切換使用的模型 (如 `gemini-1.5-pro`)。
- **API Key**: 安全輸入並儲存於本地資料庫。

### 報告試跑 (Report Dry Run)
- 點擊「生成測試報告」，系統將進行 Dry Run (不發送 Email)。
- 透過即時日誌視窗監控 AI 思考過程與產出結果。
