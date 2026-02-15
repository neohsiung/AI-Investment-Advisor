from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
from datetime import datetime
from src.domain.entities import FeedbackExample, SecurityContext

class FeedbackRepository(ABC):
    """
    Interface for storing and retrieving agent feedback.
    儲存與檢索 Agent 回饋的介面。
    """
    @abstractmethod
    def save(self, example: FeedbackExample) -> None:
        pass

    @abstractmethod
    def get_training_examples(self, agent_name: str, min_score: float, limit: int) -> List[FeedbackExample]:
        pass

class MarketDataProvider(ABC):
    """
    Interface for fetching market data.
    獲取市場數據的介面。
    """
    @abstractmethod
    def get_history(self, ticker: str, days_back: int) -> Any: # Returns DataFrame usually
        # In strict clean architecture, this should return List[SecurityContext], 
        # but for pragmatism with Pandas-heavy logic, we might return specific structures.
        pass
    
    @abstractmethod
    def get_context_at(self, ticker: str, date: datetime) -> SecurityContext:
        pass

class IChannelAdapter(ABC):
    """
    Interface for Omni-Channel Notification Adapters (e.g., Telegram, LINE).
    全通路通知適配器介面 (例如: Telegram, LINE)。
    """
    @abstractmethod
    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send a rich alert message.
        發送豐富的警報訊息。
        """
        pass
