"""
Unit Tests for Deep Q-Learning & RL Execution Smart Order Routing (RL SOR) Service (Phase 36)
=============================================================================================
測試內容：
1. 狀態離散化 MDP (S_t) 與特徵映射 (540 格離散格子)
2. 離散動作空間 (A0 ~ A5) 與 Almgren-Chriss 先驗策略注入
3. 多目標綜合獎勵函數 R_t (滑點摩擦、市場衝擊、庫存方差風險、毒性懲罰、終局二次懲罰)
4. TD(0) 貝爾曼最優更新與離線蒙地卡羅/隨機走查模擬訓練
5. 全時窗動態切片排程生成器 (Optimal Slicing Schedule)
6. SlippageGuardService 交易風控整合 (SlippageGuardDecision 擴充欄位)
7. BatchCashDeploymentService 批次建倉整合 (候選標的拆單推薦與 rl_sor_summary)
8. ConversationRouter 0-LLM /sor, /rlexec, 智慧路由指令與報告卡片
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import math
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.services.rl_execution_sor_service import (
    RLExecutionSmartOrderRoutingService,
    RLSORAction,
    RLSORActionType,
    RLSORExecutionPlan,
    RLSORExecutionSlice,
    RLSORSnapshot,
    RLSORState,
)
from src.services.slippage_guard_service import SlippageGuardDecision, SlippageGuardService
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


class TestStateDiscretization:
    """測試 MDP 狀態離散化空間"""

    def test_discretize_state_normal(self):
        state = RLExecutionSmartOrderRoutingService.discretize_state(
            remaining_qty_ratio=0.85,
            remaining_time_ratio=0.90,
            spread_bps=12.0,
            volatility=0.22,
            vpin=0.15,
            jump_regime="CALM_DIFFUSION",
        )
        assert state.inventory_bin == 4  # 0.85 -> bin 4
        assert state.time_bin == 3       # 0.90 -> bin 3
        assert state.spread_bin == "NORMAL"
        assert state.vol_bin == "NORMAL"
        assert state.toxicity_bin == "BENIGN"
        assert state.jump_bin == "CALM"
        assert "q4:t3:sp_normal:vol_normal:tox_benign:jmp_calm" in state.key

    def test_discretize_state_toxic_and_acute_jump(self):
        state = RLExecutionSmartOrderRoutingService.discretize_state(
            remaining_qty_ratio=0.10,
            remaining_time_ratio=0.10,
            spread_bps=45.0,
            volatility=0.45,
            vpin=0.55,
            jump_regime="ACUTE_JUMP_REGIME",
        )
        assert state.inventory_bin == 0
        assert state.time_bin == 0
        assert state.spread_bin == "WIDE"
        assert state.vol_bin == "HIGH"
        assert state.toxicity_bin == "TOXIC"
        assert state.jump_bin == "ACUTE"
        assert "sp_wide:vol_high:tox_toxic:jmp_acute" in state.key

    def test_discretize_boundary_clamps(self):
        state = RLExecutionSmartOrderRoutingService.discretize_state(
            remaining_qty_ratio=-0.5,
            remaining_time_ratio=1.5,
            spread_bps=-10.0,
            volatility=0.0,
            vpin=-0.2,
            jump_regime="unknown",
        )
        assert state.inventory_bin == 0
        assert state.time_bin == 3
        assert state.spread_bin == "TIGHT"
        assert state.vol_bin == "LOW"
        assert state.toxicity_bin == "BENIGN"
        assert state.jump_bin == "CALM"


class TestActionSpaceAndPriorInitialization:
    """測試離散動作空間與先驗 Q-Table 注入"""

    def test_actions_definition(self):
        actions = RLExecutionSmartOrderRoutingService.ACTIONS
        assert len(actions) == 6
        names = [a.name for a in actions]
        assert "PASSIVE_STEALTH" in names
        assert "DEFENSIVE_TWAP" in names
        assert "NEUTRAL_PACE" in names
        assert "ACTIVE_ACCELERATED" in names
        assert "AGGRESSIVE_FILL" in names
        assert "IMMEDIATE_MARKET" in names

        # 步長單調遞增
        paces = [a.pace_ratio for a in actions]
        assert paces == sorted(paces)
        assert paces[0] == 0.10
        assert paces[-1] == 1.00

    def test_prior_policy_injection(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService(),
        )
        assert len(svc._q_table) > 0

        # 當處於高毒性環境時，PASSIVE_STEALTH (A0) 應為最優動作
        toxic_state = RLExecutionSmartOrderRoutingService.discretize_state(
            remaining_qty_ratio=0.5,
            remaining_time_ratio=0.5,
            spread_bps=15.0,
            vpin=0.45,
            jump_regime="CALM",
        )
        act_toxic = svc.select_action(toxic_state, epsilon=0.0)
        assert act_toxic.name in ("PASSIVE_STEALTH", "DEFENSIVE_TWAP")

        # 當處於時間耗盡 (t=0) 且剩餘庫存極大 (q=4) 時，應傾向追價清空 (A4 / A5)
        urgent_state = RLExecutionSmartOrderRoutingService.discretize_state(
            remaining_qty_ratio=0.9,
            remaining_time_ratio=0.05,
            spread_bps=10.0,
            vpin=0.1,
            jump_regime="CALM",
        )
        act_urgent = svc.select_action(urgent_state, epsilon=0.0)
        assert act_urgent.name in ("AGGRESSIVE_FILL", "IMMEDIATE_MARKET")


class TestMultiObjectiveRewardFunction:
    """測試多目標獎勵函數 R_t"""

    def test_reward_breakdown(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService({"rl_sor_inventory_risk_aversion": 0.20}),
        )
        state = svc.discretize_state(
            remaining_qty_ratio=0.50,
            remaining_time_ratio=0.50,
            spread_bps=10.0,
            volatility=0.20,
            vpin=0.10,
        )
        action = svc.ACTIONS[2]  # NEUTRAL_PACE (25%, +2 bps)
        reward, breakdown = svc.calculate_reward(
            state=state,
            action=action,
            order_amount_usd=1000.0,
            adv_20_usd=10000000.0,
        )

        assert reward < 0.0  # 摩擦成本為負獎勵
        assert "effective_spread_bps" in breakdown
        assert "impact_bps" in breakdown
        assert "risk_penalty_bps" in breakdown
        assert "toxic_penalty_bps" in breakdown
        assert breakdown["toxic_penalty_bps"] == 0.0  # 非毒性環境無逆向選擇重罰

    def test_toxic_regime_punishes_aggressive_action(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService(),
        )
        toxic_state = svc.discretize_state(
            remaining_qty_ratio=0.50,
            remaining_time_ratio=0.50,
            spread_bps=15.0,
            volatility=0.20,
            vpin=0.50,  # TOXIC
        )
        passive_act = svc.ACTIONS[0]     # PASSIVE_STEALTH (aggression 0.10)
        aggressive_act = svc.ACTIONS[4]  # AGGRESSIVE_FILL (aggression 0.85)

        r_passive, b_passive = svc.calculate_reward(toxic_state, passive_act, 1000.0)
        r_aggr, b_aggr = svc.calculate_reward(toxic_state, aggressive_act, 1000.0)

        # 毒性聚集時，激進追價應遭到重罰，獎勵遠低於被動限價
        assert b_passive["toxic_penalty_bps"] == 0.0
        assert b_aggr["toxic_penalty_bps"] > 0.0
        assert r_passive > r_aggr


class TestTDLearningAndOfflineTraining:
    """測試在線 TD(0) 更新與離線模擬訓練"""

    def test_update_q_value(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService({"rl_sor_learning_rate": 0.20, "rl_sor_discount_factor": 0.90}),
        )
        s1 = "test_s1"
        s2 = "test_s2"
        svc._q_table[s1] = [0.0] * 6
        svc._q_table[s2] = [10.0] * 6

        # Q(s1, a0) = 0.0
        # target = 2.0 + 0.90 * 10.0 = 11.0
        # td_error = 11.0 - 0.0 = 11.0
        # new_q = 0.0 + 0.20 * 11.0 = 2.2
        td_err = svc.update_q_value(s1, 0, reward=2.0, next_state_key=s2, done=False)
        assert abs(td_err - 11.0) < 1e-4
        assert abs(svc._q_table[s1][0] - 2.2) < 1e-4
        assert svc._updates_count == 1

    def test_train_offline_episodes(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService(),
        )
        res = svc.train_offline_episodes(episodes_count=30)
        assert res["episodes"] == 30
        assert res["q_table_size"] > 0
        assert res["total_updates"] > 0
        assert isinstance(res["mean_episode_reward"], float)


class TestOptimalSlicingPlanGeneration:
    """測試全時窗動態切片排程生成"""

    @pytest.mark.asyncio
    async def test_generate_execution_plan_standard(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService(),
        )
        plan = await svc.generate_execution_plan(
            symbol="NVDA",
            total_amount_usd=1200.0,
            target_window_minutes=15,
            spread_bps=8.0,
            volatility=0.25,
        )
        assert isinstance(plan, RLSORExecutionPlan)
        assert plan.symbol == "NVDA"
        assert abs(plan.total_amount_usd - 1200.0) < 1e-2
        assert plan.recommended_slices_count >= 1
        assert len(plan.slices) == plan.recommended_slices_count

        # 檢驗切片總額守恆 (不穿透亦不少單)
        sum_slices = sum(s.amount_usd for s in plan.slices)
        assert abs(sum_slices - 1200.0) < 1e-2

        # 檢驗券商最低下單物理約束 ($10.00 USD)
        for s in plan.slices:
            assert s.amount_usd >= 10.0
            assert s.order_type in ("LIMIT", "MARKET")

    @pytest.mark.asyncio
    async def test_generate_execution_plan_small_order(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService(),
        )
        plan = await svc.generate_execution_plan(
            symbol="AAPL",
            total_amount_usd=15.0,  # 極小訂單
            target_window_minutes=10,
        )
        assert len(plan.slices) >= 1
        assert abs(sum(s.amount_usd for s in plan.slices) - 15.0) < 1e-2
        for s in plan.slices:
            assert s.amount_usd >= 10.0

    @pytest.mark.asyncio
    async def test_evaluate_trade_routing(self):
        svc = RLExecutionSmartOrderRoutingService(
            user_id="test_user",
            settings_service=DummySettingsService(),
        )
        res = await svc.evaluate_trade_routing(symbol="MSFT", amount_usd=800.0)
        assert res["enabled"] is True
        assert "recommended_action" in res
        assert res["recommended_slices"] >= 1
        assert "expected_cost_bps" in res
        assert "slices" in res


class TestSlippageGuardServiceIntegration:
    """測試 SlippageGuardService 與 RL SOR 整合"""

    @pytest.mark.asyncio
    async def test_evaluate_trade_attaches_sor_recommendation(self):
        settings_svc = DummySettingsService()
        mock_market_clock = MagicMock()
        mock_market_clock.is_market_open.return_value = True

        mock_sor = MagicMock()
        mock_sor.is_enabled = True
        mock_sor.evaluate_trade_routing = AsyncMock(return_value={
            "enabled": True,
            "recommended_action": "NEUTRAL_PACE",
            "recommended_slices": 4,
            "expected_cost_bps": 6.8,
            "q_value": 4.5,
        })

        guard = SlippageGuardService(
            user_id="test_user",
            settings_service=settings_svc,
            market_clock=mock_market_clock,
            rl_sor=mock_sor,
        )
        guard.get_ticker_quote = AsyncMock(return_value={
            "ticker": "MSFT",
            "bid": 400.0,
            "ask": 400.20,
            "mid": 400.10,
            "last": 400.10,
            "spread_pct": 0.0005,
        })
        guard.is_opening_auction_window = MagicMock(return_value=(False, ""))

        decision = await guard.evaluate_trade(
            ticker="MSFT",
            action="BUY",
            amount_usd=500.0,
            check_opening_window=False,
        )

        assert decision.passed is True
        assert decision.rl_sor_action == "NEUTRAL_PACE"
        assert decision.rl_sor_slices == 4
        assert decision.rl_sor_expected_cost_bps == 6.8

        d_dict = decision.to_dict()
        assert d_dict["rl_sor_action"] == "NEUTRAL_PACE"
        assert d_dict["rl_sor_slices"] == 4
        assert d_dict["rl_sor_expected_cost_bps"] == 6.8


class TestBatchCashDeploymentIntegration:
    """測試 BatchCashDeploymentService 與 RL SOR 整合"""

    @pytest.mark.asyncio
    async def test_get_deployment_plan_includes_rl_sor_summary(self):
        settings_svc = DummySettingsService({"enable_rl_execution_sor": True})
        mock_broker = AsyncMock()
        mock_account = MagicMock()
        mock_account.total_equity = 10000.0
        mock_account.available_cash = 5000.0
        mock_broker.get_account.return_value = mock_account
        mock_broker.get_positions.return_value = []

        mock_slippage = MagicMock()
        mock_slippage.is_opening_auction_window.return_value = (False, "")
        mock_slippage._get_setting_int.return_value = 5
        mock_slippage._nyse_tz = timezone.utc

        mock_sor = MagicMock()
        mock_sor.is_enabled = True
        mock_sor.generate_execution_plan = AsyncMock(return_value=RLSORExecutionPlan(
            symbol="NVDA",
            total_amount_usd=300.0,
            target_window_minutes=15,
            recommended_slices_count=3,
            slices=[],
            total_expected_cost_bps=7.2,
            initial_state_key="test_key",
            selected_action="DEFENSIVE_TWAP",
            q_value=5.1,
            strategy_summary="RL 拆單 3 批次",
        ))

        deployer = BatchCashDeploymentService(
            user_id="test_user",
            settings_service=settings_svc,
            broker=mock_broker,
            slippage_guard=mock_slippage,
            rl_sor=mock_sor,
        )
        deployer.get_active_batch_number = AsyncMock(return_value=1)

        plan = await deployer.get_deployment_plan(batch_number=1)
        assert "rl_sor_summary" in plan
        assert plan["rl_sor_summary"]["is_enabled"] is True


class TestConversationRouterCommand:
    """測試 0-LLM /sor 指令與報告卡片渲染"""

    @pytest.mark.asyncio
    async def test_sor_command_reply(self):
        router = ConversationRouter()
        assert router._is_system_command("/sor") is True
        assert router._is_system_command("/rlexec") is True
        assert router._is_system_command("/smartrouting") is True
        assert router._is_system_command("智慧路由") is True
        assert router._is_system_command("強化學習拆單") is True

        reply = await router._handle_system_command(
            adapter=None,
            channel_user_id="test_channel_user",
            text="/sor",
            resolved_user_id="test_owner",
        )
        assert reply is not None
        assert "強化學習自適應動態訂單拆單與智慧路由報告" in reply
        assert "Tabular Q-Learning" in reply
        assert "MDP 狀態空間格子" in reply
        assert "自適應分步切片排程" in reply
        assert "離散動作空間累計調度分佈" in reply

    @pytest.mark.asyncio
    async def test_guard_command_mentions_sor(self):
        router = ConversationRouter()
        reply = await router._handle_system_command(
            adapter=None,
            channel_user_id="test_channel_user",
            text="/guard",
            resolved_user_id="test_owner",
        )
        assert reply is not None
        assert "/sor" in reply
        assert "強化學習動態拆單智慧路由" in reply
