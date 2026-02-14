
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

    def __init__(self, base_url: str = None, mode: str = "real"):
        self.api_key = os.getenv("ETORO_API_KEY")
        self.user_key = os.getenv("ETORO_USER_KEY")
        
        # Use official endpoint if keys are provided, else fallback to bridge for legacy support
        default_base = "https://public-api.etoro.com" if self.api_key else "http://localhost:8000"
        self.base_url = base_url or os.getenv("ETORO_API_BASE_URL", default_base)
        
        self.mode = mode  # 'real' or 'demo'
        self.transaction_repo = SqliteTransactionRepository()
        self.risk_manager = RiskManager()
        self.name = "eToro"

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
            return []
            
        raw_positions = portfolio.get('Positions', portfolio.get('positions', []))
        positions = []
        for p in raw_positions:
            try:
                # Map raw position to Domain Model
                pos = Position(
                    symbol=p.get('Instrument', p.get('symbol', 'UNKNOWN')),
                    quantity=float(p.get('Amount', p.get('quantity', 0))),
                    open_price=float(p.get('OpenRate', p.get('open_price', 0))),
                    current_price=float(p.get('CurrentRate', p.get('current_price', 0))),
                    market_value=float(p.get('CurrentAmount', p.get('market_value', 0))),
                    unrealized_pnl=float(p.get('NetProfit', p.get('unrealized_pnl', 0))),
                    open_date=self._parse_date(p.get('OpenDateTime', p.get('open_date')))
                )
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

        # 2. Execute
        order_payload = {
            "Instrument": order.symbol,
            "Action": order.action.value,
            "Amount": order.quantity,
            "Leverage": order.leverage
        }
        
        endpoint = "/api/v1/trading/order"
        url = f"{self.base_url}{endpoint}"
        
        try:
             logger.info(f"ETORO EXEC: {order.action.value} {order.symbol} Qty={order.quantity}")
             response = requests.post(url, json=order_payload, headers=self._get_headers(), timeout=10)
             response.raise_for_status()
             return response.json()
        except Exception as e:
             logger.error(f"Etoro Exec Failed: {e}")
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
             if 'T' in date_str:
                  return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
             return datetime.strptime(date_str, '%Y-%m-%d')
        except:
             return datetime.now()
