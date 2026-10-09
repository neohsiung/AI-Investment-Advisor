"""
Opportunity Cost Evaluation Service
非線性換庫機會成本門檻評估服務
=============================================================================
Enforces dynamic opportunity cost hurdles for portfolio rotation, rebalancing,
and active capital redeployment.

Core Principles:
1. Two-way round-trip transaction friction:
   F_roundtrip = 2 * (slippage_pct + commission_pct)
2. Non-linear opportunity cost hurdle:
   Hurdle_total = (Multiplier * F_roundtrip) + HurdleRate
3. Swap qualification check:
   Candidate opportunity must provide net advantage >= Hurdle_total
   after absorbing two-way transaction frictions.
4. Structural long-term winners require higher displacement hurdle
   (1.5x - 1.75x) to prevent cutting flowers to water weeds.
5. Churn suppression:
   Marginal swaps that fail to clear the hurdle are suppressed to HOLD_INSUFFICIENT_EDGE,
   protecting capital from transaction fee attrition and unnecessary churning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from src.config.owner import resolve_user_id

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
    is_pruning: bool = False
    is_risk_trim: bool = False
    roundtrip_friction: float = 0.003
    friction_multiplier: float = 2.5
    hurdle_rate: float = 0.010
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_approved(self) -> bool:
        return self.should_swap

    @property
    def selling_ticker(self) -> str:
        return self.holding_ticker

    @property
    def buying_ticker(self) -> str:
        return self.candidate_ticker

    @property
    def expected_edge(self) -> float:
        return self.net_opportunity_delta

    @property
    def hurdle(self) -> float:
        return self.friction_hurdle


# Alias for backward compatibility
SwapAssessment = SwapDecision


class OpportunityCostService:
    """
    Evaluates capital rotation and trade decisions based on non-linear opportunity costs.
    機會成本決策引擎：計算資本置換的邊際效用與機會成本門檻。
    """

    DEFAULT_SLIPPAGE_PCT = 0.0010     # 0.10% per leg
    DEFAULT_COMMISSION_PCT = 0.0005   # 0.05% per leg
    DEFAULT_MULTIPLIER = 2.5          # 2.5x friction multiplier
    DEFAULT_HURDLE_RATE = 0.010       # 1.0% excess hurdle rate

    def __init__(
        self,
        user_id: Optional[str] = None,
        min_score_delta: Optional[float] = None,
        fee_pct: float = 0.001,
        slippage_pct: float = 0.0005,
        settings_service: Optional[Any] = None,
        slippage_compensator: Optional[Any] = None,
    ):
        self.user_id = resolve_user_id(user_id) if user_id else "default_user"
        self.min_score_delta = min_score_delta
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        # Two-way roundtrip friction hurdle in score points (~0.3 score penalty for 0.3% roundtrip)
        self.friction_hurdle_score = (fee_pct + slippage_pct) * 2 * 100.0
        self.settings_service = settings_service
        self.slippage_compensator = slippage_compensator

    def calculate_roundtrip_friction(
        self,
        slippage_pct: Optional[float] = None,
        commission_pct: Optional[float] = None,
        sell_ticker: Optional[str] = None,
        buy_ticker: Optional[str] = None,
    ) -> float:
        """
        Calculates 2-way round-trip transaction friction:
        F_roundtrip = 2 * (slippage + commission)
        Supports empirical calibrated slippage from AdaptiveExecutionSlippageCompensator (P6)
        when sell_ticker and buy_ticker are provided.
        """
        if (
            slippage_pct is None
            and sell_ticker is not None
            and buy_ticker is not None
            and self.slippage_compensator is not None
            and hasattr(self.slippage_compensator, "get_calibrated_roundtrip_friction")
        ):
            try:
                comm = self.DEFAULT_COMMISSION_PCT if commission_pct is None else float(commission_pct)
                assessment = self.slippage_compensator.get_calibrated_roundtrip_friction(
                    sell_ticker=sell_ticker,
                    buy_ticker=buy_ticker,
                    sell_fee_pct=comm,
                    buy_fee_pct=comm,
                )
                return round(assessment.total_roundtrip_friction, 6)
            except Exception as e:
                logger.warning(f"Failed to compute calibrated friction via compensator: {e}")

        s = self.DEFAULT_SLIPPAGE_PCT if slippage_pct is None else float(slippage_pct)
        c = self.DEFAULT_COMMISSION_PCT if commission_pct is None else float(commission_pct)
        return round(2.0 * (s + c), 6)

    def calculate_opportunity_cost_hurdle(
        self,
        multiplier: Optional[float] = None,
        hurdle_rate: Optional[float] = None,
        roundtrip_friction: Optional[float] = None,
    ) -> float:
        """
        Calculates the non-linear hurdle:
        Hurdle_total = (Multiplier * F_roundtrip) + HurdleRate
        """
        if multiplier is None:
            if self.settings_service and hasattr(self.settings_service, "get_setting"):
                try:
                    multiplier = float(self.settings_service.get_setting("rotation_friction_multiplier", self.DEFAULT_MULTIPLIER))
                except Exception:
                    multiplier = self.DEFAULT_MULTIPLIER
            else:
                multiplier = self.DEFAULT_MULTIPLIER

        if hurdle_rate is None:
            if self.settings_service and hasattr(self.settings_service, "get_setting"):
                try:
                    hurdle_rate = float(self.settings_service.get_setting("rotation_hurdle_rate", self.DEFAULT_HURDLE_RATE))
                except Exception:
                    hurdle_rate = self.DEFAULT_HURDLE_RATE
            else:
                hurdle_rate = self.DEFAULT_HURDLE_RATE

        friction = self.calculate_roundtrip_friction() if roundtrip_friction is None else float(roundtrip_friction)
        return round((multiplier * friction) + hurdle_rate, 6)

    def evaluate_swap(
        self,
        holding_ticker: Optional[str] = None,
        candidate_ticker: Optional[str] = None,
        holding_score: Optional[float] = None,
        candidate_score: Optional[float] = None,
        holding_state: Optional[Dict[str, Any]] = None,
        candidate_state: Optional[Dict[str, Any]] = None,
        min_delta_override: Optional[float] = None,
        selling_ticker: Optional[str] = None,
        buying_ticker: Optional[str] = None,
        sell_expected_return: Optional[float] = None,
        buy_expected_return: Optional[float] = None,
        sell_confidence: Optional[float] = None,
        buy_confidence: Optional[float] = None,
        horizon_days: int = 60,
        is_pruning: bool = False,
        is_risk_trim: bool = False,
    ) -> SwapDecision:
        """
        Evaluate if candidate ticker justifies liquidating or trimming holding ticker.
        Unified method supporting both SentinelService and ConfidenceRebalanceService.
        """
        sell_sym = (holding_ticker or selling_ticker or "HOLDING").upper().strip()
        buy_sym = (candidate_ticker or buying_ticker or "CANDIDATE").upper().strip()

        # Normalize score inputs: support both 0-10 and 0-1 scales
        s_score = holding_score if holding_score is not None else sell_confidence
        b_score = candidate_score if candidate_score is not None else buy_confidence
        s_score = float(s_score if s_score is not None else 5.0)
        b_score = float(b_score if b_score is not None else 5.0)

        # Scale detection: if scores are <= 1.0, convert to 0-10 scale for unified calculation
        is_decimal_scale = (s_score <= 1.0 and b_score <= 1.0)
        s_score_10 = s_score * 10.0 if is_decimal_scale else s_score
        b_score_10 = b_score * 10.0 if is_decimal_scale else b_score

        friction = self.calculate_roundtrip_friction(sell_ticker=sell_sym, buy_ticker=buy_sym)
        multiplier = self.DEFAULT_MULTIPLIER
        hurdle_rate = self.DEFAULT_HURDLE_RATE
        if self.settings_service and hasattr(self.settings_service, "get_setting"):
            try:
                multiplier = float(self.settings_service.get_setting("rotation_friction_multiplier", self.DEFAULT_MULTIPLIER))
                hurdle_rate = float(self.settings_service.get_setting("rotation_hurdle_rate", self.DEFAULT_HURDLE_RATE))
            except Exception as e:
                logger.debug(f"OpportunityCostService: Failed to read rotation settings: {e}")

        friction_hurdle_score = (multiplier * friction * 100.0)  # e.g. 2.5 * 0.3% * 100 = 0.75 points
        hurdle_rate_score = (hurdle_rate * 100.0)                 # e.g. 1.0% * 100 = 1.00 points
        total_hurdle_score = friction_hurdle_score + hurdle_rate_score  # 1.75 points

        hurdle_val = total_hurdle_score
        if min_delta_override is not None:
            hurdle_val = float(min_delta_override)
        elif self.min_score_delta is not None:
            hurdle_val = float(self.min_score_delta)

        hurdle = hurdle_val

        # 1. Exemptions
        if is_pruning:
            return SwapDecision(
                should_swap=True,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=s_score,
                candidate_score=b_score,
                raw_delta=10.0,
                net_opportunity_delta=10.0,
                friction_hurdle=hurdle,
                reason="淘汰標的與死資本清倉，豁免機會成本門檻，全額釋放流動性",
                is_pruning=True,
                is_risk_trim=False,
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
            )

        if is_risk_trim:
            return SwapDecision(
                should_swap=True,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=s_score,
                candidate_score=b_score,
                raw_delta=10.0,
                net_opportunity_delta=10.0,
                friction_hurdle=hurdle,
                reason="剛性風控平倉（產業/集群上限或體制現金防線），豁免換庫利差檢驗",
                is_pruning=False,
                is_risk_trim=True,
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
            )

        holding_state = holding_state or {}
        candidate_state = candidate_state or {}

        # Check event bias from holding_state / candidate_state
        holding_event_bias = float(holding_state.get("event_bias", 0.0))
        candidate_event_bias = float(candidate_state.get("event_bias", 0.0))

        effective_holding_score = max(0.0, s_score_10 + holding_event_bias)
        effective_candidate_score = max(0.0, min(10.0, b_score_10 + candidate_event_bias))

        raw_delta = effective_candidate_score - effective_holding_score
        net_delta = raw_delta - self.friction_hurdle_score

        # Check if holding state is explicitly broken or hit severe adverse event
        is_severe_adverse_event = (holding_event_bias <= -1.2)
        is_holding_broken = (
            holding_state.get("is_broken", False)
            or holding_state.get("stop_triggered", False)
            or is_severe_adverse_event
        )

        if is_holding_broken:
            trigger_cause = (
                f"遭遇重大負面事件衝擊 (偏置 {holding_event_bias:+.2f})"
                if is_severe_adverse_event
                else "論點破壞或觸發停損"
            )
            return SwapDecision(
                should_swap=True,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=round(effective_holding_score, 2),
                candidate_score=round(effective_candidate_score, 2),
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=f"持有標的 {sell_sym} {trigger_cause}，無條件放行置換至優質候選 {buy_sym}",
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
            )

        ret_edge = 0.0
        if buy_expected_return is not None and sell_expected_return is not None:
            horizon_factor = max(0.1, min(1.0, float(horizon_days) / 252.0))
            ret_edge = (float(buy_expected_return) - float(sell_expected_return)) * horizon_factor
            net_delta = round((0.70 * ret_edge * 100.0) + (0.30 * (raw_delta - self.friction_hurdle_score)), 2)

        metrics = {
            "friction": friction,
            "multiplier": multiplier,
            "hurdle_rate": hurdle_rate,
            "raw_delta": round(raw_delta, 4),
            "net_delta": round(net_delta, 4),
            "hurdle": round(hurdle, 4),
        }
        if buy_expected_return is not None and sell_expected_return is not None:
            metrics["expected_edge"] = round(ret_edge, 4)

        # Protection status checks
        protection_status = holding_state.get("protection_status")
        is_full_compounding = (protection_status == "FULL_PROTECT_COMPOUNDING")
        is_trim_excess = (protection_status == "TRIM_EXCESS_FOR_OPPORTUNITY")
        is_holding_runner = is_full_compounding or holding_state.get("is_runner", False) or (
            holding_state.get("unrealized_pnl_pct", 0.0) > 8.0 and holding_state.get("is_above_ma50", True)
        )

        if is_full_compounding and net_delta < (hurdle * 1.75):
            return SwapDecision(
                should_swap=False,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=s_score,
                candidate_score=b_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle * 1.75, 2),
                reason=(
                    f"持有標的 {sell_sym} 經深研認證為中長期複利贏家且短線動能健康，候選標的優勢 +{net_delta:.2f} "
                    f"未達中長期贏家高階置換門檻 +{hurdle * 1.75:.2f}，堅定持有鮮花不切斷複利"
                ),
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
                metrics=metrics,
            )

        if is_holding_runner and not is_trim_excess and net_delta < (hurdle * 1.5):
            return SwapDecision(
                should_swap=False,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=s_score,
                candidate_score=b_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle * 1.5, 2),
                reason=(
                    f"持有標的 {sell_sym} 處於強勢獲利複利期，候選標的優勢 +{net_delta:.2f} "
                    f"未達強勢贏家置換門檻 +{hurdle * 1.5:.2f}，堅定持有鮮花不切斷複利"
                ),
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
                metrics=metrics,
            )

        if is_trim_excess and (raw_delta >= hurdle or net_delta >= hurdle):
            return SwapDecision(
                should_swap=True,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=s_score,
                candidate_score=b_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=(
                    f"持有標的 {sell_sym} 短期動能受阻或存在機會成本警示，候選標的 {buy_sym} "
                    f"淨優勢 +{net_delta:.2f} (利差 +{raw_delta:.2f}) >= 門檻 {hurdle:.2f}，放行調節以把握短線高動能機會，避免死錢拖累"
                ),
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
                metrics=metrics,
            )

        if net_delta >= hurdle:
            return SwapDecision(
                should_swap=True,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=s_score,
                candidate_score=b_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=(
                    f"候選標的 {buy_sym} (評分 {b_score_10:.1f}) 顯著優於 {sell_sym} (評分 {s_score_10:.1f})，"
                    f"淨優勢 +{net_delta:.2f} >= 門檻 +{hurdle:.2f}，換庫淨利差顯著超越非線性機會成本門檻，"
                    f"足以覆蓋雙向交易摩擦 ({friction*100:.2f}% * {multiplier:.1f}x) 與超額要求，"
                    f"依機會成本原則放行置換（核准置換）"
                ),
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
                metrics=metrics,
            )
        else:
            return SwapDecision(
                should_swap=False,
                holding_ticker=sell_sym,
                candidate_ticker=buy_sym,
                holding_score=s_score,
                candidate_score=b_score,
                raw_delta=round(raw_delta, 2),
                net_opportunity_delta=round(net_delta, 2),
                friction_hurdle=round(hurdle, 2),
                reason=(
                    f"候選標的 {buy_sym} 淨優勢 +{net_delta:.2f} (利差 +{raw_delta:.2f}) "
                    f"未達非線性機會成本門檻 (+{hurdle:.2f} 分，未達換庫門檻)，"
                    f"不足以彌補雙向摩擦損耗 ({friction*100:.2f}%)，抑制無謂換手以保全原持倉複利"
                ),
                roundtrip_friction=friction,
                friction_multiplier=multiplier,
                hurdle_rate=hurdle_rate,
                metrics=metrics,
            )

    def filter_rebalance_trades(
        self,
        sells: List[Dict[str, Any]],
        buys: List[Dict[str, Any]],
        total_portfolio_value: float,
        enforce_all: bool = False,
    ) -> Dict[str, Any]:
        """
        Inspect proposed sells and buys in a rebalance plan.
        Filters out sells whose capital deployment into buys fails the opportunity cost hurdle.
        Always evaluates trades marked with is_swap=True or is_tactical_trim=True.
        When enforce_all=True, evaluates all discretionary rebalance trims.
        """
        approved_sells: List[Dict[str, Any]] = []
        suppressed_sells: List[Dict[str, Any]] = []
        assessments: List[SwapDecision] = []

        if not buys:
            for s in sells:
                if s.get("is_pruning") or s.get("is_risk_trim"):
                    approved_sells.append(s)
                else:
                    suppressed = dict(s)
                    suppressed["action"] = "HOLD_INSUFFICIENT_EDGE"
                    suppressed["suppressed_reason"] = "無對應再平衡買進標的，取消非必要換庫賣出"
                    suppressed_sells.append(suppressed)
            return {
                "approved_sells": approved_sells,
                "suppressed_sells": suppressed_sells,
                "approved_buys": buys,
                "assessments": assessments,
            }

        top_buy = max(buys, key=lambda b: float(b.get("confidence") or 0.0))
        buy_ticker = top_buy.get("ticker", "CANDIDATE")
        buy_conf = float(top_buy.get("confidence") or 0.5)

        for s in sells:
            ticker = s.get("ticker", "")
            is_pruning = bool(s.get("is_pruning", False))
            is_risk_trim = bool(s.get("is_risk_trim", False))
            is_tactical_trim = bool(s.get("is_tactical_trim", False))
            is_swap = bool(s.get("is_swap", False))

            if is_pruning or is_risk_trim:
                approved_sells.append(s)
                continue

            should_evaluate = enforce_all or is_tactical_trim or is_swap
            if not should_evaluate:
                approved_sells.append(s)
                continue

            sell_conf = float(s.get("confidence") or 0.5)
            holding_state = {
                "protection_status": s.get("protection_status"),
                "is_runner": s.get("is_runner", False),
                "unrealized_pnl_pct": s.get("unrealized_pnl_pct", 0.0),
                "is_broken": s.get("is_broken", False),
                "event_bias": s.get("event_bias", 0.0),
            }
            candidate_state = {
                "event_bias": top_buy.get("event_bias", 0.0),
            }
            assessment = self.evaluate_swap(
                holding_ticker=ticker,
                candidate_ticker=buy_ticker,
                holding_score=sell_conf,
                candidate_score=buy_conf,
                holding_state=holding_state,
                candidate_state=candidate_state,
                is_pruning=is_pruning,
                is_risk_trim=is_risk_trim,
            )
            assessments.append(assessment)

            if assessment.should_swap:
                s_copy = dict(s)
                s_copy["opportunity_assessment"] = assessment.reason
                approved_sells.append(s_copy)
            else:
                s_suppressed = dict(s)
                s_suppressed["action"] = "HOLD_INSUFFICIENT_EDGE"
                s_suppressed["suppressed_reason"] = assessment.reason
                s_suppressed["opportunity_assessment"] = assessment.reason
                suppressed_sells.append(s_suppressed)

        return {
            "approved_sells": approved_sells,
            "suppressed_sells": suppressed_sells,
            "approved_buys": buys,
            "assessments": assessments,
        }
