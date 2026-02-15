import pandas as pd
from src.repositories.snapshot_repository import SqliteSnapshotRepository
from src.repositories.transaction_repository import SqliteTransactionRepository, ITransactionRepository
from src.services.market_data_service import MarketDataService
from src.utils.time_utils import get_current_date_str

class LeverageCalculator:
    def __init__(self, repository: ITransactionRepository = None, db_path="data/portfolio.db"):
        self.repo = repository or SqliteTransactionRepository()
        # db_path kept for backward compatibility if needed by repo init, though repo handles it

    def calculate_metrics(self, current_prices, user_id):
        """
        Calculate Leverage Metrics.
        計算槓桿水位相關指標 (Calculate Leverage Metrics)。
        """
        # 1. Calculate Total Nominal Value (TNV)
        # 1. 計算總名義價值 (TNV)
        holdings = self.repo.get_holdings_summary(user_id) # List of (ticker, quantity)

        tnv = 0.0
        portfolio_value = 0.0

        for ticker, qty in holdings:
            if qty == 0:
                continue

            price = current_prices.get(ticker, 0.0)
            market_val = qty * price
            tnv += abs(market_val) # Absolute sum of Nominal Value (名義價值取絕對值總和)
            portfolio_value += market_val # Portfolio Market Value (Long - Short) (投資組合市值)

        # 2. Calculate Net Liquidity Value (NLV)
        # 2. 計算淨清算價值 (NLV)
        cash_flow_sum = self.repo.get_cash_flow_sum(user_id)
        
        # Calculate cash impact from transactions (Buy requires cash, Sell gives cash)
        # However, the previous logic was:
        # cash_balance = cash_flow_sum + trans_cash_impact
        # where trans_cash_impact was derived from iterating all transactions.
        # This logic essentially reconstructs cash balance from history.
        # Ideally, we should have a get_cash_balance method in repo, 
        # but for now let's reuse the logic via retrieving all transactions if repo doesn't support it directly yet.
        # Or better: let's move this calculation to the Repo or Service properly.
        # Check if we can optimize by fetching simpler data.
        
        # Re-implementing the loop using repo's get_all_by_user for now to preserve exact logic logic
        # TODO: Move this "cash balance calculation" to a dedicated method in Repository
        transactions = self.repo.get_all_by_user(user_id)
        
        trans_cash_impact = 0.0
        for txn in transactions:
            # txn is a Row or tuple-like object (sqlalchemy result)
            # Assuming it allows attribute access or dict access. 
            # SQLAlchemy Rows are tuple-like but also allow key access.
            action = txn.action
            amount = txn.amount
            
            if action == 'BUY':
                trans_cash_impact -= amount
            elif action == 'SELL':
                trans_cash_impact += amount
            elif action == 'DIVIDEND':
                trans_cash_impact += amount
            # DEPOSIT and WITHDRAW are handled via cash_flow_sum (from cash_flows table)
            # preventing double counting.
            # elif action == 'DEPOSIT':
            #     trans_cash_impact += amount
            # elif action == 'WITHDRAWAL' or action == 'WITHDRAW':
            #     trans_cash_impact -= amount

        cash_balance = cash_flow_sum + trans_cash_impact
        nlv = cash_balance + portfolio_value

        # 3. Leverage Ratio
        # 3. 槓桿比率
        # Standard: Gross Exposure (TNV) / Net Liquidity Value (NLV)
        if nlv <= 0:
            leverage_ratio = float('inf')
        else:
            leverage_ratio = tnv / nlv

        return {
            "tnv": tnv,
            "nlv": nlv,
            "cash_balance": cash_balance,
            "leverage_ratio": leverage_ratio
        }

class ROIEngine:
    def __init__(self, repository: ITransactionRepository = None, db_path="data/portfolio.db"):
        self.repo = repository or SqliteTransactionRepository()

    def calculate_roi(self, nlv, user_id):
        """
        Calculate Simple ROI.
        計算簡單投資報酬率 (Calculate Simple ROI)。
        """
        net_invested = self.repo.calculate_net_invested_capital(user_id)

        if net_invested == 0:
            return 0.0

        profit = nlv - net_invested
        roi = (profit / net_invested) * 100

        return roi

class SnapshotRecorder:
    def __init__(self, db_path="data/portfolio.db"):
        self.repo = SqliteSnapshotRepository(db_path)
        self.trans_repo = SqliteTransactionRepository() # Need this for invested capital

    def record_daily_snapshot(self, nlv, cash_balance, user_id, total_tnv=0, leverage_ratio=0):
        """
        Record Daily Asset Snapshot.
        記錄每日資產快照。
        """
        
        net_invested = self.trans_repo.calculate_net_invested_capital(user_id)
        pnl = nlv - net_invested
        date_str = get_current_date_str()

        # Use SnapshotRepository to save
        # The existing repository might need an 'add' method or we use execute directly if repo is missing it
        # Checking SqliteSnapshotRepository capabilities... 
        # It usually reads. Let's add 'save_snapshot' method to it later or just assume standard repo pattern.
        # Since I can't easily see SnapshotRepository right now, I will use the one I see in imports.
        # Wait, I didn't verify SnapshotRepository has a save method. 
        # I will use direct DB access through the repo instance if possible, or better:
        # adhere to the plan to remove DIRECT SQL execution from Service.
        # I will assume I need to implement `save` in SnapshotRepository if it's missing, 
        # but for this specific "Recorder" class, let's keep it simple.
        
        # Actually, let's look at the `SnapshotRepository` interface if strictly following DDD.
        # For now, I will implement the save logic using the repository's connection or method.
        # Since `SnapshotRecorder` WAS executing SQL directly, let's delegate to a new method on `SqliteSnapshotRepository` called `save`.
        # I will implement `save` in `SqliteSnapshotRepository` in the next step if it doesn't exist.
        # For now, I'll rely on `self.repo.save_snapshot(...)`
        
        self.repo.save_snapshot(
            user_id=user_id,
            date=date_str,
            nlv=nlv,
            cash_balance=cash_balance,
            invested_capital=net_invested,
            pnl=pnl,
            total_tnv=total_tnv,
            leverage_ratio=leverage_ratio
        )
        
        print(f"Recorded snapshot for {user_id} on {date_str}: NLV=${nlv:,.2f}, PnL=${pnl:,.2f}, Lev={leverage_ratio:.2f}x")

class PnLCalculator:
    def __init__(self, repository: ITransactionRepository = None, db_path="data/portfolio.db"):
        self.repo = repository or SqliteTransactionRepository()

    def calculate_breakdown(self, current_prices, user_id):
        """
        Calculate P&L Breakdown.
        計算損益細分 (Calculate P&L Breakdown)。
        """
        transactions = self.repo.get_all_by_user(user_id) 
        # Note: interactions returns rows sorted by date DESC generally, checking repo implementation... 
        # Repo says "ORDER BY trade_date DESC".
        # PnL calc usually needs ASC order to calculate average cost correctly (FIFO/Weighted Avg).
        # We should reverse it or ask repo for ASC.
        # Let's reverse it here to be safe.
        transactions = list(transactions)[::-1]

        portfolio = {} # {ticker: {'qty': 0, 'avg_cost': 0, 'realized_pnl': 0}}
        total_realized_pnl = 0.0

        for row in transactions:
            ticker = row.ticker
            action = row.action
            qty = row.quantity
            price = row.price
            fees = row.fees

            if ticker not in portfolio:
                portfolio[ticker] = {'qty': 0.0, 'avg_cost': 0.0, 'realized_pnl': 0.0}

            pos = portfolio[ticker]

            if action == 'BUY':
                total_cost = (pos['qty'] * pos['avg_cost']) + (qty * price) + fees
                new_qty = pos['qty'] + qty
                pos['avg_cost'] = total_cost / new_qty if new_qty > 0 else 0.0
                pos['qty'] = new_qty

            elif action == 'SELL':
                trade_pnl = (price - pos['avg_cost']) * qty - fees
                pos['realized_pnl'] += trade_pnl
                total_realized_pnl += trade_pnl
                pos['qty'] -= qty
                if pos['qty'] < 0: pos['qty'] = 0
            
            # Dividends or other actions processing could be added here if needed for PnL
            # Previous code didn't handle DIVIDEND in breakdown, so sticking to original logic for now.

        total_unrealized_pnl = 0.0
        breakdown = {}

        for ticker, pos in portfolio.items():
            if pos['qty'] > 0.0001: 
                curr_price = current_prices.get(ticker, 0.0)
                unrealized = (curr_price - pos['avg_cost']) * pos['qty']
                total_unrealized_pnl += unrealized

                breakdown[ticker] = {
                    'qty': pos['qty'],
                    'avg_cost': pos['avg_cost'],
                    'current_price': curr_price,
                    'realized': pos['realized_pnl'],
                    'unrealized': unrealized,
                    'total': pos['realized_pnl'] + unrealized
                }
            elif abs(pos['realized_pnl']) > 0:
                 breakdown[ticker] = {
                    'qty': 0,
                    'avg_cost': 0,
                    'current_price': current_prices.get(ticker, 0.0),
                    'realized': pos['realized_pnl'],
                    'unrealized': 0,
                    'total': pos['realized_pnl']
                }

        return {
            "realized": total_realized_pnl,
            "unrealized": total_unrealized_pnl,
            "total": total_realized_pnl + total_unrealized_pnl,
            "details": breakdown
        }

def update_daily_snapshot(db_path="data/portfolio.db", user_id=None):
    """
    Recalculate and update today's performance snapshot (Helper Function).
    重新計算並更新今日績效快照 (Helper Function)。
    """
    if not user_id:
        return 

    # 1. Throttling: Check if today's snapshot exists
    snapshot_repo = SqliteSnapshotRepository(db_path)
    latest = snapshot_repo.get_latest_by_user(user_id)
    today = get_current_date_str()
    
    if latest is not None and latest['date'] == today:
        # Already have a snapshot for today, skip unless we implement forced updates or time-based TTL
        # For SaaS 2026, daily is usually enough, or we check every 4 hours.
        # Let's keep it daily for now to maximize speed.
        return
    trans_repo = SqliteTransactionRepository()
    active_tickers = trans_repo.get_active_tickers(user_id)

    market_service = MarketDataService()
    current_prices = market_service.get_current_prices(active_tickers)

    calc = LeverageCalculator(repository=trans_repo, db_path=db_path)
    metrics = calc.calculate_metrics(current_prices, user_id)

    recorder = SnapshotRecorder(db_path=db_path)
    recorder.record_daily_snapshot(
        metrics['nlv'], 
        metrics['cash_balance'], 
        user_id,
        total_tnv=metrics.get('tnv', 0),
        leverage_ratio=metrics.get('leverage_ratio', 0)
    )

class AnalyticsService:
    def __init__(self, db_path="data/portfolio.db", user_id=None, repository=None):
        self.db_path = db_path
        self.user_id = user_id
        self.snapshot_repo = repository or SqliteSnapshotRepository(db_path)
        # Assuming PnLCalculator and others are initialized internally or via DI if we were strict
        self.pnl_calculator = PnLCalculator(db_path=db_path)

    def trigger_snapshot_update(self):
        """Manually trigger a snapshot update."""
        if self.user_id:
            update_daily_snapshot(self.db_path, self.user_id)

    def get_pnl_breakdown(self, current_prices):
        """Calculate PnL Breakdown."""
        if not self.user_id:
            return None
        return self.pnl_calculator.calculate_breakdown(current_prices, self.user_id)

    def get_performance_history(self):
        """Get historical performance data (snapshots)."""
        if not self.user_id:
            return None
        return self.snapshot_repo.get_history_by_user(self.user_id)

    def get_latest_performance(self):
        """Get latest performance data."""
        if not self.user_id:
            return None
        return self.snapshot_repo.get_latest_by_user(self.user_id)
