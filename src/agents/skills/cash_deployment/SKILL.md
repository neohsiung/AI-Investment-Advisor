# Cash Deployment Skill

## 概述 (Overview)
此技能用於分析投資組合中的閒置現金。它檢索帳戶餘額，計算相對於目標現金比例的「超額現金」(Excess Cash)，並提供可部署這些資金的潛在候選標的。

## 邏輯描述 (Logic Description)
1. **獲取帳戶資料**: 透過 `BrokerFactory` 調用當前帳戶的權益 (Equity) 與現金 (Cash)。
2. **獲取目標比例**: 從設定資料庫中讀取 `target_cash_ratio` (預設為 10%)。
3. **計算超額現金**: `Available Cash - (Total Equity * Target Cash Ratio)`.
4. **候選標的來源**:
   - **Source 1 (Holdings)**: 現有持倉中，信心程度高且當前占比低於目標比例的標的。
   - **Source 2 (Thematic)**: 預定義的戰略標的 (例如：VOO, QQQ, VTI)。
   - **Source 3 (Discovery)**: 透過 `ticker_discovery` 技能動態發現的新標的 (將在 Phase 1.2 整合)。

## 輸出結構 (Output Structure)
回傳一個 JSON 字串，包含：
- `status`: "balanced" | "overweight"
- `cash_ratio`: 當前現金比例 (0.0 - 1.0)
- `excess_cash`: 可部署金額 (USD)
- `candidates`: 建議部署的標的清單及理由

## 使用場景 (Usage Scenarios)
- 當 Sentinel 觸發 `cash_ratio_high` 警報時。
- 定期 (例如：每週或每日收盤後) 檢查資金效率。
- 使用者詢問「我現在有閒錢可以投什麼？」時。
