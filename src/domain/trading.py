
from dataclasses import dataclass
from enum import Enum
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime

class BrokerType(Enum):
    ETORO = "etoro"
    IBKR = "ibkr"
    US_GENERIC = "us_generic"
    MOCK = "mock"

class OrderAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"

class OrderSizingMode(str, Enum):
    AMOUNT = "AMOUNT"    # BUY: 以 USD 金額下單
    SHARES = "SHARES"    # SELL: 以股數下單

@dataclass
class Order:
    symbol: str
    action: OrderAction
    quantity: float
    price: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    leverage: int = 1
    amount_usd: Optional[float] = None       # 明確的 USD 金額（BUY 時使用）
    sizing_mode: OrderSizingMode = OrderSizingMode.AMOUNT  # 預設金額制
    reason: str = ""
    position_id: Optional[str] = None # For closing specific positions

@dataclass
class Position:
    symbol: str
    quantity: float
    open_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    open_date: Optional[datetime] = None
    leverage: float = 1.0
    position_id: Optional[str] = None # Added for eToro/IBKR specific closing

@dataclass
class Account:
    broker_type: BrokerType
    account_id: str
    total_equity: float
    available_cash: float
    currency: str = "USD"
    maintenance_margin: float = 0.0
    day_trades_remaining: int = 3 # For PDT rules
