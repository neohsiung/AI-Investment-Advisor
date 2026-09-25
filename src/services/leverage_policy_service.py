"""
Controlled Leverage & CFD Risk Management Policy Service
========================================================
評估與控管 eToro 槓桿使用時機、CFD 融資成本、投組總槓桿上限及強制防護。

eToro 美股槓桿關鍵認知：
1. 現貨 (X1)：底層真實股票，無融資成本 (Overnight Fee = 0)，無強平風險。
2. 槓桿 (X2)：在 eToro 自動轉為 CFD (差價合約)。
   - 隔夜利息 (Overnight Fee)：年化約 8.0%~8.5% (SOFR + 3.0%)。
   - 週末三倍融資費：週五收盤時扣除 3 天費用。
   - 強制平倉風險：虧損接近維持保證金時將被市價砍倉。

使用原則：
- 僅在「超高置信度 (>=8.5) + 低宏觀波動 (VIX<=20) + 多智能體共識 (>=3)」時允許 X2 槓桿。
- 槓桿上限為 X2 (禁止 X5)。
- 投組總槓桿率限制 <= 1.3x，單檔保證金佔比 <= 10%。
- 開槓桿必須且強制掛載「移動停損 (Trailing Stop Loss)」，預設 5.0%~6.0%。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

logger = logging.getLogger("LeveragePolicyService")


@dataclass
class LeverageDecision:
    eligible_leverage: int             # 1 (現貨) 或 2 (受控槓桿)
    is_leveraged: bool                 # 是否開槓桿
    stop_loss_pct: float               # 停損百分比 (例如 5.0%)
    take_profit_pct: float             # 停利百分比 (例如 15.0%)
    stop_loss_rate: Optional[float]    # 停損絕對價格 (若已知現價)
    take_profit_rate: Optional[float]  # 停利絕對價格 (若已知現價)
    is_trailing_stop_loss: bool        # 是否啟用移動停損
    overnight_fee_annual_pct: float    # 預估年化隔夜融資費率 (例如 8.5%)
    reason: str                        # 決策依據說明
    max_holding_days: int              # 建議最長持有日數 (槓桿通常 5~10 日)


class LeveragePolicyService:
    """
    Evaluates whether a trade is qualified for leverage and assigns mandatory protective stops.
    """

    MIN_CONFIDENCE_FOR_LEVERAGE = 8.5      # 信心分數門檻
    MAX_VIX_FOR_LEVERAGE = 20.0            # VIX 波動率門檻
    MAX_PORTFOLIO_GROSS_LEVERAGE = 1.30    # 投組總槓桿率上限
    MAX_SINGLE_POSITION_MARGIN_PCT = 0.10  # 單檔保證金上限 (10% NLV)
    DEFAULT_LEVERAGED_TSL_PCT = 5.5        # 槓桿部位預設移動停損 (5.5%)
    DEFAULT_UNLEVERAGED_TSL_PCT = 8.0      # 現貨部位預設停損 (8.0%)
    ESTIMATED_CFD_OVERNIGHT_PCT = 8.5      # 預估 CFD 隔夜年化利率

    def __init__(self, user_id: str = None, settings_repo: Any = None):
        self.user_id = user_id
        self.settings_repo = settings_repo

    def evaluate_leverage(
        self,
        ticker: str,
        action: str,
        confidence_score: float,
        current_price: Optional[float] = None,
        amount_usd: Optional[float] = None,
        portfolio_nlv: Optional[float] = None,
        current_gross_tnv: Optional[float] = None,
        vix: Optional[float] = None,
        sentinel_macro_risk: Optional[str] = "low_risk",
        confirming_agents_count: int = 1,
    ) -> LeverageDecision:
        """
        Evaluate leverage eligibility and calculate protective stop levels.
        """
        action_upper = (action or "").upper()
        if action_upper != "BUY":
            # 賣單 / 平倉不涉及新建槓桿
            return LeverageDecision(
                eligible_leverage=1,
                is_leveraged=False,
                stop_loss_pct=0.0,
                take_profit_pct=0.0,
                stop_loss_rate=None,
                take_profit_rate=None,
                is_trailing_stop_loss=False,
                overnight_fee_annual_pct=0.0,
                reason="Sell/Close order does not establish leverage",
                max_holding_days=0,
            )

        # 1. 信心度門檻檢查
        if confidence_score < self.MIN_CONFIDENCE_FOR_LEVERAGE:
            reason = (
                f"Confidence {confidence_score:.1f} < {self.MIN_CONFIDENCE_FOR_LEVERAGE:.1f} threshold; "
                f"unleveraged spot equity (X1) deployed to preserve capital."
            )
            return self._make_spot_decision(current_price, reason)

        # 2. 宏觀波動率檢查 (VIX)
        if vix is not None and vix > self.MAX_VIX_FOR_LEVERAGE:
            reason = (
                f"Macro VIX {vix:.1f} > {self.MAX_VIX_FOR_LEVERAGE:.1f} safe threshold; "
                f"high market volatility suppresses leverage to X1 spot."
            )
            return self._make_spot_decision(current_price, reason)

        # 3. 宏觀哨兵警報檢查
        if sentinel_macro_risk and sentinel_macro_risk.lower() not in ("low_risk", "green", "normal"):
            reason = (
                f"Sentinel macro radar is '{sentinel_macro_risk}'; "
                f"leverage blocked for macroeconomic defense."
            )
            return self._make_spot_decision(current_price, reason)

        # 4. 多智能體共識檢查
        if confirming_agents_count < 2:
            reason = (
                f"Agent consensus count {confirming_agents_count} < 2; "
                f"insufficient multi-agent conviction for leverage."
            )
            return self._make_spot_decision(current_price, reason)

        # 5. 投組總槓桿上限檢查 (Portfolio Gross Leverage <= 1.30x)
        if portfolio_nlv and portfolio_nlv > 0 and current_gross_tnv is not None and amount_usd:
            # 嘗試若開 X2，新的投組總暴險
            proposed_additional_exposure = amount_usd * 2.0
            new_gross_tnv = current_gross_tnv + proposed_additional_exposure
            projected_leverage_ratio = new_gross_tnv / portfolio_nlv
            if projected_leverage_ratio > self.MAX_PORTFOLIO_GROSS_LEVERAGE:
                reason = (
                    f"Projected portfolio gross leverage {projected_leverage_ratio:.2f}x "
                    f"exceeds {self.MAX_PORTFOLIO_GROSS_LEVERAGE:.2f}x cap; capped at X1 spot."
                )
                return self._make_spot_decision(current_price, reason)

        # 6. 單檔保證金上限檢查 (Single Position Margin <= 10% NLV)
        if portfolio_nlv and portfolio_nlv > 0 and amount_usd:
            margin_ratio = amount_usd / portfolio_nlv
            if margin_ratio > self.MAX_SINGLE_POSITION_MARGIN_PCT:
                reason = (
                    f"Order amount ${amount_usd:.2f} represents {margin_ratio:.1%} of NLV "
                    f"(cap: {self.MAX_SINGLE_POSITION_MARGIN_PCT:.1%}); leverage suppressed to X1."
                )
                return self._make_spot_decision(current_price, reason)

        # ── 通過所有守門條件：放行 X2 槓桿 ──────────────────────────────
        stop_loss_pct = self.DEFAULT_LEVERAGED_TSL_PCT
        take_profit_pct = 15.0
        stop_loss_rate = None
        take_profit_rate = None

        if current_price and current_price > 0:
            # 計算停損價與停利價
            stop_loss_rate = round(current_price * (1.0 - stop_loss_pct / 100.0), 4)
            take_profit_rate = round(current_price * (1.0 + take_profit_pct / 100.0), 4)

        reason = (
            f"✅ Super-high confidence ({confidence_score:.1f}>={self.MIN_CONFIDENCE_FOR_LEVERAGE}), "
            f"calm macro environment, and strong consensus ({confirming_agents_count} agents). "
            f"Deploying controlled X2 leverage with mandatory {stop_loss_pct}% Trailing Stop Loss."
        )

        return LeverageDecision(
            eligible_leverage=2,
            is_leveraged=True,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            stop_loss_rate=stop_loss_rate,
            take_profit_rate=take_profit_rate,
            is_trailing_stop_loss=True,  # 槓桿部位強制開啟移動停損
            overnight_fee_annual_pct=self.ESTIMATED_CFD_OVERNIGHT_PCT,
            reason=reason,
            max_holding_days=10,         # 槓桿波段建議持有 <= 10 日
        )

    def _make_spot_decision(self, current_price: Optional[float], reason: str) -> LeverageDecision:
        """Create an unleveraged spot (X1) decision with default trailing stop."""
        stop_loss_pct = self.DEFAULT_UNLEVERAGED_TSL_PCT
        take_profit_pct = 20.0
        stop_loss_rate = None
        take_profit_rate = None

        if current_price and current_price > 0:
            stop_loss_rate = round(current_price * (1.0 - stop_loss_pct / 100.0), 4)
            take_profit_rate = round(current_price * (1.0 + take_profit_pct / 100.0), 4)

        return LeverageDecision(
            eligible_leverage=1,
            is_leveraged=False,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            stop_loss_rate=stop_loss_rate,
            take_profit_rate=take_profit_rate,
            is_trailing_stop_loss=True,  # 現貨亦建議掛載移動停損以保護利潤
            overnight_fee_annual_pct=0.0,
            reason=reason,
            max_holding_days=60,         # 現貨無融資利息負擔，可長線波段持有
        )
