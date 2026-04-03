"""
LLM Tier Router — Abstract Base Class & Routing Context.

規範:
  - Clean Architecture: 介面定義在 infrastructure 層，不依賴具體實作
  - 開放/封閉原則: 新增路由策略只需新建類別，CouncilService 無需修改
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RoutingContext:
    """
    型別安全的路由決策情境物件。
    用 dataclass 取代 dict，確保型別安全、IDE 支援與欄位擴展性。
    未來新增情境因素只需加 field，不需修改方法簽章。
    """
    topic: str = ""
    round_num: int = 1
    market_volatility: float = 0.0
    user_id: str = ""
    task_type: str = ""
    requested_tier: str = "fast"


class ITierRouter(ABC):
    """
    Abstract base class for all LLM Tier Routers.

    負責回答: 「給定此情境，應使用哪個 Tier？」

    DI 使用模式:
        class CouncilService:
            def __init__(self, tier_router: ITierRouter = None):
                self.router = tier_router or CouncilTierRouter()
    """

    @abstractmethod
    def select_tier(self, context: RoutingContext) -> str:
        """
        Returns: "nano" | "fast" | "smart" | "advanced"
        """
        ...


class FixedTierRouter(ITierRouter):
    """
    測試用路由器，固定返回指定 tier。
    可在單元測試中確保 CouncilService 使用特定 tier 而不依賴環境。

    Example:
        service = CouncilService(tier_router=FixedTierRouter("smart"))
    """

    def __init__(self, tier: str = "fast"):
        self._tier = tier

    def select_tier(self, context: RoutingContext) -> str:
        return self._tier
