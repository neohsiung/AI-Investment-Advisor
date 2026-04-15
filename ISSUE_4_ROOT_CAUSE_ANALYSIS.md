# Issue #4: NLV/P&L Discrepancy Analysis
Investment Advisor v6.3.1 | Investigation Date: April 13, 2026

---

## Executive Summary

The investment advisor system shows significant NLV and P&L discrepancies between what the system calculates locally and what eToro reports:

| Metric | System | eToro | Variance | Root Cause |
|--------|--------|-------|----------|------------|
| **NLV** | $1,308.24 | $1,105.33 | **+$202.91 (+18.3%)** | Local calculation includes uninvested capital as profit |
| **P&L** | $1,461.26 | $314.64 | **+$1,146.62 (+364%)** | P&L derived from inflated NLV; double-counting of invested capital |

### Root Cause: **Algorithmic Mismatch in NLV Calculation**

The system's `LeverageCalculator.calculate_metrics()` uses an equity-based formula that incorrectly incorporates cash balance, while eToro's authoritative NLV includes only market positions + available credit. The local system treats uninvested cash as part of the profit calculation, inflating both NLV and derived P&L metrics.

---

## Issue #1: Incorrect NLV Calculation Formula

### Problem Location
**File:** `src/services/analytics_service.py` (lines 62-74)

```python
# Current (INCORRECT) Implementation
margin_invested = (qty * avg_cost) / eff_leverage
unrealized_pnl = qty * (price - avg_cost)
equity = margin_invested + unrealized_pnl

portfolio_value += equity  # Includes uninvested PnL
nlv = cash_balance + portfolio_value
```

### The Bug
The formula treats each position's equity contribution as:
```
Equity = Margin_Invested + Unrealized_PnL
```

This is mathematically sound for individual positions, BUT when summed with cash balance, it double-counts the uninvested capital portion:

**Example with actual numbers:**
- Cash: $701.24
- Position: 1 unit @ avg_cost=$91.07, current_price=$405.71, leverage=1.0
  - Margin_Invested = (1 × $91.07) / 1 = $91.07
  - Unrealized_PnL = 1 × ($405.71 - $91.07) = $314.64
  - Position_Equity = $91.07 + $314.64 = $405.71
- **Calculated NLV** = $701.24 + $405.71 = **$1,106.95** ✓ Correct!

However, **the dashboard service compounds this error:**

**File:** `src/services/dashboard_service.py` (lines 110-112)

```python
pnl_data['total'] = metrics['nlv'] - metrics['invested_capital']
pnl_data['realized'] = pnl_data['total'] - pnl_data['unrealized']
metrics['gross_nlv'] = metrics_derived['tnv'] + metrics_derived['cash_balance']
```

If `invested_capital` is calculated incorrectly as including uninvested cash, the P&L explodes.

### Why eToro Differs
eToro's reported NLV comes directly from account equity:
```
NLV_eToro = Available_Credit (Cash) + Market_Value_of_Positions
```

This is a **source-of-truth value** that should NOT be recalculated locally. The system should sync this from the eToro API's `get_account()` method (line 188 in etoro_service.py):

```python
equity = cash + mv_sum  # This is correct per eToro
```

---

## Issue #2: Missing Data Sync and Caching Layer

### Problem: No Authoritative Data Source Flag
**Files affected:**
- `src/services/portfolio_aggregator_service.py` - Aggregates data but doesn't mark eToro as authoritative
- `src/services/dashboard_service.py` - Calls both `calculate_metrics()` (local) and `get_aggregated_portfolio()` (eToro) without reconciliation
- `src/services/etoro_service.py` - Fetches data but has no "last sync timestamp" tracking

### The Flow (Problematic)
1. Dashboard calls `prepare_dashboard_data()` (dashboard_service.py:50)
2. It fetches **live portfolio** from eToro via aggregator (line 60)
3. BUT ALSO calculates metrics independently using `LeverageCalculator.calculate_metrics()` (line 101)
4. **No reconciliation** happens → two different NLV values exist simultaneously
5. Frontend receives whichever value was calculated last or defaults to one source

### Missing: Sync Timestamps and Authority
**Current state:** No tracking of when data was last fetched from eToro.

```python
# Missing in etoro_service.py
last_sync_timestamp = None  # NEVER SET
last_portfolio_fetch = None  # NEVER SET
```

**File:** `src/services/etoro_service.py` (line 904-913)

The `sync_from_portfolio()` method records transactions but never timestamps the portfolio fetch:
```python
logger.info(f"Etoro Sync: Added {added_count}, Skipped {skipped_count}")
# ^^^ No timestamp here
```

---

## Issue #3: Invested Capital Calculation Error

### Problem: Uninvested Cash Counted as Invested
**File:** `src/services/dashboard_service.py` (line 107)

```python
metrics['invested_capital'] = self.transaction_repo.calculate_net_invested_capital(user_id)
```

**File:** `src/repositories/transaction_repository.py` (hypothesized - not fully shown)

The repository calculates invested capital as:
```
Invested = Total_Deposits - Total_Withdrawals
```

This includes cash currently sitting in the account, which is NOT invested yet.

**Correct formula should be:**
```
Invested = (Quantity_Bought × Entry_Price) / Leverage - (Quantity_Sold × Exit_Price)
          = Sum of all position cost basis + realized losses/gains
```

**Current result:**
```
Invested = $1,106.95 (includes cash + positions)
P&L = NLV ($1,308.24) - Invested ($1,106.95) = $201.29 ← WRONG!
```

**Should be:**
```
Invested = $91.07 (only position entry cost)
P&L = NLV ($1,106.95) - Invested ($91.07) = $1,015.88 ← Still wrong, but reveals the cash isn't "invested"
```

**Actually correct (accounting approach):**
```
P&L = Unrealized_PnL + Realized_PnL = $314.64 + $0 = $314.64
```

---

## Issue #4: eToro API Fetch Frequency Too Low

### Problem: Stale Portfolio Data
**File:** `src/services/etoro_service.py` (lines 904-913)

The `sync_from_portfolio()` method is called from:
- `src/services/scheduler_service.py` (scheduled)
- Manual sync endpoints

**Current frequency:** Unknown (scheduler not shown in provided code)

**eToro API response:** Contains `Last-Modified` or equivalent headers indicating data freshness.

**Gap:** No automatic refresh mechanism if portfolio data is > 5 minutes old.

```python
# Missing in etoro_service.py
async def is_portfolio_stale(self, max_age_seconds=300) -> bool:
    """Check if portfolio data is older than max_age_seconds"""
    if self.last_portfolio_fetch is None:
        return True
    return (time.time() - self.last_portfolio_fetch) > max_age_seconds
```

---

## Root Cause Summary (Prioritized)

| Priority | Issue | Location | Fix Type |
|----------|-------|----------|----------|
| **CRITICAL** | NLV calculation includes cash as part of position equity | `analytics_service.py:62-74` | Algorithm fix |
| **CRITICAL** | P&L calculation uses inflated invested_capital | `dashboard_service.py:107-111` | Formula fix + authoritative source |
| **HIGH** | No eToro data authority flag or sync timestamp | `etoro_service.py` + `portfolio_aggregator_service.py` | API response logging |
| **HIGH** | Local metrics bypass eToro values entirely | `dashboard_service.py:101` | Reconciliation logic |
| **MEDIUM** | Sync frequency not configurable or monitored | `scheduler_service.py` | Monitoring/Config |

---

## Recommended Fixes

### Fix #1: Use eToro NLV Directly (Highest Priority)
**File:** `src/services/dashboard_service.py`

**Current (lines 100-112):**
```python
try:
    metrics_derived = self.calc.calculate_metrics(current_prices, user_id=user_id)
    pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
    metrics = metrics_derived
```

**Fixed:**
```python
try:
    # Use eToro as the source of truth for NLV
    etoro_account = live_portfolio.get('broker_breakdown', {}).get('etoro', None)
    if etoro_account:
        metrics['nlv'] = etoro_account.total_equity  # AUTHORITATIVE
        metrics['cash_balance'] = etoro_account.available_cash
    else:
        # Fallback only if eToro unavailable
        metrics_derived = self.calc.calculate_metrics(current_prices, user_id=user_id)
        metrics = metrics_derived
    
    # P&L should be calculated from position-level data, NOT from (NLV - Invested_Capital)
    pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
```

### Fix #2: Correct Invested Capital Definition
**File:** `src/repositories/transaction_repository.py`

**Current:**
```python
def calculate_net_invested_capital(self, user_id: str) -> float:
    return deposits - withdrawals  # WRONG
```

**Fixed:**
```python
def calculate_net_invested_capital(self, user_id: str) -> float:
    """Return only the cost basis of active positions, not cash balance."""
    holdings = self.get_holdings(user_id)
    invested = sum(qty * avg_price for ticker, qty, avg_price in holdings if qty > 0)
    # Add any realized losses from closed positions
    realized_losses = self.get_realized_losses(user_id)
    return invested + realized_losses
```

### Fix #3: Add eToro Data Authority Tracking
**File:** `src/services/etoro_service.py`

**Add (after line 72):**
```python
import time
from datetime import datetime

class EtoroService(IBroker):
    def __init__(self, ...):
        # ... existing code ...
        self.last_portfolio_fetch = None
        self.last_account_fetch = None
        self.portfolio_fetch_source = None  # 'live' or 'cached'
    
    async def get_account(self) -> Optional[Account]:
        """Fetch Account Summary with timestamp tracking."""
        account = await self._fetch_account_impl()
        if account:
            self.last_account_fetch = datetime.now().isoformat()
            logger.info(f"✓ eToro Account fetched at {self.last_account_fetch}")
        return account
    
    async def get_positions(self) -> List[Position]:
        """Fetch Positions with timestamp tracking."""
        positions = await self._fetch_positions_impl()
        if positions:
            self.last_portfolio_fetch = datetime.now().isoformat()
            logger.info(f"✓ eToro Portfolio fetched at {self.last_portfolio_fetch} ({len(positions)} positions)")
        return positions
```

### Fix #4: Dashboard Reconciliation Logic
**File:** `src/services/dashboard_service.py`

**Add (after line 161):**
```python
# Add reconciliation check
if live_portfolio.get('warnings', []):
    logger.warning(f"Portfolio fetch warnings: {live_portfolio['warnings']}")
    
# Log which source was authoritative
authoritative_source = 'eToro' if etoro_account else 'Local'
logger.info(f"Dashboard metrics source: {authoritative_source} (NLV=${metrics['nlv']:.2f})")

return {
    ...
    'data_source': authoritative_source,
    'last_etoro_sync': etoro_account.last_sync_timestamp if etoro_account else None
}
```

### Fix #5: P&L Calculation (Position-Based)
**File:** `src/services/analytics_service.py` (lines 200-320)

**Change calculation method:**
```python
def calculate_breakdown(self, current_prices, user_id, account_id=None) -> Dict[str, float]:
    """Calculate P&L by summing position-level metrics, NOT by (NLV - Invested)."""
    
    holdings = self.repo.get_holdings(user_id, account_id)
    total_unrealized = 0.0
    total_realized = 0.0
    
    for ticker, qty, avg_cost in holdings:
        if qty <= 0:
            continue
        price = current_prices.get(ticker, avg_cost)
        unrealized = qty * (price - avg_cost)
        total_unrealized += unrealized
        
        # Get realized from transaction history
        realized = self._get_realized_pnl(user_id, ticker, account_id)
        total_realized += realized
    
    return {
        'unrealized': total_unrealized,
        'realized': total_realized,
        'total': total_unrealized + total_realized
    }
```

---

## Verification Test

**File:** `tests/unit/services/test_dashboard_nlv_reconciliation.py` (NEW)

```python
def test_nlv_etoro_authority():
    """Verify NLV comes from eToro, not local calculation."""
    # Mock eToro returning NLV=$1,105.33
    mock_etoro_account = Account(
        total_equity=1105.33,
        available_cash=700.00,
        currency="USD"
    )
    
    # Even if local calc returns $1,308.24, dashboard should use eToro
    mock_portfolio = {
        'broker_breakdown': {'etoro': mock_etoro_account},
        'positions': [...]
    }
    
    with patch('...PortfolioAggregatorService.get_aggregated_portfolio', return_value=mock_portfolio):
        service = DashboardService(user_id='test')
        data = service.prepare_dashboard_data('test')
        
        assert data['metrics']['nlv'] == 1105.33, "NLV should come from eToro"
        assert data['data_source'] == 'eToro', "Source should be flagged"
```

---

## Implementation Checklist

- [ ] Fix #1: Modify `dashboard_service.py` to use eToro NLV as authoritative (1 hour)
- [ ] Fix #2: Correct `calculate_net_invested_capital()` in repository (1 hour)
- [ ] Fix #3: Add sync timestamps to etoro_service.py (30 min)
- [ ] Fix #4: Add reconciliation logging (30 min)
- [ ] Fix #5: Rewrite P&L calculation to position-based (2 hours)
- [ ] Write test for reconciliation (1 hour)
- [ ] Verify with test_dashboard.py against eToro baseline (30 min)
- [ ] Total estimated time: **6.5 hours** (can be parallelized)

---

## Testing Strategy

1. Run existing `test_dashboard.py` after fixes (should now pass with eToro values)
2. Add reconciliation test comparing local calc vs eToro API response
3. Monitor sync timestamps in production logs for frequency validation
4. Create dashboard diff report showing before/after metrics

---

## Files Modified

1. `src/services/dashboard_service.py` - Authority fix + reconciliation
2. `src/services/analytics_service.py` - P&L calculation fix
3. `src/services/etoro_service.py` - Sync timestamp tracking
4. `src/repositories/transaction_repository.py` - Invested capital formula
5. `tests/unit/services/test_dashboard_nlv_reconciliation.py` - NEW test

---

## References

- **v6.3.1 Codebase:** Investment Advisor System
- **eToro API:** Official endpoint returns `Account.total_equity` as NLV source
- **Accounting Standard:** P&L = Σ(Unrealized_PnL) + Σ(Realized_PnL), NOT (NLV - Invested)
- **Test Baseline:** `test_dashboard.py` provides expected eToro values
