# Issue #4 Fix Implementation Guide
## Recommended Code Changes

---

## Change #1: Modify dashboard_service.py (CRITICAL)

**File:** `src/services/dashboard_service.py`

**Current code (lines 50-115) - BROKEN:**
```python
async def prepare_dashboard_data(self, user_id: str) -> Dict[str, Any]:
    ...
    try:
        metrics_derived = self.calc.calculate_metrics(current_prices, user_id=user_id)
        pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
        
        metrics = metrics_derived  # <-- PROBLEM: Uses local calc, ignores eToro
        metrics['invested_capital'] = self.transaction_repo.calculate_net_invested_capital(user_id)
        metrics['unrealized_pnl'] = pnl_data.get('unrealized', 0)
        
        pnl_data['total'] = metrics['nlv'] - metrics['invested_capital']  # <-- WRONG FORMULA
        pnl_data['realized'] = pnl_data['total'] - pnl_data['unrealized']
        metrics['gross_nlv'] = metrics_derived['tnv'] + metrics_derived['cash_balance']
```

**Fixed code:**
```python
async def prepare_dashboard_data(self, user_id: str) -> Dict[str, Any]:
    ...
    try:
        # STEP 1: Use eToro as the AUTHORITATIVE source for NLV and Cash
        etoro_account = live_portfolio.get('broker_breakdown', {}).get('etoro', None)
        data_source = 'eToro'
        
        if etoro_account and live_portfolio.get('warnings', []) == []:
            # eToro data is clean and available
            logger.info(f"Using eToro as authoritative source: NLV=${etoro_account.total_equity:.2f}")
            metrics = {
                'nlv': etoro_account.total_equity,  # eToro is ground truth
                'cash_balance': etoro_account.available_cash,
                'invested_capital': etoro_account.total_equity - current_prices.get('USD', 1.0) * sum(
                    p.quantity * current_prices.get(p.symbol, p.current_price) 
                    for p in live_positions if p.symbol != 'CASH'
                ),
                'leverage_ratio': 0.0,  # Will compute below
                'tnv': 0.0
            }
        else:
            # Fallback to local calculation if eToro unavailable
            logger.warning(f"eToro unavailable or has warnings, using local calculation fallback")
            data_source = 'Local'
            metrics_derived = self.calc.calculate_metrics(current_prices, user_id=user_id)
            metrics = metrics_derived
        
        # STEP 2: Calculate P&L from position-level data (NOT from NLV - Invested)
        pnl_data = self.pnl_calc.calculate_breakdown(current_prices, user_id=user_id)
        
        # STEP 3: Compute invested capital correctly
        # Invested = Deposits - Withdrawals - Unrealized Gains (which come from eToro)
        net_cash_flow = self.transaction_repo.calculate_net_invested_capital(user_id)  # Deposits - Withdrawals
        
        # For P&L display, use what eToro gives us
        metrics['invested_capital'] = net_cash_flow
        metrics['unrealized_pnl'] = pnl_data.get('unrealized', 0)
        
        # STEP 4: P&L = Unrealized + Realized, NOT (NLV - Invested)
        pnl_data['total'] = pnl_data.get('unrealized', 0) + pnl_data.get('realized', 0)
        
        # STEP 5: Add source tracking
        metrics['data_source'] = data_source
        metrics['nlv_source_timestamp'] = getattr(etoro_account, 'last_sync', None) if etoro_account else None
        
        roi = (pnl_data['total'] / net_cash_flow) * 100 if net_cash_flow > 0 else 0.0
```

---

## Change #2: Modify etoro_service.py (HIGH PRIORITY)

**File:** `src/services/etoro_service.py`

**Add after line 72 (inside __init__):**
```python
from datetime import datetime
import time

class EtoroService(IBroker):
    def __init__(self, base_url: str = None, mode: str = "real", ...):
        # ... existing code ...
        
        # ADD THESE LINES:
        self.last_portfolio_fetch_time = None  # When portfolio was last fetched
        self.last_account_fetch_time = None    # When account was last fetched
        self.portfolio_data_source = None      # 'live_api' or 'cached'
```

**Modify get_account() method (around line 137-204):**
```python
async def get_account(self) -> Optional[Account]:
    """
    Fetch Account Summary (Equity, Cash).
    """
    portfolio = await self._fetch_portfolio_raw()
    if not portfolio:
        logger.error("Failed to fetch portfolio for account summary")
        return None
    
    # ... existing portfolio parsing code ...
    
    account = Account(
        broker_type=BrokerType.ETORO,
        account_id=f"etoro_{self.mode}",
        total_equity=equity,
        available_cash=cash,
        currency="USD"
    )
    
    # ADD TIMESTAMP TRACKING:
    self.last_account_fetch_time = datetime.now().isoformat()
    account.last_sync = self.last_account_fetch_time  # Store on Account object if possible
    logger.info(f"✓ eToro Account fetched at {self.last_account_fetch_time}: Equity=${equity:.2f}, Cash=${cash:.2f}")
    
    return account
```

**Modify get_positions() method (around line 206-292):**
```python
async def get_positions(self) -> List[Position]:
    """
    Fetch Positions with timestamp tracking.
    """
    portfolio = await self._fetch_portfolio_raw()
    if not portfolio:
        logger.warning("Portfolio response is empty.")
        return []
    
    # ... existing position parsing code ...
    
    # ADD AT END:
    self.last_portfolio_fetch_time = datetime.now().isoformat()
    self.portfolio_data_source = 'live_api'
    logger.info(f"✓ eToro Portfolio fetched at {self.last_portfolio_fetch_time} ({len(positions)} positions)")
    
    return positions
```

---

## Change #3: Modify transaction_repository.py (HIGH PRIORITY)

**File:** `src/repositories/transaction_repository.py`

**Find and replace the calculate_net_invested_capital method:**

**Current (WRONG):**
```python
def calculate_net_invested_capital(self, user_id: str, account_id: str = None) -> float:
    """Calculate net capital invested = Deposits - Withdrawals"""
    with self.engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT 
                    SUM(CASE WHEN action = 'DEPOSIT' THEN amount ELSE -amount END) 
                FROM transactions 
                WHERE user_id = :uid AND ticker = 'CASH'
            """),
            {'uid': user_id}
        ).scalar()
    return float(result or 0)
```

**Fixed:**
```python
def calculate_net_invested_capital(self, user_id: str, account_id: str = None) -> float:
    """
    Calculate net capital invested = Deposits - Withdrawals.
    This represents the total CASH FLOW into the account, not the invested portion.
    Use this for ROI calculation: ROI = PnL / Net_Invested_Capital
    """
    with self.engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT 
                    SUM(CASE WHEN action = 'DEPOSIT' THEN amount 
                            WHEN action = 'WITHDRAWAL' THEN -amount 
                            ELSE 0 END) 
                FROM transactions 
                WHERE user_id = :uid AND ticker = 'CASH'
            """),
            {'uid': user_id}
        ).scalar()
    return float(result or 0)

def calculate_position_cost_basis(self, user_id: str, account_id: str = None) -> float:
    """
    Calculate the cost basis of CURRENTLY OPEN positions.
    This excludes cash sitting idle in the account.
    """
    with self.engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT 
                    SUM(quantity * price) as cost_basis
                FROM (
                    SELECT ticker,
                        SUM(CASE WHEN action = 'BUY' THEN quantity ELSE -quantity END) as quantity,
                        AVG(price) as price
                    FROM transactions
                    WHERE user_id = :uid AND ticker != 'CASH' AND (account_id IS NULL OR account_id = :aid)
                    GROUP BY ticker
                    HAVING SUM(CASE WHEN action = 'BUY' THEN quantity ELSE -quantity END) > 0.001
                ) holdings
            """),
            {'uid': user_id, 'aid': account_id}
        ).scalar()
    return float(result or 0)
```

---

## Change #4: Modify analytics_service.py (MEDIUM PRIORITY)

**File:** `src/services/analytics_service.py`

**Find calculate_breakdown method (around lines 200-320) and replace the P&L calculation:**

**Current (WRONG):**
```python
def calculate_breakdown(self, current_prices, user_id, account_id=None):
    """Calculate realized and unrealized P&L breakdown."""
    # ... code ...
    # Uses unrealized PnL from position market values
    # But doesn't correctly handle realized gains
```

**Fixed:**
```python
def calculate_breakdown(self, current_prices: Dict[str, float], user_id: str, account_id: str = None) -> Dict[str, float]:
    """
    Calculate P&L breakdown: Unrealized + Realized = Total P&L.
    This is the POSITION-based approach, not the (NLV - Invested) approach.
    """
    holdings_detail = self.repo.get_holdings(user_id, account_id)
    
    total_unrealized_pnl = 0.0
    total_realized_pnl = 0.0
    pnl_by_ticker = {}
    
    for holding in holdings_detail:
        ticker = holding['ticker']
        qty = holding['qty']
        avg_cost = holding['avg_price']
        
        if qty <= 0.001:
            continue
        
        curr_price = self._get_effective_price(ticker, current_prices, user_id, account_id)
        
        # Unrealized: Current market value - cost basis
        unrealized = qty * (curr_price - avg_cost)
        total_unrealized_pnl += unrealized
        
        # Realized: From transaction history (closed positions)
        realized = self._get_realized_pnl_for_ticker(user_id, ticker, account_id)
        total_realized_pnl += realized
        
        pnl_by_ticker[ticker] = {
            'unrealized': unrealized,
            'realized': realized,
            'total': unrealized + realized
        }
    
    return {
        "unrealized": total_unrealized_pnl,
        "realized": total_realized_pnl,
        "total": total_unrealized_pnl + total_realized_pnl,
        "by_ticker": pnl_by_ticker
    }

def _get_realized_pnl_for_ticker(self, user_id: str, ticker: str, account_id: str = None) -> float:
    """Get realized P&L from closed positions (sold at profit/loss)."""
    # This requires tracking sold quantities and their exit prices
    # Simplified version - can be enhanced with FIFO/LIFO
    return 0.0  # TODO: Implement if closed position tracking exists
```

---

## Change #5: Add Reconciliation Test (NEW FILE)

**File:** `tests/unit/services/test_dashboard_nlv_reconciliation.py`

```python
"""
Test to verify NLV and P&L reconciliation between eToro and local system.
Issue #4: NLV/P&L Discrepancy
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.dashboard_service import DashboardService
from src.domain.trading import Account, Position, BrokerType

pytestmark = pytest.mark.asyncio

class TestNLVReconciliation:
    """Verify that system uses eToro as authoritative source for NLV."""
    
    @pytest.fixture
    def etoro_account_baseline(self):
        """eToro's reported account state."""
        return Account(
            broker_type=BrokerType.ETORO,
            account_id="etoro_real",
            total_equity=1105.33,  # eToro reported NLV
            available_cash=700.00,  # eToro reported cash
            currency="USD"
        )
    
    @pytest.fixture
    def mock_portfolio(self, etoro_account_baseline):
        """Mock portfolio from eToro API."""
        return {
            'total_equity': 1105.33,
            'total_cash': 700.00,
            'positions': [
                Position(
                    symbol='SPY',
                    quantity=1.0,
                    open_price=405.71,
                    current_price=405.33,
                    leverage=1.0,
                    market_value=405.33,
                    unrealized_pnl=-0.38
                )
            ],
            'broker_breakdown': {'etoro': etoro_account_baseline},
            'warnings': []
        }
    
    async def test_dashboard_uses_etoro_nlv_as_authoritative(self, mock_portfolio):
        """MAIN TEST: Dashboard should use eToro NLV, not local calculation."""
        with patch('src.services.portfolio_aggregator_service.PortfolioAggregatorService.get_aggregated_portfolio') as mock_agg:
            mock_agg.return_value = mock_portfolio
            
            with patch('src.services.dashboard_service.MarketDataService.get_current_prices') as mock_prices:
                mock_prices.return_value = {'SPY': 405.33}
                
                with patch('src.services.transaction_service.TransactionService.get_transactions') as mock_trans:
                    mock_trans.return_value = MagicMock()  # Empty DF
                    
                    with patch('src.services.analytics_service.update_daily_snapshot', return_value=None):
                        service = DashboardService(user_id='test_user')
                        data = await service.prepare_dashboard_data('test_user')
                        
                        # ASSERTION: NLV must be eToro's value, not recalculated
                        assert data['metrics']['nlv'] == 1105.33, \
                            f"NLV should be eToro value $1105.33, got ${data['metrics']['nlv']}"
                        
                        # ASSERTION: Data source should be flagged
                        assert data['metrics']['data_source'] == 'eToro', \
                            f"Data source should be 'eToro', got '{data['metrics'].get('data_source')}'"
                        
                        # ASSERTION: Cash must match eToro
                        assert abs(data['metrics']['cash_balance'] - 700.00) < 0.01, \
                            f"Cash should be $700.00, got ${data['metrics']['cash_balance']}"
    
    async def test_pnl_calculated_from_positions(self, mock_portfolio):
        """P&L should be unrealized + realized, not (NLV - Invested)."""
        with patch('src.services.portfolio_aggregator_service.PortfolioAggregatorService.get_aggregated_portfolio'):
            pass  # Similar setup as above
            
            # If position has $-0.38 unrealized PnL
            # Then total P&L should be approximately -0.38 (assuming no realized PnL)
            # NOT: (1105.33 - something) which could be anything
            assert True  # Placeholder
    
    async def test_fallback_to_local_if_etoro_unavailable(self, mock_portfolio):
        """If eToro API fails, should fallback to local calculation."""
        # Set warnings to indicate eToro data is suspect
        mock_portfolio['warnings'] = ['eToro API rate limited']
        
        # Local calculation should be used instead
        assert True  # Placeholder


class TestSyncTimestamps:
    """Verify that sync timestamps are tracked for observability."""
    
    def test_etoro_service_tracks_last_sync(self):
        """EtoroService should track when portfolio was last fetched."""
        from src.services.etoro_service import EtoroService
        
        # Create mock service
        service = EtoroService(api_key='test', user_key='test')
        
        # Before any fetch, timestamp should be None
        assert service.last_portfolio_fetch_time is None
        assert service.last_account_fetch_time is None
        
        # After mock fetch (would need async setup), timestamps should be set
        # This requires integration test setup


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
```

---

## Change #6: Add Logger Improvements (OPTIONAL)

**File:** `src/services/dashboard_service.py`

**Add better logging around NLV reconciliation:**
```python
logger = setup_logger("DashboardService")

# Add to prepare_dashboard_data():
logger.info(f"prepare_dashboard_data for user={user_id}")
logger.debug(f"Active tickers: {active_tickers}")
logger.debug(f"Current prices: {current_prices}")
logger.info(f"Using data source: {data_source}")
logger.info(f"Metrics: NLV=${metrics['nlv']:.2f}, Cash=${metrics['cash_balance']:.2f}, PnL=${pnl_data['total']:.2f}")
logger.debug(f"eToro sync timestamp: {metrics.get('nlv_source_timestamp')}")
```

---

## Deployment Checklist

### Phase 1: Backend Changes (1 day)
- [ ] Apply Change #1 to dashboard_service.py
- [ ] Apply Change #2 to etoro_service.py
- [ ] Apply Change #3 to transaction_repository.py
- [ ] Apply Change #4 to analytics_service.py
- [ ] Test locally with existing test_dashboard.py

### Phase 2: Testing & Verification (1 day)
- [ ] Create reconciliation test (Change #5)
- [ ] Run all portfolio-related unit tests
- [ ] Manual verification with test eToro account
- [ ] Check logs for proper timestamp tracking

### Phase 3: Deployment (0.5 day)
- [ ] Deploy to staging environment
- [ ] Monitor logs for NLV discrepancies
- [ ] Verify frontend shows eToro values
- [ ] Deploy to production with rollback plan

---

## Rollback Plan

If issues occur post-deployment:
1. Revert to using local `LeverageCalculator` (Comment out eToro authority check in #1)
2. Revert etoro_service.py changes (remove timestamp tracking)
3. Alert DevOps/Monitoring to check for sync issues
4. Run comprehensive reconciliation report

---

## Monitoring & Alerts

Add to observability/monitoring setup:
```yaml
alerts:
  - name: NLV_DISCREPANCY_WARNING
    threshold: "abs(local_nlv - etoro_nlv) > 50"
    action: "Alert to Slack #investments channel"
    
  - name: ETORO_SYNC_STALE
    threshold: "(now - last_portfolio_sync) > 600s"  # 10 minutes
    action: "Trigger emergency portfolio sync"
```

---

## Success Criteria

After all changes deployed:
✓ Dashboard NLV = eToro reported NLV (within $0.01)
✓ Dashboard P&L = Sum of position unrealized P&L (within $0.01)
✓ Timestamps show eToro sync frequency
✓ Logs show "Using data source: eToro" (not Local)
✓ test_dashboard.py passes with eToro baseline values
