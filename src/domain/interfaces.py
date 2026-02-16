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
    全通路通知適配器介面 (例如: Telegram, LINE).
    v3.7 Update: Added send_message, receive_command, authenticate.
    """
    @abstractmethod
    def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message (Text or Structured).
        發送通用訊息 (文字或結構化資料).
        """
        pass

    @abstractmethod
    def receive_command(self, payload: Any, **kwargs) -> Any:
        """
        Parse incoming payload into a Standard Command object.
        解析傳入負載為標準命令物件.
        """
        pass

    @abstractmethod
    def authenticate(self, request: Any, **kwargs) -> bool:
        """
        Verify the authenticity of the incoming request.
        驗證請求的真實性.
        """
        pass

    @abstractmethod
    def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send a rich alert message. (Legacy/Convenience)
        發送豐富的警報訊息.
        """
        pass

    @abstractmethod
    def register_callback(self, callback_func: Any) -> None:
        """
        Register a callback function for user interactions.
        Func signature: (request_id, action) -> None
        """
        pass

    @abstractmethod
    def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
        """
        Handle incoming webhook request.
        Parses payload, verifies signature (if needed), and triggers callback.
        """
        pass

class IIntentClassifier(ABC):
    """
    Interface for classifying user text intent.
    使用者意圖分類介面。
    """
    @abstractmethod
    def classify(self, text: str) -> str:
        """
        Returns: "APPROVE", "REJECT", or "UNKNOWN"
        """
        pass
