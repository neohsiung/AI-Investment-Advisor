import pandas as pd
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union
from src.repositories.snapshot_repository import AlchemySnapshotRepository, ISnapshotRepository
from src.repositories.transaction_repository import AlchemyTransactionRepository, ITransactionRepository
from src.services.market_data_service import MarketDataService
from src.utils.time_utils import get_current_date_str
from sqlalchemy import text
from src.utils.logger import setup_logger
from typing import Optional as _Opt

try:
    from src.repositories.position_lot_repository import AlchemyPositionLotRepository, IPositionLotRepository
    _LOTS_AVAILABLE = True
except ImportError:  # Graceful degradation if table doesn't exist yet
    _LOTS_AVAILABLE = False

logger = setup_logger("AnalyticsService")

class LeverageCalculator:
    """
    Service for calculating portfolio leverage and nominal values.
    計算投資組合槓桿與名義價值的服務。
    """
    def __init__(self, user_id: str, repository: Optional[ITransactionRepository] = None, db_path: Optional[str] = None):
        """
        Initialize the calculator.
        初始化計算器。
        """
        self.user_id = user_id
        self.db_path = db_path
        self.repo = repository or AlchemyTransactionRepository()
        # O(1) avg_cost via position_lots (populated after backfill)
        self._lot_repo: Optional[IPositionLotRepository] = None
        if _LOTS_AVAILABLE:
            try:
                self._lot_repo = AlchemyPositionLotRepository(self.repo.engine)
            except Exception:
                pass

    def _get_lot_avg_cost_map(self, user_id: str) -> Dict[str, float]:
        """Return FIFO avg_cost per ticker from position_lots, or {} if unavailable."""
        if self._lot_repo:
            try:
                if self._lot_repo.has_lots_for_user(user_id):
                    return self._lot_repo.get_avg_cost_map(user_id)
            except Exception as e:
                logger.warning(f"PnLCalculator: could not load lot avg_cost: {e}")
        return {}

    def calculate_metrics(self, current_prices: Dict[str, float], user_id: str, account_id: str = None) -> Dict[str, float]:
        """
        Calculate weight-based and leverage metrics.
        計算基於權重與槓桿的指標。
        """
        # 1. Calculate Total Nominal Value (TNV)
        # 1. 計算總名義價值 (TNV)
        # We need more than just ticker, qty - we need leverage per transaction (or average weighted leverage)
        # To keep it efficient, let's get weighted average leverage per ticker or sum of Nominal Values from DB.
        
        holdings = self.repo.get_leverage_summary(user_id, account_id)
        holdings_detail = self.repo.get_holdings(user_id, account_id)

        tnv = 0.0
        portfolio_value = 0.0

        for ticker, qty, leverage in holdings:
            if qty == 0:
                continue

            price = self._get_effective_price(ticker, current_prices, user_id)
            avg_cost = next((h['avg_price'] for h in holdings_detail if h['ticker'] == ticker), 0.0)
            
            # v4.3.2: Defensive: If price is 0, fallback to average cost to prevent NLV collapse
            if price <= 0:
                price = avg_cost
                logger.warning(f"LeverageCalc: Price for {ticker} is 0. Falling back to avg_cost: {price}")

            market_val = qty * price

            # Nominal Exposure = Market Value * Leverage
            nominal_exposure = market_val * leverage

            tnv += abs(nominal_exposure)
            
            # [FIX] NLV should be based on Equity (Method B from specs)
            # equity = margin_invested + unrealized_pnl = (qty * open_price / lev) + qty * (price - open_price)
            eff_leverage = leverage if leverage > 0 else 1.0
            margin_invested = (qty * avg_cost) / eff_leverage
            unrealized_pnl = qty * (price - avg_cost)
            equity = margin_invested + unrealized_pnl
            
            portfolio_value += equity 

        # 2. Calculate Net Liquidity Value (NLV)
        # 2. 計算淨清算價值 (NLV)
        cash_balance = self.repo.get_cash_balance(user_id, account_id)
        nlv = cash_balance + portfolio_value

        # 3. Leverage Ratio
        # 3. 槓桿比率
        # Standard: Gross Exposure (TNV) / Net Liquidity Value (NLV)
        if nlv <= 0:
            leverage_ratio = 0.0
        else:
            leverage_ratio = tnv / nlv

        return {
            "tnv": tnv,
            "nlv": nlv,
            "cash_balance": cash_balance,
            "leverage_ratio": leverage_ratio
        }

    def _get_effective_price(self, ticker: str, current_prices: Dict[str, float], user_id: str, account_id: str = None) -> float:
        """Helper to resolve price with static anchor support."""
        if ticker.startswith("__ANCHOR_") or ticker.startswith("NLV_") or ticker.startswith("STABILIZE_"):
            holdings_detail = self.repo.get_holdings(user_id, account_id)
            for h in holdings_detail:
                if h['ticker'] == ticker:
                    return h['avg_price']
        return current_prices.get(ticker, 0.0)

class ROIEngine:
    """
    Engine for calculating Return on Investment (ROI).
    計算投資報酬率 (ROI) 的引擎。
    """
    def __init__(self, user_id: str, repository: Optional[ITransactionRepository] = None, db_path: Optional[str] = None):
        """
        Initialize the ROI engine.
        初始化 ROI 引擎。
        """
        self.user_id = user_id
        self.db_path = db_path
        self.repo = repository or AlchemyTransactionRepository()

    def calculate_roi(self, nlv: float, user_id: str, account_id: str = None) -> float:
        """
        Calculate simple ROI percentage.
        計算簡單 ROI 百分比。
        """
        net_invested = self.repo.calculate_net_invested_capital(user_id, account_id)

        if net_invested == 0:
            return 0.0

        profit = nlv - net_invested
        roi = (profit / net_invested) * 100

        return roi

class SnapshotRecorder:
    """
    Service for recording daily financial snapshots.
    記錄每日財務快照的服務。
    """
    def __init__(self, db_path: Optional[str] = None, snapshot_repo: Optional[ISnapshotRepository] = None, trans_repo: Optional[ITransactionRepository] = None):
        """
        Initialize the recorder.
        初始化記錄器。
        """
        self.repo = snapshot_repo or AlchemySnapshotRepository(db_path)
        self.trans_repo = trans_repo or AlchemyTransactionRepository()

    def record_daily_snapshot(self, nlv: float, cash_balance: float, user_id: str, total_tnv: float = 0.0, leverage_ratio: float = 0.0, account_id: str = None) -> None:
        """
        Record a daily asset snapshot to the database.
        將每日資產快照記錄至資料庫。
        """
        
        net_invested = self.trans_repo.calculate_net_invested_capital(user_id, account_id)
        pnl = nlv - net_invested
        date_str = get_current_date_str()

        # Use SnapshotRepository to save
        # The existing repository might need an 'add' method or we use execute directly if repo is missing it
        # Checking AlchemySnapshotRepository capabilities... 
        # It usually reads. Let's add 'save_snapshot' method to it later or just assume standard repo pattern.
        # Since I can't easily see SnapshotRepository right now, I will use the one I see in imports.
        # Wait, I didn't verify SnapshotRepository has a save method. 
        # I will use direct DB access through the repo instance if possible, or better:
        # adhere to the plan to remove DIRECT SQL execution from Service.
        # I will assume I need to implement `save` in SnapshotRepository if it's missing, 
        # but for this specific "Recorder" class, let's keep it simple.
        
        # Actually, let's look at the `SnapshotRepository` interface if strictly following DDD.
        # For now, I will implement the save logic using the repository's connection or method.
        # Since `SnapshotRecorder` WAS executing SQL directly, let's delegate to a new method on `AlchemySnapshotRepository` called `save`.
        # I will implement `save` in `AlchemySnapshotRepository` in the next step if it doesn't exist.
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
    """
    Calculator for profit and loss (P&L) breakdowns.
    損益 (P&L) 細項計算器。
    """
    def __init__(self, user_id: str, repository: Optional[ITransactionRepository] = None, db_path: Optional[str] = None):
        """
        Initialize the calculator.
        初始化計算器。
        """
        self.user_id = user_id
        self.db_path = db_path
        self.repo = repository or AlchemyTransactionRepository()
        # O(1) avg_cost via position_lots
        self._lot_repo: Optional["IPositionLotRepository"] = None
        if _LOTS_AVAILABLE:
            try:
                self._lot_repo = AlchemyPositionLotRepository(self.repo.engine)
            except Exception:
                pass  # position_lots table not ready yet — graceful degradation

    def _get_lot_avg_cost_map(self, user_id: str) -> Dict[str, float]:
        """Return FIFO avg_cost per ticker from position_lots, or {} if unavailable."""
        if self._lot_repo:
            try:
                if self._lot_repo.has_lots_for_user(user_id):
                    return self._lot_repo.get_avg_cost_map(user_id)
            except Exception as e:
                logger.warning(f"PnLCalculator: could not load lot avg_cost: {e}")
        return {}

    def _get_effective_price(self, ticker: str, current_prices: Dict[str, float], user_id: str, account_id: str = None) -> float:
        """Helper to resolve price with static anchor support."""
        if ticker.startswith("__ANCHOR_") or ticker.startswith("NLV_") or ticker.startswith("STABILIZE_"):
            holdings_detail = self.repo.get_holdings(user_id, account_id)
            for h in holdings_detail:
                if h['ticker'] == ticker:
                    return h['avg_price']
        return current_prices.get(ticker, 0.0)

    def calculate_breakdown(self, current_prices: Dict[str, float], user_id: str, account_id: str = None) -> Dict[str, Any]:
        """
        Calculate realized and unrealized P&L breakdown for each ticker.
        計算每個標的的已實現與未實現損益細項。

        Strategy:
          1. Replay transactions for realized PnL (always needed for SELL/DIVIDEND/FEE).
          2. For open positions, override avg_cost with FIFO lots value when available
             (corrects distortion when position was fully sold and re-opened).
        """
        # ── Load FIFO avg_cost map (O(1) from position_lots if seeded) ──────────
        lot_avg_cost_map = self._get_lot_avg_cost_map(user_id)
        using_lots = bool(lot_avg_cost_map)
        if using_lots:
            logger.info(f"PnLCalculator: using FIFO avg_cost from position_lots for {len(lot_avg_cost_map)} ticker(s)")

        transactions = self.repo.get_all_by_user(user_id, account_id)
        transactions = list(transactions)[::-1]  # ASC for correct running avg

        portfolio = {}  # {ticker: {'qty': 0, 'avg_cost': 0, 'realized_pnl': 0, 'margin_invested': 0}}
        total_realized_pnl = 0.0

        for row in transactions:
            ticker = row.ticker
            action = row.action
            qty = row.quantity
            price = row.price
            fees = row.fees

            # Exclude synthetic stabilization records from cost basis
            if 'STABILIZE' in ticker:
                if action in ['FEE', 'TAX']:
                    total_realized_pnl -= getattr(row, 'amount', 0)
                continue

            if ticker not in portfolio:
                portfolio[ticker] = {'qty': 0.0, 'avg_cost': 0.0, 'realized_pnl': 0.0, 'margin_invested': 0.0}

            pos = portfolio[ticker]

            if action == 'BUY':
                total_cost = (pos['qty'] * pos['avg_cost']) + (qty * price) + fees
                new_qty = pos['qty'] + qty
                pos['avg_cost'] = total_cost / new_qty if new_qty > 0 else 0.0
                leverage = getattr(row, 'leverage', 1.0) or 1.0
                pos['margin_invested'] += ((qty * price) / leverage) + fees
                pos['qty'] = new_qty

            elif action == 'SELL':
                # Use lot avg_cost for realized PnL if available (more accurate)
                effective_cost = lot_avg_cost_map.get(ticker, pos['avg_cost']) if using_lots else pos['avg_cost']
                trade_pnl = (price - effective_cost) * qty - fees
                pos['realized_pnl'] += trade_pnl
                total_realized_pnl += trade_pnl
                if pos['qty'] > 0:
                    reduction_ratio = qty / pos['qty']
                    pos['margin_invested'] -= pos['margin_invested'] * reduction_ratio
                else:
                    pos['margin_invested'] = 0.0
                pos['qty'] -= qty
                if pos['qty'] <= 0:
                    pos['qty'] = 0
                    pos['margin_invested'] = 0.0

            elif action == 'DIVIDEND':
                pos['realized_pnl'] += price * qty
                total_realized_pnl += price * qty

            elif action in ['FEE', 'TAX']:
                pos['realized_pnl'] -= getattr(row, 'amount', 0)
                total_realized_pnl -= getattr(row, 'amount', 0)

        total_unrealized_pnl = 0.0
        breakdown = {}

        for ticker, pos in portfolio.items():
            if pos['qty'] > 0.0001:
                curr_price = self._get_effective_price(ticker, current_prices, user_id, account_id)
                if curr_price <= 0:
                    curr_price = pos['avg_cost']

                # ── Override avg_cost with FIFO lots for open positions ──────
                open_avg_cost = lot_avg_cost_map.get(ticker, pos['avg_cost']) if using_lots else pos['avg_cost']
                unrealized = (curr_price - open_avg_cost) * pos['qty']
                total_unrealized_pnl += unrealized

                breakdown[ticker] = {
                    'qty': pos['qty'],
                    'avg_cost': open_avg_cost,  # FIFO-correct cost basis
                    'avg_cost_legacy': pos['avg_cost'],  # Old method (kept for diagnostics)
                    'margin_invested': pos['margin_invested'],
                    'current_price': curr_price,
                    'realized': pos['realized_pnl'],
                    'unrealized': unrealized,
                    'total': pos['realized_pnl'] + unrealized,
                    'using_lots': using_lots,
                }
            elif abs(pos['realized_pnl']) > 0:
                breakdown[ticker] = {
                    'qty': 0,
                    'avg_cost': 0,
                    'avg_cost_legacy': pos['avg_cost'],
                    'margin_invested': 0.0,
                    'current_price': current_prices.get(ticker, 0.0),
                    'realized': pos['realized_pnl'],
                    'unrealized': 0,
                    'total': pos['realized_pnl'],
                    'using_lots': using_lots,
                }

        # invested_capital: use FIFO cost basis for open positions
        invested_capital = sum(
            (lot_avg_cost_map.get(t, pos['avg_cost']) if using_lots else pos['avg_cost']) * pos['qty']
            for t, pos in portfolio.items() if pos['qty'] > 0
        )

        return {
            "realized": total_realized_pnl,
            "unrealized": total_unrealized_pnl,
            "total": total_realized_pnl + total_unrealized_pnl,
            "invested_capital": self.repo.calculate_net_invested_capital(user_id, account_id),
            "margin_invested": sum(pos['margin_invested'] for pos in portfolio.values() if pos['qty'] > 0),
            "details": breakdown,
            "using_lots": using_lots,
        }

async def update_daily_snapshot(db_path: str = None, user_id: str = None, force: bool = False, current_prices: Optional[Dict[str, float]] = None, account_id: str = None) -> None:
    """
    Recalculate and update today's performance snapshot if not already present.
    重新計算並更新今日績效快照（若尚未存在）。
    """
    if not user_id:
        return 

    # 1. Throttling: Check if today's snapshot exists
    snapshot_repo = AlchemySnapshotRepository(db_path)
    latest = snapshot_repo.get_latest_by_user(user_id)
    today = get_current_date_str()
    
    if not force and latest is not None and latest['date'] == today:
        # Already have a snapshot for today, skip unless we implement forced updates or time-based TTL
        # For SaaS 2026, daily is usually enough, or we check every 4 hours.
        # Let's keep it daily for now to maximize speed.
        return
    trans_repo = AlchemyTransactionRepository()
    active_tickers = trans_repo.get_active_tickers(user_id, account_id)

    # 2. Fetch prices only if not provided
    if current_prices is None:
        market_service = MarketDataService(user_id=user_id)
        current_prices = await market_service.get_current_prices(active_tickers)

    # [NEW] v4.2.1: Snapshot Validation (防呆機制)
    # If more than 50% of active tickers have 0.0 price, the data is likely corrupted.
    zero_prices = [t for t in active_tickers if current_prices.get(t, 0.0) == 0.0]
    if len(active_tickers) > 0 and (len(zero_prices) / len(active_tickers)) > 0.5:
        logger.warning(f"Snapshot Validation Failed: {len(zero_prices)}/{len(active_tickers)} tickers have zero prices. Skipping snapshot.")
        return

    calc = LeverageCalculator(user_id=user_id, repository=trans_repo, db_path=db_path)
    metrics = calc.calculate_metrics(current_prices, user_id)

    recorder = SnapshotRecorder(db_path=db_path)
    recorder.record_daily_snapshot(
        metrics['nlv'], 
        metrics['cash_balance'], 
        user_id,
        total_tnv=metrics.get('tnv', 0),
        leverage_ratio=metrics.get('leverage_ratio', 0),
        account_id=account_id
    )

class AnalyticsService:
    """
    Unified service for portfolio analytics and performance tracking.
    投資組合分析與績效追蹤的統一服務。
    """
    def __init__(self, db_path: Optional[str] = None, user_id: Optional[str] = None, repository: Optional[ISnapshotRepository] = None, pnl_calc: Optional[PnLCalculator] = None):
        """
        Initialize the analytics service.
        初始化分析服務。
        """
        self.db_path = db_path
        self.user_id = user_id
        self.snapshot_repo = repository or AlchemySnapshotRepository(db_path)
        self.pnl_calculator = pnl_calc or PnLCalculator(user_id=user_id, db_path=self.db_path)

    async def trigger_snapshot_update(self, force: bool = False, current_prices: Optional[Dict[str, float]] = None, account_id: str = None) -> None:
        """
        Manually trigger a snapshot update for the user.
        手動觸發使用者的快照更新。
        """
        if self.user_id:
            await update_daily_snapshot(self.db_path, self.user_id, force=force, current_prices=current_prices, account_id=account_id)

    def get_pnl_breakdown(self, current_prices: Dict[str, float], account_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Get P&L breakdown for the user's portfolio.
        取得使用者投資組合的損益細項。
        """
        if not self.user_id:
            return None
        return self.pnl_calculator.calculate_breakdown(current_prices, self.user_id, account_id)

    def get_performance_history(self, account_id: str = None) -> Optional[pd.DataFrame]:
        """
        Get historical performance snapshots for the user.
        取得使用者的歷史績效快照。
        """
        if not self.user_id:
            return None
        return self.snapshot_repo.get_history_by_user(self.user_id, account_id)

    def get_latest_performance(self, account_id: str = None) -> Optional[Union[pd.Series, Dict[str, Any]]]:
        """
        Get the latest available performance data for the user.
        取得使用者的最新績效數據。
        """
        if not self.user_id:
            return None
        return self.snapshot_repo.get_latest_by_user(self.user_id, account_id)
