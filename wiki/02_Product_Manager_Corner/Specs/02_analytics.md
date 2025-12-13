# Analytics Engine Specification v3

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Analytics Engine Specification v3

> **Status**: Draft
> **Version**: 1.0

### 1. Overview
The mathematical core. Responsible for Portfolio Health, Leverage, and ROI. Strictly adheres to **DETERMINISTIC_MATH** (Python only, no LLM guessing).

### 2. Core Components

#### 2.1 LeverageCalculator
Calculates "True Leverage".
*   **TNV (Total Nominal Value)**: `Sum(abs(Qty * Price))`
*   **NLV (Net Liquidation Value)**: Total Equity.
*   **Ratio**: `TNV / NLV`
*   **Risk**: <1.0 Safe, >1.5 High Risk, >2.0 Danger.

#### 2.2 ROIEngine
*   **Simple ROI**: `(Net Profit / Net Invested Capital) * 100%`
*   **Net Invested Capital**: `Deposits - Withdrawals`

#### 2.3 PnLCalculator
*   **Realized P&L**: `(Exit - Entry) * Qty`
*   **Unrealized P&L**: `(Current - AvgCost) * Qty`

### 3. Data Dependency
*   Input: `current_prices`, `user_id`.
*   Source: `src/market_data.py`, DB `transactions`.

### 4. Implementation
*   Code: `src/analytics.py`
*   Test: `tests/test_analytics.py`

---

<a id="traditional-chinese"></a>

## 🇹🇼 分析引擎規格 (Analytics Engine Specification) v3

> **狀態**: 草稿 (Draft)
> **版本**: 1.0

### 1. 概觀 (Overview)
分析引擎是系統的數學核心，負責計算投資組合健康度、槓桿比率以及績效指標 (ROI)。必須嚴格遵守 **確定性數學 (DETERMINISTIC_MATH)** 原則 (基於 Python 計算，不依賴 LLM 猜測)。

### 2. 核心組件 (Core Components)

#### 2.1 槓桿計算器 (LeverageCalculator)
負責計算投資組合的「真實槓桿 (True Leverage)」。
*   **總名義價值 (Total Nominal Value, TNV)**: 所有持倉絕對名義價值的總和。 `TNV = Sum(abs(Quantity * Price))`
*   **淨流動資產價值 (Net Liquidation Value, NLV)**: 總權益。 `NLV = Cash Balance + Market Value of Positions`
*   **槓桿比率 (Leverage Ratio)**: `Ratio = TNV / NLV`
*   **風險等級 (Risk Levels)**:
    *   `< 1.0`: 安全 (現金部位高)
    *   `1.0 - 1.5`: 正常
    *   `1.5 - 2.0`: 高風險
    *   `> 2.0`: 危險 (保證金追繳警告)

#### 2.2 投資報酬率引擎 (ROIEngine)
*   **簡單 ROI (Simple ROI)**: `(Net Profit / Net Invested Capital) * 100%`
*   **淨投入資本 (Net Invested Capital)**: `Sum(Deposits) - Sum(Withdrawals)`

#### 2.3 損益計算器 (PnLCalculator)
*   **已實現損益 (Realized P&L)**: `(Exit Price - Entry Cost) * Qty`
*   **未實現損益 (Unrealized P&L)**: `(Current Price - Avg Cost) * Qty`
*   **總損益 (Total P&L)**: 已實現 + 未實現

### 3. 數據依賴 (Data Dependency)
*   輸入: `current_prices` (Dict[Ticker, Price]), `user_id`.
*   來源: `src/market_data.py` (即時報價), `transactions` 資料表 (歷史紀錄)。

### 4. 實作計畫 (Implementation Plan)
*   位置: `src/analytics.py`
*   測試: `tests/test_analytics.py`
