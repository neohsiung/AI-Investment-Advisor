# 量化分析規格 (Analytics Specification)

本文件定義了系統如何計算關鍵財務指標：槓桿水位 (Leverage Water Level) 與投資報酬率 (ROI)。

## 1. 槓桿水位 (Leverage Water Level)

槓桿水位反映帳戶的風險暴露程度，用於觸發 Margin Call 警示。

### 1.1 定義
- **總名義價值 (Total Notional Value, TNV)**: 所有持倉的市值總和。
    - 股票: $Quantity \times Price$
    - 選擇權: $Quantity \times 100 \times UnderlyingPrice \times Delta$ (Phase 2 初期可簡化為市值，Phase 3 引入 Delta)
- **淨清算價值 (Net Liquidation Value, NLV)**: $Total Assets - Total Liabilities$ (即帳戶總權益)。
- **槓桿比率 (Leverage Ratio)**:
  $$ Leverage Ratio = \frac{TNV}{NLV} $$

### 1.2 風險分級
系統應根據 Leverage Ratio 顯示不同顏色的警示：
- **Safe (Green)**: Ratio < 1.0 (無槓桿)
- **Moderate (Yellow)**: 1.0 <= Ratio < 1.5
- **Risky (Orange)**: 1.5 <= Ratio < 2.0
- **Critical (Red)**: Ratio >= 2.0 (接近 Margin Call 風險)

## 2. 槓桿調整後 ROI (Leverage-Adjusted ROI)

傳統 ROI ($Profit / TotalAsset$) 無法反映槓桿交易的真實回報。本系統採用「本金回報率」。

### 2.1 計算公式
$$ ROI_{leveraged} = \frac{\text{Net Profit}}{\text{Invested Equity}} \times 100\% $$

- **Net Profit**: $\sum (Realized P\&L + Unrealized P\&L) - Fees - Margin Interest$
- **Invested Equity**: 初始入金 + 後續入金 - 出金 (即 Net Deposits)。

### 2.2 時間加權回報 (Time-Weighted Return, TWR) - *Advanced*
為了排除出入金對績效的影響，理想情況應計算 TWR。
Phase 2 先實作簡單的 `Money-Weighted Return` (MWR) 或上述的 `Simple ROI`，若有餘力再升級為 TWR。

## 3. 實作架構

### 3.1 `LeverageCalculator`
- 輸入: `Positions` (from DB), `Current Prices`
- 輸出: `Leverage Ratio`, `Margin Level`

### 3.2 `ROIEngine`
- 輸入: `Transactions`, `CashFlows`, `Current Portfolio Value`
- 輸出: `Total ROI`, `YTD ROI`, `Equity Curve` (DataFrame)

## 4. 數據來源
- 歷史價格: 用於繪製 Equity Curve。初期可使用 `yfinance` 獲取每日收盤價。
- 即時價格: 用於計算當前槓桿。
