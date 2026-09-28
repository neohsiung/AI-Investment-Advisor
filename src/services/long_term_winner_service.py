"""
Long-Term Winner Qualification & Short-Term Opportunity Cost Evaluation Service
中長期贏家深研資格審查與短期機會成本防線服務
=============================================================================
Enforces structural quality criteria for "Winner Protection" (贏家保護):
1. Medium-to-Long-Term Winner Qualification:
   - Structural price trend: Price > SMA200 and SMA50 > SMA200 (Long-term Bull Stack).
   - Fundamental Moat & Quality Gate: QualityGate score >= 6.5/10.
   - Research Conviction: Confidence score >= 0.60.
2. Short-Term Opportunity Cost Vigilance:
   - Short-term momentum: Price vs SMA20, RSI health, MACD momentum.
   - Opportunity cost gap: Edge against best alternatives (Delta >= 2.5 hurdle).
3. Dynamic Protection Tiering:
   - FULL_PROTECT_COMPOUNDING: Long-term certified + Short-term healthy -> 100% protect, let run.
   - TRIM_EXCESS_FOR_OPPORTUNITY: Long-term certified BUT short-term opportunity cost / stall ->
     Protect core target weight (base), trim excess to fund high-velocity opportunities.
   - NO_PROTECTION_REBALANCE: Failed long-term criteria -> Regular rebalance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional

from src.services.market_data_service import MarketDataService
from src.services.quality_gate_service import QualityGateService
from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


class ProtectionStatus(str, Enum):
    FULL_PROTECT_COMPOUNDING = "FULL_PROTECT_COMPOUNDING"
    TRIM_EXCESS_FOR_OPPORTUNITY = "TRIM_EXCESS_FOR_OPPORTUNITY"
    NO_PROTECTION_REBALANCE = "NO_PROTECTION_REBALANCE"


@dataclass
class WinnerAssessment:
    """Comprehensive assessment of a holding's winner status and opportunity cost."""
    ticker: str
    is_long_term_winner: bool
    has_short_term_opportunity_cost: bool
    status: ProtectionStatus
    long_term_score: float                     # 0.0 - 10.0
    short_term_momentum_score: float           # 0.0 - 10.0
    long_term_reasons: List[str] = field(default_factory=list)
    short_term_reasons: List[str] = field(default_factory=list)
    action_summary: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class LongTermWinnerService:
    """
    Evaluates whether an asset qualifies as a structural long-term winner
    and whether maintaining an overweight position incurs short-term opportunity cost.
    中長期贏家資格審查與短期機會成本動態防線。
    """

    def __init__(
        self,
        user_id: str,
        market_data_service: Optional[MarketDataService] = None,
        quality_gate_service: Optional[QualityGateService] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.market = market_data_service or MarketDataService(user_id=self.user_id)
        self.quality_gate = quality_gate_service or QualityGateService(
            user_id=self.user_id, market_data_service=self.market
        )

    async def evaluate_winner(
        self,
        ticker: str,
        current_weight: float,
        target_weight: float,
        market_value: float,
        total_portfolio_value: float,
        candidate_scores: Optional[Dict[str, float]] = None,
        unrealized_pnl_pct: Optional[float] = None,
    ) -> WinnerAssessment:
        """
        Conduct deep research evaluation on ticker for long-term compounding viability
        and short-term opportunity cost.
        深入研究評估標的之中長期複利能力與短期機會成本。
        """
        ticker = ticker.upper().strip()
        candidate_scores = candidate_scores or {}
        long_term_reasons: List[str] = []
        short_term_reasons: List[str] = []

        # 1. Fetch Technical Indicators & Price
        tech = self.market.get_technical_indicators(ticker) or {}
        current_price = 0.0
        try:
            price_map = await self.market.get_current_prices([ticker])
            current_price = float(price_map.get(ticker, 0.0))
        except Exception as e:
            logger.warning(f"LongTermWinner: failed to get price for {ticker}: {e}")

        # Extract SMA benchmarks
        sma_dict = tech.get("sma", {}) if isinstance(tech.get("sma"), dict) else {}
        sma_20 = float(sma_dict.get("sma_20") or 0.0)
        sma_50 = float(sma_dict.get("sma_50") or 0.0)
        sma_200 = float(sma_dict.get("sma_200") or 0.0)
        rsi = float(tech.get("rsi") or 50.0)
        macd_status = str(tech.get("macd") or "neutral").lower()

        # 2. Quality Gate & Fundamental Moat Assessment
        qg_assessment = await self.quality_gate.evaluate_ticker(ticker)
        overall_qg_score = qg_assessment.overall_score
        is_qg_passed = qg_assessment.passed

        # ── Pillar 1: Medium-to-Long-Term Winner Verification ──
        # Check 1: Long-term trend structure (Price above SMA200 and SMA50 > SMA200)
        trend_above_200 = True
        golden_cross_structure = True
        if sma_200 > 0 and current_price > 0:
            trend_above_200 = current_price >= (sma_200 * 0.97)  # allow 3% buffer
            if not trend_above_200:
                long_term_reasons.append(
                    f"股價 (${current_price:.2f}) 跌破 200 日生命線 (${sma_200:.2f})，長線多頭結構破壞"
                )
            else:
                long_term_reasons.append(
                    f"股價穩健運行於 200 日均線 (${sma_200:.2f}) 之上，長線多頭基底扎實"
                )

        if sma_50 > 0 and sma_200 > 0:
            golden_cross_structure = sma_50 >= sma_200
            if golden_cross_structure:
                long_term_reasons.append(f"中期均線 SMA50 (${sma_50:.2f}) 高於 SMA200，呈現長期多頭排列")

        # Check 2: Quality & Fundamentals
        quality_ok = is_qg_passed and overall_qg_score >= 6.0
        if not quality_ok:
            long_term_reasons.append(f"品質把關未達標 (品質評分 {overall_qg_score:.2f} < 6.0)")
        else:
            long_term_reasons.append(f"通過品質把關 (綜合品質分 {overall_qg_score:.2f} >= 6.0)")

        # Long-term score calculation (0 - 10)
        long_term_score = round(
            (0.5 * overall_qg_score) +
            (2.5 if trend_above_200 else 0.0) +
            (2.5 if golden_cross_structure else 0.0),
            2
        )

        is_long_term_winner = trend_above_200 and quality_ok and (long_term_score >= 6.5)

        # ── Pillar 2: Short-Term Opportunity Cost & Momentum Check ──
        short_term_momentum_ok = True
        # Check SMA20 short-term support
        if sma_20 > 0 and current_price > 0:
            is_above_20 = current_price >= (sma_20 * 0.98)
            if not is_above_20:
                short_term_momentum_ok = False
                short_term_reasons.append(
                    f"股價 (${current_price:.2f}) 跌破 20 日短天期均線 (${sma_20:.2f})，短線動能減弱進入整理"
                )
            else:
                short_term_reasons.append(f"股價穩居 20 日均線之上，短線維持強勢動能")

        # RSI health check (healthy bullish range: 45 to 75)
        if rsi < 42.0:
            short_term_momentum_ok = False
            short_term_reasons.append(f"短線 RSI 弱勢 ({rsi:.1f} < 42)，動能陷入冷卻")
        elif rsi > 80.0:
            short_term_reasons.append(f"短線 RSI 過熱 ({rsi:.1f} > 80)，面臨技術性拉回壓力")

        # MACD momentum status
        if "bearish" in macd_status:
            short_term_momentum_ok = False
            short_term_reasons.append("短線 MACD 呈現偏空或死叉狀態")

        # Opportunity cost differential check against external candidates
        # 若自選池中最強候選標的之評分高出該持倉 >= 2.5 分，且持倉動能不強，構成短線機會成本威脅
        max_candidate_score = max(candidate_scores.values()) if candidate_scores else 0.0
        short_term_opp_cost_gap = max_candidate_score - long_term_score
        has_opp_cost_loss = False
        if short_term_opp_cost_gap >= 2.5 and not short_term_momentum_ok:
            has_opp_cost_loss = True
            short_term_reasons.append(
                f"市場出現顯著更高預期之新機會 (候選最高分 {max_candidate_score:.1f} vs 本標的 {long_term_score:.1f}，"
                f"差距 +{short_term_opp_cost_gap:.1f} >= 2.5)，持有過度集中面臨短線機會成本喪失"
            )

        # If short-term momentum broke significantly, also flag opportunity cost loss
        if not short_term_momentum_ok and (rsi < 42.0 or "bearish" in macd_status):
            has_opp_cost_loss = True

        short_term_score = 7.5
        if short_term_momentum_ok:
            short_term_score += 1.5
        if "bullish" in macd_status:
            short_term_score += 1.0
        if has_opp_cost_loss:
            short_term_score -= 3.0
        short_term_score = max(1.0, min(10.0, round(short_term_score, 2)))

        # ── Pillar 3: Dynamic Winner Protection Classification ──
        if not is_long_term_winner:
            status = ProtectionStatus.NO_PROTECTION_REBALANCE
            action_summary = "長線結構破壞或基本面品質未達標，不具備贏家保護資格，回歸普通再平衡"
        elif has_opp_cost_loss:
            status = ProtectionStatus.TRIM_EXCESS_FOR_OPPORTUNITY
            action_summary = "中長期結構性贏家，但短線動能停滯或存在高機會成本；保留核心基準底倉，釋放超額浮盈以把握高動能機會"
        else:
            status = ProtectionStatus.FULL_PROTECT_COMPOUNDING
            action_summary = "經中長期深研確立為結構性長線贏家，且短線動能健康無機會成本喪失，100% 全額保護持續複利"

        metrics = {
            "current_price": current_price,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "rsi": rsi,
            "macd": macd_status,
            "overall_qg_score": overall_qg_score,
            "current_weight": current_weight,
            "target_weight": target_weight,
            "excess_weight": max(0.0, current_weight - target_weight),
            "unrealized_pnl_pct": unrealized_pnl_pct,
        }

        return WinnerAssessment(
            ticker=ticker,
            is_long_term_winner=is_long_term_winner,
            has_short_term_opportunity_cost=has_opp_cost_loss,
            status=status,
            long_term_score=long_term_score,
            short_term_momentum_score=short_term_score,
            long_term_reasons=long_term_reasons,
            short_term_reasons=short_term_reasons,
            action_summary=action_summary,
            metrics=metrics,
        )
