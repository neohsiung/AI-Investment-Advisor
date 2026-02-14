
import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import os
import json

from src.domain.broker import IBroker
from src.domain.trading import Order, Position, Account, OrderAction, BrokerType
from src.repositories.transaction_repository import SqliteTransactionRepository
from src.infrastructure.risk_manager import RiskManager

logger = logging.getLogger(__name__)

class EtoroService(IBroker):
    """
    Etoro Broker Implementation.
    Wraps Etoro API and enforces Risk Management.
    Supports official Public API (api-portal.etoro.com).
    """

    def __init__(self, base_url: str = None, mode: str = "real", api_key: str = None, user_key: str = None):
        # Authentication (Priority: Arg > Env)
        self.api_key = api_key or os.getenv("ETORO_API_KEY")
        self.user_key = user_key or os.getenv("ETORO_USER_KEY")

        # Use official endpoint if keys are provided, else fallback to bridge for legacy support
        default_base = "https://public-api.etoro.com" if self.api_key else "http://localhost:8000"
        self.base_url = base_url or os.getenv("ETORO_API_BASE_URL", default_base)
        
        self.mode = mode  # 'real' or 'demo'
        self.transaction_repo = SqliteTransactionRepository()
        self.risk_manager = RiskManager()
        self.name = "eToro"
        self._id_to_symbol = {} # Reverse map: ID -> Ticker

    def get_name(self) -> str:
        return self.name

    def _get_headers(self) -> Dict[str, str]:
        """
        Construct headers for eToro API.
        Reference: https://api-portal.etoro.com/getting-started/authentication
        """
        import uuid
        headers = {
            "Content-Type": "application/json",
            "x-request-id": str(uuid.uuid4())
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
            headers["x-user-key"] = self.user_key
        return headers

    def get_account(self) -> Optional[Account]:
        """
        Fetch Account Summary (Equity, Cash).
        """
        portfolio = self._fetch_portfolio_raw()
        if not portfolio:
            return None
        
        # Handle clientPortfolio (Credit = Cash)
        if 'clientPortfolio' in portfolio:
             cp = portfolio['clientPortfolio']
             try:
                 cash = float(cp.get('credit', 0))
                 # Equity = Cash + MV of positions
                 # We need to parse positions from THIS raw data to avoid double fetch
                 raw_positions = cp.get('positions', [])
                 mv_sum = 0.0
                 for p in raw_positions:
                     val = float(p.get('unitsBaseValueDollars', p.get('CurrentAmount', 0)))
                     mv_sum += val
                 
                 equity = cash + mv_sum
             except Exception as e:
                 logger.error(f"Failed to calc account from clientPortfolio: {e}")
                 equity = 0.0
                 cash = 0.0
        else:
            # Mapping based on official API / legacy bridge
            equity = float(portfolio.get('TotalEquity', portfolio.get('equity', 0)))
            cash = float(portfolio.get('AvailableCash', portfolio.get('cash', 0)))
        
        return Account(
            broker_type=BrokerType.ETORO,
            account_id=f"etoro_{self.mode}",
            total_equity=equity,
            available_cash=cash,
            currency="USD"
        )

    def get_positions(self) -> List[Position]:
        """
        Fetch Positions.
        """
        portfolio = self._fetch_portfolio_raw()
        if not portfolio:
            logger.warning("Portfolio response is empty.")
            return []
            
        # Inspect Map - Lazy Load if empty and we have raw numeric IDs?
        # Actually, just check if we have the map.
        if not self._id_to_symbol:
            logger.info("ID Map empty, fetching watchlists to populate...")
            self.get_watchlists()
            
        logger.info(f"Raw Portfolio Keys: {portfolio.keys()}")
            
        # Handle API response nesting: { "AggregatedMirror": { "positions": [...] } }
        # Or { "clientPortfolio": { "positions": [...] } }
        data_source = portfolio.get('AggregatedMirror', portfolio.get('clientPortfolio', portfolio))
        
        if isinstance(data_source, dict):
             logger.info(f"DataSource Keys: {data_source.keys()}")
        
        raw_positions = data_source.get('Positions', data_source.get('positions', []))
        
        positions = []
        for p in raw_positions:
            try:
                # Map raw position to Domain Model
                # Debug output shows: instrumentID, units, openRate, etc.
                # Use provided mapping or fallback
                
                # Note: 'Instrument' name is not in the position object in debug output!
                # We only have 'instrumentID'.
                # We need to resolve ID back to Symbol? 
                # Or maybe it's in the 'relatedAssets' or we need to use the cache/InstrumentID map.
                # The debug output showed 'instrumentID': 4237.
                # It does NOT show the symbol name directly in the position object.
                
                # We might need to fetch instrument details or use a map.
                # For now, let's use ID as symbol if name missing, or try 'InstrumentID'.
                
                # ID Resolution
                # We prioritize the cached Ticker from watchlists, fallback to Instrument ID
                inst_id = str(p.get('instrumentID', p.get('Instrument', '')))
                symbol = self._id_to_symbol.get(inst_id, inst_id) or "UNKNOWN"
                
                # Normalize Symbol (Remove .RTH, .EXT, etc. if breaking yfinance)
                if symbol.endswith('.RTH'):
                    symbol = symbol.replace('.RTH', '')
                
                pos = Position(
                    symbol=symbol,
                    quantity=float(p.get('units', p.get('Amount', p.get('quantity', 0)))),
                    open_price=float(p.get('openRate', p.get('OpenRate', p.get('open_price', 0)))),
                    current_price=float(p.get('CurrentRate', 0)) or float(p.get('openRate', 0)),
                    market_value=float(p.get('unitsBaseValueDollars', p.get('CurrentAmount', 0))),
                    # NetProfit not in debug snippet, maybe calc?
                    unrealized_pnl=float(p.get('NetProfit', 0)), 
                    open_date=self._parse_date(p.get('openDateTime', p.get('OpenDateTime', '')))
                )
                # Force set leverage to avoid constructor issues
                raw_lev = float(p.get('leverage', p.get('Leverage', 1.0)))
                pos.leverage = raw_lev
                
                positions.append(pos)
            except Exception as e:
                logger.warning(f"Failed to map position: {e}")
                continue
        return positions

    def get_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch Trade History.
        """
        endpoint = "/api/v1/trading/info/trade/history"
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch history: {e}")
            return []

    def execute_order(self, order: Order) -> Dict[str, Any]:
        """
        Execute Order with Risk Check.
        """
        user_id = "default_user" 
        
        # 1. Risk Check
        history = self.get_history()
        positions = self.get_positions()
        
        if not self.risk_manager.check_constraints(user_id, history, positions):
             return {"status": "failed", "reason": "Risk Manager Blocked"}

    def execute_order(self, order: Order) -> Dict[str, Any]:
        """
        Execute Order with Risk Check.
        """
        user_id = "default_user" 
        
        # 1. Risk Check
        history = self.get_history()
        positions = self.get_positions()
        
        if not self.risk_manager.check_constraints(user_id, history, positions):
             return {"status": "failed", "reason": "Risk Manager Blocked"}

        # 2. Resolve Instrument ID
        instrument_id = self._resolve_instrument_id(order.symbol)
        if not instrument_id:
             return {"status": "failed", "reason": f"Instrument ID not found for {order.symbol}"}

        # 3. Execute
        order_payload = {
            "InstrumentID": instrument_id,
            "Action": order.action.value,
            "Amount": order.quantity,
            "Leverage": order.leverage
        }
        
        endpoint = "/api/v1/trading/order"
        url = f"{self.base_url}{endpoint}"
        
        try:
             logger.info(f"ETORO EXEC: {order.action.value} {order.symbol} (ID: {instrument_id}) Qty={order.quantity}")
             response = requests.post(url, json=order_payload, headers=self._get_headers(), timeout=10)
             response.raise_for_status()
             return response.json()
        except Exception as e:
             logger.error(f"Etoro Exec Failed: {e}")
             return {"status": "error", "error": str(e)}

    def get_watchlists(self) -> List[Dict[str, Any]]:
        """
        Fetch all user watchlists.
        """
        endpoint = "/api/v1/watchlists"
        try:
            url = f"{self.base_url}{endpoint}"
            logger.info(f"Fetching Watchlists from: {url}")
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            logger.info(f"Watchlists HTTP Status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            
            # Populate ID Map from Watchlist Metadata
            # Structure: { "Watchlists": [ ... ] } OR { "watchlists": [ ... ] }
            watchlists = data.get('Watchlists', data.get('watchlists', []))
            
            logger.info(f"Raw Watchlists Keys: {data.keys()}")
            logger.info(f"Watchlists Count in Response: {len(watchlists)}")
            
            for wl in watchlists:
                # Items might be 'Items' or 'items'
                items = wl.get('Items', wl.get('items', []))
                for item in items:
                    market = item.get('market')
                    if market:
                        m_id = str(market.get('id', ''))
                        m_sym = market.get('symbolName')
                        if m_id and m_sym:
                            self._id_to_symbol[m_id] = m_sym
                            
            return data
        except Exception as e:
            logger.error(f"Failed to fetch watchlists: {e}")
            return []

    def _resolve_instrument_id(self, ticker: str) -> Optional[int]:
        """
        Resolve Ticker to eToro Instrument ID.
        Uses simplistic caching.
        """
        if not hasattr(self, '_id_cache'):
            self._id_cache = {}
            
        if ticker in self._id_cache:
            return self._id_cache[ticker]
            
        endpoint = "/api/v1/market-data/search"
        params = {"internalSymbolFull": ticker}
        
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, params=params, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Assuming resonse is list of matches or direct object
            # Adjust based on actual API response structure for search
            # If data is a list:
            if isinstance(data, list) and len(data) > 0:
                 inst_id = data[0].get('InstrumentID')
                 if inst_id:
                     self._id_cache[ticker] = inst_id
                     return inst_id
            
            # If data is a dict (single result)
            if isinstance(data, dict):
                 inst_id = data.get('InstrumentID')
                 if inst_id:
                     self._id_cache[ticker] = inst_id
                     return inst_id
                     
            return None
        except Exception as e:
            logger.error(f"Failed to resolve Instrument ID for {ticker}: {e}")
            return None

    def sync_history(self, user_id: str = "default_user") -> Dict[str, int]:
        """
        Sync external history to local DB.
        """
        history = self.get_history()
        if not history:
            return {"added": 0, "skipped": 0}

        added_count = 0
        skipped_count = 0
        
        existing_txs = self.transaction_repo.get_all_by_user(user_id)
        existing_sigs = set()
        for tx in existing_txs:
            try:
                sig = f"{tx.ticker}_{tx.trade_date}_{tx.action}_{float(tx.quantity):.4f}_{float(tx.price):.4f}"
                existing_sigs.add(sig)
            except: continue

        for trade in history:
            ticker = trade.get('Instrument', trade.get('symbol', 'UNKNOWN'))
            date_str = trade.get('OpenDateTime', trade.get('open_date', datetime.now().strftime('%Y-%m-%d')))
            action = trade.get('Action', trade.get('action', 'BUY')).upper()
            quantity = float(trade.get('Amount', trade.get('quantity', 0)))
            price = float(trade.get('OpenRate', trade.get('open_price', 0)))
            fees = float(trade.get('Fees', trade.get('fees', 0)))
            
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
            
        logger.info(f"Etoro Sync: Added {added_count}, Skipped {skipped_count}")
        return {"added": added_count, "skipped": skipped_count}

    # --- Helpers ---
    def _fetch_portfolio_raw(self) -> Dict[str, Any]:
        """Raw API Call"""
        endpoint = "/api/v1/trading/info/portfolio"
        if not self.api_key and self.mode == "demo":
             endpoint = "/api/v1/trading/info/demo/portfolio"
             
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Etoro Portfolio Error: {e}")
            return {}

    def _parse_date(self, date_str: str) -> datetime:
        if not date_str:
             return datetime.now()
        try:
            # Handle Z and fractional seconds
            # Example: 2025-04-21T14:42:03.703Z
            normalized = date_str.replace('Z', '')
            if '.' in normalized:
                # Truncate fractional seconds for simple parsing
                normalized = normalized.split('.')[0]
                
            if 'T' in normalized:
                 return datetime.strptime(normalized, '%Y-%m-%dT%H:%M:%S')
            return datetime.strptime(normalized, '%Y-%m-%d')
        except Exception as e:
             logger.warning(f"Date parse error for {date_str}: {e}")
             return datetime.now()
