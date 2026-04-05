from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from src.domain.entities import FeedbackExample, SecurityContext


# ============================================================
# Model Layer Abstractions (Model > Agent > Skill Philosophy)
# 模型層抽象 — CPU 角色
# ============================================================

@dataclass(frozen=True)
class Message:
    """
    Immutable value object representing a single LLM message.
    不可變值物件，代表單一 LLM 訊息。
    """
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class LLMConfig:
    """
    Immutable value object for LLM invocation configuration.
    不可變值物件，LLM 調用配置。
    """
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    max_retries: int = 3
    timeout_seconds: int = 30


class ILLMGateway(ABC):
    """
    Interface for LLM Provider Gateway (Model Layer).
    模型層閘道介面 — 隔離所有 LLM 供應商的具體 HTTP 呼叫。

    Clean Architecture: 此介面定義於 Domain 層，
    具體實作 (OpenRouter/Gemini/OpenAI) 位於 Infrastructure 層。
    """

    @abstractmethod
    def chat(self, messages: List[Message], config: LLMConfig) -> str:
        """
        Send messages to LLM and return generated text.
        向 LLM 發送訊息並回傳生成的文本。
        """
        pass

    @abstractmethod
    def stream_chat(self, messages: List[Message], config: LLMConfig) -> typing.Generator[str, None, None]:
        """
        Send messages to LLM and yield generated text chunks.
        向 LLM 發送訊息並以 Generator 形式回傳生成的文本片段。
        """
        pass

    @abstractmethod
    def embed(self, text: str, config: LLMConfig) -> List[float]:
        """
        Generate embedding vector for the given text.
        為給定文本生成嵌入向量。
        """
        pass

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
    async def send_message(self, user_id: str, message: Any, **kwargs) -> bool:
        """
        Send a generic message (Text or Structured).
        發送通用訊息 (文字或結構化資料).
        """
        pass

    @abstractmethod
    async def receive_command(self, payload: Any, **kwargs) -> Any:
        """
        Parse incoming payload into a Standard Command object.
        解析傳入負載為標準命令物件.
        """
        pass

    @abstractmethod
    async def authenticate(self, request: Any, **kwargs) -> bool:
        """
        Verify the authenticity of the incoming request.
        驗證請求的真實性.
        """
        pass

    @abstractmethod
    async def send_alert(self, user_id: str, title: str, content: str, actions: List[Dict[str, str]] = None, **kwargs) -> bool:
        """
        Send a rich alert message. (Legacy/Convenience)
        發送豐富的警報訊息.
        """
        pass

    @abstractmethod
    def register_callback(self, callback_func: Any) -> None:
        """
        Register a callback function for user interactions (e.g. Button clicks).
        Func signature: (request_id, action) -> None
        """
        pass

    @abstractmethod
    def register_text_callback(self, callback_func: Any) -> None:
        """
        Register a callback function for incoming text messages.
        Func signature: (adapter, user_id, text) -> None
        """
        pass

    @abstractmethod
    async def handle_webhook(self, payload: Any, headers: Dict[str, Any] = None) -> Any:
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

class INotificationFilter(ABC):
    """
    Interface for filtering notifications before sending.
    通知過濾介面。
    """
    @abstractmethod
    def should_notify(self, adapter: IChannelAdapter, category: str) -> bool:
        """
        Returns True if the notification should be sent through the given adapter.
        """
        pass


class IMemoryRepository(ABC):
    """
    Interface for Memory Repository (Report Memory).
    記憶儲存庫介面（報告記憶）。
    """
    @abstractmethod
    def get_recent_reports(self, user_id: str, report_type: str, limit: int) -> List[Any]:
        pass

    @abstractmethod
    def save_report(self, item: Any) -> None:
        pass


class ILLMProvider(ABC):
    """
    Interface for LLM operations needed by MemoryService.
    MemoryService 所需的 LLM 操作介面。
    """
    @abstractmethod
    async def summarize(self, text: str) -> str:
        pass

    @abstractmethod
    async def check_contradictions(self, new_text: str, context_text: str) -> List[str]:
        pass
