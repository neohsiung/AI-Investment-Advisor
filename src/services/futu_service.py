
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import time

from src.domain.broker import IBroker
from src.domain.trading import Order, Position, Account, BrokerType, OrderAction, OrderType
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.infrastructure.risk_manager import RiskManager

logger = logging.getLogger(__name__)

# Try import futu, handle missing dependency for optional components
try:
    from futu import (
        OpenQuoteContext, OpenTradeContext, TrdSide, TrdEnv, 
        TrdMarket, SecurityFamily, RET_OK, TrdFilterConditions, SortDir
    )
    FUTU_AVAILABLE = True
except ImportError:
    FUTU_AVAILABLE = False
    logger.warning("Futu API not installed. FutuService will not function properly.")

class FutuService(IBroker):
    """
    Futu (FutuOpenD) Broker Implementation.
    富途 (FutuOpenD) 證券商實作。
    
    Requires FutuOpenD running locally or remotely.
    需要 FutuOpenD 在本機或遠端運行。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 11111, is_sim: bool = False, pwd: str = None, user_id: str = None) -> None:
        """
        Initialize the Futu service.
        初始化富途服務。
        """
        self.host = host
        self.port = port
        self.is_sim = is_sim
        self.pwd = pwd
        self.user_id = user_id
        self.transaction_repo = AlchemyTransactionRepository()
        self.risk_manager = RiskManager()
        self.name = "Futu"
        
        self.trd_ctx = None
        self.quote_ctx = None
        
        if FUTU_AVAILABLE:
            try:
                # Initialize Contexts
                # Connect to US Stock Market by default for now
                self.trd_ctx = OpenTradeContext(host=self.host, port=self.port, is_profile_trd_market=False, security_firm=SecurityFamily.FUTU_SECURITIES)
                # self.quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
                logger.info(f"Futu Context Initialized: {host}:{port}")
            except Exception as e:
                logger.error(f"Failed to connect to FutuOpenD: {e}")

    def get_name(self) -> str:
        return self.name

    def _get_trd_env(self) -> Any:
        """
        Determine the trading environment (Simulate or Real).
        確定交易環境（模擬或真實）。
        """
        return TrdEnv.SIMULATE if self.is_sim else TrdEnv.REAL

    def get_account(self) -> Optional[Account]:
        if not self.trd_ctx:
            logger.warning("Futu Context not connected.")
            return None

        try:
            ret, data = self.trd_ctx.accinfo_query(trd_env=self._get_trd_env())
            if ret != RET_OK:
                logger.error(f"Futu AccInfo Error: {data}")
                return None
            
            # Data is a DataFrame
            # Typically returns one row per currency/market
            # We filter for USD or summarize
            usd_row = data[data['currency'] == 'USD']
            if usd_row.empty:
                # Fallback to first row
                row = data.iloc[0]
            else:
                row = usd_row.iloc[0]

            total_assets = float(row.get('total_assets', 0))
            cash = float(row.get('cash', 0))
            
            return Account(
                broker_type=BrokerType.FUTU,
                account_id=str(row.get('acc_id', 'unknown')),
                total_equity=total_assets,
                available_cash=cash,
                currency="USD"
            )
        except Exception as e:
            logger.error(f"Get Account Exception: {e}")
            return None

    def get_positions(self) -> List[Position]:
        if not self.trd_ctx:
            return []

        try:
            ret, data = self.trd_ctx.position_list_query(trd_env=self._get_trd_env())
            if ret != RET_OK:
                logger.error(f"Futu Position Error: {data}")
                return []
            
            positions = []
            for _, row in data.iterrows():
                # Map Futu Row to Position
                # Fields: code, stock_name, qty, cost_price, nominal_price, pl_val
                qty = float(row.get('qty', 0))
                if qty == 0: continue

                pos = Position(
                    symbol=row.get('code', 'UNKNOWN'),
                    quantity=qty,
                    open_price=float(row.get('cost_price', 0)),
                    current_price=float(row.get('nominal_price', 0)), # or 'cur_price'
                    market_value=float(row.get('market_val', 0)),
                    unrealized_pnl=float(row.get('pl_val', 0)),
                    open_date=None # Futu position doesn't give simple open date, aggregate
                )
                positions.append(pos)
            return positions
        except Exception as e:
            logger.error(f"Get Positions Exception: {e}")
            return []

    def get_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch Trade History.
        """
        if not self.trd_ctx:
            return []
            
        try:
            # history_order_list_query
            # Filter status: FILLED_ALL, FILLED_PART
            # Start/End date
            end = datetime.now()
            # start = end - timedelta(days=days) 
            # Futu date format string
            
            ret, data = self.trd_ctx.history_order_list_query(
                status_filter_list=[
                    # TrdOrderStatus.FILLED_ALL, TrdOrderStatus.FILLED_PART 
                    # Use constants if available, or fetch all and filter
                ],
                trd_env=self._get_trd_env()
            )
            
            if ret != RET_OK:
                return []
                
            history = []
            for _, row in data.iterrows():
                # Convert to dict
                history.append(row.to_dict())
            return history
        except Exception as e:
            logger.error(f"Get History Exception: {e}")
            return []

    def execute_order(self, order: Order) -> Dict[str, Any]:
        """
        Place Order.
        """
        if not FUTU_AVAILABLE or not self.trd_ctx:
             return {"status": "failed", "reason": "Futu Context Offline"}

        # 1. Risk Check
        user_id = self.user_id or "default_user"
        history = self.get_history()
        positions = self.get_positions()
        
        if not self.risk_manager.check_constraints(user_id, history, positions):
             return {"status": "failed", "reason": "Risk Manager Blocked"}

        # 2. Map Constants
        trd_side = TrdSide.BUY if order.action == OrderAction.BUY else TrdSide.SELL
        # Order Type logic (default market)
        # futu-api typically requires price for limit, adjust if market is different
        # For simplicity, using MARKET if simulated, validation needed for real
        
        # 3. Unlock Trade (If needed)
        # self.trd_ctx.unlock_trade(password='...') # Warning: Security Risk. 
        # Rely on FutuOpenD being unlocked or session duration.
        
        try:
            logger.info(f"FUTU PLACE ORDER: {order.action.value} {order.symbol} Qty={order.quantity}")
            
            # price=100.0 is dummy for market order usually, or 0? Check docs.
            # Using 0 for market order in some APIs, but Futu might require adjust_limit
            
            ret, data = self.trd_ctx.place_order(
                price=order.price if order.price else 0.0,
                qty=order.quantity,
                code=order.symbol,
                trd_side=trd_side,
                trd_env=self._get_trd_env()
                # order_type=OrderType.NORMAL # Limit
                # adjust_limit=0 # for Market?
            )
            
            if ret != RET_OK:
                 logger.error(f"Futu Order Failed: {data}")
                 return {"status": "error", "message": data}
            
            # data is DataFrame with order_id
            order_id = data.iloc[0]['order_id']
            return {"status": "executed", "order_id": str(order_id)}
            
        except Exception as e:
            logger.error(f"Futu Exec Exception: {e}")
            return {"status": "error", "error": str(e)}
    
    def sync_history(self, user_id: str = "default_user") -> Dict[str, int]:
        """
        Sync external history to local DB.
        """
        history = self.get_history()
        if not history:
             return {"added": 0, "skipped": 0}
             
        added_count = 0
        skipped_count = 0
        
        # Deduplication Strategy
        existing_txs = self.transaction_repo.get_all_by_user(user_id)
        existing_sigs = set()
        for tx in existing_txs:
            try:
                sig = f"{tx.ticker}_{tx.trade_date}_{tx.action}_{float(tx.quantity):.4f}_{float(tx.price):.4f}"
                existing_sigs.add(sig)
            except Exception: continue

        for trade in history:
            # Map Futu History Row to Transaction
            # Expected columns from history_order_list_query: 'code', 'stock_name', 'txn_id'?, 'create_time', 'updated_time', 'dealt_avg_price', 'dealt_qty', 'trd_side'
            
            ticker = trade.get('code', 'UNKNOWN')
            # Use updated_time as trade date
            date_str = trade.get('updated_time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            # Format to just YYYY-MM-DD for consistency? or full timestamp? 
            # System uses flexible string currently.
            
            side = trade.get('trd_side', 'BUY') # futu returns enum or string? usually string like 'BUY'/'SELL' in dict
            action = str(side).upper().replace('TRDSIDE.', '') # Clean up if it's enum str
            
            quantity = float(trade.get('dealt_qty', 0))
            price = float(trade.get('dealt_avg_price', 0))
            # Fees calculation might need 'order_fee_struct' parsing
            fees = 0.0 
            
            sig = f"{ticker}_{date_str}_{action}_{quantity:.4f}_{price:.4f}"
            
            if sig in existing_sigs:
                skipped_count += 1
                continue
            
            self.transaction_repo.add(
                user_id=user_id,
                ticker=ticker,
                date=date_str,
                action=action,
                quantity=quantity,
                price=price,
                fees=fees
            )
            added_count += 1
            
        logger.info(f"Futu Sync: Added {added_count}, Skipped {skipped_count}")
        return {"added": added_count, "skipped": skipped_count}

    def __del__(self):
        if self.trd_ctx:
            try:
                self.trd_ctx.close()
            except Exception: pass
        if self.quote_ctx:
            try:
                self.quote_ctx.close()
            except Exception: pass
