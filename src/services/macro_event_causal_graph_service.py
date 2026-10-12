"""
Macro Event Causal Graph & Narrative Risk Hedging Engine (Phase 37)
===================================================================
宏觀突發事件即時輿情因果傳播與大腦避險代理 (Macro Event Causal Graph Service)

職責：
1. 構建動態宏觀突發事件有向加權因果圖譜 (Directed Weighted Causal Event Graph Network):
   - 節點 (Nodes):
     - 宏觀衝擊源 (Macro Shocks):
       * GEOPOLITICAL_CONFLICT (地緣衝突/封鎖)
       * CENTRAL_BANK_HAWKISH (央行鷹派超預期升息)
       * BANKING_LIQUIDITY_RUN (銀行擠兌/信貸收縮)
       * SUPPLY_CHAIN_CHOKEPOINT (半導體/關鍵原物料斷鏈)
       * COMMODITY_ENERGY_SPIKE (原油天然氣惡性飆漲)
       * TECH_REGULATORY_BAN (技術出口禁令/反壟斷裁決)
       * SOVEREIGN_DEBT_CRISIS (主權違約/流動性緊縮)
     - 產業子板塊 (Industry Sectors):
       * SEMI_CHIPS (半導體晶片)
       * CLOUD_SOFTWARE (雲端與企服軟體)
       * HARDWARE_DEVICES (硬體與消費電子)
       * MEGA_CAP_TECH (巨型科技龍頭)
       * DEFENSE_AEROSPACE (國防航太)
       * ENERGY_OIL_GAS (能源油氣)
       * FINANCIALS_BANKING (金融銀行)
       * SAFE_HAVEN_ASSETS (避險黃金與美債)
     - 標的映射 (Tickers): 投組個股 (NVDA, TSM, AMD, MSFT, AAPL, MU, META) 與避險 ETF (SPY, QQQ, SH, SQQQ, TLT, GLD)。
   - 有向加權因果邊 (Directed Causal Edges):
     - 衝擊彈性傳導係數 β_ij ∈ [-1.0, +1.0] (正向同向波動，負向逆向受損)
     - 傳播速度 (INSTANT, HOURLY, DAYS) 與置信度權重。
2. 實時因果震盪擴散演算法 (Network Causal Shock Diffusion):
   - 藉由隨機遊走與吸收馬可夫鏈/PageRank 變體求解全網穩態衝擊向量：
     s^(k+1) = (1 - d) * e_0 + d * W^T * s^(k)
     (d 為網絡阻尼衰減係數，預設 0.75；e_0 為原始事件輸入向量)
   - 精算各標的之「淨因果受損度 (Net Shock Damage Index, ΔD_i ∈ [-1.0, +1.0])」：
     * ΔD_i < -0.30: 重度受損 (SEVERE_DAMAGE)
     * -0.30 <= ΔD_i < -0.10: 中度受損 (MODERATE_DAMAGE)
     * -0.10 <= ΔD_i <= +0.10: 中性微波 (NEUTRAL)
     * ΔD_i > +0.10: 避險受益 (POSITIVE_HEDGE)
   - 提取各標的之最高影響因果傳播鏈 (Causal Propagation Path)。
3. 即時事件輿情抽取與時間半衰期衰減 (Narrative Velocity & Half-Life Decay):
   - 快速解析新聞快訊、社群/SEC 文本，識別關聯衝擊源與極性強度。
   - 結合指數時間衰減模型：EffectiveShock(t) = Shock_0 * exp(-ln(2) * Δt / T_half)。
4. 閉環避險與分批建倉防禦聯動：
   - 聯動 MacroHedgingService：受損標的優先納入防禦性減碼清單，並依據風險溢價建議配置反向 ETF。
   - 聯動 BatchCashDeploymentService：若候選標的處於重大衝擊鏈條且 ΔD_i <= -0.40，前置暫緩建倉 (event_graph_deferred)。
5. Redis 分散式快取與持久化 (event_graph:state:{user_id})。
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import numpy as np

from src.config.owner import resolve_user_id

logger = logging.getLogger("MacroEventCausalGraphService")


class CausalNodeType(str, Enum):
    """因果圖譜節點類型"""
    MACRO_SHOCK = "MACRO_SHOCK"        # 宏觀外部衝擊事件源
    INDUSTRY_SECTOR = "INDUSTRY_SECTOR"  # 產業子板塊 / 傳導樞紐
    TICKER_ASSET = "TICKER_ASSET"      # 具體投資標的 (持倉 / ETF)


class CausalTransmissionSpeed(str, Enum):
    """因果傳導速度"""
    INSTANT = "INSTANT"  # 即時 (< 15 分鐘，例如突發地緣交火、油價急拉)
    HOURLY = "HOURLY"    # 小時級 (1~6 小時，例如制裁公告、評級下調)
    DAYS = "DAYS"        # 日級 (1~3 天，例如供應鏈斷鏈、貨幣政策發酵)


class ShockDamageTier(str, Enum):
    """標的淨受損等級"""
    SEVERE_DAMAGE = "SEVERE_DAMAGE"      # 重度受損 (ΔD < -0.30)
    MODERATE_DAMAGE = "MODERATE_DAMAGE"  # 中度受損 (-0.30 <= ΔD < -0.10)
    NEUTRAL = "NEUTRAL"                  # 中性微波 (-0.10 <= ΔD <= 0.10)
    POSITIVE_HEDGE = "POSITIVE_HEDGE"    # 避險受益 (ΔD > 0.10)


@dataclass
class CausalEdge:
    """因果有向邊規格"""
    source: str
    target: str
    elasticity: float       # 傳導彈性 β_ij ∈ [-1.0, 1.0]
    speed: CausalTransmissionSpeed
    weight: float = 1.0     # 邊置信度權重 [0.1, 1.0]
    mechanism: str = ""     # 傳導機制描述

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "elasticity": round(self.elasticity, 3),
            "speed": self.speed.value,
            "weight": round(self.weight, 2),
            "mechanism": self.mechanism,
        }


@dataclass
class ActiveEventShock:
    """單一活躍突發事件衝擊"""
    event_id: str
    shock_node: str           # 對應 MACRO_SHOCK 節點名稱
    headline: str
    raw_intensity: float      # 原始強度 0.0 ~ 1.0
    effective_intensity: float  # 經過時間半衰期衰減後的當前有效強度
    timestamp: str
    source: str = "news"
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "shock_node": self.shock_node,
            "headline": self.headline,
            "raw_intensity": round(self.raw_intensity, 3),
            "effective_intensity": round(self.effective_intensity, 3),
            "timestamp": self.timestamp,
            "source": self.source,
            "keywords": self.keywords,
        }


@dataclass
class TickerShockDamage:
    """單一標的之因果傳播衝擊與受損度評估"""
    ticker: str
    net_damage: float               # 淨受損度指數 ΔD_i ∈ [-1.0, +1.0] (負為受損，正為受益)
    damage_tier: ShockDamageTier
    direct_exposure_path: List[str] # 最具代表性因果路徑
    primary_shock_source: str       # 最大衝擊來源
    suggested_action: str           # "TRIM", "DEFER_BUY", "HOLD", "ADD_HEDGE"
    hedge_priority: float           # 避險優先順序 (0.0 ~ 1.0)
    rationale: str

    @property
    def damage_level(self) -> ShockDamageTier:
        return self.damage_tier

    @property
    def recommended_action(self) -> str:
        return self.suggested_action

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "net_damage": round(self.net_damage, 4),
            "damage_tier": self.damage_tier.value,
            "damage_level": self.damage_tier.value,
            "direct_exposure_path": self.direct_exposure_path,
            "primary_shock_source": self.primary_shock_source,
            "suggested_action": self.suggested_action,
            "recommended_action": self.suggested_action,
            "hedge_priority": round(self.hedge_priority, 3),
            "rationale": self.rationale,
        }


@dataclass
class CausalGraphSnapshot:
    """因果圖譜全系統狀態快照"""
    is_enabled: bool
    nodes_count: int
    edges_count: int
    active_events_count: int
    decay_factor: float
    half_life_hours: float
    systemic_shock_score: float     # 全市場綜合衝擊總分
    severely_damaged_tickers: List[str]
    positive_hedge_tickers: List[str]
    damages: Dict[str, TickerShockDamage]
    active_events: List[ActiveEventShock]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def ticker_damages(self) -> Dict[str, TickerShockDamage]:
        return self.damages

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_enabled": self.is_enabled,
            "nodes_count": self.nodes_count,
            "edges_count": self.edges_count,
            "active_events_count": self.active_events_count,
            "decay_factor": round(self.decay_factor, 3),
            "half_life_hours": round(self.half_life_hours, 1),
            "systemic_shock_score": round(self.systemic_shock_score, 4),
            "severely_damaged_tickers": self.severely_damaged_tickers,
            "positive_hedge_tickers": self.positive_hedge_tickers,
            "damages": {k: v.to_dict() for k, v in self.damages.items()},
            "ticker_damages": {k: v.to_dict() for k, v in self.damages.items()},
            "active_events": [e.to_dict() for e in self.active_events],
            "timestamp": self.timestamp,
        }


class MacroEventCausalGraphService:
    """宏觀突發事件即時輿情因果傳播與大腦避險代理 (Phase 37)"""

    DEFAULT_DECAY_FACTOR = 0.75
    DEFAULT_HALF_LIFE_HOURS = 24.0
    DEFAULT_SHOCK_ALERT_THRESHOLD = 0.40

    _REDIS_STATE_KEY_PREFIX = "event_graph:state"

    # 1. 預設圖譜節點清單
    MACRO_SHOCK_NODES = {
        "GEOPOLITICAL_CONFLICT": "地緣政治軍事衝突與海峽封鎖",
        "CENTRAL_BANK_HAWKISH": "美聯儲與全球央行超預期鷹派緊縮",
        "BANKING_LIQUIDITY_RUN": "金融同業擠兌與信貸流動性衝擊",
        "SUPPLY_CHAIN_CHOKEPOINT": "關鍵半導體與原物料卡喉斷鏈",
        "COMMODITY_ENERGY_SPIKE": "原油天然氣惡性通膨跳升",
        "TECH_REGULATORY_BAN": "先進科技出口管制與重度反壟斷制裁",
        "SOVEREIGN_DEBT_CRISIS": "主權債券拍賣違約與美債殖利率暴衝",
    }

    INDUSTRY_SECTOR_NODES = {
        "SEMI_CHIPS": "半導體先進製程與晶片設計",
        "CLOUD_SOFTWARE": "企業雲端運算與 SaaS 軟體",
        "HARDWARE_DEVICES": "消費電子、手機與伺服器硬體",
        "MEGA_CAP_TECH": "超大型科技平台龍頭",
        "DEFENSE_AEROSPACE": "國防軍工與航太",
        "ENERGY_OIL_GAS": "傳統石油與天然氣探勘開採",
        "FINANCIALS_BANKING": "商業銀行與大型投行",
        "SAFE_HAVEN_ASSETS": "終極防禦性資產 (黃金、短期美債、反向 ETF)",
    }

    TICKER_ASSET_NODES = {
        # 持倉標的
        "NVDA": "SEMI_CHIPS",
        "TSM": "SEMI_CHIPS",
        "AMD": "SEMI_CHIPS",
        "MU": "SEMI_CHIPS",
        "MSFT": "CLOUD_SOFTWARE",
        "AAPL": "HARDWARE_DEVICES",
        "META": "MEGA_CAP_TECH",
        # 基準與避險標的
        "SPY": "MEGA_CAP_TECH",
        "QQQ": "MEGA_CAP_TECH",
        "SH": "SAFE_HAVEN_ASSETS",
        "SQQQ": "SAFE_HAVEN_ASSETS",
        "TLT": "SAFE_HAVEN_ASSETS",
        "GLD": "SAFE_HAVEN_ASSETS",
    }

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
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

        self.redis_client = redis_client
        self._graph = nx.DiGraph()
        self._active_events: List[ActiveEventShock] = []
        self._cached_damages: Dict[str, TickerShockDamage] = {}

        # 初始化基礎網絡拓撲
        self._build_causal_network()
        self._load_state_from_redis()

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
        return self._get_setting_bool("enable_macro_event_causal_graph", True)

    @property
    def decay_factor(self) -> float:
        return self._get_setting_float("event_graph_decay_factor", self.DEFAULT_DECAY_FACTOR)

    @property
    def half_life_hours(self) -> float:
        return self._get_setting_float("event_graph_half_life_hours", self.DEFAULT_HALF_LIFE_HOURS)

    @property
    def shock_alert_threshold(self) -> float:
        return self._get_setting_float("event_graph_shock_alert_threshold", self.DEFAULT_SHOCK_ALERT_THRESHOLD)

    # ── 網絡拓撲構建 ──────────────────────────────────────────────────

    def _build_causal_network(self) -> None:
        """
        構建宏觀衝擊 -> 產業傳導 -> 個股標的的有向加權因果網絡。
        """
        self._graph.clear()

        # 1. 加入節點
        for node_id, desc in self.MACRO_SHOCK_NODES.items():
            self._graph.add_node(node_id, node_type=CausalNodeType.MACRO_SHOCK, description=desc)

        for node_id, desc in self.INDUSTRY_SECTOR_NODES.items():
            self._graph.add_node(node_id, node_type=CausalNodeType.INDUSTRY_SECTOR, description=desc)

        for node_id, sector in self.TICKER_ASSET_NODES.items():
            self._graph.add_node(node_id, node_type=CausalNodeType.TICKER_ASSET, sector=sector)

        # 2. 定義宏觀衝擊 -> 產業之因果傳導邊
        macro_to_sector_edges = [
            # 地緣政治衝擊 -> 重挫半導體(-0.85)、暴拉油氣(+0.80)、軍工(+0.75)、避險(+0.70)
            CausalEdge("GEOPOLITICAL_CONFLICT", "SEMI_CHIPS", elasticity=-0.85, speed=CausalTransmissionSpeed.INSTANT, mechanism="海峽運輸封鎖與晶圓供應鏈中斷風險"),
            CausalEdge("GEOPOLITICAL_CONFLICT", "ENERGY_OIL_GAS", elasticity=0.80, speed=CausalTransmissionSpeed.INSTANT, mechanism="中東產油區斷供與原油地緣溢價急拉"),
            CausalEdge("GEOPOLITICAL_CONFLICT", "DEFENSE_AEROSPACE", elasticity=0.75, speed=CausalTransmissionSpeed.HOURLY, mechanism="軍備採購急劇擴張預期"),
            CausalEdge("GEOPOLITICAL_CONFLICT", "SAFE_HAVEN_ASSETS", elasticity=0.70, speed=CausalTransmissionSpeed.INSTANT, mechanism="避險資金瘋狂湧入美債、黃金與反向標的"),
            CausalEdge("GEOPOLITICAL_CONFLICT", "MEGA_CAP_TECH", elasticity=-0.45, speed=CausalTransmissionSpeed.HOURLY, mechanism="全球風險偏好驟降與估值折現"),

            # 央行鷹派超預期緊縮 -> 重挫雲端軟體(-0.75)、科技巨頭(-0.65)、晶片(-0.55)、推升銀行淨息差(+0.30)、推升反向(+0.60)
            CausalEdge("CENTRAL_BANK_HAWKISH", "CLOUD_SOFTWARE", elasticity=-0.75, speed=CausalTransmissionSpeed.INSTANT, mechanism="長天期現金流折現率飆升重創 SaaS 高估值"),
            CausalEdge("CENTRAL_BANK_HAWKISH", "MEGA_CAP_TECH", elasticity=-0.65, speed=CausalTransmissionSpeed.INSTANT, mechanism="利率攀升壓制大型權值股本益比"),
            CausalEdge("CENTRAL_BANK_HAWKISH", "SEMI_CHIPS", elasticity=-0.55, speed=CausalTransmissionSpeed.HOURLY, mechanism="資本開支融資成本墊高壓抑晶圓建廠"),
            CausalEdge("CENTRAL_BANK_HAWKISH", "SAFE_HAVEN_ASSETS", elasticity=0.50, speed=CausalTransmissionSpeed.INSTANT, mechanism="現金收益率提升促使資金撤出高風險資產轉向反向對沖"),

            # 銀行擠兌與流動性危機 -> 摧毀金融(-0.90)、衝擊科技(-0.50)、避險(+0.85)
            CausalEdge("BANKING_LIQUIDITY_RUN", "FINANCIALS_BANKING", elasticity=-0.90, speed=CausalTransmissionSpeed.INSTANT, mechanism="同業存貸互疑、未實現資本虧損引爆恐慌擠兌"),
            CausalEdge("BANKING_LIQUIDITY_RUN", "MEGA_CAP_TECH", elasticity=-0.50, speed=CausalTransmissionSpeed.HOURLY, mechanism="信貸緊縮壓抑新創投融資與企業 IT 預算"),
            CausalEdge("BANKING_LIQUIDITY_RUN", "SAFE_HAVEN_ASSETS", elasticity=0.85, speed=CausalTransmissionSpeed.INSTANT, mechanism="極度恐慌驅使資金尋求避險"),

            # 供應鏈卡喉斷鏈 / 晶片出口管制 -> 晶片直接遭擊(-0.80)、硬體設備受創(-0.60)
            CausalEdge("SUPPLY_CHAIN_CHOKEPOINT", "SEMI_CHIPS", elasticity=-0.80, speed=CausalTransmissionSpeed.INSTANT, mechanism="核心關鍵材料或光刻機禁運斷供"),
            CausalEdge("SUPPLY_CHAIN_CHOKEPOINT", "HARDWARE_DEVICES", elasticity=-0.60, speed=CausalTransmissionSpeed.HOURLY, mechanism="晶片零組件缺料導致終端產品延後出貨"),

            # 原油大宗商品飆漲 -> 能源受益(+0.85)、壓抑軟體與硬體(-0.40)
            CausalEdge("COMMODITY_ENERGY_SPIKE", "ENERGY_OIL_GAS", elasticity=0.85, speed=CausalTransmissionSpeed.INSTANT, mechanism="油價飆漲直接提振上游油氣自由現金流"),
            CausalEdge("COMMODITY_ENERGY_SPIKE", "MEGA_CAP_TECH", elasticity=-0.40, speed=CausalTransmissionSpeed.DAYS, mechanism="二次通膨預期引發聯準會重回緊縮擔憂"),

            # 科技出口管制與重磅反壟斷 -> 晶片受挫(-0.75)、科技巨頭受挫(-0.60)
            CausalEdge("TECH_REGULATORY_BAN", "SEMI_CHIPS", elasticity=-0.75, speed=CausalTransmissionSpeed.HOURLY, mechanism="海外關鍵市場營收直接被政策閹割"),
            CausalEdge("TECH_REGULATORY_BAN", "MEGA_CAP_TECH", elasticity=-0.60, speed=CausalTransmissionSpeed.HOURLY, mechanism="巨額反壟斷罰款或拆分營運威脅"),

            # 主權債務違約危機 -> 衝擊金融(-0.75)、科技(-0.60)、推升反向避險(+0.75)
            CausalEdge("SOVEREIGN_DEBT_CRISIS", "FINANCIALS_BANKING", elasticity=-0.75, speed=CausalTransmissionSpeed.INSTANT, mechanism="國債資產減計導致銀行資本適足率崩塌"),
            CausalEdge("SOVEREIGN_DEBT_CRISIS", "SAFE_HAVEN_ASSETS", elasticity=0.75, speed=CausalTransmissionSpeed.INSTANT, mechanism="避險需求急劇升溫"),
        ]

        # 3. 定義產業 -> 個股/ETF 之歸屬映射邊
        sector_to_ticker_edges = [
            # SEMI_CHIPS
            CausalEdge("SEMI_CHIPS", "NVDA", elasticity=0.95, speed=CausalTransmissionSpeed.INSTANT, mechanism="AI 算力晶片龍頭極高 Beta 彈性"),
            CausalEdge("SEMI_CHIPS", "TSM", elasticity=0.92, speed=CausalTransmissionSpeed.INSTANT, mechanism="全球晶圓代工樞紐製造彈性"),
            CausalEdge("SEMI_CHIPS", "AMD", elasticity=0.90, speed=CausalTransmissionSpeed.INSTANT, mechanism="高效能運算與伺服器晶片彈性"),
            CausalEdge("SEMI_CHIPS", "MU", elasticity=0.85, speed=CausalTransmissionSpeed.INSTANT, mechanism="記憶體週期與晶圓供給彈性"),

            # CLOUD_SOFTWARE
            CausalEdge("CLOUD_SOFTWARE", "MSFT", elasticity=0.85, speed=CausalTransmissionSpeed.INSTANT, mechanism="Azure 雲端與 Office 企業訂閱主幹"),

            # HARDWARE_DEVICES
            CausalEdge("HARDWARE_DEVICES", "AAPL", elasticity=0.88, speed=CausalTransmissionSpeed.INSTANT, mechanism="iPhone 與 Mac 全球消費供應鏈樞紐"),

            # MEGA_CAP_TECH
            CausalEdge("MEGA_CAP_TECH", "META", elasticity=0.85, speed=CausalTransmissionSpeed.INSTANT, mechanism="數位廣告與社群元宇宙巨頭"),
            CausalEdge("MEGA_CAP_TECH", "MSFT", elasticity=0.75, speed=CausalTransmissionSpeed.INSTANT, mechanism="巨型科技藍籌權重指數連動"),
            CausalEdge("MEGA_CAP_TECH", "AAPL", elasticity=0.75, speed=CausalTransmissionSpeed.INSTANT, mechanism="大盤權值第一主力指數連動"),
            CausalEdge("MEGA_CAP_TECH", "NVDA", elasticity=0.80, speed=CausalTransmissionSpeed.INSTANT, mechanism="科技牛市權重衝鋒代表"),

            # 大盤基準
            CausalEdge("MEGA_CAP_TECH", "SPY", elasticity=0.70, speed=CausalTransmissionSpeed.INSTANT, mechanism="標普 500 核心權重連動"),
            CausalEdge("MEGA_CAP_TECH", "QQQ", elasticity=0.85, speed=CausalTransmissionSpeed.INSTANT, mechanism="那斯達克 100 科技核心連動"),

            # SAFE_HAVEN_ASSETS
            CausalEdge("SAFE_HAVEN_ASSETS", "SH", elasticity=0.80, speed=CausalTransmissionSpeed.INSTANT, mechanism="標普 500 單倍反向 ETF"),
            CausalEdge("SAFE_HAVEN_ASSETS", "SQQQ", elasticity=0.95, speed=CausalTransmissionSpeed.INSTANT, mechanism="那斯達克 100 三倍反向對沖 ETF"),
            CausalEdge("SAFE_HAVEN_ASSETS", "TLT", elasticity=0.70, speed=CausalTransmissionSpeed.INSTANT, mechanism="20年期以上美國長天期公債避險"),
            CausalEdge("SAFE_HAVEN_ASSETS", "GLD", elasticity=0.75, speed=CausalTransmissionSpeed.INSTANT, mechanism="實體黃金抗通膨與防地緣避險"),
        ]

        # 寫入有向圖
        for edge in macro_to_sector_edges + sector_to_ticker_edges:
            self._graph.add_edge(
                edge.source,
                edge.target,
                elasticity=edge.elasticity,
                speed=edge.speed,
                weight=edge.weight,
                mechanism=edge.mechanism,
            )

        logger.info(
            f"Initialized Causal Graph: {self._graph.number_of_nodes()} nodes, "
            f"{self._graph.number_of_edges()} edges"
        )

    # ── 突發事件攝取與關鍵詞解析 ──────────────────────────────────────────

    def ingest_event(
        self,
        headline: str,
        content: str = "",
        source: str = "news",
        severity_override: Optional[float] = None,
        event_time: Optional[datetime] = None,
    ) -> Optional[ActiveEventShock]:
        """
        攝取新聞、快訊或 SEC 文本，透過正則規則與關鍵字抽取識別宏觀衝擊源。
        """
        txt = (headline + " " + content).lower()
        now_dt = event_time or datetime.now(timezone.utc)
        iso_ts = now_dt.isoformat()

        # 衝擊源匹配關鍵字詞庫
        shock_patterns: Dict[str, Tuple[List[str], float]] = {
            "GEOPOLITICAL_CONFLICT": (
                ["taiwan", "strait", "missile", "military", "war", "blockade", "middle east", "iran", "israel", "gaza", "russia", "ukraine", "invasion", "台海", "軍演", "開戰", "飛彈", "封鎖"],
                0.85,
            ),
            "CENTRAL_BANK_HAWKISH": (
                ["fed", "powell", "hike", "rate hike", "hawkish", "tightening", "cpi surge", "hot inflation", "50bps", "升息", "鷹派", "通膨惡化", "緊縮"],
                0.75,
            ),
            "BANKING_LIQUIDITY_RUN": (
                ["bank run", "liquidity crisis", "insolvency", "bailout", "default", "credit squeeze", "svb", "credit suisse", "銀行擠兌", "倒閉", "清算", "流動性枯竭"],
                0.90,
            ),
            "SUPPLY_CHAIN_CHOKEPOINT": (
                ["embargo", "sanction", "export control", "chokepoint", "lithography", "asml", "rare earth", "chip ban", "斷鏈", "禁運", "制裁", "出口管制", "斷供"],
                0.80,
            ),
            "COMMODITY_ENERGY_SPIKE": (
                ["crude oil", "brent", "opec", "energy crisis", "pipeline blast", "gas spike", "油價暴漲", "天然氣飆漲", "能源危機"],
                0.70,
            ),
            "TECH_REGULATORY_BAN": (
                ["antitrust", "doj", "breakup", "ftc", "investigation", "monopoly", "ai restriction", "反壟斷", "拆分", "重度開罰", "監管封殺"],
                0.65,
            ),
            "SOVEREIGN_DEBT_CRISIS": (
                ["treasury auction", "yield spike", "debt ceiling", "downgrade", "sovereign default", "美債標售慘澹", "債務上限", "主權評級調降"],
                0.75,
            ),
        }

        matched_shock = None
        highest_matched_intensity = 0.0
        matched_kws = []

        for shock_key, (kws, base_intensity) in shock_patterns.items():
            hit_kws = [k for k in kws if k in txt]
            if hit_kws:
                # 關鍵詞越多，衝擊強度加乘
                intensity = min(1.0, base_intensity + (len(hit_kws) - 1) * 0.05)
                if intensity > highest_matched_intensity:
                    highest_matched_intensity = intensity
                    matched_shock = shock_key
                    matched_kws = hit_kws

        if not matched_shock:
            return None

        final_intensity = (
            max(0.1, min(1.0, float(severity_override)))
            if severity_override is not None
            else highest_matched_intensity
        )

        event_id = f"ev_{matched_shock.lower()}_{int(now_dt.timestamp())}"
        shock_obj = ActiveEventShock(
            event_id=event_id,
            shock_node=matched_shock,
            headline=headline.strip(),
            raw_intensity=final_intensity,
            effective_intensity=final_intensity,
            timestamp=iso_ts,
            source=source,
            keywords=matched_kws,
        )

        # 儲存至活動清單（若同一衝擊源已有近期事件，更新為強度較高者）
        existing = [e for e in self._active_events if e.shock_node == matched_shock]
        if existing:
            existing[0].headline = headline.strip()
            existing[0].raw_intensity = max(existing[0].raw_intensity, final_intensity)
            existing[0].effective_intensity = existing[0].raw_intensity
            existing[0].timestamp = iso_ts
            existing[0].keywords = list(set(existing[0].keywords + matched_kws))
            shock_obj = existing[0]
        else:
            self._active_events.append(shock_obj)

        logger.warning(
            f"Ingested Macro Shock Event: {matched_shock} (Intensity: {final_intensity:.2f}) - {headline}"
        )
        self.propagate_shocks()
        self._save_state_to_redis()
        return shock_obj

    # ── 時間半衰期衰減計算 ──────────────────────────────────────────

    def _decay_active_events(self, as_of: Optional[datetime] = None) -> None:
        """
        計算所有活躍事件隨時間的指數半衰期衰減：
        effective_intensity = raw_intensity * exp(-ln(2) * Δt / T_half)
        若衰減後低於 0.05 則自動清理。
        """
        now_dt = as_of or datetime.now(timezone.utc)
        decay_const = math.log(2.0) / max(0.5, self.half_life_hours)

        retained: List[ActiveEventShock] = []
        for ev in self._active_events:
            try:
                ev_time = datetime.fromisoformat(ev.timestamp)
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=timezone.utc)
                delta_hours = max(0.0, (now_dt - ev_time).total_seconds() / 3600.0)
                eff = ev.raw_intensity * math.exp(-decay_const * delta_hours)
                ev.effective_intensity = round(eff, 4)
                if ev.effective_intensity >= 0.05:
                    retained.append(ev)
            except Exception as e:
                logger.debug(f"Event decay calculation error: {e}")
                retained.append(ev)

        self._active_events = retained

    # ── 網絡因果傳播演算法 (Causal Shock Diffusion) ───────────────────

    def propagate_shocks(
        self,
        custom_shocks: Optional[Dict[str, float]] = None,
    ) -> Dict[str, TickerShockDamage]:
        """
        執行因果圖譜傳播演算法，計算各產業樞紐與投資標的之淨受損度 ΔD_i。
        """
        self._decay_active_events()

        nodes = list(self._graph.nodes())
        n = len(nodes)
        node_idx = {name: i for i, name in enumerate(nodes)}

        # 1. 構建初始衝擊向量 e_0
        e_0 = np.zeros(n, dtype=float)

        if custom_shocks:
            for s_name, s_val in custom_shocks.items():
                if s_name in node_idx:
                    e_0[node_idx[s_name]] = float(s_val)
        else:
            for ev in self._active_events:
                if ev.shock_node in node_idx:
                    e_0[node_idx[ev.shock_node]] = max(
                        e_0[node_idx[ev.shock_node]], ev.effective_intensity
                    )

        # 2. 構建帶符號彈性傳播轉移矩陣 W
        W = np.zeros((n, n), dtype=float)
        for u, v, data in self._graph.edges(data=True):
            elast = data.get("elasticity", 0.0)
            weight = data.get("weight", 1.0)
            W[node_idx[u], node_idx[v]] = elast * weight

        # 3. 網絡震盪傳播迭代求解：保持外生宏觀衝擊源強度，沿有向加權邊依阻尼衰減擴散
        d = self.decay_factor
        s = np.copy(e_0)

        # 進行 5 輪拓撲迭代收斂 (因果圖為 DAG/低環結構，5 輪足以擴散至終端資產)
        for _ in range(5):
            s_next = d * np.dot(W.T, s)
            for shock_name in self.MACRO_SHOCK_NODES:
                if shock_name in node_idx and e_0[node_idx[shock_name]] > 0:
                    s_next[node_idx[shock_name]] = e_0[node_idx[shock_name]]
            if np.allclose(s, s_next, atol=1e-4):
                break
            s = s_next

        # 4. 解析終端 TICKER_ASSET 節點之淨受損度
        damages: Dict[str, TickerShockDamage] = {}
        for ticker, sector in self.TICKER_ASSET_NODES.items():
            if ticker not in node_idx:
                continue
            idx = node_idx[ticker]
            # s[idx] 正值代表受到負向衝擊造成的受損（若傳播彈性為負，則數值為負）
            # 我們定義淨受損度 net_damage ∈ [-1.0, 1.0]：
            # 負值代表股價承壓受損（例如 -0.75），正值代表避險受益（例如 +0.60）
            raw_val = float(s[idx])

            # 若為避險資產 (SAFE_HAVEN_ASSETS 如 SH, SQQQ, GLD, TLT)，其彈性已為正向
            is_hedge_asset = sector == "SAFE_HAVEN_ASSETS"
            net_damage = raw_val

            # 判定等級
            if net_damage <= -0.30:
                tier = ShockDamageTier.SEVERE_DAMAGE
                suggested_act = "TRIM"
                hedge_prio = min(1.0, abs(net_damage) * 1.2)
            elif net_damage <= -0.10:
                tier = ShockDamageTier.MODERATE_DAMAGE
                suggested_act = "DEFER_BUY"
                hedge_prio = min(1.0, abs(net_damage))
            elif net_damage >= 0.10:
                tier = ShockDamageTier.POSITIVE_HEDGE
                suggested_act = "ADD_HEDGE" if is_hedge_asset else "HOLD"
                hedge_prio = 0.0
            else:
                tier = ShockDamageTier.NEUTRAL
                suggested_act = "HOLD"
                hedge_prio = 0.0

            # 搜尋最強因果路徑
            best_path = []
            primary_shock = "NONE"
            max_shock_val = 0.0

            for shock_name in self.MACRO_SHOCK_NODES:
                if shock_name in node_idx and e_0[node_idx[shock_name]] > 0:
                    try:
                        if nx.has_path(self._graph, shock_name, ticker):
                            paths = list(nx.all_simple_paths(self._graph, shock_name, ticker, cutoff=3))
                            if paths:
                                p = paths[0]
                                if e_0[node_idx[shock_name]] > max_shock_val:
                                    max_shock_val = e_0[node_idx[shock_name]]
                                    best_path = p
                                    primary_shock = shock_name
                    except Exception:
                        pass

            if not best_path:
                best_path = [sector, ticker]

            path_str = " -> ".join(best_path)
            if net_damage < 0:
                rationale = (
                    f"受 {primary_shock} 經由 [{path_str}] 傳播波及，"
                    f"預估因果受損度 {net_damage:+.1%}，建議處置: {suggested_act}"
                )
            elif net_damage > 0:
                rationale = (
                    f"受 {primary_shock} 經由 [{path_str}] 避險受益推升，"
                    f"預估因果推升度 {net_damage:+.1%}，建議處置: {suggested_act}"
                )
            else:
                rationale = f"未受重大宏觀因果波及，維持正常配置 ({suggested_act})"

            damages[ticker] = TickerShockDamage(
                ticker=ticker,
                net_damage=net_damage,
                damage_tier=tier,
                direct_exposure_path=best_path,
                primary_shock_source=primary_shock,
                suggested_action=suggested_act,
                hedge_priority=hedge_prio,
                rationale=rationale,
            )

        self._cached_damages = damages
        return damages

    # ── 對外查詢與評估接口 ──────────────────────────────────────────

    def get_snapshot(self) -> CausalGraphSnapshot:
        """取得當前宏觀事件因果圖譜與避險狀態快照"""
        damages = self.propagate_shocks()
        severe = [t for t, d in damages.items() if d.damage_tier == ShockDamageTier.SEVERE_DAMAGE]
        hedges = [t for t, d in damages.items() if d.damage_tier == ShockDamageTier.POSITIVE_HEDGE]

        # 系統性總衝擊分：活躍事件有效強度之歐式範數
        sys_shock = float(
            math.sqrt(sum(ev.effective_intensity ** 2 for ev in self._active_events))
            if self._active_events
            else 0.0
        )

        return CausalGraphSnapshot(
            is_enabled=self.is_enabled,
            nodes_count=self._graph.number_of_nodes(),
            edges_count=self._graph.number_of_edges(),
            active_events_count=len(self._active_events),
            decay_factor=self.decay_factor,
            half_life_hours=self.half_life_hours,
            systemic_shock_score=min(1.0, sys_shock),
            severely_damaged_tickers=severe,
            positive_hedge_tickers=hedges,
            damages=damages,
            active_events=list(self._active_events),
        )

    def evaluate_ticker_damage_sync(self, ticker: str) -> Optional[TickerShockDamage]:
        """評估單一標的之因果受損度（同步版本）"""
        sym = ticker.strip().upper()
        if not self.is_enabled:
            return None
        if not self._cached_damages:
            self.propagate_shocks()
        return self._cached_damages.get(sym)

    async def evaluate_ticker_damage(self, ticker: str) -> Optional[TickerShockDamage]:
        """評估單一標的之因果受損度（供交易與建倉守衛非同步調用）"""
        return self.evaluate_ticker_damage_sync(ticker)

    async def evaluate_portfolio_shock(
        self, tickers: Optional[List[str]] = None
    ) -> CausalGraphSnapshot:
        """非同步評估給定標的或全投資組合之因果衝擊快照"""
        return self.get_snapshot()

    def clear_active_events(self) -> None:
        """清空所有活躍事件（回歸常態）"""
        self._active_events.clear()
        self._cached_damages.clear()
        self._save_state_to_redis()
        logger.info("Cleared all active events in MacroEventCausalGraphService")

    def simulate_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """
        內建壓力測試與代表性黑天鵝劇本模擬：
        - TAIWAN_STRAIT_BLOCKADE: 台海晶片斷鏈危機
        - FED_INTERMEETING_HIKE: 聯準會緊急突擊升息
        - REGIONAL_BANK_CASCADE: 區域性銀行連鎖倒閉擠兌
        - MIDDLE_EAST_OIL_WAR: 中東產油區戰火油價飆破 $130
        """
        scenarios = {
            "TAIWAN_STRAIT_BLOCKADE": {
                "headline": "🚨 突發地緣封鎖：台海關鍵航道軍演禁航，先進晶圓空海運受阻",
                "content": "taiwan strait blockade missile military semi chips supply chain chokepoint",
                "severity": 0.90,
            },
            "FED_INTERMEETING_HIKE": {
                "headline": "🚨 聯準會緊急召開非常規閉門會議，突擊調升聯邦基準利率 50 bps",
                "content": "fed powell rate hike hawkish hot cpi 50bps tightening cloud software",
                "severity": 0.85,
            },
            "REGIONAL_BANK_CASCADE": {
                "headline": "🚨 美國多家區域商業銀行遭遇未實現債券虧損擠兌，流動性枯竭告急",
                "content": "bank run liquidity crisis insolvency svb credit squeeze bailout",
                "severity": 0.88,
            },
            "MIDDLE_EAST_OIL_WAR": {
                "headline": "🚨 中東主要產油國輸油管道遇襲爆炸，布蘭特原油狂拉逼近 130 美元",
                "content": "middle east crude oil brent opec pipeline blast energy crisis",
                "severity": 0.80,
            },
        }

        sc = scenarios.get(scenario_name.upper())
        if not sc:
            raise ValueError(f"Unknown scenario: {scenario_name}. Options: {list(scenarios.keys())}")

        ev = self.ingest_event(
            headline=sc["headline"],
            content=sc["content"],
            source="simulation",
            severity_override=sc["severity"],
        )
        snap = self.get_snapshot()
        return {
            "scenario": scenario_name,
            "event": ev.to_dict() if ev else {},
            "snapshot": snap.to_dict(),
        }

    # ── Redis 存取與持久化 ──────────────────────────────────────────

    def _save_state_to_redis(self) -> None:
        """保存活躍事件與受損評估至 Redis"""
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                key = f"{self._REDIS_STATE_KEY_PREFIX}:{self.user_id}"
                payload = json.dumps([e.to_dict() for e in self._active_events])
                r.set(key, payload, ex=86400 * 3)  # 3 天有效期
        except Exception as e:
            logger.debug(f"Redis write error for causal graph state: {e}")

    def _load_state_from_redis(self) -> None:
        """從 Redis 還原活躍事件"""
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync(decode_responses=True)
            if r:
                key = f"{self._REDIS_STATE_KEY_PREFIX}:{self.user_id}"
                raw = r.get(key)
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        self._active_events = [ActiveEventShock(**item) for item in data]
                        self.propagate_shocks()
                        logger.info(f"Loaded {len(self._active_events)} active events from Redis")
        except Exception as e:
            logger.debug(f"Redis read error for causal graph state: {e}")
