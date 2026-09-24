"""
Universe Lifecycle Service
Coordinates dynamic evolution of the ticker universe based on external macro regimes,
quality degradation evictions, and qualified market candidate admissions.
標的池生命週期管理服務：根據宏觀環境與市場狀態，動態剔除惡化標的並遴選優質新標的。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set

from src.repositories.ticker_universe_repository import TickerUniverseRepository
from src.services.market_data_service import MarketDataService
from src.services.quality_gate_service import QualityGateService, QualityAssessment
from src.services.settings_service import SettingsService
from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)

# Curated diversified universe of US large-cap leaders across key sectors
DEFAULT_CANDIDATE_POOL = [
    # Technology / Semiconductors / Software
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "CRM", "AMD", "ADBE", "QCOM", "TXN", "NOW", "IBM", "ORCL",
    # Financials & Payments
    "JPM", "V", "MA", "BAC", "WFC", "MS", "GS", "BLK",
    # Healthcare & Biotech
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR",
    # Consumer & Retail
    "WMT", "PG", "COST", "HD", "PEP", "KO", "MCD", "NKE",
    # Industrials & Energy
    "CAT", "GE", "UNP", "HON", "XOM", "CVX", "LIN",
]


@dataclass
class MacroRegime:
    """Macro regime context and lifecycle parameters."""
    regime: str                                # BULL_GROWTH, HIGH_VOLATILITY, INVERSION_DEFENSIVE, NEUTRAL_BALANCED
    vix: float
    yield_curve_inverted: bool
    spy_above_200sma: bool
    quality_score_adjustment: float            # Adjustment applied to admission threshold
    summary: str
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class UniverseLifecycleService:
    """
    Manages the dynamic lifecycle of the user's ticker universe:
    - Monitors external macro conditions (VIX, yield curve, SPY trend).
    - Evicts active tickers whose quality has degraded below threshold.
    - Screens and admits top-quality candidate tickers up to capacity.
    """

    def __init__(
        self,
        user_id: str,
        repo: Optional[TickerUniverseRepository] = None,
        market: Optional[MarketDataService] = None,
        quality_gate: Optional[QualityGateService] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.repo = repo or TickerUniverseRepository()
        self.market = market or MarketDataService(user_id=self.user_id)
        self.quality_gate = quality_gate or QualityGateService(user_id=self.user_id, market_data_service=self.market)
        self.settings = SettingsService(user_id=self.user_id)

    async def detect_macro_regime(self) -> MacroRegime:
        """
        Evaluate external macro economic state to guide universe quality criteria.
        評估外部宏觀經濟狀態（殖利率倒掛、恐慌指數 VIX、大盤年線趨勢）。
        """
        vix = 18.0
        spy_above_200sma = True
        yield_curve_inverted = False

        try:
            # 1. Fetch benchmark prices (^VIX, SPY)
            prices = await self.market.get_current_prices(["^VIX", "SPY"])
            vix = float(prices.get("^VIX") or 18.0)
            spy_price = float(prices.get("SPY") or 0.0)

            # 2. Check SPY technical indicators
            spy_tech = self.market.get_technical_indicators("SPY") or {}
            sma_dict = spy_tech.get("sma", {}) if isinstance(spy_tech.get("sma"), dict) else {}
            spy_sma200 = float(sma_dict.get("sma_200") or 0.0)
            if spy_price > 0 and spy_sma200 > 0:
                spy_above_200sma = spy_price >= spy_sma200

            # 3. Check yield curve
            yc = self.market.get_yield_curve_inversion() or {}
            yield_curve_inverted = bool(yc.get("is_inverted", False))

        except Exception as e:
            logger.warning(f"Error detecting macro regime indicators: {e}", exc_info=True)

        # Classify regime
        if vix >= 25.0:
            regime = "HIGH_VOLATILITY"
            quality_adj = 0.5
            summary = f"High volatility regime (VIX {vix:.1f} >= 25). Heightened quality and liquidity filter."
        elif yield_curve_inverted:
            regime = "INVERSION_DEFENSIVE"
            quality_adj = 0.5
            summary = "Yield curve inverted. Defensive posture: prioritizing balance sheet quality and low debt."
        elif spy_above_200sma and vix < 20.0:
            regime = "BULL_GROWTH"
            quality_adj = 0.0
            summary = f"Bull growth regime (SPY > 200-SMA, VIX {vix:.1f}). Standard quality gate."
        else:
            regime = "NEUTRAL_BALANCED"
            quality_adj = 0.0
            summary = f"Neutral market conditions (VIX {vix:.1f}). Balanced quality screening."

        return MacroRegime(
            regime=regime,
            vix=vix,
            yield_curve_inverted=yield_curve_inverted,
            spy_above_200sma=spy_above_200sma,
            quality_score_adjustment=quality_adj,
            summary=summary,
        )

    async def review_and_evict_active_tickers(
        self,
        eviction_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Review all active tickers in the universe. Evict any that degrade below quality threshold.
        審核當前所有活躍標的，剔除品質惡化或跌破硬性門檻之標的。
        """
        if eviction_threshold is None:
            try:
                eviction_threshold = float(self.settings.get_setting("universe_eviction_threshold"))
            except Exception:
                eviction_threshold = 4.0

        active_tickers = self.repo.get_all(self.user_id, status="active")
        evicted = []

        for item in active_tickers:
            ticker = item["ticker"]
            try:
                assessment = await self.quality_gate.evaluate_ticker(ticker)
                
                # If market data was temporarily missing, do not evict immediately to prevent false triggers
                if assessment._insufficient_data:
                    logger.warning(
                        f"Skipping lifecycle eviction check for {ticker} due to insufficient data."
                    )
                    continue

                should_evict = False
                eviction_reasons = []

                # Trigger 1: Score degraded below eviction threshold
                if assessment.overall_score < eviction_threshold:
                    should_evict = True
                    eviction_reasons.append(
                        f"Quality score degraded to {assessment.overall_score:.2f} (< threshold {eviction_threshold:.2f})"
                    )

                # Trigger 2: Hard gate catastrophic failure (e.g. price fell into penny stock territory)
                if not assessment.hard_gates_passed:
                    gate_details = assessment.hard_gate_details
                    if not gate_details.get("price_passed", True):
                        should_evict = True
                        eviction_reasons.append(
                            f"Price ${gate_details.get('price', 0.0):.2f} fell below minimum requirement"
                        )

                if should_evict:
                    reason_str = "; ".join(eviction_reasons or assessment.reasons[:2])
                    ok = self.repo.remove(self.user_id, ticker, reason=reason_str)
                    if ok:
                        self.repo.add_log(
                            self.user_id,
                            ticker,
                            "evicted",
                            "UniverseLifecycleService",
                            reasoning=f"Evicted: {reason_str}. Score: {assessment.overall_score:.2f}",
                            old_status="active",
                            new_status="removed",
                        )
                        evicted.append({
                            "ticker": ticker,
                            "score": assessment.overall_score,
                            "reason": reason_str,
                            "evicted_at": datetime.now(timezone.utc).isoformat(),
                        })
                        logger.info(f"Evicted {ticker} from universe: {reason_str}")
            except Exception as e:
                logger.warning(f"Error reviewing ticker {ticker} during eviction check: {e}", exc_info=True)

        return evicted

    async def screen_and_admit_candidates(
        self,
        candidate_pool: Optional[List[str]] = None,
        max_active: Optional[int] = None,
        min_quality_score: Optional[float] = None,
        regime_adjustment: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Screen candidates against the quality gate and admit top-scoring ones up to capacity.
        篩選市場候選標的，依照綜合品質評分由高至低擇優納入自選池，直至額滿。
        """
        try:
            max_active = max_active or int(self.settings.get_setting("universe_max_active_tickers"))
        except Exception:
            max_active = 30

        try:
            min_quality_score = min_quality_score or float(self.settings.get_setting("universe_min_quality_score"))
        except Exception:
            min_quality_score = 6.5

        effective_min_score = min_quality_score + regime_adjustment

        # 1. Determine currently active tickers
        current_active = self.repo.get_all(self.user_id, status="active")
        active_set: Set[str] = {t["ticker"].upper() for t in current_active}
        available_slots = max(0, max_active - len(active_set))

        if available_slots <= 0:
            logger.info(f"Universe at maximum capacity ({len(active_set)}/{max_active}). No admissions.")
            return []

        # 2. Build candidate pool
        candidates_to_check: Set[str] = set()
        if candidate_pool:
            candidates_to_check.update(c.upper() for c in candidate_pool)
        else:
            candidates_to_check.update(DEFAULT_CANDIDATE_POOL)
            # S&P ETF holdings if available
            try:
                spy_holdings = self.market.get_etf_holdings("SPY")
                for h in spy_holdings[:25]:
                    symbol = h.get("symbol") or h.get("ticker")
                    if symbol:
                        candidates_to_check.add(symbol.upper())
            except Exception as etfe:
                logger.debug(f"ETF holdings lookup skipped: {etfe}")

            # Dynamic AI ticker discovery
            try:
                from src.agents.skills.ticker_discovery.impl import ticker_discovery
                import json
                disc_res_str = await ticker_discovery(self.user_id, strategy="growth")
                disc_data = json.loads(disc_res_str)
                for item in disc_data.get("tickers", []):
                    t_sym = item.get("ticker")
                    if t_sym:
                        candidates_to_check.add(t_sym.upper())
            except Exception as de:
                logger.warning(f"Lifecycle dynamic ticker discovery skipped: {de}")

        # Exclude active tickers
        eligible_candidates = [c for c in candidates_to_check if c not in active_set]

        # 3. Evaluate candidates concurrently
        semaphore = asyncio.Semaphore(4)
        assessments: List[QualityAssessment] = []

        async def eval_one(sym: str) -> Optional[QualityAssessment]:
            async with semaphore:
                try:
                    res = await self.quality_gate.evaluate_ticker(sym)
                    return res
                except Exception as ex:
                    logger.warning(f"Error evaluating candidate {sym}: {ex}")
                    return None

        tasks = [eval_one(sym) for sym in eligible_candidates]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r and r.passed and r.overall_score >= effective_min_score:
                assessments.append(r)

        # 4. Sort by overall quality score descending
        assessments.sort(key=lambda a: a.overall_score, reverse=True)

        # 5. Admit top candidates up to available slots
        admitted = []
        for assessment in assessments[:available_slots]:
            ticker = assessment.ticker
            # Fetch company name, sector if available
            fin = self.market.get_financials(ticker) or {}
            company_name = str(fin.get("shortName") or fin.get("longName") or ticker)
            sector = str(fin.get("sector") or "")
            industry = str(fin.get("industry") or "")

            ok = self.repo.upsert(
                self.user_id,
                ticker,
                company_name=company_name,
                sector=sector,
                industry=industry,
                status="active"
            )

            if ok:
                log_reasoning = (
                    f"Auto-admitted by lifecycle service: Score {assessment.overall_score:.2f} "
                    f"(Fund: {assessment.fundamental_score:.1f}, Tech: {assessment.technical_score:.1f}, "
                    f"Liq: {assessment.liquidity_score:.1f}). Sector: {sector}"
                )
                self.repo.add_log(
                    self.user_id,
                    ticker,
                    "auto_admitted",
                    "UniverseLifecycleService",
                    reasoning=log_reasoning,
                    old_status="",
                    new_status="active",
                )
                admitted.append({
                    "ticker": ticker,
                    "company_name": company_name,
                    "sector": sector,
                    "score": assessment.overall_score,
                    "admitted_at": datetime.now(timezone.utc).isoformat(),
                })
                logger.info(f"Admitted {ticker} into universe with score {assessment.overall_score:.2f}")

        return admitted

    async def run_lifecycle_cycle(
        self,
        candidate_pool: Optional[List[str]] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Execute a complete universe lifecycle evolution cycle:
        1. Check if universe auto-refresh is enabled (unless force=True).
        2. Detect macro regime and adjust quality threshold.
        3. Review and evict degraded active tickers.
        4. Screen and admit top qualified candidates up to capacity.
        執行標的池生命週期演化循環：偵測宏觀環境、剔除劣質標的、補入優質標的。
        """
        try:
            enabled = self.settings.get_setting("universe_auto_refresh_enabled")
            if str(enabled).lower() in ("false", "0", "no") and not force:
                return {
                    "success": True,
                    "message": "Universe auto-refresh is disabled in settings.",
                    "regime": None,
                    "evicted": [],
                    "admitted": [],
                    "active_count": len(self.repo.get_all(self.user_id, status="active")),
                }
        except Exception as se:
            logger.warning(f"Failed to read universe_auto_refresh_enabled setting: {se}")

        # 1. Macro Regime Detection
        regime = await self.detect_macro_regime()

        # 2. Evict degraded tickers
        evicted = await self.review_and_evict_active_tickers()

        # 3. Screen & admit new candidates
        admitted = await self.screen_and_admit_candidates(
            candidate_pool=candidate_pool,
            regime_adjustment=regime.quality_score_adjustment
        )

        current_active = self.repo.get_all(self.user_id, status="active")

        summary_message = (
            f"Lifecycle run completed [{regime.regime}]. "
            f"Evicted: {len(evicted)}, Admitted: {len(admitted)}, Current active: {len(current_active)}."
        )
        logger.info(summary_message)

        return {
            "success": True,
            "message": summary_message,
            "regime": {
                "regime": regime.regime,
                "vix": regime.vix,
                "yield_curve_inverted": regime.yield_curve_inverted,
                "spy_above_200sma": regime.spy_above_200sma,
                "summary": regime.summary,
            },
            "evicted": evicted,
            "admitted": admitted,
            "active_count": len(current_active),
        }
