---
name: macro-data-ingestion
description: Best practices for fetching and cleaning macroeconomic data from FRED and Yahoo Finance APIs, including rate limit handling.
---

# Macro Data Ingestion Guidelines

## When to use this skill
- Building data pipelines for `FredService`, `MarketDataService`, or `MacroAgent`.
- Fetching ISM, NFP, CPI, or price data.

## How to use it

### 1. Rate Limiting & Reliability
- **Exponential Backoff**: Implement retries for HTTP 429 errors.
- **Caching**: Aggressively cache macro data (it changes slowly). Use `ttl_hours=24` for daily indicators.

### 2. Data Alignment
Merging data sources with different frequencies is critical.
- **FRED** is often Monthly (M) or Quarterly (Q).
- **Yahoo Finance** is Daily (D) or Intraday.

#### Forward Filling (ffill)
Always forward-fill macro data to match market data dates.
```python
# Example: Aligning Monthly CPI to Daily SPY Prices
merged_df = price_df.join(cpi_df, how='left')
merged_df.fillna(method='ffill', inplace=True)
```
*Never back-fill (lookahead bias).*

### 3. Robust Parsing
- APIs (especially FRED/Yahoo) change schemas.
- Wrap parsing in `try-except` blocks.
- Validate essential columns exist before processing.
- If a specific series fails, log a warning and return partial data rather than crashing the `MacroAgent`.

### 4. Specific Series IDs (FRED)
- **ISM Manufacturing PMI**: `NAPM` (check specific sub-indices like `NAPMNO` for New Orders).
- **ISM Services PMI**: `NM_NMF` (Non-Manufacturing Index) or similar.
- **Non-Farm Payrolls**: `PAYEMS`.
- **Unemployment Rate**: `UNRATE`.
- **10Y-2Y Spread**: `T10Y2Y`.
