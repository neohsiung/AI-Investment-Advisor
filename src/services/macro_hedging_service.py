"""
Cross-Asset Macro Volatility Hedging Service (MacroHedgingService)
=================================================================
跨市場宏觀波動率體制自動避險服務

當大盤波動率體制突變進入恐慌／極端波動時（例如 VIX Spike、Z-Score > 2.5σ、或總體經濟壓力驟升），
系統自主啟動跨市場宏觀防禦避險：
1. 動態提升防守現金比例 (Dynamic Cash Scaling)：
   將目標現金比例由基礎值（如 10%）動態調升至防禦水位（如 20%~25%），並識別應修剪之高 Beta 或弱勢持倉以騰出流動性。
2. 反向／防禦標的對沖 (Inverse / Defensive Asset Hedging)：
   當開啟反向標的避險 (enable_inverse_etf_hedge) 或遭遇極端波動時，依據風險預算配置反向 ETF (如 SH、SQQQ) 或防禦性資產 (如 TLT)。
3. 曝險防守監控 (Exposure Guard)：
   計算整體投組的加權 Beta 與淨市場曝險 (Net Market Exposure)，評估對沖效益與最大回撤防守。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MacroHedgingService")

STRATEGY_NAME = "macro_volatility_hedge"


class HedgingActionType(str, Enum):
    """Hedging action directives."""
    NONE = "NONE"
    RAISE_CASH = "RAISE_CASH"
    TRIM_HIGH_BETA = "TRIM_HIGH_BETA"
    BUY_INVERSE_HEDGE = "BUY_INVERSE_HEDGE"
    UNWIND_HEDGE = "UNWIND_HEDGE"


class HedgingSeverity(str, Enum):
    """Severity of market macro volatility stress."""
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class HedgeRecommendation:
    """Specific hedging recommendation item."""
    action: HedgingActionType
    ticker: Optional[str]
    suggested_weight: float
    suggested_amount: float
    reason: str


@dataclass
class MacroHedgeEvaluation:
    """Consolidated macro volatility hedging evaluation result."""
    is_hedging_active: bool
    severity: HedgingSeverity
    vix: float
    vix_z_score: float
    macro_stress_bias: float
    portfolio_gross_exposure: float
    portfolio_weighted_beta: float
    current_cash_ratio: float
    target_cash_ratio: float
    required_cash_raise: float
    recommendations: List[HedgeRecommendation] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_hedging_active": self.is_hedging_active,
            "severity": self.severity.value,
            "vix": round(self.vix, 2),
            "vix_z_score": round(self.vix_z_score, 2),
            "macro_stress_bias": round(self.macro_stress_bias, 3),
            "portfolio_gross_exposure": round(self.portfolio_gross_exposure, 4),
            "portfolio_weighted_beta": round(self.portfolio_weighted_beta, 4),
            "current_cash_ratio": round(self.current_cash_ratio, 4),
            "target_cash_ratio": round(self.target_cash_ratio, 4),
            "required_cash_raise": round(self.required_cash_raise, 2),
            "recommendations": [
                {
                    "action": r.action.value,
                    "ticker": r.ticker,
                    "suggested_weight": round(r.suggested_weight, 4),
                    "suggested_amount": round(r.suggested_amount, 2),
                    "reason": r.reason,
                }
                for r in self.recommendations
            ],
            "summary": self.summary,
        }


class MacroHedgingService:
    """
    Evaluates cross-asset volatility regimes, computes portfolio market beta exposure,
    and formulates defensive cash expansion or inverse ETF allocation directives.
    """

    DEFAULT_VIX_THRESHOLD: float = 30.0
    DEFAULT_TARGET_DEFENSE_CASH: float = 0.25
    DEFAULT_HEDGE_INSTRUMENT: str = "SH"

    def __init__(
        self,
        settings_service: Optional[Any] = None,
        market_service: Optional[Any] = None,
        event_impact_service: Optional[Any] = None,
        winner_service: Optional[Any] = None,
    ):
        self.settings_service = settings_service
        self.market_service = market_service
        self.event_impact_service = event_impact_service
        self.winner_service = winner_service

    def _get_setting(self, key: str, default: Any, user_id: Optional[str] = None) -> Any:
        if self.settings_service:
            try:
                val = self.settings_service.get_setting(key, default, user_id=user_id)
                if val is not None:
                    return val
            except Exception as e:
                logger.debug(f"Failed to read setting '{key}': {e}")
        return default

    def classify_severity(
        self,
        vix: float,
        vix_z_score: float = 0.0,
        macro_stress_bias: float = 0.0,
        yield_spread: Optional[float] = None,
        vix_threshold: float = 30.0,
    ) -> HedgingSeverity:
        """
        Classify market stress severity based on multi-dimensional volatility & macro metrics.
        """
        if vix >= 40.0 or vix_z_score >= 3.0 or macro_stress_bias <= -0.6:
            return HedgingSeverity.CRITICAL

        if (
            vix >= vix_threshold
            or vix_z_score >= 2.5
            or macro_stress_bias <= -0.3
            or (yield_spread is not None and yield_spread < -0.5)
        ):
            return HedgingSeverity.HIGH

        if (
            vix >= 24.0
            or vix_z_score >= 1.8
            or macro_stress_bias <= -0.15
            or (yield_spread is not None and yield_spread < 0.0)
        ):
            return HedgingSeverity.ELEVATED

        return HedgingSeverity.NORMAL

    def compute_portfolio_metrics(
        self,
        portfolio: Dict[str, Any],
    ) -> Tuple[float, float, float, float]:
        """
        Compute total NLV, cash ratio, gross exposure, and weighted beta from portfolio snapshot.

        Returns:
            (total_nlv, cash_ratio, gross_exposure, weighted_beta)
        """
        total_nlv = float(portfolio.get("total_nlv", 0.0) or portfolio.get("net_liquidation_value", 0.0) or 0.0)
        cash_balance = float(portfolio.get("cash_balance", 0.0) or portfolio.get("available_cash", 0.0) or 0.0)
        positions = portfolio.get("positions", []) or []

        if total_nlv <= 0:
            # Fallback calculate from positions + cash
            pos_val = sum(float(p.get("market_value", 0.0) or 0.0) for p in positions)
            total_nlv = pos_val + cash_balance

        if total_nlv <= 0:
            return 0.0, 1.0, 0.0, 1.0

        cash_ratio = max(0.0, min(1.0, cash_balance / total_nlv))
        gross_exposure = max(0.0, (total_nlv - cash_balance) / total_nlv)

        weighted_beta_sum = 0.0
        invested_weight_sum = 0.0

        for p in positions:
            mval = float(p.get("market_value", 0.0) or 0.0)
            if mval <= 0:
                continue
            weight = mval / total_nlv
            # default beta = 1.0 if not specified
            beta = float(p.get("beta", 1.0) or 1.0)
            weighted_beta_sum += weight * beta
            invested_weight_sum += weight

        if invested_weight_sum > 0:
            portfolio_weighted_beta = weighted_beta_sum / invested_weight_sum
        else:
            portfolio_weighted_beta = 1.0

        return total_nlv, cash_ratio, gross_exposure, portfolio_weighted_beta

    def determine_target_cash_ratio(
        self,
        base_cash_ratio: float,
        severity: HedgingSeverity,
        max_target_cash_ratio: float = 0.25,
    ) -> float:
        """
        Dynamically scale target defensive cash ratio based on stress severity.
        """
        if severity == HedgingSeverity.CRITICAL:
            return max(base_cash_ratio, max_target_cash_ratio)
        elif severity == HedgingSeverity.HIGH:
            scaled = base_cash_ratio * 1.8
            return min(max_target_cash_ratio, max(scaled, 0.20))
        elif severity == HedgingSeverity.ELEVATED:
            scaled = base_cash_ratio * 1.4
            return min(max_target_cash_ratio, max(scaled, 0.15))
        else:
            return base_cash_ratio

    def identify_trim_candidates(
        self,
        positions: List[Dict[str, Any]],
        required_cash_raise: float,
        total_nlv: float,
        user_id: Optional[str] = None,
    ) -> List[HedgeRecommendation]:
        """
        Identify high-beta or weak positions to trim to raise required defensive cash.
        Preserves certified long-term winners where possible.
        """
        if required_cash_raise <= 0 or not positions or total_nlv <= 0:
            return []

        # Retrieve protected winners if available
        protected_symbols = set()
        if self.winner_service:
            try:
                winners = self.winner_service.get_certified_winners(user_id=user_id)
                protected_symbols = {w.get("symbol") for w in winners if isinstance(w, dict)}
            except Exception as e:
                logger.debug(f"Error querying winner_service: {e}")

        # Rank positions for trimming:
        # Score higher = better candidate to trim
        # Factors: High beta (>1.2), low unrealized return, non-winner
        scored_positions = []
        for p in positions:
            symbol = p.get("symbol") or p.get("ticker")
            if not symbol:
                continue
            mval = float(p.get("market_value", 0.0) or 0.0)
            if mval <= 0:
                continue

            beta = float(p.get("beta", 1.0) or 1.0)
            pnl_pct = float(p.get("unrealized_pnl_pct", 0.0) or 0.0)
            is_protected = symbol in protected_symbols

            # Trimming priority score:
            # High beta increases score, negative return increases score, protected drastically lowers score
            trim_score = (beta * 2.0) - (pnl_pct * 1.5)
            if is_protected:
                trim_score -= 10.0

            scored_positions.append({
                "symbol": symbol,
                "market_value": mval,
                "weight": mval / total_nlv,
                "beta": beta,
                "pnl_pct": pnl_pct,
                "is_protected": is_protected,
                "trim_score": trim_score,
            })

        # Sort descending by trim score (highest priority to trim first)
        scored_positions.sort(key=lambda x: x["trim_score"], reverse=True)

        recommendations = []
        remaining_cash_needed = required_cash_raise

        for sp in scored_positions:
            if remaining_cash_needed <= 0:
                break

            # Suggest trimming up to 50% of the position or what's needed
            max_trim_amount = sp["market_value"] * 0.50
            trim_amount = min(max_trim_amount, remaining_cash_needed)
            if trim_amount < 50.0:  # Ignore trivial trim amounts
                continue

            trim_weight = trim_amount / total_nlv
            remaining_cash_needed -= trim_amount

            reason = (
                f"宏觀波動率避險防守減碼：{sp['symbol']} (Beta={sp['beta']:.2f}, 損益={sp['pnl_pct']*100:.1f}%)，"
                f"建議減碼 ${trim_amount:.0f} ({trim_weight*100:.1f}%) 以增厚防禦現金儲備"
            )
            recommendations.append(HedgeRecommendation(
                action=HedgingActionType.TRIM_HIGH_BETA,
                ticker=sp["symbol"],
                suggested_weight=trim_weight,
                suggested_amount=trim_amount,
                reason=reason,
            ))

        return recommendations

    def evaluate_hedging(
        self,
        portfolio: Dict[str, Any],
        vix: float,
        vix_z_score: float = 0.0,
        macro_stress_bias: float = 0.0,
        yield_spread: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> MacroHedgeEvaluation:
        """
        Evaluate full portfolio macro volatility hedging state and generate defensive plan.
        """
        is_enabled = bool(self._get_setting("enable_macro_volatility_hedging", True, user_id=user_id))
        vix_threshold = float(self._get_setting("macro_hedge_vix_threshold", self.DEFAULT_VIX_THRESHOLD, user_id=user_id))
        max_target_cash = float(self._get_setting("macro_hedge_target_cash_ratio", self.DEFAULT_TARGET_DEFENSE_CASH, user_id=user_id))
        hedge_instrument = str(self._get_setting("macro_hedge_instrument", self.DEFAULT_HEDGE_INSTRUMENT, user_id=user_id))
        enable_inverse_etf = bool(self._get_setting("enable_inverse_etf_hedge", False, user_id=user_id))
        base_cash_ratio = float(self._get_setting("target_cash_ratio", 0.10, user_id=user_id))

        total_nlv, cash_ratio, gross_exposure, weighted_beta = self.compute_portfolio_metrics(portfolio)

        if not is_enabled:
            return MacroHedgeEvaluation(
                is_hedging_active=False,
                severity=HedgingSeverity.NORMAL,
                vix=vix,
                vix_z_score=vix_z_score,
                macro_stress_bias=macro_stress_bias,
                portfolio_gross_exposure=gross_exposure,
                portfolio_weighted_beta=weighted_beta,
                current_cash_ratio=cash_ratio,
                target_cash_ratio=base_cash_ratio,
                required_cash_raise=0.0,
                recommendations=[],
                summary="宏觀波動率避險已由使用者設定停用 (enable_macro_volatility_hedging=false)",
            )

        severity = self.classify_severity(
            vix=vix,
            vix_z_score=vix_z_score,
            macro_stress_bias=macro_stress_bias,
            yield_spread=yield_spread,
            vix_threshold=vix_threshold,
        )

        is_hedging_active = severity in (HedgingSeverity.HIGH, HedgingSeverity.CRITICAL)

        target_cash_ratio = self.determine_target_cash_ratio(
            base_cash_ratio=base_cash_ratio,
            severity=severity,
            max_target_cash_ratio=max_target_cash,
        )

        required_cash_raise = 0.0
        if cash_ratio < target_cash_ratio and total_nlv > 0:
            required_cash_raise = (target_cash_ratio - cash_ratio) * total_nlv

        recommendations: List[HedgeRecommendation] = []

        # 1. Check if holding existing hedge instruments when volatility has normalized
        positions = portfolio.get("positions", []) or []
        existing_hedge_pos = next(
            (p for p in positions if (p.get("symbol") or p.get("ticker")) == hedge_instrument),
            None,
        )

        if severity == HedgingSeverity.NORMAL and existing_hedge_pos:
            mval = float(existing_hedge_pos.get("market_value", 0.0) or 0.0)
            if mval > 0:
                recommendations.append(HedgeRecommendation(
                    action=HedgingActionType.UNWIND_HEDGE,
                    ticker=hedge_instrument,
                    suggested_weight=mval / total_nlv if total_nlv > 0 else 0.0,
                    suggested_amount=mval,
                    reason=f"宏觀波動率已平復 (VIX={vix:.1f}, Z={vix_z_score:.1f}σ)，建議平倉反向避險標的 {hedge_instrument} 回歸常態成長陣型",
                ))

        # 2. Defensive cash trim recommendations
        if is_hedging_active and required_cash_raise > 0:
            trim_recs = self.identify_trim_candidates(
                positions=positions,
                required_cash_raise=required_cash_raise,
                total_nlv=total_nlv,
                user_id=user_id,
            )
            recommendations.extend(trim_recs)

        # 3. Inverse ETF Hedging Allocation
        if is_hedging_active and enable_inverse_etf and total_nlv > 0:
            target_hedge_weight = 0.05 if severity == HedgingSeverity.HIGH else 0.10
            hedge_amount = total_nlv * target_hedge_weight
            recommendations.append(HedgeRecommendation(
                action=HedgingActionType.BUY_INVERSE_HEDGE,
                ticker=hedge_instrument,
                suggested_weight=target_hedge_weight,
                suggested_amount=hedge_amount,
                reason=(
                    f"極端宏觀波動防守對沖 (體制={severity.value}, VIX={vix:.1f}, Z={vix_z_score:.1f}σ)："
                    f"建議配置 {target_hedge_weight*100:.0f}% 反向避險標的 {hedge_instrument} (${hedge_amount:.0f}) 壓制最大回撤"
                ),
            ))

        summary_parts = []
        if is_hedging_active:
            summary_parts.append(
                f"⚠️ 宏觀波動率警戒啟動 [{severity.value}] (VIX={vix:.1f}, Z={vix_z_score:.1f}σ, 壓力={macro_stress_bias:.2f})。"
                f"目標防守現金比例調升至 {target_cash_ratio*100:.1f}% (當前 {cash_ratio*100:.1f}%)。"
            )
            if required_cash_raise > 0:
                summary_parts.append(f"需籌措防守現金 ${required_cash_raise:.0f}。")
            if enable_inverse_etf:
                summary_parts.append(f"已啟用反向 ETF ({hedge_instrument}) 對沖防護。")
        else:
            summary_parts.append(f"✅ 宏觀波動率體制正常 (VIX={vix:.1f}, Z={vix_z_score:.1f}σ)，維持預設資本配置陣型。")

        return MacroHedgeEvaluation(
            is_hedging_active=is_hedging_active,
            severity=severity,
            vix=vix,
            vix_z_score=vix_z_score,
            macro_stress_bias=macro_stress_bias,
            portfolio_gross_exposure=gross_exposure,
            portfolio_weighted_beta=weighted_beta,
            current_cash_ratio=cash_ratio,
            target_cash_ratio=target_cash_ratio,
            required_cash_raise=required_cash_raise,
            recommendations=recommendations,
            summary=" ".join(summary_parts),
        )


class MacroVolatilityHedgeContract:
    """
    Contract wrapper adapting MacroHedgingService to the generalized StrategyContract interface.
    """
    def __init__(self, hedging_service: Optional[MacroHedgingService] = None):
        from src.domain.strategy_contract import StrategyContract, MarketRegimeType, RiskBudget
        self.strategy_id = STRATEGY_NAME
        self.hedging_service = hedging_service or MacroHedgingService()
        self.subscribed_regimes = [
            MarketRegimeType.VOLATILITY_EXTREME,
            MarketRegimeType.VOLATILITY_PIVOT,
        ]
        self.risk_budget = RiskBudget(
            max_underlying_stop_pct=10.0,
            trailing_stop_pct=5.0,
            max_position_margin_pct=0.15,
            max_holding_days=30,
            max_portfolio_gross_leverage=1.0,
            max_allowed_leverage=1,
        )

    def evaluate_entry(self, market_context: Dict[str, Any]):
        from src.domain.strategy_contract import StrategyExecutionPlan
        vix = market_context.get("vix")
        if vix is None:
            return None
        vix_val = float(vix)
        vix_z = float(market_context.get("vix_z_score", 0.0) or 0.0)
        macro_stress = float(market_context.get("macro_stress_bias", 0.0) or 0.0)
        yield_spread = market_context.get("yield_spread")
        user_id = market_context.get("user_id")
        portfolio = market_context.get("portfolio") or {}

        evaluation = self.hedging_service.evaluate_hedging(
            portfolio=portfolio,
            vix=vix_val,
            vix_z_score=vix_z,
            macro_stress_bias=macro_stress,
            yield_spread=yield_spread,
            user_id=user_id,
        )

        if evaluation.is_hedging_active:
            # Check recommendations for inverse ETF or defensive cash scaling
            inverse_rec = next(
                (r for r in evaluation.recommendations if r.action == HedgingActionType.BUY_INVERSE_HEDGE),
                None,
            )
            target_weight = inverse_rec.suggested_weight if inverse_rec else 0.0
            return StrategyExecutionPlan(
                action="BUY" if inverse_rec else "HOLD",
                stage=1 if evaluation.severity == HedgingSeverity.HIGH else 2,
                target_leverage=1,
                target_cumulative_weight=target_weight,
                incremental_weight=target_weight,
                stop_loss_pct=5.0,
                take_profit_pct=15.0,
                is_trailing_stop_loss=True,
                reason=evaluation.summary,
            )
        return None

    def evaluate_exit(self, position: Any, market_context: Dict[str, Any]):
        from src.domain.strategy_contract import StrategyExecutionPlan
        vix = market_context.get("vix")
        if vix is None:
            return None
        vix_val = float(vix)
        vix_z = float(market_context.get("vix_z_score", 0.0) or 0.0)
        macro_stress = float(market_context.get("macro_stress_bias", 0.0) or 0.0)
        severity = self.hedging_service.classify_severity(
            vix=vix_val,
            vix_z_score=vix_z,
            macro_stress_bias=macro_stress,
        )
        if severity == HedgingSeverity.NORMAL:
            return StrategyExecutionPlan(
                action="SELL",
                stage=0,
                target_leverage=1,
                target_cumulative_weight=0.0,
                incremental_weight=0.0,
                reason="宏觀波動率已回落至常態體制，解除對沖部位回歸常態配置",
            )
        return None

    def is_safety_control(self) -> bool:
        return True

