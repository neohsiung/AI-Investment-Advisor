from abc import ABC, abstractmethod
from typing import List, Optional, Any
from datetime import datetime
from src.domain.entities import FeedbackExample, SecurityContext

class FeedbackRepository(ABC):
    """
    Interface for storing and retrieving agent feedback.
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
    """
    @abstractmethod
    def get_history(self, ticker: str, days_back: int) -> Any: # Returns DataFrame usually
        # In strict clean architecture, this should return List[SecurityContext], 
        # but for pragmatism with Pandas-heavy logic, we might return specific structures.
        pass
    
    @abstractmethod
    def get_context_at(self, ticker: str, date: datetime) -> SecurityContext:
        pass
