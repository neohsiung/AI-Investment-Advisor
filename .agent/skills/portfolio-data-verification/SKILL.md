---
name: portfolio-data-verification
description: Best practices for auditing and aligning portfolio metrics (NLV, Profit, Cash) between database transactions and external broker API states.
---

# Portfolio Data Verification Skill

This skill defines the methodology for ensuring that the Investment Advisor dashboard accurately reflects the "Source of Truth" (transactons) while allowing for stable metric anchoring.

## 1. Metric Definitions & Formulas

Standardize definitions across the system to avoid "vibe-based" discrepancies.

- **資產淨值 (NLV)**: `Cash Balance + Total Market Value (Long + Short)`.
- **獲利/虧損 (Profit)**: `NLV - Net Invested Capital`.
- **浮動 (Floating)**: `Unrealized P/L` based on current position cost basis vs market price.
- **總曝險 (Gross)**: `Uninvested Cash + Sum(abs(Nominal Value of each ticker * Leverage))`.

## 2. Identifying Discrepancies

When the Dashboard doesn't match the Broker (e.g., eToro):

1. **Check for "Ghost Data"**: Look for numeric ID positions (e.g., `1234567`) that might be duplicates of named tickers.
2. **Verify Cash Flow**: Compare `calculate_net_invested_capital` (Deposits - Withdrawals) against manual transfer logs.
3. **Compare Calculations**: Verify if `DashboardService` is incorrectly using "Current Cost Basis" instead of "Net Invested Capital" for Profit metrics.

## 3. Calibration Techniques

If metrics are off due to historical data noise, use "Calibration Transactions":

- **CASH / ETORO_SYNC**: Use a `CASH` action transaction to adjust the local cash balance to match the broker.
- **NLV_ADJUST / STABILIZE_CAP**: Use these tickers with `action='BUY'` to artificially anchor the Net Liquidity Value or Invested Capital.
- **USD / STABILIZE_CASH**: Use to anchor cash specifically.

## 4. Static Anchoring for Stability

To prevent "drift" from market price fluctuations or missing API data:

1. **Naming Convention**: Tickers starting with `__ANCHOR_`, `NLV_`, or `STABILIZE_` are treated as static.
2. **Implementation**: In `AnalyticsService.calculate_metrics`, ignore real-time price lookups for these tickers. Use their **Average Cost** (from the DB) as the "Price".
3. **Effect**: The metric stays fixed at the target anchor regardless of market volatility.

## 5. Verification Snippets

Always verify via `docker exec` to bypass caching layers:

```python
# Verify NLV and Profit Alignment
from src.services.dashboard_service import DashboardService
ds = DashboardService()
data = ds.prepare_dashboard_data('USER_ID')
metrics = data['metrics']
pnl = data['pnl_data']
print(f"NLV: {metrics['nlv']}, Profit: {pnl['total']}, Cash: {metrics['cash_balance']}")
```

```sql
-- Check for anchor transactions
SELECT * FROM transactions WHERE ticker LIKE '%ANCHOR%' OR ticker LIKE 'NLV%' OR ticker LIKE 'STABILIZE%';
```

## 6. Security & Integrity

- **Parameterized Queries**: Always use `src.repositories.transaction_repository` to avoid SQL injection.
- **No Hardcoded Values**: Anchors should be database records, not values in code.
