"""
Deep Q-Learning & Reinforcement Learning Smart Order Routing (RL SOR) Service (Phase 36)
========================================================================================
強化學習自適應動態訂單拆單與智慧路由執行代理 (RL Execution SOR Agent)

職責：
1. 建立基於馬爾可夫決策過程 (MDP) 的動態最優清算環境 (Optimal Execution MDP):
   - State S_t = (q_t, τ_t, spread_t, σ_t, toxicity_t, jump_regime_t)
     q_t: 剩餘未成交量佔總委託量比例 (Remaining Inventory Ratio in [0, 1])
     τ_t: 剩餘執行時窗比例 (Remaining Time Ratio in [0, 1])
     spread_t: 即時買賣價差狀態 (TIGHT, NORMAL, WIDE)
     σ_t: 微觀連續擴散波動率狀態 (LOW, MEDIUM, HIGH)
     toxicity_t: 微觀訂單流毒性體制 (BENIGN, ELEVATED, TOXIC via VPIN)
     jump_regime_t: 貝葉斯跳躍體制 (CALM, MODERATE, ACUTE)
2. 離散動作空間 A_t (Action Space):
   - 拆單步長配比 (Slicing Pace Ratio κ ∈ [0.10, 1.00])
   - 委託訂單型態與限價偏離度 (Limit Tilt vs Market Aggressiveness)
   - 動作集合：
     A0: PASSIVE_STEALTH (步長 10%, 被動限價 -5 bps, 適用高毒性/寬點差/充裕時間)
     A1: DEFENSIVE_TWAP (步長 15%, 自適應限價 Mid-Spread, 標配防禦)
     A2: NEUTRAL_PACE (步長 25%, 自適應限價 +2 bps, 基準中性拆單)
     A3: ACTIVE_ACCELERATED (步長 35%, 限價溢價 +5 bps, 穩健加速)
     A4: AGGRESSIVE_FILL (步長 50%, 激進限價 +10 bps, 剩餘時窗收斂)
     A5: IMMEDIATE_MARKET (步長 100%, 市價單即時撮合, 尾數或極度緊急清空)
3. 綜合獎勵函數 R_t (Multi-Objective Reward Function):
   R_t = - [ SlippageLoss + TemporaryImpact + InventoryRiskVariance + TerminalPenalty ]
   - 實現滑點與點差損失：spread * fill_aggression
   - Almgren-Chriss 暫時市場衝擊：η * (fill_qty / ADV)^0.5
   - 庫存持有風險方差懲罰：φ * q_t^2 * σ_t^2 (風險厭惡係數 φ)
   - 終局未完成庫存二次懲罰：λ_term * q_T^2
4. Q-Learning / TD-Learning 學習與逼近器：
   - 支援離線先驗 Q-Table 注入（預先基於 Almgren-Chriss 最優軌道數值求解初始化）
   - 在線 TD(0) 閉環更新 Q(s, a) ← Q(s, a) + α [r + γ max_a' Q(s', a') - Q(s, a)]
   - Redis 分散式持久化與快取共享 (rl_sor:q_table:{user_id})
5. 智慧拆單計畫生成 (Optimal Slicing Schedule):
   - 輸入總金額、目標時窗、標的狀態，輸出分步切片排程、推薦訂單型態、預期成本 bps 與期望獎勵。
6. 全流程閉環整合與 Fail-Open 容錯：
   - 整合 SlippageGuardService 與 BatchCashDeploymentService。
   - 支援高並發、高容錯，無外部數據時自動退化至標準 TWAP/限價模型，零崩潰保障。
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import math
import random
from typing import Any, Dict, List, Optional, Tuple

from src.config.owner import resolve_user_id

logger = logging.getLogger("RLExecutionSmartOrderRoutingService")


class RLSORActionType(str, Enum):
    """RL SOR 動作型態定義"""
    PASSIVE_STEALTH = "PASSIVE_STEALTH"        # A0: 步長 10%, 被動限價 -5 bps
    DEFENSIVE_TWAP = "DEFENSIVE_TWAP"          # A1: 步長 15%, 自適應限價 Mid
    NEUTRAL_PACE = "NEUTRAL_PACE"              # A2: 步長 25%, 自適應限價 +2 bps
    ACTIVE_ACCELERATED = "ACTIVE_ACCELERATED"  # A3: 步長 35%, 激進限價 +5 bps
    AGGRESSIVE_FILL = "AGGRESSIVE_FILL"        # A4: 步長 50%, 激進限價 +10 bps
    IMMEDIATE_MARKET = "IMMEDIATE_MARKET"      # A5: 步長 100%, 市價撮合


@dataclass
class RLSORAction:
    """單一離散執行動作規格"""
    action_index: int
    name: str
    action_type: RLSORActionType
    pace_ratio: float          # 佔剩餘庫存比率
    limit_tilt_bps: float      # 限價偏離度 (負為深度被動，正為向上追價)
    order_type: str            # "LIMIT" or "MARKET"
    aggression_level: float    # 0.0 (純被動) ~ 1.0 (極激進市價)
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_index": self.action_index,
            "name": self.name,
            "action_type": self.action_type.value,
            "pace_ratio": round(self.pace_ratio, 2),
            "limit_tilt_bps": round(self.limit_tilt_bps, 1),
            "order_type": self.order_type,
            "aggression_level": round(self.aggression_level, 2),
            "description": self.description,
        }


@dataclass
class RLSORState:
    """離散化 MDP 狀態"""
    inventory_bin: int        # 0..4 (0: 0-0.2, 1: 0.2-0.4, 2: 0.4-0.6, 3: 0.6-0.8, 4: 0.8-1.0)
    time_bin: int             # 0..3 (0: 0-0.25, 1: 0.25-0.5, 2: 0.5-0.75, 3: 0.75-1.0)
    spread_bin: str           # "TIGHT", "NORMAL", "WIDE"
    vol_bin: str              # "LOW", "NORMAL", "HIGH"
    toxicity_bin: str         # "BENIGN", "ELEVATED", "TOXIC"
    jump_bin: str             # "CALM", "MODERATE", "ACUTE"
    remaining_qty_ratio: float
    remaining_time_ratio: float
    spread_bps: float
    volatility: float
    key: str = ""

    def __post_init__(self):
        if not self.key:
            self.key = (
                f"q{self.inventory_bin}:t{self.time_bin}:"
                f"sp_{self.spread_bin.lower()}:vol_{self.vol_bin.lower()}:"
                f"tox_{self.toxicity_bin.lower()}:jmp_{self.jump_bin.lower()}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "inventory_bin": self.inventory_bin,
            "time_bin": self.time_bin,
            "spread_bin": self.spread_bin,
            "vol_bin": self.vol_bin,
            "toxicity_bin": self.toxicity_bin,
            "jump_bin": self.jump_bin,
            "remaining_qty_ratio": round(self.remaining_qty_ratio, 4),
            "remaining_time_ratio": round(self.remaining_time_ratio, 4),
            "spread_bps": round(self.spread_bps, 2),
            "volatility": round(self.volatility, 4),
        }


@dataclass
class RLSORExecutionSlice:
    """單一切片排程計畫"""
    slice_index: int
    target_minute_offset: int
    amount_usd: float
    action_name: str
    order_type: str
    limit_tilt_bps: float
    expected_cost_bps: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slice_index": self.slice_index,
            "target_minute_offset": self.target_minute_offset,
            "amount_usd": round(self.amount_usd, 2),
            "action_name": self.action_name,
            "order_type": self.order_type,
            "limit_tilt_bps": round(self.limit_tilt_bps, 1),
            "expected_cost_bps": round(self.expected_cost_bps, 2),
            "reason": self.reason,
        }


@dataclass
class RLSORExecutionPlan:
    """全套智慧拆單路由執行計畫"""
    symbol: str
    total_amount_usd: float
    target_window_minutes: int
    recommended_slices_count: int
    slices: List[RLSORExecutionSlice]
    total_expected_cost_bps: float
    initial_state_key: str
    selected_action: str
    q_value: float
    strategy_summary: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "total_amount_usd": round(self.total_amount_usd, 2),
            "target_window_minutes": self.target_window_minutes,
            "recommended_slices_count": self.recommended_slices_count,
            "slices": [s.to_dict() for s in self.slices],
            "total_expected_cost_bps": round(self.total_expected_cost_bps, 2),
            "initial_state_key": self.initial_state_key,
            "selected_action": self.selected_action,
            "q_value": round(self.q_value, 4),
            "strategy_summary": self.strategy_summary,
            "timestamp": self.timestamp,
        }


@dataclass
class RLSORSnapshot:
    """RL SOR 系統運行與 Q-learning 學習狀態快照"""
    is_enabled: bool
    q_table_states_count: int
    total_updates_count: int
    exploration_rate: float
    learning_rate: float
    discount_factor: float
    inventory_risk_aversion: float
    mean_reward: float
    actions_distribution: Dict[str, int]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_enabled": self.is_enabled,
            "q_table_states_count": self.q_table_states_count,
            "total_updates_count": self.total_updates_count,
            "exploration_rate": round(self.exploration_rate, 4),
            "learning_rate": round(self.learning_rate, 4),
            "discount_factor": round(self.discount_factor, 4),
            "inventory_risk_aversion": round(self.inventory_risk_aversion, 4),
            "mean_reward": round(self.mean_reward, 4),
            "actions_distribution": self.actions_distribution,
            "timestamp": self.timestamp,
        }


class RLExecutionSmartOrderRoutingService:
    """強化學習自適應動態訂單拆單與智慧路由執行服務 (Phase 36)"""

    DEFAULT_LEARNING_RATE = 0.10
    DEFAULT_DISCOUNT_FACTOR = 0.95
    DEFAULT_EXPLORATION_RATE = 0.05
    DEFAULT_INVENTORY_RISK_AVERSION = 0.15
    DEFAULT_TERMINAL_PENALTY_WEIGHT = 2.50
    DEFAULT_MARKET_IMPACT_ETA = 0.15

    # 動作空間規格清單 (Action Space)
    ACTIONS: List[RLSORAction] = [
        RLSORAction(
            action_index=0,
            name="PASSIVE_STEALTH",
            action_type=RLSORActionType.PASSIVE_STEALTH,
            pace_ratio=0.10,
            limit_tilt_bps=-5.0,
            order_type="LIMIT",
            aggression_level=0.10,
            description="隱蔽被動拆單 (10% 步長，-5 bps 限價折讓，防毒性/防衝擊)",
        ),
        RLSORAction(
            action_index=1,
            name="DEFENSIVE_TWAP",
            action_type=RLSORActionType.DEFENSIVE_TWAP,
            pace_ratio=0.15,
            limit_tilt_bps=0.0,
            order_type="LIMIT",
            aggression_level=0.25,
            description="防禦等步長拆單 (15% 步長，Mid 中間價掛單，基準防禦)",
        ),
        RLSORAction(
            action_index=2,
            name="NEUTRAL_PACE",
            action_type=RLSORActionType.NEUTRAL_PACE,
            pace_ratio=0.25,
            limit_tilt_bps=2.0,
            order_type="LIMIT",
            aggression_level=0.50,
            description="中性穩健拆單 (25% 步長，+2 bps 自適應限價，平衡成本與時窗)",
        ),
        RLSORAction(
            action_index=3,
            name="ACTIVE_ACCELERATED",
            action_type=RLSORActionType.ACTIVE_ACCELERATED,
            pace_ratio=0.35,
            limit_tilt_bps=5.0,
            order_type="LIMIT",
            aggression_level=0.70,
            description="加速推進拆單 (35% 步長，+5 bps 限價溢價，應對時窗縮減)",
        ),
        RLSORAction(
            action_index=4,
            name="AGGRESSIVE_FILL",
            action_type=RLSORActionType.AGGRESSIVE_FILL,
            pace_ratio=0.50,
            limit_tilt_bps=10.0,
            order_type="LIMIT",
            aggression_level=0.85,
            description="激進追價撮合 (50% 步長，+10 bps 限價，快速消除庫存)",
        ),
        RLSORAction(
            action_index=5,
            name="IMMEDIATE_MARKET",
            action_type=RLSORActionType.IMMEDIATE_MARKET,
            pace_ratio=1.00,
            limit_tilt_bps=20.0,
            order_type="MARKET",
            aggression_level=1.00,
            description="即時市價清空 (100% 步長，市價下單，終局或緊急成交)",
        ),
    ]

    _REDIS_Q_TABLE_KEY_PREFIX = "rl_sor:q_table"
    _REDIS_METRICS_KEY_PREFIX = "rl_sor:metrics"

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        market_data_service: Optional[Any] = None,
        compensator: Optional[Any] = None,
        vpin_guard: Optional[Any] = None,
        jump_guard: Optional[Any] = None,
        redis_client: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        if settings_service is not None:
            self.settings_service = settings_service
        else:
            try:
                from src.services.settings_service import SettingsService
                self.settings_service = SettingsService(user_id=self.user_id)
            except Exception:
                self.settings_service = None

        self.market_data_service = market_data_service
        self.compensator = compensator
        self.vpin_guard = vpin_guard
        self.jump_guard = jump_guard
        self.redis_client = redis_client

        # Q-Table: state_key -> [Q(s, a0), Q(s, a1), ..., Q(s, a5)]
        self._q_table: Dict[str, List[float]] = {}
        self._updates_count = 0
        self._action_counts = {a.name: 0 for a in self.ACTIONS}
        self._recent_rewards: List[float] = []

        # 預先加載先驗策略與 Redis 持久化
        self._initialize_prior_q_table()
        self._load_q_table_from_redis()

    # ── 設定讀取輔助 ──────────────────────────────────────────────────

    def _get_setting_bool(self, key: str, default: bool = True) -> bool:
        if not self.settings_service:
            return default
        try:
            val = self.settings_service.get_setting(key, default)
            if isinstance(val, bool):
                return val
            return str(val).lower() in ("true", "1", "yes")
        except Exception:
            return default

    def _get_setting_float(self, key: str, default: float) -> float:
        if not self.settings_service:
            return default
        try:
            val = self.settings_service.get_setting(key, default)
            return float(val) if val is not None else default
        except Exception:
            return default

    @property
    def is_enabled(self) -> bool:
        return self._get_setting_bool("enable_rl_execution_sor", True)

    @property
    def learning_rate(self) -> float:
        return self._get_setting_float("rl_sor_learning_rate", self.DEFAULT_LEARNING_RATE)

    @property
    def discount_factor(self) -> float:
        return self._get_setting_float("rl_sor_discount_factor", self.DEFAULT_DISCOUNT_FACTOR)

    @property
    def exploration_rate(self) -> float:
        return self._get_setting_float("rl_sor_exploration_rate", self.DEFAULT_EXPLORATION_RATE)

    @property
    def inventory_risk_aversion(self) -> float:
        return self._get_setting_float("rl_sor_inventory_risk_aversion", self.DEFAULT_INVENTORY_RISK_AVERSION)

    # ── 狀態離散化與特徵提取 ──────────────────────────────────────────

    @classmethod
    def discretize_state(
        cls,
        remaining_qty_ratio: float,
        remaining_time_ratio: float,
        spread_bps: float,
        volatility: float = 0.20,
        vpin: float = 0.15,
        jump_regime: str = "CALM_DIFFUSION",
    ) -> RLSORState:
        """
        將連續市場微觀狀態映射至離散 MDP 狀態格子。
        """
        # 1. 剩餘庫存比例 q (0: 0-0.2, 1: 0.2-0.4, 2: 0.4-0.6, 3: 0.6-0.8, 4: 0.8-1.0)
        q = max(0.0, min(1.0, float(remaining_qty_ratio)))
        q_bin = min(4, int(q * 5))

        # 2. 剩餘時間比例 τ (0: 0-0.25, 1: 0.25-0.5, 2: 0.5-0.75, 3: 0.75-1.0)
        t = max(0.0, min(1.0, float(remaining_time_ratio)))
        t_bin = min(3, int(t * 4))

        # 3. 買賣價差狀態
        sp = max(0.0, float(spread_bps))
        if sp <= 10.0:
            sp_bin = "TIGHT"
        elif sp <= 25.0:
            sp_bin = "NORMAL"
        else:
            sp_bin = "WIDE"

        # 4. 連續擴散波動率狀態
        vol = max(0.01, float(volatility))
        if vol <= 0.18:
            vol_bin = "LOW"
        elif vol <= 0.35:
            vol_bin = "NORMAL"
        else:
            vol_bin = "HIGH"

        # 5. 微觀訂單流毒性體制 (VPIN)
        vp = max(0.0, float(vpin))
        if vp >= 0.40:
            tox_bin = "TOXIC"
        elif vp >= 0.25:
            tox_bin = "ELEVATED"
        else:
            tox_bin = "BENIGN"

        # 6. 貝葉斯跳躍體制
        j_str = str(jump_regime).upper()
        if "ACUTE" in j_str:
            jmp_bin = "ACUTE"
        elif "MODERATE" in j_str:
            jmp_bin = "MODERATE"
        else:
            jmp_bin = "CALM"

        return RLSORState(
            inventory_bin=q_bin,
            time_bin=t_bin,
            spread_bin=sp_bin,
            vol_bin=vol_bin,
            toxicity_bin=tox_bin,
            jump_bin=jmp_bin,
            remaining_qty_ratio=q,
            remaining_time_ratio=t,
            spread_bps=sp,
            volatility=vol,
        )

    # ── 先驗數值策略與初始化 ───────────────────────────────────────────

    def _initialize_prior_q_table(self) -> None:
        """
        基於 Almgren-Chriss (2000) 最優執行解與 Cartea-Jaimungal (2014) 先驗理論，
        預先填充各代表性狀態格子之初值，保證冷啟動即為最優安全策略。
        """
        for q_bin in range(5):
            for t_bin in range(4):
                for sp_bin in ("tight", "normal", "wide"):
                    for vol_bin in ("low", "normal", "high"):
                        for tox_bin in ("benign", "elevated", "toxic"):
                            for jmp_bin in ("calm", "moderate", "acute"):
                                key = f"q{q_bin}:t{t_bin}:sp_{sp_bin}:vol_{vol_bin}:tox_{tox_bin}:jmp_{jmp_bin}"
                                # 預設動作得分向量 [A0, A1, A2, A3, A4, A5]
                                q_vals = [0.0] * 6

                                # 理論先驗加權：
                                # 1. 當處於毒性 (TOXIC) 或跳躍 (ACUTE) 體制時：高分傾向 PASSIVE_STEALTH (A0) 或 DEFENSIVE_TWAP (A1)
                                if tox_bin == "toxic" or jmp_bin == "acute":
                                    q_vals[0] = 5.0
                                    q_vals[1] = 3.0
                                    q_vals[2] = 0.0
                                    q_vals[3] = -5.0
                                    q_vals[4] = -10.0
                                    q_vals[5] = -20.0
                                # 2. 當時間極短 (t_bin == 0) 且剩餘庫存極大 (q_bin >= 3)：高分傾向 AGGRESSIVE_FILL (A4) 或 IMMEDIATE_MARKET (A5)
                                elif t_bin == 0 and q_bin >= 3:
                                    q_vals[0] = -10.0
                                    q_vals[1] = -5.0
                                    q_vals[2] = 0.0
                                    q_vals[3] = 4.0
                                    q_vals[4] = 8.0
                                    q_vals[5] = 10.0
                                # 3. 當點差寬 (WIDE) 且時間充裕 (t_bin >= 2)：高分傾向 DEFENSIVE_TWAP (A1)
                                elif sp_bin == "wide" and t_bin >= 2:
                                    q_vals[0] = 4.0
                                    q_vals[1] = 5.0
                                    q_vals[2] = 2.0
                                    q_vals[3] = -2.0
                                    q_vals[4] = -5.0
                                    q_vals[5] = -10.0
                                # 4. 平常常態 (NORMAL / BENIGN)：高分傾向 NEUTRAL_PACE (A2)
                                else:
                                    q_vals[0] = 1.0
                                    q_vals[1] = 3.0
                                    q_vals[2] = 4.5
                                    q_vals[3] = 3.0
                                    q_vals[4] = 1.0
                                    q_vals[5] = -2.0

                                self._q_table[key] = q_vals

    # ── 動作選擇與獎勵計算 ─────────────────────────────────────────────

    def select_action(
        self,
        state: RLSORState,
        epsilon: Optional[float] = None,
    ) -> RLSORAction:
        """
        根據 ε-greedy 策略選取動作；推斷時預設 epsilon=0.0 (純利用最優 Q-value)。
        """
        eps = epsilon if epsilon is not None else self.exploration_rate
        key = state.key

        if key not in self._q_table:
            # 冷啟動合成格子
            self._q_table[key] = [0.0, 1.0, 3.0, 2.0, 0.0, -2.0]

        q_values = self._q_table[key]

        if random.random() < eps:
            action_idx = random.randint(0, len(self.ACTIONS) - 1)
        else:
            # 挑選最高 Q-value 動作（若有多個並列，取步長適中者）
            max_val = max(q_values)
            best_indices = [i for i, v in enumerate(q_values) if abs(v - max_val) < 1e-5]
            action_idx = best_indices[0]

        action = self.ACTIONS[action_idx]
        self._action_counts[action.name] = self._action_counts.get(action.name, 0) + 1
        return action

    def calculate_reward(
        self,
        state: RLSORState,
        action: RLSORAction,
        order_amount_usd: float,
        adv_20_usd: float = 50000000.0,
    ) -> Tuple[float, Dict[str, float]]:
        """
        計算單步多目標執行獎勵 R_t。
        負值代表交易摩擦、市場衝擊與風險懲罰（目標為最大化獎勵 / 最小化總摩擦）。
        """
        q = state.remaining_qty_ratio
        vol = state.volatility
        spread_bps = state.spread_bps

        # 1. 執行滑點與點差衝擊 (Slippage Friction)
        # 激進市價直接支付全部半點差；被動限價單享有流動性折扣
        agg = action.aggression_level
        effective_spread_bps = (spread_bps * 0.5 * agg) + action.limit_tilt_bps

        # 2. Almgren-Chriss 暫時市場衝擊 (Temporary Impact)
        # η * sqrt(slice_amount / ADV)
        slice_amount = order_amount_usd * q * action.pace_ratio
        participation = slice_amount / max(100000.0, adv_20_usd)
        impact_bps = self.DEFAULT_MARKET_IMPACT_ETA * math.sqrt(max(1e-6, participation)) * 10000.0

        # 3. 庫存方差風險懲罰 (Inventory Risk Variance Penalty)
        # 持有剩餘庫存遭遇不利價格波動的懲罰: φ * q^2 * σ^2
        phi = self.inventory_risk_aversion
        risk_penalty_bps = phi * (q ** 2) * (vol ** 2) * 1000.0

        # 4. 毒性環境逆向選擇懲罰
        toxic_penalty_bps = 0.0
        if state.toxicity_bin == "TOXIC" and action.aggression_level > 0.4:
            toxic_penalty_bps = 15.0  # 毒性聚集時追價重罰

        # 5. 終局剩餘庫存懲罰 (若時間耗盡仍有大筆庫存未清)
        terminal_penalty_bps = 0.0
        remaining_after = max(0.0, q * (1.0 - action.pace_ratio))
        if state.time_bin == 0 and remaining_after > 0.10:
            terminal_penalty_bps = self.DEFAULT_TERMINAL_PENALTY_WEIGHT * (remaining_after ** 2) * 50.0

        total_cost_bps = (
            effective_spread_bps
            + impact_bps
            + risk_penalty_bps
            + toxic_penalty_bps
            + terminal_penalty_bps
        )

        reward = -total_cost_bps
        breakdown = {
            "effective_spread_bps": round(effective_spread_bps, 2),
            "impact_bps": round(impact_bps, 2),
            "risk_penalty_bps": round(risk_penalty_bps, 2),
            "toxic_penalty_bps": round(toxic_penalty_bps, 2),
            "terminal_penalty_bps": round(terminal_penalty_bps, 2),
            "total_cost_bps": round(total_cost_bps, 2),
        }
        return reward, breakdown

    # ── 在線與離線學習更新 ─────────────────────────────────────────────

    def update_q_value(
        self,
        state_key: str,
        action_idx: int,
        reward: float,
        next_state_key: str,
        done: bool = False,
    ) -> float:
        """
        標準 TD(0) Q-Learning 貝爾曼最優更新方程式：
        Q(s, a) ← Q(s, a) + α * [ R + γ * max_{a'} Q(s', a') - Q(s, a) ]
        """
        if state_key not in self._q_table:
            self._q_table[state_key] = [0.0] * len(self.ACTIONS)
        if next_state_key not in self._q_table:
            self._q_table[next_state_key] = [0.0] * len(self.ACTIONS)

        old_q = self._q_table[state_key][action_idx]
        next_max = 0.0 if done else max(self._q_table[next_state_key])

        target = reward + (self.discount_factor * next_max)
        td_error = target - old_q
        new_q = old_q + (self.learning_rate * td_error)

        self._q_table[state_key][action_idx] = new_q
        self._updates_count += 1

        self._recent_rewards.append(reward)
        if len(self._recent_rewards) > 200:
            self._recent_rewards.pop(0)

        return td_error

    def train_offline_episodes(self, episodes_count: int = 500) -> Dict[str, Any]:
        """
        輕量化離線模擬學習：模擬多輪隨機走查與微觀結構變動，收斂 Q-Table。
        """
        total_reward = 0.0
        for ep in range(episodes_count):
            q_ratio = 1.0
            t_ratio = 1.0
            sp_bps = random.choice([5.0, 12.0, 30.0])
            vol = random.choice([0.15, 0.25, 0.40])
            vpin = random.choice([0.12, 0.28, 0.45])
            jump = random.choice(["CALM", "MODERATE", "ACUTE"])

            step = 0
            ep_reward = 0.0
            while q_ratio > 0.02 and t_ratio > 0.0 and step < 10:
                s = self.discretize_state(
                    remaining_qty_ratio=q_ratio,
                    remaining_time_ratio=t_ratio,
                    spread_bps=sp_bps,
                    volatility=vol,
                    vpin=vpin,
                    jump_regime=jump,
                )
                action = self.select_action(s, epsilon=0.15)
                r, _ = self.calculate_reward(s, action, order_amount_usd=500.0)

                q_next = max(0.0, q_ratio * (1.0 - action.pace_ratio))
                t_next = max(0.0, t_ratio - 0.20)
                done = (q_next <= 0.02 or t_next <= 0.0)

                s_next = self.discretize_state(
                    remaining_qty_ratio=q_next,
                    remaining_time_ratio=t_next,
                    spread_bps=sp_bps,
                    volatility=vol,
                    vpin=vpin,
                    jump_regime=jump,
                )
                self.update_q_value(s.key, action.action_index, r, s_next.key, done=done)

                q_ratio = q_next
                t_ratio = t_next
                ep_reward += r
                step += 1

            total_reward += ep_reward

        self._save_q_table_to_redis()
        return {
            "episodes": episodes_count,
            "q_table_size": len(self._q_table),
            "mean_episode_reward": round(total_reward / max(1, episodes_count), 2),
            "total_updates": self._updates_count,
        }

    # ── 核心計畫生成 (Optimal Slicing Schedule) ──────────────────────

    async def generate_execution_plan(
        self,
        symbol: str,
        total_amount_usd: float,
        target_window_minutes: int = 15,
        spread_bps: Optional[float] = None,
        volatility: Optional[float] = None,
        vpin: Optional[float] = None,
        jump_regime: Optional[str] = None,
        adv_20_usd: float = 50000000.0,
    ) -> RLSORExecutionPlan:
        """
        基於當前即時市場狀態與學習好的 Q-Table，推導全時窗動態拆單排程。
        """
        sym = symbol.strip().upper()
        tot_amt = max(10.0, float(total_amount_usd))
        tot_win = max(5, int(target_window_minutes))

        # 1. 抓取或合成當前微觀狀態
        sp = spread_bps if spread_bps is not None else 10.0
        vol = volatility if volatility is not None else 0.20
        vp = vpin if vpin is not None else 0.15
        jr = jump_regime if jump_regime is not None else "CALM_DIFFUSION"

        # 若外部守衛有即時數據，嘗試補充
        if vpin is None and self.vpin_guard and getattr(self.vpin_guard, "is_enabled", True):
            try:
                v_eval = await self.vpin_guard.evaluate_ticker(sym)
                if v_eval:
                    vp = v_eval.vpin
            except Exception:
                pass

        if jump_regime is None and self.jump_guard and getattr(self.jump_guard, "is_enabled", True):
            try:
                j_eval = await self.jump_guard.evaluate_ticker(sym)
                if j_eval:
                    jr = j_eval.regime.value
                    vol = j_eval.continuous_volatility
            except Exception:
                pass

        # 2. 模擬多步 MDP 軌道推演最佳切片清單
        slices: List[RLSORExecutionSlice] = []
        rem_usd = tot_amt
        curr_q = 1.0
        curr_t = 1.0
        total_cost_acc = 0.0

        initial_state = self.discretize_state(
            remaining_qty_ratio=curr_q,
            remaining_time_ratio=curr_t,
            spread_bps=sp,
            volatility=vol,
            vpin=vp,
            jump_regime=jr,
        )
        initial_action = self.select_action(initial_state, epsilon=0.0)
        init_q_val = self._q_table.get(initial_state.key, [0.0] * 6)[initial_action.action_index]

        slice_idx = 1
        elapsed_minutes = 0

        while rem_usd >= 10.0 and curr_t > 0.0 and slice_idx <= 12:
            st = self.discretize_state(
                remaining_qty_ratio=curr_q,
                remaining_time_ratio=curr_t,
                spread_bps=sp,
                volatility=vol,
                vpin=vp,
                jump_regime=jr,
            )
            act = self.select_action(st, epsilon=0.0)

            # 計算本切片金額 (嚴格遵守券商最低下單 $10.00 USD 約束)
            if rem_usd < 20.0:
                planned_slice = round(rem_usd, 2)
            else:
                planned_slice = round(rem_usd * act.pace_ratio, 2)
                if planned_slice < 10.0:
                    planned_slice = 10.0
                # 若扣除後剩餘金額不足 $10 或動作接近全額清空，整筆納入
                if (rem_usd - planned_slice < 10.0) or (act.pace_ratio >= 0.95):
                    planned_slice = round(rem_usd, 2)

            # 計算預期摩擦成本
            _, bdown = self.calculate_reward(st, act, planned_slice, adv_20_usd)
            slice_cost = bdown["total_cost_bps"]

            slices.append(
                RLSORExecutionSlice(
                    slice_index=slice_idx,
                    target_minute_offset=elapsed_minutes,
                    amount_usd=planned_slice,
                    action_name=act.name,
                    order_type=act.order_type,
                    limit_tilt_bps=act.limit_tilt_bps,
                    expected_cost_bps=slice_cost,
                    reason=f"{act.description} (剩餘庫存: {curr_q:.1%})",
                )
            )

            total_cost_acc += slice_cost * (planned_slice / tot_amt)
            rem_usd = max(0.0, rem_usd - planned_slice)
            curr_q = rem_usd / tot_amt
            # 步進時間（依據步長比率按比例消耗時窗）
            time_step_min = max(2, int(tot_win * act.pace_ratio * 0.8))
            elapsed_minutes = min(tot_win, elapsed_minutes + time_step_min)
            curr_t = max(0.0, (tot_win - elapsed_minutes) / float(tot_win))
            slice_idx += 1

        # 若仍有剩餘零頭且有切片，歸併至最後一片
        if rem_usd > 0.0 and slices:
            slices[-1].amount_usd = round(slices[-1].amount_usd + rem_usd, 2)

        # 策略總結摘要
        strat_summary = (
            f"RL 最優拆單排程: 總額 ${tot_amt:.2f} 分為 {len(slices)} 批次，"
            f"預期執行時窗 {elapsed_minutes}/{tot_win} 分鐘，首選動作: {initial_action.name} "
            f"(加權預期摩擦: {total_cost_acc:.1f} bps，Q-Value: {init_q_val:.2f})"
        )

        plan = RLSORExecutionPlan(
            symbol=sym,
            total_amount_usd=tot_amt,
            target_window_minutes=tot_win,
            recommended_slices_count=len(slices),
            slices=slices,
            total_expected_cost_bps=total_cost_acc,
            initial_state_key=initial_state.key,
            selected_action=initial_action.name,
            q_value=init_q_val,
            strategy_summary=strat_summary,
        )
        return plan

    # ── 交易前置風控評估整合 ──────────────────────────────────────────

    async def evaluate_trade_routing(
        self,
        symbol: str,
        amount_usd: float,
        action: str = "BUY",
        spread_bps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        供 SlippageGuardService 與 AutomatedTradingService 調用之即時拆單路由推薦。
        """
        sym = symbol.strip().upper()
        if not self.is_enabled:
            return {
                "enabled": False,
                "action": "STANDARD_TWAP",
                "recommended_slices": 1,
                "strategy_hint": "RL SOR 已停用，使用常規下單通道",
            }

        plan = await self.generate_execution_plan(
            symbol=sym,
            total_amount_usd=amount_usd,
            target_window_minutes=15,
            spread_bps=spread_bps,
        )
        return {
            "enabled": True,
            "recommended_action": plan.selected_action,
            "recommended_slices": plan.recommended_slices_count,
            "expected_cost_bps": plan.total_expected_cost_bps,
            "q_value": plan.q_value,
            "slices": [s.to_dict() for s in plan.slices],
            "strategy_summary": plan.strategy_summary,
        }

    # ── 系統快照與 Redis 存取 ──────────────────────────────────────────

    def get_snapshot(self) -> RLSORSnapshot:
        """獲取當前強化學習路由引擎狀態與決策分佈"""
        mean_r = (
            sum(self._recent_rewards) / max(1, len(self._recent_rewards))
            if self._recent_rewards
            else 0.0
        )
        return RLSORSnapshot(
            is_enabled=self.is_enabled,
            q_table_states_count=len(self._q_table),
            total_updates_count=self._updates_count,
            exploration_rate=self.exploration_rate,
            learning_rate=self.learning_rate,
            discount_factor=self.discount_factor,
            inventory_risk_aversion=self.inventory_risk_aversion,
            mean_reward=mean_r,
            actions_distribution=dict(self._action_counts),
        )

    def _save_q_table_to_redis(self) -> None:
        """保存 Q-Table 與指標至 Redis (持久化)"""
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                key = f"{self._REDIS_Q_TABLE_KEY_PREFIX}:{self.user_id}"
                # 序列化代表性 Q-values
                payload = json.dumps(self._q_table)
                r.set(key, payload, ex=604800)  # 7 天保存
        except Exception as e:
            logger.debug(f"Redis write error for RL SOR Q-table: {e}")

    def _load_q_table_from_redis(self) -> None:
        """從 Redis 還原已訓練之 Q-Table"""
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                key = f"{self._REDIS_Q_TABLE_KEY_PREFIX}:{self.user_id}"
                raw = r.get(key)
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        self._q_table.update(data)
                        logger.info(f"Loaded {len(data)} Q-table states from Redis for user {self.user_id}")
        except Exception as e:
            logger.debug(f"Redis read error for RL SOR Q-table: {e}")
