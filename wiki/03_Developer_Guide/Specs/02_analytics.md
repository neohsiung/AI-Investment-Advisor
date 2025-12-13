# Analytics Engine Specification (v3)

> **Status**: Draft
> **Version**: 1.0

## 1. Overview
The Analytics Engine is the mathematical core of the system, responsible for calculating portfolio health, leverage ratios, and performance metrics (ROI). It must adhere to the `DETERMINISTIC_MATH` principle (Python-based, no LLM guessing).

## 2. Core Components

### 2.1 LeverageCalculator
Calculates the "True Leverage" of the portfolio.

*   **Total Nominal Value (TNV)**: Sum of absolute notional value of all positions.
    *   `TNV = Sum(abs(Quantity * Price))`
*   **Net Liquidation Value (NLV)**: Total Equity.
    *   `NLV = Cash Balance + Market Value of Positions`
*   **Leverage Ratio**:
    *   `Ratio = TNV / NLV`
*   **Risk Levels**:
    *   `< 1.0`: Safe (Cash heavy)
    *   `1.0 - 1.5`: Normal
    *   `1.5 - 2.0`: High Risk
    *   `> 2.0`: Critical (Margin Call Warning)

### 2.2 ROIEngine
Calculates Return on Investment.

*   **Simple ROI**:
    *   `ROI = (Net Profit / Net Invested Capital) * 100%`
*   **Net Invested Capital**:
    *   `Sum(Deposits) - Sum(Withdrawals)`
*   **Time-Weighted Return (TWR)**: *Future Scope*

### 2.3 PnLCalculator
Breakdown of Profit and Loss.

*   **Realized P&L**: (Exit Price - Entry Cost) * Qty
*   **Unrealized P&L**: (Current Price - Avg Cost) * Qty
*   **Total P&L**: Realized + Unrealized

## 3. Data Dependency
*   Input: `current_prices` (Dict[Ticker, Price]), `user_id`.
*   Source: `src/market_data.py` (Real-time), `transactions` table (Historical).

## 4. Implementation Plan
*   Location: `src/analytics.py`
*   Tests: `tests/test_analytics.py`
