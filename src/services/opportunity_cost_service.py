"""
Opportunity Cost Evaluation Service — 機會成本評估服務
===================================================
Evaluates whether capital should be reallocated from an existing holding to a candidate asset.
Decisions are driven by:
1. Expected risk-adjusted return delta (Score(Candidate) - Score(Holding)).
2. Transaction friction cost hurdle (broker fees, slippage, bid-ask spread).
3. Asset state (momentum, thesis validity, drawdown status).

買賣與換庫取決於機會成本，而非持倉佔比大小。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SwapDecision:
    """Opportunity Cost Swap Evaluation Result."""
    should_swap: bool
    holding_ticker: str
    candidate_ticker: str
    holding_score: float
    candidate_score: float
    raw_delta: float
    net_opportunity_delta: float
    friction_hurdle: float
    reason: str


class OpportunityCostService:
    """
    Evaluates capital rotation and trade decisions based on opportunity costs.
    機會成本決策引擎：計算資本置換的邊際效用與機會成本門檻。
    """

    def __init__(
        self,
        min_score_delta: float = 2.0,
        fee_pct: float = 0.001,
        slippage_pct: float = 0.0005,
    ):
        self.min_score_delta = min_score_delta
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        # Two-way roundtrip friction hurdle in score points (~0.3 score penalty for 0.3% roundtrip)
        self.friction_hurdle_score = (fee_pct + slippage_pct) * 2 * 100.0

    def evaluate_swap(
        self,
        holding_ticker: str,
        candidate_ticker: str,
        holding_score: float,
        candidate_score: float,
        holding_state: Optional[Dict[str, Any]] = None,
        candidate_state: Optional[Dict[str, Any]] = None,
        min_delta_override: Optional[float] = None,
    ) -> SwapDecision:
        """
        Evaluate if candidate ticker justifies liquidating or trimming holding ticker.
        評估新候選標的是否具備足夠的機會成本優勢，以置換現有持倉。
        """
        holding_state = holding_state or {}
        candidate_state = candidate_state or {}

        hurdle = min_delta_override if min_delta_override is not None else self.min_score_delta
        raw_delta = candidate_score - holding_score
        net_delta = raw_delta - self.friction_hurdle_score

        # Check if holding state is explicitly broken (e.g. stop hit, thesis broke)
        is_holding_broken = holding_state.get("is_broken", False) or holding_state.get("stop_triggered", False)
        
        # Check protection status from LongTermWinnerService
        protection_status = holding_state.get("protection_status")
        is_full_compounding = (protection_status == "FULL_PROTECT_COMPOUNDING")
        is_trim_excess = (protection_status == "TRIM_EXCESS_FOR_OPPORTUNITY")
        
        # Check if holding is a strong runner (e.g. profitable compounder with healthy trend)
        is_holding_runner = is_full_compounding or holding_state.get("is_runner", False) or (
            holding_state.get("unrealized_pnl_pct", 0.0) > 8.0 and holding_state.get("is_above_ma50", True)
        )

        if is_holding_broken:
            return SwapDecision(
                should_swap=True,
                holding_ticker=holding_ticker,
                candidate_ticker=candidate_ticker,
                holding_score=holding_score,
                candidate_score=candidate_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=f"持有標的 {holding_ticker} 論點破壞或觸發停損，無條件放行置換至優質候選 {candidate_ticker}",
            )

        # Full compounding winner: require 1.75x hurdle to displace structural long-term winner
        if is_full_compounding and net_delta < (hurdle * 1.75):
            return SwapDecision(
                should_swap=False,
                holding_ticker=holding_ticker,
                candidate_ticker=candidate_ticker,
                holding_score=holding_score,
                candidate_score=candidate_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle * 1.75, 2),
                reason=(
                    f"持有標的 {holding_ticker} 經深研認證為中長期複利贏家且短線動能健康，候選標的優勢 +{net_delta:.2f} "
                    f"未達中長期贏家高階置換門檻 +{hurdle * 1.75:.2f}，堅定持有鮮花不切斷複利"
                ),
            )

        if is_holding_runner and not is_trim_excess and net_delta < (hurdle * 1.5):
            # Runner bonus: strong compounders require higher hurdle to displace
            return SwapDecision(
                should_swap=False,
                holding_ticker=holding_ticker,
                candidate_ticker=candidate_ticker,
                holding_score=holding_score,
                candidate_score=candidate_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle * 1.5, 2),
                reason=(
                    f"持有標的 {holding_ticker} 處於強勢獲利複利期，候選標的優勢 +{net_delta:.2f} "
                    f"未達強勢贏家置換門檻 +{hurdle * 1.5:.2f}，堅定持有鮮花不切斷複利"
                ),
            )

        if is_trim_excess and net_delta >= hurdle:
            return SwapDecision(
                should_swap=True,
                holding_ticker=holding_ticker,
                candidate_ticker=candidate_ticker,
                holding_score=holding_score,
                candidate_score=candidate_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=(
                    f"持有標的 {holding_ticker} 短期動能受阻或存在機會成本警示，候選標的 {candidate_ticker} "
                    f"淨優勢 +{net_delta:.2f} >= 門檻 {hurdle:.2f}，放行調節以把握短線高動能機會，避免死錢拖累"
                ),
            )

        if net_delta >= hurdle:
            return SwapDecision(
                should_swap=True,
                holding_ticker=holding_ticker,
                candidate_ticker=candidate_ticker,
                holding_score=holding_score,
                candidate_score=candidate_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=(
                    f"候選標的 {candidate_ticker} (評分 {candidate_score:.1f}) 顯著優於 "
                    f"{holding_ticker} (評分 {holding_score:.1f})，淨優勢 +{net_delta:.2f} >= 門檻 {hurdle:.2f}，"
                    f"依機會成本原則放行置換"
                ),
            )
        else:
            return SwapDecision(
                should_swap=False,
                holding_ticker=holding_ticker,
                candidate_ticker=candidate_ticker,
                holding_score=holding_score,
                candidate_score=candidate_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=(
                    f"候選標的 {candidate_ticker} 淨優勢 +{net_delta:.2f} 未達換庫門檻 {hurdle:.2f}，"
                    f"不值得支付換庫摩擦成本與承擔不確定性"
                ),
            )
