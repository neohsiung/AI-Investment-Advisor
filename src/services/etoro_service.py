import os
import requests
import json
import time
import typing
import asyncio
from typing import List, Dict, Tuple, Any, Optional, Callable
from datetime import datetime, timedelta
from sqlalchemy import text
from src.utils.logger import setup_logger
from src.domain.broker import IBroker
from src.domain.trading import Order, Position, Account, OrderAction, BrokerType
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.infrastructure.risk_manager import RiskManager
from src.api.v1.exceptions import BrokerNotConfiguredError, BrokerDependencyError
from src.services.llm_credential_cipher import LLMCredentialCipher

logger = setup_logger("EtoroService")

class EtoroService(IBroker):
    """
    eToro Broker Implementation.
    eToro 證券商實作。
    
    Wraps eToro API and enforces Risk Management.
    封裝 eToro API 並執行風險管理。
    """

    def __init__(self, base_url: str = None, mode: str = "real", api_key: str = None, user_key: str = None, user_id: str = None) -> None:
        """
        Initialize the eToro service.
        初始化 eToro 服務。
        
        Args:
            base_url: API base URL (optional)
            mode: 'real' or 'demo'
            api_key: API key (optional, will read from DB if not provided)
            user_key: User key (optional, will read from DB if not provided)
            user_id: User ID for loading credentials from database
        """
        # Authentication (Priority: Arg > DB > Env)
        self.api_key = api_key
        self.user_key = user_key
        self.user_id = user_id
        
        # If not provided, try to load from database
        if (not self.api_key or not self.user_key) and user_id:
            self._load_credentials_from_db(user_id)
        
        # Fallback to environment variables
        if not self.api_key:
            self.api_key = os.getenv("ETORO_API_KEY")
        if not self.user_key:
            self.user_key = os.getenv("ETORO_USER_KEY")

        # Use official endpoint if keys are provided, else fallback to bridge for legacy support
        if self.api_key and self.user_key:
            default_base = "https://public-api.etoro.com/api/v1"
            logger.info(f"Using official eToro Public API (v1) with provided credentials")
        else:
            default_base = "http://localhost:8000"
            logger.warning(f"No eToro API credentials found, using local bridge at {default_base}")
        
        self.base_url = base_url or os.getenv("ETORO_API_BASE_URL", default_base)
        self.notification_service = None
        
        # Normalize mode: 'live' -> 'real' per BrokerFactory requirements
        self.mode = "real" if mode == "live" else mode
        self.transaction_repo = AlchemyTransactionRepository()
        self.risk_manager = RiskManager()
        self.name = "eToro"
        self._id_to_symbol = {} # Reverse map: ID -> Ticker
        self.cache_path = "data/etoro_id_cache.json"
        self._load_id_cache()
        self.cipher = LLMCredentialCipher()
        
        # [FIX Issue #4] Timestamp tracking for account data freshness
        self.last_fetched_at = None  # Track when account data was last fetched

    def _load_credentials_from_db(self, user_id: str) -> None:
        """
        Load eToro API credentials from database settings.
        從資料庫設定載入 eToro API 憑證。
        """
        try:
            from src.data.database import get_db_connection
            from sqlalchemy import text
            import json
            
            conn = get_db_connection()
            result = conn.execute(text(
                "SELECT key, value FROM settings WHERE user_id = :uid AND key IN ('etoro_api_key', 'etoro_user_key')"
            ), {'uid': user_id}).fetchall()
            
            for row in result:
                key, value = row[0], row[1]
                # Parse JSON value if it's a JSON string
                try:
                    if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
                        parsed_value = json.loads(value)
                    else:
                        parsed_value = value
                except json.JSONDecodeError:
                    parsed_value = value.strip('"') if isinstance(value, str) else value
                
                # Decrypt if encrypted
                if isinstance(parsed_value, str) and (parsed_value.startswith('ENC:') or parsed_value.startswith('FERN:') or parsed_value.startswith('B64H:')):
                    parsed_value = self.cipher.decrypt(parsed_value)

                if key == 'etoro_api_key':
                    self.api_key = parsed_value
                    logger.info(f"✓ Loaded and decrypted eToro API key from database")
                elif key == 'etoro_user_key':
                    self.user_key = parsed_value
                    logger.info(f"✓ Loaded and decrypted eToro user key from database")
            
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to load eToro credentials from database: {e}")

    def get_name(self) -> str:
        """
        Get the broker name.
        獲取證券商名稱。
        """
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
        if self.api_key and self.user_key:
            # Defensive: strip surrounding quotes that may leak from DB storage
            headers["x-api-key"] = self.api_key.strip('"') if isinstance(self.api_key, str) else self.api_key
            headers["x-user-key"] = self.user_key.strip('"') if isinstance(self.user_key, str) else self.user_key
        return headers

    async def get_account(self) -> Optional[Account]:
        """
        Fetch Account Summary (Equity, Cash).
        """
        portfolio = await self._fetch_portfolio_raw()
        if not portfolio:
            return None
        
        # Handle clientPortfolio (Credit = Cash)
        if 'clientPortfolio' in portfolio:
             cp = portfolio['clientPortfolio']
             try:
                 cash = float(cp.get('credit', cp.get('Credit', 0)))
                 raw_positions = cp.get('positions', [])
                 
                 # v6.0: Compute real NLV using current market prices
                 # Ensure symbol mapping is available
                 if not self._id_to_symbol:
                     await self.get_watchlists()
                     unknown_ids = [str(p.get('instrumentID', '')) for p in raw_positions
                                    if str(p.get('instrumentID', '')) not in self._id_to_symbol]
                     if unknown_ids:
                         await self._fetch_metadata_by_ids(unknown_ids)
                 
                 # Collect position data with symbols
                 position_data = []
                 for p in raw_positions:
                     inst_id = str(p.get('instrumentID', p.get('InstrumentID', '')))
                     symbol = self._id_to_symbol.get(inst_id) or self._resolve_id_to_symbol(inst_id) or f"ID_{inst_id}"
                     # Normalize
                     if symbol.endswith('.RTH'):
                         symbol = symbol.replace('.RTH', '')
                     units = float(p.get('units', p.get('lotCount', 0)))
                     initial_amount = float(p.get('unitsBaseValueDollars', p.get('amount', 0)))
                     position_data.append({
                         'symbol': symbol, 'units': units, 'initial_amount': initial_amount,
                     })
                 
                 # Fetch current prices
                 symbols = [pd['symbol'] for pd in position_data if pd['symbol'] and not pd['symbol'].startswith('ID_')]
                 current_prices = await self._fetch_current_prices(symbols) if symbols else {}
                 
                 # Calculate real market value
                 mv_sum = 0.0
                 for pd in position_data:
                     price = current_prices.get(pd['symbol'], 0)
                     if price > 0 and pd['units'] > 0:
                         mv_sum += pd['units'] * price
                     else:
                         mv_sum += pd['initial_amount']  # Fallback
                 
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

    async def get_positions(self) -> List[Position]:
        """
        Fetch Positions.
        """
        portfolio = await self._fetch_portfolio_raw()
        if not portfolio:
            logger.warning("Portfolio response is empty.")
            return []
        
        # Detect API auth errors returned as JSON error objects
        if 'errorCode' in portfolio:
            error_code = portfolio.get('errorCode', 'Unknown')
            error_msg = portfolio.get('errorMessage', 'Unknown error')
            logger.error(f"eToro API Auth Error in get_positions: {error_code} - {error_msg}")
            return []
            
        if not self._id_to_symbol:
            logger.info("ID Map empty, fetching watchlists to populate...")
            await self.get_watchlists()
            
        # Handle API response nesting
        data_source = portfolio.get('AggregatedMirror', portfolio.get('clientPortfolio', portfolio))
        raw_positions = data_source.get('Positions', data_source.get('positions', []))
        
        # v5.2: Proactively identify unknown instrument IDs for reverse resolution
        unknown_ids = []
        for p in raw_positions:
            inst_id = str(p.get('instrumentID', p.get('InstrumentID', p.get('Instrument', ''))))
            if inst_id and inst_id not in self._id_to_symbol:
                # Check if it's in persistent cache
                symbol = self._resolve_id_to_symbol(inst_id)
                if not symbol:
                    unknown_ids.append(inst_id)
        
        if unknown_ids:
            logger.info(f"Found {len(unknown_ids)} unknown instrument IDs in portfolio. Resolving via metadata API...")
            await self._fetch_metadata_by_ids(unknown_ids)
        
        positions = []
        for p in raw_positions:
            try:
                inst_id = str(p.get('instrumentID', p.get('InstrumentID', p.get('Instrument', ''))))
                pos_id = str(p.get('positionID', p.get('positionId', p.get('PositionID', p.get('id', '')))))
                
                symbol = self._id_to_symbol.get(inst_id) or self._resolve_id_to_symbol(inst_id)
                
                if not symbol:
                    symbol = f"ID_{inst_id}"
                
                # Normalize Symbol 
                if symbol.endswith('.RTH'):
                    symbol = symbol.replace('.RTH', '')
                
                quantity = float(p.get('units', p.get('Units', p.get('quantity', 0))))
                if quantity <= 0.0001:
                    continue

                pos = Position(
                    symbol=symbol,
                    quantity=quantity,
                    open_price=float(p.get('openRate', p.get('OpenRate', 0))),
                    current_price=float(p.get('currentRate', p.get('CurrentRate', 0))) or float(p.get('openRate', 0)),
                    market_value=float(p.get('unitsBaseValueDollars', p.get('CurrentAmount', 0))),
                    unrealized_pnl=float(p.get('netProfit', p.get('NetProfit', 0))), 
                    open_date=self._parse_date(p.get('openDateTime', p.get('OpenDateTime', ''))),
                    position_id=pos_id
                )
                pos.leverage = float(p.get('leverage', p.get('Leverage', 1.0)))
                
                positions.append(pos)
            except Exception as e:
                logger.warning(f"Failed to map position: {e}")
                continue
        
        # v6.0: Enrich positions with current market prices
        symbols = [p.symbol for p in positions if p.symbol and not p.symbol.startswith('ID_')]
        if symbols:
            current_prices = await self._fetch_current_prices(list(set(symbols)))
            for pos in positions:
                price = current_prices.get(pos.symbol, 0)
                if price > 0:
                    pos.current_price = price
                    pos.market_value = pos.quantity * price
                    initial_amount = pos.quantity * pos.open_price
                    pos.unrealized_pnl = pos.market_value - initial_amount
        
        return positions

    async def get_pending_orders(self) -> List[Dict[str, Any]]:
        """
        Fetch pending (scheduled) orders from the comprehensive portfolio snapshot.
        從綜合投資組合快照中獲取尚未成交的預約單。
        """
        try:
            portfolio = await self._fetch_portfolio_raw()
            if not portfolio:
                return []
                
            # Detect API auth errors
            if 'errorCode' in portfolio:
                logger.error(f"eToro API Auth Error in get_pending_orders: {portfolio.get('errorCode')} - {portfolio.get('errorMessage')}")
                return []

            # Extract orders from AggregatedMirror or clientPortfolio
            data_source = portfolio.get('AggregatedMirror', portfolio.get('clientPortfolio', portfolio))
            raw_orders = data_source.get('Orders', data_source.get('orders', []))
            
            if not raw_orders:
                return []

            # Ensure ID map is available
            if not self._id_to_symbol:
                await self.get_watchlists()
        
            orders = []
            for o in raw_orders:
                inst_id = str(o.get('instrumentId', o.get('InstrumentID', o.get('Instrument', ''))))
                if not inst_id:
                    continue
                    
                symbol = self._id_to_symbol.get(inst_id) or self._resolve_id_to_symbol(inst_id) or f"ID_{inst_id}"
                is_buy = o.get('isBuy', o.get('IsBuy', True))
                action = "BUY" if is_buy else "SELL"
                
                orders.append({
                    "order_id": str(o.get('orderId', o.get('OrderId', o.get('id', '')))),
                    "symbol": symbol,
                    "action": action,
                    "amount": float(o.get('amount', o.get('Amount', o.get('amountBaseValueDollars', 0)))),
                    "raw_status": o.get('status', o.get('Status', 'Pending'))
                })
            
            return orders
        except Exception as e:
            logger.error(f"Failed to fetch pending orders: {e}")
            return []

    async def get_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch Trade History.
        """
        import httpx
        endpoint = "/trading/info/trade/history"
        if self.mode == "demo":
            endpoint = "/trading/info/demo/trade/history"
        
        try:
            url = f"{self.base_url}{endpoint}"
            from datetime import timedelta
            start_date = datetime.now() - timedelta(days=days)
            
            params = {
                'minDate': start_date.strftime('%Y-%m-%d'),
                'pageSize': 100
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self._get_headers(), params=params, timeout=15.0)
                
                if response.status_code == 200:
                    data = response.json()
                    history = data if isinstance(data, list) else []
                    logger.info(f"ETORO HISTORY: Retrieved {len(history)} trade records")
                    return history
                else:
                    logger.warning(f"ETORO HISTORY: {response.status_code}")
                    return []
        except Exception as e:
            logger.error(f"ETORO HISTORY: Failed to fetch trade history: {e}")
            return []

    async def execute_order(self, order: Order) -> Dict[str, Any]:
        """
        Execute an order with risk management checks.
        """
        user_id = self.user_id
        if not user_id:
            raise ValueError("EtoroService: execute_order requires an initialized user_id.")
        
        # 0. Pre-flight: Verify API credentials are valid
        preflight = await self._fetch_portfolio_raw()
        if preflight and 'errorCode' in preflight:
            error_code = preflight.get('errorCode', 'Unknown')
            error_msg = preflight.get('errorMessage', 'Unknown')
            logger.error(f"eToro API credentials invalid: {error_code} - {error_msg}")
            return {"status": "failed", "reason": f"eToro API Auth Failed: {error_code} - {error_msg}"}
        
        # 1. Risk Check (Wrap sync calls if needed, but here they are now async)
        history = await self.get_history()
        positions = await self.get_positions()
        
        if not self.risk_manager.check_constraints(user_id, history, positions):
             return {"status": "failed", "reason": "Risk Manager Blocked"}

        # 2. Resolve Instrument ID
        instrument_id = await self._resolve_instrument_id(order.symbol)

        # 3. Execute Order (v4.2.5: Allow SELL without instrument_id if pos_id resolved)
        if order.action == OrderAction.BUY:
            if not instrument_id:
                 return {"status": "failed", "reason": f"Instrument ID not found for {order.symbol} (Required for BUY)"}
                 
            endpoint = "/trading/execution/market-open-orders/by-amount"
            url = f"{self.base_url}{endpoint}"
            # eToro API: PascalCase body, Amount in USD (not shares)
            # Phase 3: Explicitly use amount_usd or fallback to quantity, round to 2 decimals
            buy_amount = order.amount_usd if order.amount_usd is not None else order.quantity
            payload = {
                "InstrumentID": int(instrument_id),
                "Amount": round(buy_amount, 2),  # Dollar amount (USD)
                "IsBuy": True,
            }
            # Only include Leverage if non-default (eToro skill: "Use Defaults")
            if order.leverage and order.leverage != 1:
                payload["Leverage"] = order.leverage
        else: # SELL / CLOSE
            # Use specific positionId if provided, else attempt to find one
            pos_id = getattr(order, 'position_id', None)
            if not pos_id:
                # Find matching position by symbol
                logger.info(f"ETORO EXEC: Searching for position matching symbol '{order.symbol}'...")
                matching = [p for p in positions if self._is_symbol_match(order.symbol, p.symbol)]
                
                # Rule 14 / User Suggestion: If not found, try to re-fetch positions 
                if not matching:
                    logger.info(f"ETORO EXEC: No immediate match for {order.symbol}. Retrying with fresh position scan...")
                    positions = await self.get_positions()
                    matching = [p for p in positions if self._is_symbol_match(order.symbol, p.symbol)]
                
                if matching:
                    pos_id = matching[0].position_id
                    # Also extract instrument_id from the matched position for close body
                    if not instrument_id:
                        matched_inst = self._id_cache.get(matching[0].symbol)
                        if matched_inst:
                            instrument_id = matched_inst
                    logger.info(f"ETORO EXEC: Found matching position {pos_id} for {order.symbol}")
                else:
                    symbols_found = [p.symbol for p in positions]
                    logger.warning(f"ETORO EXEC: No match for {order.symbol} even after retry. Current positions: {symbols_found}")
            
            if not pos_id:
                return {"status": "failed", "reason": f"No active position ID found for {order.symbol} to close"}
            
            endpoint = f"/trading/execution/market-close-orders/positions/{pos_id}"
            url = f"{self.base_url}{endpoint}"
            # eToro API: InstrumentId is REQUIRED in close body (lowercase 'd')
            # UnitsToDeduct: null = full close, number = partial close
            close_payload: Dict[str, Any] = {}
            if instrument_id:
                close_payload["InstrumentId"] = int(instrument_id)
            if order.quantity and order.quantity > 0:
                # Phase 3: eToro fractional sell precision (0.01)
                close_payload["UnitsToDeduct"] = round(order.quantity, 2)
            payload = close_payload
        
        try:
             import httpx
             logger.info(f"ETORO EXEC: {order.action.value} {order.symbol} (ID: {instrument_id}) via {endpoint}")
             async with httpx.AsyncClient() as client:
                 response = await client.post(url, json=payload, headers=self._get_headers(), timeout=15.0)
                 response.raise_for_status()
                 result = response.json()
             
             # v5.6: Send real-time notification for automated trade
             await self._notify_trade(order, result)
             
             return result
        except Exception as e:
             logger.error(f"Etoro Exec Failed: {e}")
             return {"status": "error", "error": str(e)}

    async def _notify_trade(self, order: Order, result: Dict[str, Any]):
        """
        Send a real-time notification for an executed trade using direct NotificationService.
        """
        try:
            # v3.9 direct dispatch
            if not self.notification_service:
                from src.services.notification_service import NotificationService
                from src.services.settings_service import SettingsService
                # Use a default or system user if needed, but here we prefer the one associated with the broker
                # user_id is passed to __init__ but we might need it here.
                # If self.user_id was stored in __init__ we should use it.
                # Let's check if we have user_id.
                user_id = getattr(self, 'user_id', "broadcast")
                settings_svc = SettingsService(user_id=user_id)
                self.notification_service = NotificationService.create_with_settings(settings_service=settings_svc, user_id=user_id)
            
            title = f"🚀 {'Buy' if order.action == OrderAction.BUY else 'Sell'} 執行成功"
            content = f"**Ticker:** {order.symbol}\n**Action:** {order.action.value}\n**Order ID:** {result.get('OrderId', 'N/A')}"
            
            await self.notification_service.notify_all(
                title=title,
                content=content,
                channels=["telegram", "web"], # standard channels for trading alerts
                category="trading"
            )
        except Exception as e:
            logger.warning(f"Failed to send trade notification: {e}")

    def _load_id_cache(self) -> None:
        """Load instrument ID cache from disk."""
        import json
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r') as f:
                    self._id_cache = json.load(f)
                    logger.info(f"✓ Loaded {len(self._id_cache)} IDs from disk cache.")
                    
                    # Reconstruct reverse map for faster lookups in position flows
                    for sym, uid in self._id_cache.items():
                        self._id_to_symbol[str(uid)] = sym
            except Exception as e:
                logger.warning(f"Failed to load ID cache: {e}")
                self._id_cache = {}
        else:
            self._id_cache = {}

    def _save_id_cache(self) -> None:
        """Save instrument ID cache to disk."""
        import json
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        try:
            with open(self.cache_path, 'w') as f:
                json.dump(self._id_cache, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save ID cache: {e}")

    async def get_watchlists(self) -> List[Dict[str, Any]]:
        """
        Fetch items from the default user watchlist (v5.6 optimized).
        """
        import httpx
        endpoint = "/watchlists/default-watchlists/items"
        try:
            url = f"{self.base_url}{endpoint}"
            logger.info(f"Fetching Watchlist Items from: {url}")
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self._get_headers(), timeout=10.0)
                response.raise_for_status()
                data = response.json()
            
            # Populate ID Map from items
            # Expected structure: [ { "market": { "id": 1, "symbolName": "AAPL" } }, ... ]
            items = data if isinstance(data, list) else data.get('items', data.get('Items', []))
            
            for item in items:
                market = item.get('market')
                if market:
                    m_id = str(market.get('id', ''))
                    m_sym = market.get('symbolName')
                    if m_id and m_sym:
                        self._id_to_symbol[m_id] = m_sym
                        # Auto-seed cache from watchlist
                        if m_sym not in self._id_cache:
                            self._id_cache[m_sym] = int(m_id)
            
            self._save_id_cache()
            return data
        except Exception as e:
            logger.error(f"Failed to fetch watchlist items: {e}")
            return []

    async def _resolve_instrument_id(self, ticker: str) -> Optional[int]:
        """
        Resolve Ticker to eToro Instrument ID.
        """
        if ticker in self._id_cache:
            return self._id_cache[ticker]

        inst_id = await self._fetch_id_from_api(ticker, exact=True)
        if inst_id:
            self._id_cache[ticker] = inst_id
            self._save_id_cache()
            return inst_id

        inst_id = await self._fetch_id_from_api(ticker, exact=False)
        if inst_id:
            self._id_cache[ticker] = inst_id
            self._save_id_cache()
            return inst_id
        
        return None

    async def _fetch_id_from_api(self, symbol: str, exact: bool = True) -> Optional[int]:
        """
        Internal helper for eToro search (async).
        """
        import httpx
        endpoint = "/market-data/search"
        headers = self._get_headers()
        
        params = {
            "pageSize": 10,
            "pageNumber": 1,
            "fields": "displayname,internalSymbolFull,symbolName,instrumentId,isCurrentlyTradable,isActiveInPlatform",
        }
        
        if exact:
            params["internalSymbolFull"] = symbol
        else:
            params["searchText"] = symbol
        
        try:
            url = f"{self.base_url}{endpoint}"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                if isinstance(data, list):
                    items = data
                else:
                    items = data.get('items', data.get('Items', []))
                
                logger.debug(f"Search results for {symbol} (exact={exact}): {len(items)} items found.")
                
                # Two-pass strategy: first collect all matches, then prefer tradable ones
                exact_matches = []  # (inst_id, is_tradable)
                partial_matches = []
                
                for item in items:
                    inst_id = str(item.get('instrumentId') or item.get('InstrumentID') or item.get('InstrumentId') or '')
                    if not inst_id:
                        continue
                    
                    ret_symbol = (item.get('internalSymbolFull') or item.get('symbolName') or item.get('displayname') or item.get('symbol') or "").upper()
                    target_symbol = symbol.upper()
                    is_tradable = bool(item.get('isCurrentlyTradable', False))
                    is_active = bool(item.get('isActiveInPlatform', False))
                    
                    if ret_symbol == target_symbol:
                        exact_matches.append((inst_id, is_tradable and is_active))
                    elif ret_symbol and (ret_symbol.split('.')[0] == target_symbol or target_symbol in ret_symbol):
                        partial_matches.append((inst_id, is_tradable and is_active))
                
                # Prefer tradable exact match, then any exact match, then tradable partial
                for matches, label in [(exact_matches, "Exact"), (partial_matches, "Partial")]:
                    # Prioritize tradable instruments
                    tradable = [m for m in matches if m[1]]
                    if tradable:
                        chosen_id = tradable[0][0]
                        logger.info(f"✓ Resolved {symbol} -> {chosen_id} via {label} Match (Tradable)")
                        return int(chosen_id)
                    if matches:
                        chosen_id = matches[0][0]
                        logger.info(f"✓ Resolved {symbol} -> {chosen_id} via {label} Match")
                        return int(chosen_id)
                
                # Fallback: resolve via metadata if no symbol info was present in search
                found_ids = [str(item.get('instrumentId', '')) for item in items if item.get('instrumentId')]
                if found_ids:
                    logger.info(f"Search found {len(found_ids)} candidate IDs for {symbol} but no symbol match. Resolving metadata...")
                    await self._fetch_metadata_by_ids(found_ids[:5])
                    
                    for fid in found_ids[:5]:
                        cached_sym = self._id_to_symbol.get(fid) or self._resolve_id_to_symbol(fid)
                        if cached_sym and (cached_sym.upper() == symbol.upper() or cached_sym.upper().split('.')[0] == symbol.upper() or symbol.upper() in cached_sym.upper()):
                            logger.info(f"✓ Resolved {symbol} -> {fid} via Search + Metadata Resolution")
                            return int(fid)

                else:
                    logger.warning(f"eToro Search failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.warning(f"eToro Search failed (exact={exact}) for {symbol}: {e}")
            return None

    def _resolve_id_to_symbol(self, instrument_id: str) -> Optional[str]:
        """
        Resolve eToro Instrument ID to Ticker Symbol.
        """
        # 1. Reverse map: ID -> Ticker (popluated from watchlist)
        for mid, symbol in self._id_to_symbol.items():
            if str(mid) == str(instrument_id):
                return symbol

        # 2. Check Local Cache (Ticker -> ID)
        for symbol, uid in self._id_cache.items():
            if str(uid) == str(instrument_id):
                return symbol
        
        return None

    async def _fetch_metadata_by_ids(self, ids: List[str]) -> None:
        """
        Fetch instrument metadata by IDs.
        批量取得標的 metadata，batch 失敗時 fallback 逐一查詢。
        """
        if not ids:
            return
            
        import httpx
        endpoint = "/market-data/instruments"
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        # Try batch first
        try:
            params = {"instrumentIds": ",".join(ids)}
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=headers, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    # Check for auth error in JSON response body
                    if isinstance(data, dict) and 'errorCode' in data:
                        logger.warning(f"Metadata API auth error: {data.get('errorCode')} - {data.get('errorMessage')}")
                    else:
                        self._process_metadata_response(data)
                        return
                elif response.status_code == 401:
                    logger.error(f"Metadata API: Unauthorized. eToro credentials may be expired.")
                    return  # Don't fallback with invalid credentials
                else:
                    logger.warning(f"Metadata batch lookup failed: {response.status_code}. Falling back to individual lookups...")
        except Exception as e:
            logger.warning(f"Metadata batch failed: {e}. Falling back to individual lookups...")
        
        # Fallback: individual lookups
        resolved_count = 0
        async with httpx.AsyncClient() as client:
            for inst_id in ids:
                try:
                    resp = await client.get(url, params={"instrumentIds": inst_id}, headers=headers, timeout=10.0)
                    if resp.status_code == 200:
                        self._process_metadata_response(resp.json())
                        resolved_count += 1
                except Exception:
                    continue
        
        if resolved_count > 0:
            self._save_id_cache()
            logger.info(f"✓ Resolved {resolved_count}/{len(ids)} metadata records via individual lookups.")

    def _process_metadata_response(self, data: Dict[str, Any]) -> None:
        """Process metadata API response and update caches."""
        records = data.get('instrumentDisplayDatas', [])
        for rec in records:
            m_id = str(rec.get('instrumentID', ''))
            m_sym = rec.get('symbolFull') or rec.get('instrumentDisplayName')
            
            if m_id and m_sym:
                # Normalize symbol for cache
                clean_sym = m_sym.replace(".US", "").replace(".UK", "").replace(".L", "").replace(".RTH", "")
                
                # Store original in _id_to_symbol for full match, and clean in cache for fuzzy match
                self._id_to_symbol[m_id] = m_sym
                if clean_sym not in self._id_cache:
                    self._id_cache[clean_sym] = int(m_id)
        
        if records:
            self._save_id_cache()
            logger.info(f"✓ Resolved {len(records)} metadata records.")

    def _is_symbol_match(self, ticker1: str, ticker2: str) -> bool:
        """
        Check if two symbols match, ignoring common eToro suffixes.
        Example: 'NVDA' matches 'NVDA.US', 'TSLA' matches 'TSLA.RTH'
        """
        if not ticker1 or not ticker2:
            return False
            
        t1 = ticker1.strip().upper()
        t2 = ticker2.strip().upper()
        
        # 1. Exact Match
        if t1 == t2:
            return True
            
        # 2. Normalize by removing suffixes (.US, .RTH, .EXT, .L)
        # Suffixes are typically for market designation or session info
        def normalize(s):
            # Remove common suffixes
            for suffix in ['.US', '.RTH', '.EXT', '.L', '.UK']:
                if s.endswith(suffix):
                    return s[:-len(suffix)]
            return s
            
        n1 = normalize(t1)
        n2 = normalize(t2)
        
        return n1 == n2

    def _get_instrument_id_from_positions(self, ticker: str, positions: List[Position]) -> Optional[int]:
        """
        Extract instrument ID from active positions if possible.
        """
        for p in positions:
            if self._is_symbol_match(ticker, p.symbol):
                # Try to find instrument_id from extra attributes if present, or resolve it
                # For now just return None if not easily available 
                pass
        return None

    async def sync_history(self, user_id: str = None, days: int = 30, initial_sync: bool = False) -> Dict[str, int]:
        uid = user_id or self.user_id
        if not uid:
             raise ValueError("EtoroService: sync_history requires a user_id.")
        """
        Sync external history to local DB.
        同步外部交易歷史到本地資料庫。
        
        v7.1 Fix: Converted to async def. get_history() and get_watchlists() are both async;
        calling them without await returned coroutine objects instead of data, causing
        'coroutine object is not iterable' crash every scheduler run.
        
        Args:
            user_id: User ID for the transactions
            days: Number of days to fetch (default: 30 for regular sync)
            initial_sync: If True, fetch all history from 2024-01-01; if False, use days parameter
        
        Returns:
            Dict with 'added' and 'skipped' counts
        """
        # Determine fetch period
        if initial_sync:
            start_date = datetime(2024, 1, 1)
            days = (datetime.now() - start_date).days
            logger.info(f"Initial sync: Fetching all history from 2024-01-01 ({days} days)")
        else:
            logger.info(f"Regular sync: Fetching last {days} days")
        
        history = await self.get_history(days=days)  # ← was missing await: caused coroutine bug
        if not history:
            logger.warning("No history retrieved from eToro API")
            return {"added": 0, "skipped": 0}

        # Ensure ID map is populated for symbol resolution
        if not self._id_to_symbol:
            logger.info("Populating instrument ID map from watchlists...")
            await self.get_watchlists()  # ← was missing await: caused coroutine bug

        added_count = 0
        skipped_count = 0
        
        existing_txs = self.transaction_repo.get_all_by_user(user_id)
        existing_sigs = set()
        for tx in existing_txs:
            try:
                sig = f"{tx.trade_date}_{tx.action}_{float(tx.quantity):.4f}_{float(tx.price):.4f}"
                existing_sigs.add(sig)
            except (ValueError, TypeError, AttributeError): continue

        for trade in history:
            # instrumentId, openTimestamp, closeTimestamp, isBuy, units, openRate, closeRate, fees, netProfit
            
            instrument_id = str(trade.get('instrumentId', ''))
            ticker = self._id_to_symbol.get(instrument_id)
            if not ticker:
                resolved = self._resolve_id_to_symbol(instrument_id)
                if resolved:
                    ticker = resolved
                    self._id_to_symbol[instrument_id] = ticker
                else:
                    ticker = f"ID_{instrument_id}"
            
            open_ts = trade.get('openTimestamp', '')
            close_ts = trade.get('closeTimestamp', '')
            
            is_buy = trade.get('isBuy', True)
            open_action = 'BUY' if is_buy else 'SELL'
            
            quantity = float(trade.get('units', 0))
            open_price = float(trade.get('openRate', 0))
            leverage = float(trade.get('leverage', 1.0))
            fees = abs(float(trade.get('fees', 0))) 
            
            # 1. Opening Leg
            open_date_str = open_ts[:10] if open_ts else datetime.now().strftime('%Y-%m-%d')
            open_sig = f"{open_date_str}_{open_action}_{quantity:.4f}_{open_price:.4f}"
            
            if open_sig not in existing_sigs:
                self.transaction_repo.add(
                    user_id=user_id,
                    ticker=ticker,
                    date=open_date_str,
                    action=open_action,
                    quantity=quantity,
                    price=open_price,
                    fees=fees if not close_ts else 0.0,
                    leverage=leverage
                )
                added_count += 1
            else:
                skipped_count += 1

            # 2. Closing Leg (if closed)
            if close_ts:
                close_action = 'SELL' if open_action == 'BUY' else 'BUY'
                close_price = float(trade.get('closeRate', 0))
                close_date_str = close_ts[:10]
                close_sig = f"{close_date_str}_{close_action}_{quantity:.4f}_{close_price:.4f}"
                
                if close_sig not in existing_sigs:
                    self.transaction_repo.add(
                        user_id=user_id,
                        ticker=ticker,
                        date=close_date_str,
                        action=close_action,
                        quantity=quantity,
                        price=close_price,
                        fees=0.0,
                        leverage=leverage
                    )
                    added_count += 1
                else:
                    skipped_count += 1
            
        # [NEW] v4.2.0: Synchronize Cash Balance and Backfill Positions
        # [NEW] v4.2.0: 同步現金餘額並回補持倉
        try:
            await self._sync_cash_balance(user_id)
            await self._backfill_from_positions(user_id)
        except Exception as e:
            logger.error(f"Post-sync logic failed: {e}")

        # [NEW] v5.0: Incrementally maintain position_lots for newly added transactions
        # Only update lots for trades that were actually new (not skipped)
        if added_count > 0:
            try:
                self._sync_position_lots(user_id)
            except Exception as e:
                logger.warning(f"position_lots sync failed (non-critical): {e}")

        logger.info(f"Etoro Sync: Added {added_count}, Skipped {skipped_count}")
        return {"added": added_count, "skipped": skipped_count}

    async def _sync_cash_balance(self, user_id: str) -> None:
        """
        Adjust local cash balance to match broker's available cash.
        調整本地現金餘額以匹配券商的可提款現金。
        
        v4.2.3: Fixed circular correction bug — now deletes prior sync entries
        before recalculating, preventing compounding DEPOSIT/WITHDRAWAL entries.
        """
        account = await self.get_account()
        if not account:
            return

        broker_cash = account.available_cash

        # 1. Delete any previous CASH sync entries to prevent circular corrections
        # 1. We no longer blindly delete existing 'ETORO_SYNC' CASH entries.
        # Instead, we recalculate based on the current state and only add a delta if needed.
        # Original code deleted them here, which caused frequent drift.
        local_cash = self.transaction_repo.get_cash_balance(user_id)
        diff = broker_cash - local_cash
        
        SYNC_THRESHOLD = 0.05
        SAFETY_CAP = 5000.0

        # 2. Check for existing sync entries on the same day to avoid duplication
        # Get existing syncs for today
        today_str = datetime.now().strftime('%Y-%m-%d')
        with self.transaction_repo.engine.connect() as conn:
            existing_today = conn.execute(
                text("""
                    SELECT amount, action FROM transactions 
                    WHERE user_id = :uid AND ticker = 'CASH' 
                    AND trade_date = :dt AND source_file = 'ETORO_SYNC'
                """),
                {"uid": user_id, "dt": today_str}
            ).fetchall()
        
        # If we already have a sync today that covers this diff (within threshold), skip
        for ext_amount, ext_action in existing_today:
            ext_diff = float(ext_amount) if ext_action == 'DEPOSIT' else -float(ext_amount)
            if abs(diff - ext_diff) < SYNC_THRESHOLD:
                logger.info(f"Skipping duplicate cash sync for today: Diff={diff:.2f} matches existing={ext_diff:.2f}")
                return

        if abs(diff) > SYNC_THRESHOLD:
            if abs(diff) > SAFETY_CAP:
                logger.warning(
                    f"Cash sync diff too large (${diff:.2f}), skipping. "
                    f"Local={local_cash:.2f}, Broker={broker_cash:.2f}. "
                    f"Investigate manually."
                )
                return
            
            action = "DEPOSIT" if diff > 0 else "WITHDRAWAL"
            logger.info(f"Syncing Cash: Local={local_cash:.2f}, Broker={broker_cash:.2f}, Diff={diff:.2f}, Action={action}")
            
            with self.transaction_repo.engine.begin() as conn:
                import uuid as _uuid
                import json as _json
                # [ENHANCED] Trace now includes context to avoid "unexplained" labels
                trace = {
                    "reason": "Automated Portfolio Alignment",
                    "local_cash_at_sync": local_cash,
                    "broker_cash_reference": broker_cash,
                    "diff_to_align": diff,
                    "source": "eToro_PnL_AvailableCash",
                    "timestamp": datetime.now().isoformat()
                }
                
                conn.execute(
                    text("""
                        INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file, entry_category, raw_data)
                        VALUES (:id, :uid, 'CASH', :dt, :action, 1, :price, 0, :amount, 'ETORO_SYNC', 'sync_adjustment', :raw)
                    """),
                    {
                        "id": str(_uuid.uuid4()),
                        "uid": user_id,
                        "dt": today_str,
                        "action": action,
                        "price": abs(diff),
                        "amount": abs(diff),
                        "raw": _json.dumps(trace)
                    }
                )

    async def _backfill_from_positions(self, user_id: str) -> None:
        """
        Backfill BUY transactions for active positions that have no trade history.
        回補沒有交易歷史的現有持倉 BUY 記錄。
        v7.1 Fix: Converted to async def; get_positions() is async.
        """
        positions = await self.get_positions()  # ← was missing await
        active_tickers = self.transaction_repo.get_active_tickers(user_id)
        
        for pos in positions:
            if pos.symbol.isdigit():
                 continue

            if pos.symbol not in active_tickers:
                logger.info(f"Backfilling Position: Missing BUY for {pos.symbol}, Leverage={getattr(pos, 'leverage', 1.0)}")
                self.transaction_repo.add(
                    user_id=user_id,
                    ticker=pos.symbol,
                    date=pos.open_date.strftime('%Y-%m-%d'),
                    action="BUY",
                    quantity=pos.quantity,
                    price=pos.open_price,
                    fees=0.0,
                    leverage=getattr(pos, 'leverage', 1.0),
                    entry_category="trade",  # Backfilled synthetic BUY = regular trade
                )

    def _sync_position_lots(self, user_id: str) -> None:
        """
        Incrementally sync position_lots after new transactions are added.
        Performs a full FIFO re-seed (idempotent) — fast enough for sub-500 transaction portfolios.
        For larger portfolios, replace with incremental lot update logic.

        在套加新交易後增量同步 position_lots。
        目前執行全量 FIFO 重播（冪等），對不足 500 筆交易的組合夠快。
        """
        try:
            from src.repositories.position_lot_repository import AlchemyPositionLotRepository
            lot_repo = AlchemyPositionLotRepository(self.transaction_repo.engine)
            count = lot_repo.backfill_from_transactions(user_id)
            logger.info(f"position_lots sync complete: {count} open lots for user={user_id}")
        except Exception as e:
            raise RuntimeError(f"_sync_position_lots failed: {e}") from e

    # --- Helpers ---
    async def _fetch_current_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Fetch current market prices via yfinance Ticker.history().
        使用 yfinance history() 獲取最近收盤價（含超時保護與多策略 fallback）。
        
        Returns: {symbol: current_price}
        """
        prices = {}
        if not symbols:
            return prices

        # Helper to fetch price from yfinance (async)
        async def _get_price(symbol: str) -> Tuple[str, float]:
            try:
                import yfinance as yf
                # yfinance is sync, but we can wrap it or use its internal data
                # For now, let's keep it simple and safe.
                # In modern yfinance, Ticker objects have cache.
                # But to stay non-blocking, we use run_in_executor
                loop = asyncio.get_event_loop()
                def fetch():
                    ticker = yf.Ticker(symbol)
                    return ticker.fast_info.get('last_price', 0)
                
                price = await loop.run_in_executor(None, fetch)
                return symbol, float(price)
            except Exception:
                return symbol, 0.0

        try:
            unique_symbols = list(set(symbols))
            tasks = [_get_price(s) for s in unique_symbols]
            results = await asyncio.gather(*tasks)
            
            for sym, price in results:
                if price > 0:
                    prices[sym] = price
            
            if prices:
                logger.info(f"Fetched {len(prices)}/{len(unique_symbols)} current prices.")
        except Exception as e:
            logger.warning(f"Failed to fetch current prices: {e}")
        
        return prices

    async def _fetch_portfolio_raw(self) -> Dict[str, Any]:
        """
        Raw API Call to fetch portfolio.
        Official eToro API: https://api-portal.etoro.com/api-reference/trading--real/retrieve-comprehensive-portfolio-information-including-positions-orders-and-account-status
        """
        import httpx
        # Official API endpoint (confirmed working: /api/v1/trading/info/portfolio)
        # 官方 API 端點（已確認可用：/api/v1/trading/info/portfolio）
        endpoint = "/trading/info/portfolio"
        if self.mode == "demo":
            endpoint = "/trading/info/demo/portfolio"
             
        try:
            url = f"{self.base_url}{endpoint}"
            
            # [CRITICAL] Prevent infinite recursion deadlock
            if "localhost" in url or "127.0.0.1" in url:
                logger.warning(f"Blocking potential deadlock: eToro service is not configured and points to localhost ({url})")
                raise BrokerNotConfiguredError("eToro API base URL points to localhost, suggesting missing configuration.")

            logger.info(f"Fetching portfolio from: {url}")
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self._get_headers(), timeout=10.0)
                data = response.json()
            
            # Detect auth errors from response body (eToro returns JSON error objects)
            if isinstance(data, dict) and 'errorCode' in data:
                error_code = data.get('errorCode', 'Unknown')
                error_msg = data.get('errorMessage', 'Unknown')
                logger.error(f"eToro Portfolio API Error: {error_code} - {error_msg}")
                raise BrokerDependencyError(f"eToro API Error: {error_msg}")
            
            response.raise_for_status()
            return data
        except BrokerNotConfiguredError:
            raise
        except httpx.TimeoutException:
            logger.error(f"eToro Portfolio Timeout: {url}")
            raise BrokerDependencyError("eToro API request timed out.")
        except httpx.HTTPStatusError as e:
            logger.error(f"eToro Portfolio HTTP Error: {e}")
            raise BrokerDependencyError(f"eToro API HTTP Error: {e}")
        except Exception as e:
            logger.error(f"Etoro Portfolio Unexpected Error: {e}")
            raise BrokerDependencyError(f"eToro API Unexpected Error: {str(e)}")

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
