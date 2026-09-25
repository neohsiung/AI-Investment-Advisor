"""
Quality Gate Service
Enforces strict quality admission and ongoing standards for tickers in the universe.
Includes scale, liquidity, financial health, technical trend, and composite scoring.
品質把關服務：對標的池進行嚴格的規模、流動性、財務健康度與趨勢品質審核。
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.services.market_data_service import MarketDataService
from src.services.settings_service import SettingsService
from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


@dataclass
class QualityAssessment:
    """Structured assessment result for a ticker."""
    ticker: str
    passed: bool
    overall_score: float                       # 0.0 - 10.0 composite quality score
    hard_gates_passed: bool
    hard_gate_details: Dict[str, Any]
    fundamental_score: float                   # 0.0 - 10.0
    technical_score: float                     # 0.0 - 10.0
    liquidity_score: float                     # 0.0 - 10.0
    reasons: List[str]
    metrics: Dict[str, Any]
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    _fallback_reason: Optional[str] = None
    _insufficient_data: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QualityGateService:
    """
    Evaluates tickers against strict quality criteria before admission
    or retention in the persistent ticker universe.
    """

    def __init__(self, user_id: str, market_data_service: Optional[MarketDataService] = None):
        self.user_id = resolve_user_id(user_id)
        self.market = market_data_service or MarketDataService(user_id=self.user_id)
        self.settings = SettingsService(user_id=self.user_id)

    def _get_thresholds(self) -> Dict[str, float]:
        """Fetch user-configurable or default quality thresholds."""
        try:
            min_score = float(self.settings.get_setting("universe_min_quality_score"))
        except Exception:
            min_score = 6.5

        try:
            min_cap_b = float(self.settings.get_setting("universe_min_market_cap_billions"))
        except Exception:
            min_cap_b = 2.0

        try:
            min_vol_m = float(self.settings.get_setting("universe_min_daily_volume_millions"))
        except Exception:
            min_vol_m = 5.0

        return {
            "min_quality_score": min_score,
            "min_market_cap": min_cap_b * 1e9,
            "min_dollar_volume": min_vol_m * 1e6,
            "min_price": 5.0,  # Strict penny stock exclusion
        }

    async def evaluate_ticker(self, ticker: str) -> QualityAssessment:
        """
        Perform comprehensive quality assessment for a ticker.
        對標的執行全方位品質檢查（硬門檻、基本面、技術面、流動性）。
        """
        ticker = ticker.upper().strip()
        thresholds = self._get_thresholds()
        reasons: List[str] = []

        try:
            # 1. Fetch Financials & Fundamental Info
            financials = self.market.get_financials(ticker) or {}
            
            # 2. Fetch Price
            price = 0.0
            if "currentPrice" in financials and financials["currentPrice"]:
                price = float(financials["currentPrice"])
            elif "regularMarketPrice" in financials and financials["regularMarketPrice"]:
                price = float(financials["regularMarketPrice"])
            else:
                try:
                    price_map = await self.market.get_current_prices([ticker])
                    price = float(price_map.get(ticker, 0.0))
                except Exception as pe:
                    logger.warning(f"Could not fetch current price for {ticker}: {pe}")
                    price = 0.0

            # 3. Fetch Technical Indicators
            tech = self.market.get_technical_indicators(ticker) or {}

            # Check for total lack of data
            has_insufficient_data = bool(
                tech.get("_insufficient_data") or (not financials and price <= 0.0)
            )
            if has_insufficient_data and not financials and price <= 0.0:
                logger.warning(
                    f"Quality check for {ticker} has insufficient data: no financials or price found."
                )
                return QualityAssessment(
                    ticker=ticker,
                    passed=False,
                    overall_score=0.0,
                    hard_gates_passed=False,
                    hard_gate_details={"data_available": False},
                    fundamental_score=0.0,
                    technical_score=0.0,
                    liquidity_score=0.0,
                    reasons=["Insufficient market data to perform quality assessment"],
                    metrics={},
                    _insufficient_data=True,
                    _fallback_reason="Insufficient data from market data providers",
                )

            # 4. Extract Key Metrics
            market_cap = float(financials.get("marketCap") or financials.get("market_cap") or 0.0)
            
            # Volume & Dollar volume
            vol_dict = tech.get("volume", {}) if isinstance(tech.get("volume"), dict) else {}
            avg_vol_20 = float(vol_dict.get("avg_20") or financials.get("averageVolume") or financials.get("volume") or 0.0)
            dollar_volume = avg_vol_20 * price if (avg_vol_20 > 0 and price > 0) else 0.0

            # Fundamental ratios
            debt_to_equity = financials.get("debtToEquity")
            if debt_to_equity is not None:
                # yfinance often reports D/E as percentage (e.g. 150 for 1.5)
                debt_to_equity = float(debt_to_equity)
                if debt_to_equity > 10.0:
                    debt_to_equity = debt_to_equity / 100.0
            roe = float(financials.get("returnOnEquity") or 0.0)
            operating_margin = float(financials.get("operatingMargins") or financials.get("profitMargins") or 0.0)
            rev_growth = float(financials.get("revenueGrowth") or 0.0)
            pe_ratio = float(financials.get("forwardPE") or financials.get("trailingPE") or 0.0)

            # Technical readings
            sma_dict = tech.get("sma", {}) if isinstance(tech.get("sma"), dict) else {}
            sma_50 = float(sma_dict.get("sma_50") or 0.0)
            sma_200 = float(sma_dict.get("sma_200") or 0.0)
            rsi = float(tech.get("rsi") or 50.0)
            macd_status = str(tech.get("macd") or "neutral").lower()

            # 5. Check Hard Gates (Penny stock, Market cap, Dollar volume)
            price_passed = price >= thresholds["min_price"]
            cap_passed = market_cap >= thresholds["min_market_cap"] if market_cap > 0 else True
            vol_passed = dollar_volume >= thresholds["min_dollar_volume"] if dollar_volume > 0 else True

            hard_gate_details = {
                "price": price,
                "price_passed": price_passed,
                "min_price": thresholds["min_price"],
                "market_cap": market_cap,
                "cap_passed": cap_passed,
                "min_market_cap": thresholds["min_market_cap"],
                "dollar_volume": dollar_volume,
                "vol_passed": vol_passed,
                "min_dollar_volume": thresholds["min_dollar_volume"],
            }

            hard_gates_passed = price_passed and cap_passed and vol_passed
            if not price_passed:
                reasons.append(f"Price ${price:.2f} below penny stock threshold ${thresholds['min_price']:.2f}")
            if not cap_passed:
                reasons.append(f"Market cap ${market_cap/1e9:.2f}B below minimum ${thresholds['min_market_cap']/1e9:.2f}B")
            if not vol_passed:
                reasons.append(f"Daily dollar volume ${dollar_volume/1e6:.2f}M below minimum ${thresholds['min_dollar_volume']/1e6:.2f}M")

            # 6. Fundamental Scoring (0 - 10)
            fund_scores = []
            
            # Leverage score
            if debt_to_equity is not None:
                if debt_to_equity <= 1.0:
                    fund_scores.append(10.0)
                elif debt_to_equity <= 2.0:
                    fund_scores.append(7.5)
                elif debt_to_equity <= 3.5:
                    fund_scores.append(5.0)
                else:
                    fund_scores.append(2.0)
                    reasons.append(f"High debt-to-equity ratio ({debt_to_equity:.2f})")
            else:
                fund_scores.append(5.0)

            # Profitability (ROE)
            if roe >= 0.15:
                fund_scores.append(10.0)
            elif roe >= 0.08:
                fund_scores.append(8.0)
            elif roe > 0:
                fund_scores.append(6.0)
            else:
                fund_scores.append(2.5)
                if roe < 0:
                    reasons.append(f"Negative ROE ({roe*100:.1f}%)")

            # Operating Margins
            if operating_margin >= 0.20:
                fund_scores.append(10.0)
            elif operating_margin >= 0.10:
                fund_scores.append(8.0)
            elif operating_margin > 0:
                fund_scores.append(6.0)
            else:
                fund_scores.append(3.0)

            # Revenue Growth
            if rev_growth >= 0.15:
                fund_scores.append(10.0)
            elif rev_growth >= 0.05:
                fund_scores.append(8.0)
            elif rev_growth >= 0:
                fund_scores.append(6.0)
            else:
                fund_scores.append(3.0)
                reasons.append(f"Contracting revenue growth ({rev_growth*100:.1f}%)")

            # Valuation (PE)
            if 5.0 <= pe_ratio <= 35.0:
                fund_scores.append(8.5)
            elif 35.0 < pe_ratio <= 60.0:
                fund_scores.append(7.0)
            elif pe_ratio > 60.0:
                fund_scores.append(4.5)
            elif pe_ratio > 0:
                fund_scores.append(6.0)
            else:
                # Negative PE indicates unprofitable
                fund_scores.append(3.5)

            fundamental_score = round(sum(fund_scores) / len(fund_scores), 2)

            # 7. Technical Scoring (0 - 10)
            tech_components = []
            
            # Trend vs 200-SMA
            if sma_200 > 0 and price > 0:
                if price >= sma_200:
                    tech_components.append(9.0)
                else:
                    tech_components.append(3.0)
                    reasons.append(f"Price (${price:.2f}) below 200-day SMA (${sma_200:.2f})")
            else:
                tech_components.append(5.0)

            # Trend vs 50-SMA
            if sma_50 > 0 and price > 0:
                if price >= sma_50:
                    tech_components.append(8.5)
                else:
                    tech_components.append(4.0)
            else:
                tech_components.append(5.0)

            # RSI Score
            if 45.0 <= rsi <= 65.0:
                tech_components.append(9.0)  # Ideal healthy trend
            elif 35.0 <= rsi < 45.0:
                tech_components.append(7.0)  # Moderate
            elif 65.0 < rsi <= 75.0:
                tech_components.append(7.0)  # Strong momentum
            elif rsi < 35.0:
                tech_components.append(4.0)  # Oversold / distressed
                reasons.append(f"Depressed RSI ({rsi:.1f})")
            else:
                tech_components.append(4.5)  # Overextended (> 75)

            # MACD
            if macd_status == "bullish":
                tech_components.append(8.5)
            elif macd_status == "bearish":
                tech_components.append(4.0)
            else:
                tech_components.append(6.0)

            technical_score = round(sum(tech_components) / len(tech_components), 2)

            # 8. Liquidity Score (0 - 10)
            liq_components = []
            if market_cap >= 50e9:
                liq_components.append(10.0)
            elif market_cap >= 10e9:
                liq_components.append(8.5)
            elif market_cap >= 2e9:
                liq_components.append(6.5)
            else:
                liq_components.append(4.0)

            if dollar_volume >= 50e6:
                liq_components.append(10.0)
            elif dollar_volume >= 20e6:
                liq_components.append(8.5)
            elif dollar_volume >= 5e6:
                liq_components.append(6.5)
            else:
                liq_components.append(4.0)

            liquidity_score = round(sum(liq_components) / len(liq_components), 2)

            # 9. Composite Score
            overall_score = round(
                0.45 * fundamental_score + 0.35 * technical_score + 0.20 * liquidity_score,
                2
            )

            min_required_score = thresholds["min_quality_score"]
            score_passed = overall_score >= min_required_score
            if not score_passed:
                reasons.append(
                    f"Overall quality score {overall_score:.2f} below admission threshold {min_required_score:.2f}"
                )

            passed = hard_gates_passed and score_passed
            if passed and not reasons:
                reasons.append(f"Passed all quality checks with composite score {overall_score:.2f}")

            metrics = {
                "price": price,
                "market_cap": market_cap,
                "dollar_volume": dollar_volume,
                "debt_to_equity": debt_to_equity,
                "roe": roe,
                "operating_margin": operating_margin,
                "rev_growth": rev_growth,
                "pe_ratio": pe_ratio,
                "rsi": rsi,
                "macd": macd_status,
                "sma_50": sma_50,
                "sma_200": sma_200,
            }

            return QualityAssessment(
                ticker=ticker,
                passed=passed,
                overall_score=overall_score,
                hard_gates_passed=hard_gates_passed,
                hard_gate_details=hard_gate_details,
                fundamental_score=fundamental_score,
                technical_score=technical_score,
                liquidity_score=liquidity_score,
                reasons=reasons,
                metrics=metrics,
                _fallback_reason=None,
                _insufficient_data=has_insufficient_data,
            )

        except Exception as e:
            logger.warning(
                f"QualityGateService evaluation failed unexpectedly on {ticker}: {e}",
                exc_info=True
            )
            return QualityAssessment(
                ticker=ticker,
                passed=False,
                overall_score=0.0,
                hard_gates_passed=False,
                hard_gate_details={"error": str(e)},
                fundamental_score=0.0,
                technical_score=0.0,
                liquidity_score=0.0,
                reasons=[f"Evaluation failed due to exception: {str(e)}"],
                metrics={},
                _fallback_reason=f"Exception: {str(e)}",
            )
