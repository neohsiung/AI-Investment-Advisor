# 回饋迴路與自動化規格 (Refinement & Automation Specification)

本文件定義了系統如何透過歷史績效回測來自我優化 (Self-Improvement)，以及如何自動化執行每週任務。

## 1. 績效歸因分析 (Attribution Analysis)

系統每月將執行一次回顧，評估各個 Agent 的預測準確度。

### 1.1 評分邏輯
- **預測視窗**: 30 天 (針對 Momentum/Fundamental 建議)。
- **準確率 (Accuracy)**:
    - 若 Agent 建議 BUY，且 30 天後 Price > Cost * 1.05 -> 正確 (+1)。
    - 若 Agent 建議 BUY，且 30 天後 Price < Cost * 0.95 -> 錯誤 (-1)。
    - 其他情況 -> 中立 (0)。
- **權重調整 (Weight Adjustment)**:
    - 每個 Agent 初始權重為 1.0。
    - 連續 3 個月準確率 < 40%，權重降低 0.1 (最低 0.5)。
    - 連續 3 個月準確率 > 60%，權重增加 0.1 (最高 1.5)。

### 1.2 實作架構
- `RefinementEngine`: 讀取歷史建議 (需儲存於 DB) 與歷史股價，計算分數。
- `AgentConfig`: 儲存各 Agent 的權重與動態參數 (JSON)。

## 2. Prompt 動態優化 (Dynamic Prompt Refinement)

除了調整權重，系統還能微調 System Prompt。

### 2.1 機制
- **In-Context Learning**: 將上個月「最準確」與「最錯誤」的案例，追加到 System Prompt 的 `## Historical Context` 區塊中。
- **範例**:
    > "Last month, you recommended BUY on NVDA based on RSI, but it fell 10%. Be more cautious when VIX > 25."

## 3. 自動化排程 (Automation)

### 3.1 排程任務
- **Daily Update (08:00 AM)**: 更新股價數據。
- **Weekly Report (Sat 09:00 AM)**: 執行 `workflow.py` 生成週報。
- **Monthly Refinement (1st Day)**: 執行 `refinement.py` 調整權重與 Prompt。

### 3.2 實作方式
- 使用 Python `schedule` 庫或系統級 `cron`。
- 為了 Antigravity 環境簡便性，將提供一個 `scheduler.py` 腳本持續運行。

## 4. 數據儲存擴充
- `recommendations` table: 儲存 Agent 的歷史建議，用於回測。
    - `id`, `date`, `agent`, `ticker`, `signal`, `price_at_signal`
