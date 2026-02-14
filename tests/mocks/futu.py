
# Mock futu library for testing when it is not installed
from unittest.mock import MagicMock

class OpenTradeContext:
    def __init__(self, *args, **kwargs):
        pass
    def close(self):
        pass

class OpenQuoteContext:
    def __init__(self, *args, **kwargs):
        pass
    def close(self):
        pass

class TrdEnv:
    REAL = 0
    SIMULATE = 1

class TrdSide:
    BUY = "BUY"
    SELL = "SELL"
    
class OrderType:
    NORMAL = 0
    MARKET = 1

class SecurityFamily:
    FUTU_SECURITIES = 1

class SortDir:
    ASCEND = 0
    DESCEND = 1

class TrdFilterConditions:
    def __init__(self, *args, **kwargs):
        pass

class TrdMarket:
    US = 1
    HK = 2

RET_OK = 0
RET_ERROR = -1
