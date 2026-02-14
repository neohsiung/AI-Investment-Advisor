
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime

class BrokerType(Enum):
    ETORO = "etoro"
    FUTU = "futu"
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

@dataclass
class Order:
    symbol: str
    action: OrderAction
    quantity: float
    price: Optional[float] = None
    order_type: OrderType = OrderType.MARKET
    leverage: int = 1
    reason: str = ""

@dataclass
class Position:
    symbol: str
    quantity: float
    open_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    open_date: Optional[datetime] = None

@dataclass
class Account:
    broker_type: BrokerType
    account_id: str
    total_equity: float
    available_cash: float
    currency: str = "USD"
    maintenance_margin: float = 0.0
    day_trades_remaining: int = 3 # For PDT rules
