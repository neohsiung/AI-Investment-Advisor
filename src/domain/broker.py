
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.trading import Order, Position, Account, BrokerType

class IBroker(ABC):
    """
    Abstract Interface for Trading Brokers (Adapter Pattern).
    Standardizes interaction with Etoro, Futu, IBKR, etc.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the broker name/type."""
        pass

    @abstractmethod
    def get_account(self) -> Optional[Account]:
        """Get account summary (Equity, Cash, etc)."""
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        """Get current open positions."""
        pass

    @abstractmethod
    def get_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get trade history (normalized format preferred)."""
        pass

    @abstractmethod
    def execute_order(self, order: Order) -> Dict[str, Any]:
        """Execute a trade order."""
        pass
    
    @abstractmethod
    def sync_history(self) -> Dict[str, int]:
        """Sync external history to local DB."""
        pass
