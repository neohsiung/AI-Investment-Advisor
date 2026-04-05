import pytz
import pandas as pd
import pandas_market_calendars as mcal
from datetime import datetime
from typing import Dict, Any

class MarketClock:
    """
    Professional Utility for US Market Hours and DST Handling.
    動態美股市場時鐘：處理夏令/冬令切換與交易所休市日。
    """
    
    def __init__(self, exchange_name: str = 'NYSE'):
        self.exchange_name = exchange_name
        self.nyse = mcal.get_calendar(exchange_name)
        self.tz = pytz.timezone('US/Eastern')

    def is_market_open(self, buffer_minutes: int = 0) -> bool:
        """
        Check if the market is currently open.
        檢查市場目前是否開市（含緩衝時間）。
        """
        now = datetime.now(pytz.utc)
        schedule = self.nyse.schedule(start_date=now.date(), end_date=now.date())
        
        if schedule.empty:
            return False
            
        market_open = schedule.iloc[0]['market_open']
        market_close = schedule.iloc[0]['market_close']
        
        # Apply buffer if needed (e.g. for pre-market checks)
        return (market_open - pd.Timedelta(minutes=buffer_minutes)) <= now <= market_close

    def get_market_status(self) -> Dict[str, Any]:
        """
        Get detailed US market status including DST information.
        獲取詳細市場狀態，包含夏令時切換資訊。
        """
        now = datetime.now(self.tz)
        is_dst = now.dst().total_seconds() != 0
        
        # Get next open
        today = datetime.now(pytz.utc).date()
        schedule = self.nyse.schedule(start_date=today, end_date=pd.Timestamp(today) + pd.Timedelta(days=7))
        
        next_session = schedule.iloc[0]
        is_open = self.is_market_open()
        
        return {
            "is_open": is_open,
            "is_dst": is_dst,
            "timezone": "US/Eastern",
            "current_time": now.isoformat(),
            "next_open": next_session['market_open'].isoformat(),
            "next_close": next_session['market_close'].isoformat(),
            "exchange": self.exchange_name
        }

    @classmethod
    def get_nyse_time(cls) -> datetime:
        """Helper to get current time in New York."""
        return datetime.now(pytz.timezone('US/Eastern'))
