"""
Unit Tests for CouncilTierRouter and ITierRouter interface.
"""
import pytest
from src.infrastructure.llm.tier_router_base import RoutingContext, ITierRouter, FixedTierRouter
from src.infrastructure.llm.council_tier_router import CouncilTierRouter


class TestRoutingContext:
    def test_default_values(self):
        ctx = RoutingContext()
        assert ctx.topic == ""
        assert ctx.round_num == 1
        assert ctx.market_volatility == 0.0
        assert ctx.requested_tier == "fast"

    def test_custom_values(self):
        ctx = RoutingContext(topic="crash analysis", market_volatility=30.0)
        assert ctx.topic == "crash analysis"
        assert ctx.market_volatility == 30.0


class TestCouncilTierRouterRules:
    @pytest.fixture
    def router(self):
        return CouncilTierRouter()

    def test_default_returns_fast(self, router):
        """正常市場應返回 fast"""
        result = router.select_tier(RoutingContext(topic="Weekly Portfolio Review"))
        assert result == "fast"

    def test_high_vix_escalates_to_smart(self, router):
        """VIX > 25 應升級至 smart"""
        result = router.select_tier(RoutingContext(topic="Normal Topic", market_volatility=30.0))
        assert result == "smart"

    def test_deep_debate_escalates_to_smart(self, router):
        """第 4 輪以上辯論應升級至 smart"""
        result = router.select_tier(RoutingContext(topic="Normal Topic", round_num=4))
        assert result == "smart"

    def test_complex_keyword_escalates_to_smart(self, router):
        """包含危機關鍵字應升級至 smart"""
        result = router.select_tier(RoutingContext(topic="Market Crash Analysis"))
        assert result == "smart"

    def test_strategy_keyword_escalates_to_advanced(self, router):
        """包含戰略關鍵字應升級至 advanced"""
        result = router.select_tier(RoutingContext(topic="Long-term Portfolio Strategy"))
        assert result == "advanced"

    def test_vix_takes_priority_over_strategy(self, router):
        """VIX 高 + 戰略主題時，VIX 優先"""
        # Market_volatility > 25 → smart
        result = router.select_tier(
            RoutingContext(topic="Portfolio Strategy", market_volatility=30.0)
        )
        assert result == "smart"

    def test_custom_keywords(self):
        """自訂關鍵字列表應可注入"""
        router = CouncilTierRouter(complex_keywords=["zombie", "apocalypse"])
        result = router.select_tier(RoutingContext(topic="Zombie Corporation Analysis"))
        assert result == "smart"


class TestFixedTierRouter:
    def test_always_returns_fixed_tier(self):
        """FixedTierRouter 應固定返回指定 tier"""
        router = FixedTierRouter("nano")
        result = router.select_tier(RoutingContext(topic="anything", market_volatility=100.0))
        assert result == "nano"

    def test_implements_interface(self):
        """FixedTierRouter 應實作 ITierRouter 介面"""
        router = FixedTierRouter("smart")
        assert isinstance(router, ITierRouter)

    def test_council_service_accepts_fixed_router(self):
        """CouncilService 應接受任何 ITierRouter 實作（DI 驗證）"""
        from src.services.council_service import CouncilService
        from unittest.mock import MagicMock
        
        # Mock settings_service to avoid initialization overhead
        settings = MagicMock()
        settings.user_id = "test_user"

        router = FixedTierRouter("fast")
        service = CouncilService(user_id="test_user", settings_service=settings, tier_router=router)
        assert service.router is router
