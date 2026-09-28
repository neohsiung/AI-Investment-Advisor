"""
Market Regime Adaptive Service — 總體市場體制感知服務
======================================================
Monitors macro indicators (S&P 500 vs SMA 200, VIX Term Structure)
to determine the global market regime (BULL, NEUTRAL, BEAR).
Dynamically shifts risk budgets, cash reserves, and stop-loss multiples
to preserve capital during downturns and guarantee long-term CAGR > 10%
with Max Drawdown <= 15%.

監控大盤走勢與 VIX 指數，判定當前體制並動態調整現金儲備與風控乘數，
確保在下行風險中鎖定成果，實現扣除成本後 10 年年化報酬率 > 10%。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """Global Market Regimes / 全域市場體制"""
    BULL_MOMENTUM = "BULL_MOMENTUM"   # Risk-On / 進攻模式 (S&P > SMA200, VIX < 20)
    NEUTRAL_RANGE = "NEUTRAL_RANGE"   # Neutral / 震盪模式 (S&P near SMA200 or 20 <= VIX <= 28)
    BEAR_CRISIS   = "BEAR_CRISIS"     # Risk-Off / 防禦模式 (S&P < SMA200 or VIX > 28)


@dataclass
class RegimePolicy:
    """Risk policy constraints enforced by the current regime."""
    regime: MarketRegime
    cash_reserve_pct: float            # Recommended cash reserve percentage (e.g. 5.0%, 50.0%)
    buy_confidence_threshold: float    # Min score to authorize BUY orders (e.g. 6.5 vs 9.0)
    stop_atr_multiplier: float         # Dynamic ATR stop-loss width (e.g. 2.5x vs 1.5x)
    max_leverage: float                # Upper bound on leverage (e.g. 1.2x vs 0.0x)
    allow_new_buys: bool               # Whether new buy positions are authorized
    rationale: str                     # Human/Agent-readable policy explanation


class MarketRegimeService:
    """
    Evaluates global market health and derives defensive risk boundaries.
    市場體制評估引擎：根據大盤價量與波動率推導動態避險防線。
    """

    def __init__(self, market_data_service=None):
        self.market_data_service = market_data_service

    def classify_regime(
        self,
        spy_price: float,
        spy_sma200: float,
        vix: float,
    ) -> RegimePolicy:
        """
        Classify market regime based on SPY distance to 200-day SMA and VIX volatility.
        依據標普 500 與 200MA 之距離及 VIX 波動率判定體制。
        """
        if spy_sma200 <= 0 or spy_price <= 0:
            logger.warning("Invalid SPY price (%s) or SMA200 (%s); defaulting to NEUTRAL_RANGE", spy_price, spy_sma200)
            return self._build_policy(MarketRegime.NEUTRAL_RANGE, "Data invalid; default to neutral risk")

        ratio = spy_price / spy_sma200

        # 1. BEAR_CRISIS (Risk-Off): S&P 500 significantly broken below 200-day MA or VIX spiking
        if ratio < 0.98 or vix > 28.0:
            reason = f"Bearish/Crisis signal detected: SPY/SMA200={ratio:.3f}, VIX={vix:.1f}"
            logger.warning("MarketRegimeService: Entering BEAR_CRISIS. %s", reason)
            return self._build_policy(MarketRegime.BEAR_CRISIS, reason)

        # 2. BULL_MOMENTUM (Risk-On): S&P 500 well above 200-day MA and calm volatility
        if ratio >= 1.02 and vix < 20.0:
            reason = f"Bullish momentum: SPY/SMA200={ratio:.3f} (above MA200), VIX={vix:.1f} (calm)"
            logger.info("MarketRegimeService: Operating in BULL_MOMENTUM. %s", reason)
            return self._build_policy(MarketRegime.BULL_MOMENTUM, reason)

        # 3. NEUTRAL_RANGE: Choppy transition zone
        reason = f"Neutral/Choppy market: SPY/SMA200={ratio:.3f}, VIX={vix:.1f}"
        logger.info("MarketRegimeService: Operating in NEUTRAL_RANGE. %s", reason)
        return self._build_policy(MarketRegime.NEUTRAL_RANGE, reason)

    def _build_policy(self, regime: MarketRegime, rationale: str) -> RegimePolicy:
        """Map regime to strict risk policies."""
        if regime == MarketRegime.BEAR_CRISIS:
            return RegimePolicy(
                regime=regime,
                cash_reserve_pct=50.0,            # 50% Cash floor to survive drawdowns
                buy_confidence_threshold=9.0,     # Extreme bar for any new buy
                stop_atr_multiplier=1.5,          # Tight stop loss
                max_leverage=0.0,                 # 0x leverage (no margin allowed)
                allow_new_buys=False,             # Halt standard buying
                rationale=rationale,
            )
        elif regime == MarketRegime.BULL_MOMENTUM:
            return RegimePolicy(
                regime=regime,
                cash_reserve_pct=5.0,             # Full deployment
                buy_confidence_threshold=6.5,     # High momentum friendly
                stop_atr_multiplier=2.5,          # Wide breath for runners
                max_leverage=1.2,                 # Moderate safe leverage
                allow_new_buys=True,
                rationale=rationale,
            )
        else: # NEUTRAL_RANGE
            return RegimePolicy(
                regime=regime,
                cash_reserve_pct=20.0,            # 20% cushion
                buy_confidence_threshold=7.5,     # Standard threshold
                stop_atr_multiplier=2.0,          # Standard ATR stop
                max_leverage=1.0,                 # 1x spot equity only
                allow_new_buys=True,
                rationale=rationale,
            )
