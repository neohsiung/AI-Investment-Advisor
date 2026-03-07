import logging
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from collections import Counter
from src.services.etoro_service import EtoroService
from src.services.market_data_service import MarketDataService

logger = logging.getLogger(__name__)

class UserFocusService:
    """
    Service for extracting the user's investment focus (Sectors/Industries) from eToro Watchlists.
    使用者焦點服務：從 eToro 觀察名單中提取使用者的投資焦點（板塊/產業）。
    """
    
    def __init__(self, etoro_service: Optional[EtoroService] = None, market_data_service: Optional[MarketDataService] = None) -> None:
        """
        Initialize the UserFocusService with optional service overrides.
        初始化 UserFocusService，可選用自定義服務覆蓋。
        """
        self.etoro = etoro_service or EtoroService()
        self.market_data = market_data_service or MarketDataService()
        
    def get_user_focus(self, top_n: int = 3) -> Dict[str, Any]:
        """
        Analyzes watchlists to identify top sectors and industries of interest.
        分析觀察名單以識別最感興趣的板塊與產業。
        """
        try:
            watchlists = self.etoro.get_watchlists()
            if not watchlists:
                return {}
                
            all_tickers = set()
            
            # Extract tickers from all watchlists
            # Structure depends on API response. Assuming:
            # { "Watchlists": [ { "Items": [ { "InstrumentDisplayName": "AAPL" } ] } ] }
            # But get_watchlists returns json. Let's assume list of dicts or dict with list.
            # Official doc says GET /watchlists returns a list of Watchlist objects usually.
            
            # Defensive parsing based on common patterns
            raw_lists = watchlists if isinstance(watchlists, list) else watchlists.get('Watchlists', watchlists.get('watchlists', []))
            
            for wl in raw_lists:
                items = wl.get('Items', wl.get('items', []))
                for item in items:
                    # Item structure might contain 'InstrumentDisplayName' or 'Symbol'
                    # Or 'market' -> 'symbolName' (from debug output)
                    symbol = item.get('InstrumentDisplayName') or item.get('Symbol')
                    
                    if not symbol and 'market' in item:
                        symbol = item['market'].get('symbolName')
                        
                    if symbol:
                        all_tickers.add(symbol)
                        
            if not all_tickers:
                logger.info("No tickers found in watchlists.")
                return {}
                
            logger.info(f"Analyzing user focus from {len(all_tickers)} unique tickers...")
            
            # Fetch sector info
            # Utilize get_financials or get_market_context from MarketDataService?
            # get_financials gives 'sector' and 'industry'.
            
            sectors = []
            industries = []
            
            # Note: Batch fetching would be better but get_financials is single ticker.
            # We will limit to first 20 tickers to avoid rate limits if many.
            target_tickers = list(all_tickers)[:20]
            
            for ticker in target_tickers:
                try:
                    info = self.market_data.get_financials(ticker)
                    sec = info.get('sector')
                    ind = info.get('industry')
                    
                    if sec: sectors.append(sec)
                    if ind: industries.append(ind)
                except Exception as e:
                    logger.debug(f"Error fetching financials for {ticker}: {e}")
                    continue
                    
            top_sectors = [s for s, c in Counter(sectors).most_common(top_n)]
            top_industries = [i for i, c in Counter(industries).most_common(top_n)]
            
            focus_summary = {
                "top_sectors": top_sectors,
                "top_industries": top_industries,
                "source_count": len(target_tickers)
            }
            
            logger.info(f"User Focus Identified: {focus_summary}")
            return focus_summary
            
        except Exception as e:
            logger.error(f"Failed to analyze user focus: {e}")
            return {}
