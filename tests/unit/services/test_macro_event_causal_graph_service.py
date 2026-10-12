"""
Unit Tests for Macro Event Causal Graph & Narrative Risk Engine (Phase 37)
=============================================================================
測試內容：
1. 有向加權因果圖譜拓撲構建 (Macro Shock Sources, Industry Sectors, Ticker Assets)
2. 突發事件輿情抽取與關鍵詞正規化識別 (Regex & Keyword Mapping)
3. 輿情衝擊指數半衰期時間衰減 (Exponential Half-Life Decay & Pruning)
4. 帶符號彈性傳播轉移矩陣與阻尼震盪擴散演算法 (Damped Shock Diffusion)
5. 典型黑天鵝劇本模擬與壓力測試 (Taiwan Strait Blockade, Fed Hike, Bank Run, Oil War)
6. 活躍事件清空與 Redis 狀態持久化 (Persistence & Reset)
7. MacroHedgingService 宏觀避險代理聯動 (Severity classification, trim candidate weighting, causal chain rationale)
8. BatchCashDeploymentService 分批建倉整合 (Damage check, deferral, and event_graph_deferred status)
9. ConversationRouter 0-LLM /eventgraph, /causal, 模擬與守衛卡片導流
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import math
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.macro_event_causal_graph_service import (
    ActiveEventShock,
    CausalEdge,
    CausalGraphSnapshot,
    CausalTransmissionSpeed,
    MacroEventCausalGraphService,
    ShockDamageTier,
    TickerShockDamage,
)
from src.services.macro_hedging_service import (
    HedgingActionType,
    HedgingSeverity,
    MacroHedgingService,
)
from src.services.batch_cash_deployment_service import BatchCashDeploymentService
from src.services.conversation_router import ConversationRouter


class DummySettingsService:
    def __init__(self, settings: dict = None):
        self.settings = settings or {}
        self.settings_repo = self

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def get_all_settings(self):
        return self.settings

    def get(self, user_id: str, key: str, default=None):
        return self.settings.get(key, default)


class TestCausalNetworkTopology:
    """測試因果網絡節點與拓撲結構"""

    def test_nodes_and_edges_initialization(self):
        settings = DummySettingsService()
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)

        assert svc.is_enabled is True
        assert svc.decay_factor == 0.75
        assert svc.half_life_hours == 24.0

        # 檢驗 7 大宏觀衝擊源節點
        for shock_k in svc.MACRO_SHOCK_NODES:
            assert svc._graph.has_node(shock_k)
            assert getattr(svc._graph.nodes[shock_k].get("node_type"), "value", None) == "MACRO_SHOCK"

        # 檢驗 8 大產業傳導樞紐節點
        for sector_k in svc.INDUSTRY_SECTOR_NODES:
            assert svc._graph.has_node(sector_k)
            assert getattr(svc._graph.nodes[sector_k].get("node_type"), "value", None) == "INDUSTRY_SECTOR"

        # 檢驗 13 檔核心標的
        for ticker, sector in svc.TICKER_ASSET_NODES.items():
            assert svc._graph.has_node(ticker)
            assert getattr(svc._graph.nodes[ticker].get("node_type"), "value", None) == "TICKER_ASSET"
            assert svc._graph.has_edge(sector, ticker)

        # 總節點數 >= 28，總邊數 >= 30
        assert svc._graph.number_of_nodes() >= 28
        assert svc._graph.number_of_edges() >= 30


class TestEventIngestionAndDecay:
    """測試突發事件輿情抽取與半衰期衰減"""

    def test_regex_keyword_mapping(self):
        settings = DummySettingsService()
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)

        # 1. 地緣軍事衝突
        ev1 = svc.ingest_event("Tensions rise as military blockade exercises detected in Taiwan Strait")
        assert ev1 is not None
        assert ev1.shock_node == "GEOPOLITICAL_CONFLICT"
        assert 0.85 <= ev1.raw_intensity <= 1.0

        # 2. 央行鷹派升息
        ev2 = svc.ingest_event("Fed announces unexpected 50bps rate hike amid sticky inflation")
        assert ev2 is not None
        assert ev2.shock_node == "CENTRAL_BANK_HAWKISH"
        assert 0.75 <= ev2.raw_intensity <= 1.0

        # 3. 銀行流動性擠兌
        ev3 = svc.ingest_event("Regional bank run triggers liquidity crisis and insolvency fears")
        assert ev3 is not None
        assert ev3.shock_node == "BANKING_LIQUIDITY_RUN"

        # 4. 原油能源惡性通膨
        ev4 = svc.ingest_event("Major crude oil pipeline explosion sends Brent prices surging")
        assert ev4 is not None
        assert ev4.shock_node == "COMMODITY_ENERGY_SPIKE"

        # 5. 反壟斷與監管分拆
        ev5 = svc.ingest_event("DOJ and FTC launch major antitrust investigation and breakup proceedings against tech monopoly")
        assert ev5 is not None
        assert ev5.shock_node == "TECH_REGULATORY_BAN"

        # 6. 供應鏈卡喉斷鏈
        ev6 = svc.ingest_event("ASML lithography export control triggers semiconductor chip ban and embargo")
        assert ev6 is not None
        assert ev6.shock_node == "SUPPLY_CHAIN_CHOKEPOINT"

        # 7. 無關雜訊新聞
        ev_none = svc.ingest_event("Sunny weather expected this weekend in Central Park")
        assert ev_none is None

    def test_exponential_half_life_decay(self):
        settings = DummySettingsService({"event_graph_half_life_hours": 24.0})
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)

        now = datetime.now(timezone.utc)
        t_24h_ago = now - timedelta(hours=24)
        t_120h_ago = now - timedelta(hours=120)

        # 攝取 24 小時前的事件 (經過 1 個半衰期，強度應減半)
        ev_decayed = svc.ingest_event(
            headline="Taiwan Strait naval drills concluded yesterday",
            severity_override=0.80,
            event_time=t_24h_ago,
        )
        # 攝取 120 小時前 (5 個半衰期，強度應 < 0.05 被剔除)
        ev_stale = svc.ingest_event(
            headline="Fed meeting summary from last week notes hawkish bias",
            severity_override=0.80,
            event_time=t_120h_ago,
        )

        svc._decay_active_events(as_of=now)

        # 24h 前事件應保留且強度約 0.40 (0.80 * 0.5)
        active_ids = [e.event_id for e in svc._active_events]
        assert ev_decayed.event_id in active_ids
        retained = next(e for e in svc._active_events if e.event_id == ev_decayed.event_id)
        assert 0.35 <= retained.effective_intensity <= 0.45

        # 120h 前事件應被自動清理
        assert ev_stale.event_id not in active_ids


class TestShockDiffusionAndScenario:
    """測試震盪傳播擴散與黑天鵝劇本模擬"""

    def test_geopolitical_shock_diffusion(self):
        settings = DummySettingsService()
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)

        # 模擬台海封鎖斷鏈劇本
        res = svc.simulate_scenario("TAIWAN_STRAIT_BLOCKADE")
        assert res["scenario"] == "TAIWAN_STRAIT_BLOCKADE"

        snap = svc.get_snapshot()
        assert snap.systemic_shock_score >= 0.85
        assert len(snap.severely_damaged_tickers) >= 2

        # 晶片核心 NVDA, TSM, AMD 應為 SEVERE_DAMAGE 且建議 TRIM
        for sym in ["NVDA", "TSM", "AMD", "MU"]:
            dmg = snap.damages.get(sym)
            assert dmg is not None
            assert dmg.net_damage < -0.30
            assert dmg.damage_tier == ShockDamageTier.SEVERE_DAMAGE
            assert dmg.suggested_action == "TRIM"
            assert dmg.direct_exposure_path[0] == "GEOPOLITICAL_CONFLICT"
            assert dmg.direct_exposure_path[1] == "SEMI_CHIPS"

        # 避險資產 SQQQ, GLD 應為 POSITIVE_HEDGE 且建議 ADD_HEDGE
        for hedge_sym in ["SQQQ", "GLD", "SH", "TLT"]:
            dmg = snap.damages.get(hedge_sym)
            assert dmg is not None
            assert dmg.net_damage > 0.15
            assert dmg.damage_tier == ShockDamageTier.POSITIVE_HEDGE
            assert dmg.suggested_action == "ADD_HEDGE"

    def test_fed_hike_shock_diffusion(self):
        settings = DummySettingsService()
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)

        res = svc.simulate_scenario("FED_INTERMEETING_HIKE")
        assert res["scenario"] == "FED_INTERMEETING_HIKE"
        snap = svc.get_snapshot()

        # 科技藍籌與雲端軟體承壓
        assert "MSFT" in snap.damages
        assert snap.damages["MSFT"].net_damage < 0

    def test_invalid_scenario_raises_value_error(self):
        settings = DummySettingsService()
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)
        with pytest.raises(ValueError, match="Unknown scenario"):
            svc.simulate_scenario("ALIEN_INVASION")

    def test_clear_active_events(self):
        settings = DummySettingsService()
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)
        svc.simulate_scenario("MIDDLE_EAST_OIL_WAR")
        assert len(svc._active_events) > 0

        svc.clear_active_events()
        assert len(svc._active_events) == 0
        snap = svc.get_snapshot()
        assert snap.systemic_shock_score == 0.0
        assert len(snap.severely_damaged_tickers) == 0

    @pytest.mark.asyncio
    async def test_async_evaluate_ticker_and_portfolio_shock(self):
        settings = DummySettingsService()
        svc = MacroEventCausalGraphService(user_id="test_user", settings_service=settings)
        svc.simulate_scenario("TAIWAN_STRAIT_BLOCKADE")

        # 非同步查詢單一標的
        dmg = await svc.evaluate_ticker_damage("TSM")
        assert dmg is not None
        assert dmg.net_damage <= -0.30
        assert dmg.damage_level == ShockDamageTier.SEVERE_DAMAGE
        assert dmg.recommended_action == "TRIM"

        # 非同步查詢全組合快照
        snap = await svc.evaluate_portfolio_shock(["TSM", "NVDA"])
        assert snap is not None
        assert snap.systemic_shock_score >= 0.85
        assert "TSM" in snap.ticker_damages


class TestRedisPersistence:
    """測試 Redis 狀態序列化與還原"""

    def test_save_and_load_state_from_redis(self):
        mock_redis = MagicMock()
        stored_data = {}

        def mock_set(key, val, ex=None):
            stored_data[key] = val

        def mock_get(key):
            return stored_data.get(key)

        mock_redis.set.side_effect = mock_set
        mock_redis.get.side_effect = mock_get

        settings = DummySettingsService()
        with patch("src.infrastructure.cache.redis_client.get_redis_sync", return_value=mock_redis):
            svc1 = MacroEventCausalGraphService(user_id="persist_user", settings_service=settings)
            svc1.simulate_scenario("REGIONAL_BANK_CASCADE")

            # 驗證 Redis 寫入
            key = f"event_graph:state:persist_user"
            assert key in stored_data

            # 新建立另一個實例，應能從 Redis 還原活躍事件
            svc2 = MacroEventCausalGraphService(user_id="persist_user", settings_service=settings)
            assert len(svc2._active_events) == 1
            assert svc2._active_events[0].shock_node == "BANKING_LIQUIDITY_RUN"


class TestMacroHedgingServiceIntegration:
    """測試 MacroHedgingService 宏觀避險代理與因果圖譜整合"""

    def test_severity_classification_with_event_shock(self):
        hedging_svc = MacroHedgingService(settings_service=DummySettingsService())

        # 平靜市場 + 無事件衝擊 -> NORMAL
        sev_calm = hedging_svc.classify_severity(
            vix=18.0, vix_z_score=0.2, macro_stress_bias=0.0, event_graph_shock=0.0
        )
        assert sev_calm == HedgingSeverity.NORMAL

        # 平靜市場 + 中度突發因果衝擊 (0.50) -> 升級為 HIGH
        sev_shocked = hedging_svc.classify_severity(
            vix=18.0, vix_z_score=0.2, macro_stress_bias=0.0, event_graph_shock=0.50
        )
        assert sev_shocked == HedgingSeverity.HIGH

        # 偏高 VIX + 極端突發因果衝擊 (0.85) -> 升級為 CRITICAL
        sev_crit = hedging_svc.classify_severity(
            vix=26.0, vix_z_score=1.5, macro_stress_bias=0.1, event_graph_shock=0.85
        )
        assert sev_crit == HedgingSeverity.CRITICAL

    def test_identify_trim_candidates_prioritizes_shock_damaged_assets(self):
        hedging_svc = MacroHedgingService(settings_service=DummySettingsService())
        positions = [
            {"symbol": "AAPL", "market_value": 2000.0, "beta": 1.1, "unrealized_pnl_pct": 0.05},
            {"symbol": "TSM", "market_value": 2000.0, "beta": 1.2, "unrealized_pnl_pct": 0.10},
            {"symbol": "NVDA", "market_value": 2000.0, "beta": 1.4, "unrealized_pnl_pct": 0.15},
        ]

        # 模擬因果圖譜：TSM 與 NVDA 遭遇 -0.65 重創，AAPL 僅 -0.10
        damages = {
            "TSM": TickerShockDamage(
                ticker="TSM",
                net_damage=-0.65,
                damage_tier=ShockDamageTier.SEVERE_DAMAGE,
                direct_exposure_path=["GEOPOLITICAL_CONFLICT", "SEMI_CHIPS", "TSM"],
                primary_shock_source="GEOPOLITICAL_CONFLICT",
                suggested_action="TRIM",
                hedge_priority=0.85,
                rationale="受台海危機波及",
            ),
            "NVDA": TickerShockDamage(
                ticker="NVDA",
                net_damage=-0.70,
                damage_tier=ShockDamageTier.SEVERE_DAMAGE,
                direct_exposure_path=["GEOPOLITICAL_CONFLICT", "SEMI_CHIPS", "NVDA"],
                primary_shock_source="GEOPOLITICAL_CONFLICT",
                suggested_action="TRIM",
                hedge_priority=0.90,
                rationale="受台海危機波及",
            ),
            "AAPL": TickerShockDamage(
                ticker="AAPL",
                net_damage=-0.10,
                damage_tier=ShockDamageTier.NEUTRAL,
                direct_exposure_path=["GEOPOLITICAL_CONFLICT", "MEGA_CAP_TECH", "AAPL"],
                primary_shock_source="GEOPOLITICAL_CONFLICT",
                suggested_action="HOLD",
                hedge_priority=0.10,
                rationale="輕度波及",
            ),
        }

        # 需變現 $2,500
        trims = hedging_svc.identify_trim_candidates(
            positions=positions,
            required_cash_raise=2500.0,
            total_nlv=10000.0,
            user_id="test_user",
            damages=damages,
        )

        assert len(trims) > 0
        # NVDA (受損 -0.70) 與 TSM (受損 -0.65) 應優先於 AAPL 被減碼
        trim_symbols = [t.ticker for t in trims]
        assert "NVDA" in trim_symbols
        assert trims[0].ticker in ("NVDA", "TSM")
        assert "因果受損" in trims[0].reason

    def test_evaluate_macro_hedging_snapshot_integration(self):
        mock_graph = MagicMock()
        mock_snap = CausalGraphSnapshot(
            is_enabled=True,
            nodes_count=28,
            edges_count=35,
            active_events_count=1,
            decay_factor=0.75,
            half_life_hours=24.0,
            systemic_shock_score=0.90,
            severely_damaged_tickers=["TSM", "NVDA"],
            positive_hedge_tickers=["SQQQ"],
            damages={
                "TSM": TickerShockDamage(
                    ticker="TSM",
                    net_damage=-0.60,
                    damage_tier=ShockDamageTier.SEVERE_DAMAGE,
                    direct_exposure_path=["GEOPOLITICAL_CONFLICT", "SEMI_CHIPS", "TSM"],
                    primary_shock_source="GEOPOLITICAL_CONFLICT",
                    suggested_action="TRIM",
                    hedge_priority=0.80,
                    rationale="地緣衝突重創",
                )
            },
            active_events=[],
        )
        mock_graph.is_enabled = True
        mock_graph.get_snapshot.return_value = mock_snap

        hedging_svc = MacroHedgingService(
            settings_service=DummySettingsService({"enable_macro_volatility_hedging": True}),
            event_graph_service=mock_graph,
        )

        res = hedging_svc.evaluate_hedging(
            portfolio={
                "total_nlv": 10000.0,
                "cash_balance": 1000.0,
                "positions": [{"symbol": "TSM", "market_value": 3000.0, "beta": 1.2}],
            },
            vix=18.0,
        )

        assert res.event_graph_shock == 0.90
        assert "TSM" in res.severely_damaged_tickers
        assert res.severity in (HedgingSeverity.HIGH, HedgingSeverity.CRITICAL)
        assert "因果圖譜衝擊" in res.summary


class TestBatchCashDeploymentIntegration:
    """測試 BatchCashDeploymentService 分批建倉與因果圖譜整合"""

    @pytest.mark.asyncio
    async def test_get_deployment_plan_defers_shock_damaged_candidate(self):
        mock_graph = MagicMock()
        # 標定 NVDA 遭受重大衝擊
        async def mock_eval_damage(ticker):
            if ticker == "NVDA":
                return TickerShockDamage(
                    ticker="NVDA",
                    net_damage=-0.65,
                    damage_tier=ShockDamageTier.SEVERE_DAMAGE,
                    direct_exposure_path=["GEOPOLITICAL_CONFLICT", "SEMI_CHIPS", "NVDA"],
                    primary_shock_source="GEOPOLITICAL_CONFLICT",
                    suggested_action="TRIM",
                    hedge_priority=0.90,
                    rationale="重創斷鏈",
                )
            return TickerShockDamage(
                ticker=ticker,
                net_damage=0.0,
                damage_tier=ShockDamageTier.NEUTRAL,
                direct_exposure_path=[],
                primary_shock_source="",
                suggested_action="HOLD",
                hedge_priority=0.0,
                rationale="正常",
            )

        async def mock_eval_portfolio_shock(tickers):
            return CausalGraphSnapshot(
                is_enabled=True,
                nodes_count=28,
                edges_count=35,
                active_events_count=1,
                decay_factor=0.75,
                half_life_hours=24.0,
                systemic_shock_score=0.75,
                severely_damaged_tickers=["NVDA"],
                positive_hedge_tickers=[],
                damages={"NVDA": await mock_eval_damage("NVDA")},
                active_events=[],
            )

        mock_graph.is_enabled = True
        mock_graph.evaluate_ticker_damage = AsyncMock(side_effect=mock_eval_damage)
        mock_graph.evaluate_portfolio_shock = AsyncMock(side_effect=mock_eval_portfolio_shock)

        deploy_svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=DummySettingsService(),
            event_graph=mock_graph,
        )

        # 模擬現金充裕
        with patch.object(deploy_svc, "get_portfolio_status", AsyncMock(return_value={
            "deployable_cash": 1000.0,
            "total_equity": 5000.0,
            "available_cash": 2000.0,
            "required_reserve_usd": 1000.0,
        })), patch("src.repositories.ticker_universe_repository.TickerUniverseRepository.get_target_allocations", return_value=[]), \
             patch.object(deploy_svc, "_get_broker", AsyncMock(return_value=None)):

            plan = await deploy_svc.get_deployment_plan(batch_number=1)

            # 檢驗 all_candidates
            candidates = {c["ticker"]: c for c in plan.get("all_candidates", [])}
            assert "NVDA" in candidates
            nvda = candidates["NVDA"]
            assert nvda["event_shock_active"] is True
            assert nvda["amount_usd"] == 0.0  # 遭因果熔斷清零
            assert "event_graph_summary" in plan

    @pytest.mark.asyncio
    async def test_execute_batch_defers_trade_due_to_event_graph(self):
        mock_graph = MagicMock()
        mock_graph.is_enabled = True

        async def mock_eval_damage(ticker):
            return TickerShockDamage(
                ticker=ticker,
                net_damage=-0.55,
                damage_tier=ShockDamageTier.SEVERE_DAMAGE,
                direct_exposure_path=["GEOPOLITICAL_CONFLICT", "SEMI_CHIPS", ticker],
                primary_shock_source="GEOPOLITICAL_CONFLICT",
                suggested_action="TRIM",
                hedge_priority=0.80,
                rationale="受突發事件波及",
            )

        mock_graph.evaluate_ticker_damage = AsyncMock(side_effect=mock_eval_damage)

        deploy_svc = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=DummySettingsService(),
            event_graph=mock_graph,
        )

        mock_plan = {
            "can_execute": True,
            "items": [
                {"ticker": "NVDA", "amount_usd": 50.0, "confidence_score": 7.0, "role": "Alpha Top 1", "rationale": "測試"}
            ],
            "all_candidates": [
                {"ticker": "NVDA", "amount_usd": 50.0, "event_shock_active": True}
            ],
            "total_batch_amount": 50.0,
        }

        with patch.object(deploy_svc, "get_deployment_plan", AsyncMock(return_value=mock_plan)), \
             patch.object(deploy_svc.blackout_guard, "evaluate_candidate", AsyncMock(return_value=MagicMock(is_blackout=False))), \
             patch.object(deploy_svc, "_get_broker", AsyncMock(return_value=None)):

            res = await deploy_svc.execute_batch(batch_number=1, force=False, enforce_market_hours=False)

            # 檢驗 NVDA 標的被標記為 event_graph_deferred
            trades = res.get("executed_trades", [])
            assert len(trades) == 1
            assert trades[0]["status"] == "event_graph_deferred"
            assert "因果圖譜熔斷觸發" in trades[0]["reason"]


class TestConversationRouterEventGraphCommand:
    """測試 ConversationRouter 對話路由器指令"""

    @pytest.mark.asyncio
    async def test_router_handles_eventgraph_query(self):
        router = ConversationRouter()
        resp = await router._handle_system_command(None, "user_1", "/eventgraph", "user_1")
        assert resp is not None
        assert "宏觀突發事件即時輿情因果傳播與大腦避險報告" in resp
        assert "Directed Weighted Causal Event Graph" in resp
        assert "各標的因果傳播淨受損度矩陣" in resp

    @pytest.mark.asyncio
    async def test_router_handles_simulation_command(self):
        router = ConversationRouter()
        resp = await router._handle_system_command(None, "user_1", "/eventgraph sim fed", "user_1")
        assert resp is not None
        assert "劇本模擬中: FED_INTERMEETING_HIKE" in resp
        assert "CENTRAL_BANK_HAWKISH" in resp

    @pytest.mark.asyncio
    async def test_router_handles_clear_command(self):
        router = ConversationRouter()
        resp = await router._handle_system_command(None, "user_1", "/eventgraph clear", "user_1")
        assert resp is not None
        assert "宏觀突發事件因果圖譜已重置" in resp

    @pytest.mark.asyncio
    async def test_guard_command_includes_eventgraph_link(self):
        router = ConversationRouter()
        resp = await router._handle_system_command(None, "user_1", "/guard", "user_1")
        assert resp is not None
        assert "/eventgraph" in resp
        assert "宏觀突發事件因果圖譜與避險" in resp
