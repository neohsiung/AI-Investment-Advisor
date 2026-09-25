"""
Strategy Contract & Market Regime Domain Models
================================================
定義通用市場體制 (Market Regime)、策略契約 (Strategy Contract)、
階梯調度 (Ladder Stage)、降槓桿規則 (Deleveraging Rule) 與風險預算 (Risk Budget)。

本模組旨在建立策略通用抽象化介面，避免在決策、執行與風控層寫死特定策略的特化邏輯。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MarketRegimeType(str, Enum):
    """
    Standardized Macro & Market Regime Types.
    標準化宏觀與市場體制類型。
    """
    VOLATILITY_EXTREME = "VOLATILITY_EXTREME"       # 波動率極值 (VIX >= 40, 極端恐慌)
    VOLATILITY_PIVOT = "VOLATILITY_PIVOT"           # 波動率拐點 (VIX 衝頂回落跌破 5MA, 恐慌力竭)
    TREND_ACCELERATION = "TREND_ACCELERATION"       # 順勢動能加速突破
    RANGE_COMPRESSION = "RANGE_COMPRESSION"         # 波動率壓縮 (布林帶窄化, 變盤前夕)
    LIQUIDITY_SHOCK = "LIQUIDITY_SHOCK"             # 流動性危機 / 利差暴噴
    NORMAL = "NORMAL"                               # 常態平穩市場


@dataclass
class MarketRegimeEvent:
    """
    Represents an observed market regime occurrence.
    記錄被觀察到的市場體制事件。
    """
    regime_type: MarketRegimeType
    severity: str = "medium"                        # low, medium, high, critical
    confidence: float = 1.0                         # 置信度 (0.0 ~ 1.0)
    indicators: Dict[str, Any] = field(default_factory=dict)  # 觸發指標 (如 {"vix": 42.5, "ma5": 43.1})
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RiskBudget:
    """
    Standardized Risk Constraints for a Strategy.
    策略的標準化風險預算與硬性約束。
    """
    max_underlying_stop_pct: float = 8.0            # 底層標的最大容忍硬停損百分比
    trailing_stop_pct: float = 6.0                  # 預設移動停損百分比
    max_position_margin_pct: float = 0.10           # 單檔保證金佔帳戶淨值 (NLV) 上限 (預設 10%)
    max_holding_days: int = 60                      # 最長持有時限 (超過則強制檢查或平倉)
    max_portfolio_gross_leverage: float = 1.30      # 投組總名目槓桿率上限
    max_allowed_leverage: int = 2                   # 允許之最高槓桿倍數 (1, 2, 5)


@dataclass
class LadderStage:
    """
    Defines one tier in a pyramid entry scaling strategy.
    定義金字塔分批建倉階梯中的一個階段。
    """
    stage_num: int                                  # 階梯序號 (1, 2, 3...)
    target_cumulative_weight: float                 # 目標累積部位權重 (例如 0.3, 0.6, 1.0)
    incremental_weight: float                       # 本次應加碼權重 (例如 0.3)
    recommended_leverage: int = 1                   # 本階建議槓桿 (1, 2, 5)
    stop_loss_pct: float = 6.0                      # 本階停損百分比
    is_trailing_stop_loss: bool = True              # 是否啟用移動停損
    description: str = ""                           # 階梯描述


@dataclass
class DeleveragingRule:
    """
    Defines a condition under which leverage must be stepped down.
    定義必須降槓桿或部分獲利了結的規則。
    """
    trigger_gain_pct: Optional[float] = None        # 當獲利達到此百分比時 (例如 +4.0%)
    trigger_regime_exit: Optional[MarketRegimeType] = None  # 當體制回歸常態時
    target_leverage: int = 1                        # 降階後目標槓桿 (如 5x -> 2x, 2x -> 1x)
    close_ratio: float = 0.50                       # 平倉比例 (例如平倉 50%)
    description: str = ""


@dataclass
class StrategyExecutionPlan:
    """
    Unified execution decision returned by a StrategyContract.
    由策略契約回傳之統一調度決策。
    """
    action: str                                     # "BUY", "HOLD", "SELL", "PARTIAL_EXIT", "STOP_LOSS"
    stage: int                                      # 目前階梯 (0 代表空手/完全退場)
    target_leverage: int = 1                        # 建議槓桿倍數
    target_cumulative_weight: float = 0.0           # 目標總權重
    incremental_weight: float = 0.0                 # 本次調倉增量權重
    stop_loss_pct: float = 6.0                      # 停損百分比
    take_profit_pct: float = 20.0                   # 停利百分比
    is_trailing_stop_loss: bool = True              # 是否掛載移動停損
    reason: str = ""                                # 決策說明


class StrategyContract(ABC):
    """
    Standard Strategy Interface (Contract).
    所有受系統承認與調度之量化投資策略契約基礎類別。
    """
    strategy_id: str
    subscribed_regimes: List[MarketRegimeType]
    risk_budget: RiskBudget

    @abstractmethod
    def evaluate_entry(self, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        """
        Evaluate entry signals based on market context and active regimes.
        根據當前市場體制與環境評估是否產生進場階梯訊號。
        """
        pass

    @abstractmethod
    def evaluate_exit(self, position: Any, market_context: Dict[str, Any]) -> Optional[StrategyExecutionPlan]:
        """
        Evaluate exit, stop-loss, or deleveraging signals.
        評估出場、停損或降槓桿訊號。
        """
        pass

    def is_safety_control(self) -> bool:
        """
        Whether this strategy represents capital safety control (e.g. stop loss, emergency exit).
        是否屬於資本安全控制策略 (豁免於回測閘門)。
        """
        return False
