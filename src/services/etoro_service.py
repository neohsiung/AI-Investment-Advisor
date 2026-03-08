import os
import requests
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from datetime import datetime
from sqlalchemy import text
from src.utils.logger import setup_logger
from src.domain.broker import IBroker
from src.domain.trading import Order, Position, Account, OrderAction, BrokerType
from src.repositories.transaction_repository import AlchemyTransactionRepository
from src.infrastructure.risk_manager import RiskManager

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
            default_base = "https://public-api.etoro.com"
            logger.info(f"Using official eToro Public API with provided credentials")
        else:
            default_base = "http://localhost:8000"
            logger.warning(f"No eToro API credentials found, using local bridge at {default_base}")
        
        self.base_url = base_url or os.getenv("ETORO_API_BASE_URL", default_base)
        
        # Normalize mode: 'live' -> 'real' per BrokerFactory requirements
        self.mode = "real" if mode == "live" else mode
        self.transaction_repo = AlchemyTransactionRepository()
        self.risk_manager = RiskManager()
        self.name = "eToro"
        self._id_to_symbol = {} # Reverse map: ID -> Ticker

    def _load_credentials_from_db(self, user_id: str) -> None:
        """
        Load eToro API credentials from database settings.
        從資料庫設定載入 eToro API 憑證。
        """
        try:
            # Ensure PostgreSQL connection
            if os.getenv('DB_TYPE') == 'postgres' and os.getenv('DB_HOST') == 'postgres':
                os.environ['DB_HOST'] = 'localhost'
            
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
                    # Check if value starts with quote (JSON encoded string)
                    if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
                        parsed_value = json.loads(value)
                    else:
                        parsed_value = value
                except json.JSONDecodeError:
                    parsed_value = value
                
                if key == 'etoro_api_key':
                    self.api_key = parsed_value
                    logger.info(f"✓ Loaded eToro API key from database")
                elif key == 'etoro_user_key':
                    self.user_key = parsed_value
                    logger.info(f"✓ Loaded eToro user key from database")
            
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
                symbol = self._id_to_symbol.get(inst_id)
                
                if not symbol:
                    # Try reverse resolution or hardcoded map
                    resolved = self._resolve_id_to_symbol(inst_id)
                    if resolved:
                        symbol = resolved
                        self._id_to_symbol[inst_id] = symbol
                    else:
                        symbol = f"ID_{inst_id}"
                
                # Normalize Symbol (Remove .RTH, .EXT, etc. if breaking yfinance)
                if symbol.endswith('.RTH'):
                    symbol = symbol.replace('.RTH', '')
                
                quantity = float(p.get('units', p.get('Amount', p.get('quantity', 0))))
                if quantity <= 0.0001:
                    continue

                pos = Position(
                    symbol=symbol,
                    quantity=quantity,
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
        獲取交易歷史紀錄。
        
        Reference: https://public-api.etoro.com/api/v1/trading/info/trade/history
        Official endpoint: GET /api/v1/trading/info/trade/history
        
        Required Parameters:
        - minDate: The start date of the period (YYYY-MM-DD format)
        
        Optional Parameters:
        - page: The page number
        - pageSize: The amount of trades in each page
        
        Workflow:
        1. Call GET /api/v1/trading/info/trade/history to get all historical trades
        2. Filter by instrumentId on client side if needed
        3. Use GET /api/v1/market-data/search?internalSymbolFull=SYMBOL to get instrumentId
        """
        # Official eToro API endpoint for trading history
        # 官方 eToro API 交易歷史端點
        endpoint = "/api/v1/trading/info/trade/history"
        if self.mode == "demo":
            endpoint = "/api/v1/trading/info/demo/trade/history"
        
        try:
            url = f"{self.base_url}{endpoint}"
            headers = self._get_headers()
            
            # Query parameters based on official API documentation
            # Required: minDate (YYYY-MM-DD format)
            from datetime import timedelta
            start_date = datetime.now() - timedelta(days=days)
            
            params = {
                'minDate': start_date.strftime('%Y-%m-%d'),
                'pageSize': 100  # Get up to 100 trades per request
            }
            
            logger.info(f"ETORO HISTORY: Fetching from {url}")
            logger.info(f"ETORO HISTORY: Query params: {params}")
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                # Response is a list of trade objects
                # Each trade contains: netProfit, closeRate, closeTimestamp, positionId, instrumentId,
                # isBuy, leverage, openRate, openTimestamp, stopLossRate, takeProfitRate, etc.
                history = data if isinstance(data, list) else []
                logger.info(f"ETORO HISTORY: Retrieved {len(history)} trade records")
                return history
            else:
                logger.warning(f"ETORO HISTORY: {response.status_code} - {response.text[:200]}")
                return []
        except Exception as e:
            logger.error(f"ETORO HISTORY: Failed to fetch trade history: {e}")
            return []

    def execute_order(self, order: Order) -> Dict[str, Any]:
        """
        Execute an order with risk management checks.
        執行帶有風險管理檢查的訂單。
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
            
            if isinstance(data, list) and len(data) > 0:
                 inst_id = data[0].get('InstrumentID')
                 if inst_id:
                     self._id_cache[ticker] = inst_id
                     return inst_id
            return None
        except Exception as e:
            logger.error(f"Failed to resolve Instrument ID for {ticker}: {e}")
            return None

    def _resolve_id_to_symbol(self, instrument_id: str) -> Optional[str]:
        """
        Resolve eToro Instrument ID to Ticker Symbol.
        """
        # Hardcoded common IDs for quick fix
        hardcoded = {
            "4300": "700.HK",   # Tencent (RTH)
            "4309": "700.HK",   # Tencent
            "8756": "9988.HK",  # Alibaba
            "1": "AAPL",
            "2": "AMZN",
            "4": "GOOG",
            "5": "MSFT",
            "6": "META",
            "7": "TSLA",
            "100": "V"
        }
        if instrument_id in hardcoded:
            return hardcoded[instrument_id]

        # In future, we could query a metadata endpoint
        return None

    def sync_history(self, user_id: str = "default_user", days: int = 30, initial_sync: bool = False) -> Dict[str, int]:
        """
        Sync external history to local DB.
        同步外部交易歷史到本地資料庫。
        
        Args:
            user_id: User ID for the transactions
            days: Number of days to fetch (default: 30 for regular sync)
            initial_sync: If True, fetch all history from 2024-01-01; if False, use days parameter
        
        Returns:
            Dict with 'added' and 'skipped' counts
        
        Usage:
            # Initial sync: Get all history from 2024
            service.sync_history(user_id, initial_sync=True)
            
            # Regular sync: Get last 30 days
            service.sync_history(user_id, days=30)
        """
        # Determine fetch period
        if initial_sync:
            start_date = datetime(2024, 1, 1)
            days = (datetime.now() - start_date).days
            logger.info(f"Initial sync: Fetching all history from 2024-01-01 ({days} days)")
        else:
            logger.info(f"Regular sync: Fetching last {days} days")
        
        history = self.get_history(days=days)
        if not history:
            logger.warning("No history retrieved from eToro API")
            return {"added": 0, "skipped": 0}

        # Ensure ID map is populated for symbol resolution
        if not self._id_to_symbol:
            logger.info("Populating instrument ID map from watchlists...")
            self.get_watchlists()

        added_count = 0
        skipped_count = 0
        
        existing_txs = self.transaction_repo.get_all_by_user(user_id)
        existing_sigs = set()
        for tx in existing_txs:
            try:
                sig = f"{tx.ticker}_{tx.trade_date}_{tx.action}_{float(tx.quantity):.4f}_{float(tx.price):.4f}"
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
            open_sig = f"{ticker}_{open_date_str}_{open_action}_{quantity:.4f}_{open_price:.4f}"
            
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
                close_sig = f"{ticker}_{close_date_str}_{close_action}_{quantity:.4f}_{close_price:.4f}"
                
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
            self._sync_cash_balance(user_id)
            self._backfill_from_positions(user_id)
        except Exception as e:
            logger.error(f"Post-sync logic failed: {e}")

        logger.info(f"Etoro Sync: Added {added_count}, Skipped {skipped_count}")
        return {"added": added_count, "skipped": skipped_count}

    def _sync_cash_balance(self, user_id: str) -> None:
        """
        Adjust local cash balance to match broker's available cash.
        調整本地現金餘額以匹配券商的可提款現金。
        
        v4.2.3: Fixed circular correction bug — now deletes prior sync entries
        before recalculating, preventing compounding DEPOSIT/WITHDRAWAL entries.
        """
        account = self.get_account()
        if not account:
            return

        broker_cash = account.available_cash

        # 1. Delete any previous CASH sync entries to prevent circular corrections
        # 1. We no longer blindly delete existing 'ETORO_SYNC' CASH entries.
        # Instead, we recalculate based on the current state and only add a delta if needed.
        # Original code deleted them here, which caused frequent drift.
        pass

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
                        INSERT INTO transactions (id, user_id, ticker, trade_date, action, quantity, price, fees, amount, source_file, raw_data)
                        VALUES (:id, :uid, 'CASH', :dt, :action, 1, :price, 0, :amount, 'ETORO_SYNC', :raw)
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

    def _backfill_from_positions(self, user_id: str) -> None:
        """
        Backfill BUY transactions for active positions that have no trade history.
        回補沒有交易歷史的現有持倉 BUY 記錄。
        """
        positions = self.get_positions()
        active_tickers = self.transaction_repo.get_active_tickers(user_id)
        
        for pos in positions:
            # Avoid numeric IDs if we already have the named ticker
            if pos.symbol.isdigit():
                 # Look if we have a named ticker that might match this qty (approximate)
                 # Or just skip numeric IDs if we want to be safe, as named ones come from sync_history
                 continue

            if pos.symbol not in active_tickers:
                logger.info(f"Backfilling Position: Missing BUY for {pos.symbol}, Leverage={getattr(pos, 'leverage', 1.0)}")
                # Create synthetic BUY record
                self.transaction_repo.add(
                    user_id=user_id,
                    ticker=pos.symbol,
                    date=pos.open_date.strftime('%Y-%m-%d'),
                    action="BUY",
                    quantity=pos.quantity,
                    price=pos.open_price,
                    fees=0.0,
                    leverage=getattr(pos, 'leverage', 1.0)
                )

    # --- Helpers ---
    def _fetch_portfolio_raw(self) -> Dict[str, Any]:
        """
        Raw API Call to fetch portfolio.
        Official eToro API: https://api-portal.etoro.com/api-reference/trading--real/retrieve-comprehensive-portfolio-information-including-positions-orders-and-account-status
        """
        # Official API endpoint (confirmed working: /api/v1/trading/info/portfolio)
        # 官方 API 端點（已確認可用：/api/v1/trading/info/portfolio）
        endpoint = "/api/v1/trading/info/portfolio"
        if self.mode == "demo":
            endpoint = "/api/v1/trading/info/demo/portfolio"
             
        try:
            url = f"{self.base_url}{endpoint}"
            logger.info(f"Fetching portfolio from: {url}")
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
