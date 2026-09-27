"""
Two-Stage Pyramid Screener Service
兩階段金字塔標的初篩器服務

Solves the universe expansion dilemma:
- Stage 1: Zero-cost, high-speed Python deterministic quant filter across 150+ large-cap
  and high-momentum US assets to eliminate penny stocks, illiquid names, and downtrends,
  producing a ranked Top N (e.g. Top 12) candidate elite.
- Stage 2: Deep multi-dimensional evaluation (financials, debt, margins, growth, quality gate)
  on only the Top N elite, preventing LLM token and API budget exhaustion.
第一階段純 Python 數值初篩收窄至 Top 12，第二階段深入品質把關，兼顧標的廣度與計算成本。
"""

import asyncio
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set

from src.config.owner import resolve_user_id
from src.repositories.ticker_universe_repository import TickerUniverseRepository
from src.services.market_data_service import MarketDataService
from src.services.quality_gate_service import QualityGateService, QualityAssessment
from src.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Broad pool of 160+ curated US large-cap leaders, high-momentum technology,
# financials, healthcare, and industrial blue-chips across S&P 100 and Nasdaq 100.
EXPANDED_UNIVERSE_POOL: List[str] = [
    # Mega-Cap Tech & Semis
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "ORCL", "ADBE",
    "CRM", "AMD", "QCOM", "TXN", "NOW", "AMAT", "LRCX", "PANW", "SNPS", "CDNS",
    "MU", "KLAC", "INTU", "APH", "MSI", "CRWD", "PLTR", "ARM", "ANET", "UBER",
    # Financials & Payments
    "JPM", "V", "MA", "BAC", "WFC", "MS", "GS", "BLK", "AXP", "C",
    "SPGI", "MCO", "CB", "MMC", "PGR", "ICE", "CME", "COIN", "HOOD",
    # Healthcare & Biotech
    "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "ISRG", "PFE",
    "AMGN", "BMY", "MDT", "ELV", "SYK", "REGN", "VRTX", "GILD", "BSX", "CI",
    # Consumer & Retail
    "WMT", "PG", "COST", "HD", "PEP", "KO", "MCD", "NKE", "DIS", "SBUX",
    "TGT", "LOW", "TJX", "BKNG", "ABNB", "MDLZ", "PM", "MO", "CMG", "LULU",
    # Industrials, Aerospace & Tech Hardware
    "CAT", "GE", "UNP", "HON", "RTX", "BA", "LMT", "DE", "ETN", "FDX",
    "UPS", "NSC", "CSX", "WM", "EMR", "PCAR", "GD", "TDG",
    # Energy, Materials & Utilities
    "XOM", "CVX", "COP", "SLB", "EOG", "LIN", "APD", "SHW", "FCX", "NEM",
    "NEE", "SO", "DUK", "CEG", "VST", "OKE", "KMI", "WMB",
    # Communication & Media
    "NFLX", "TMUS", "CMCSA", "VZ", "T", "SPOT",
    # High-Growth Tech & Cloud
    "SNOW", "DDOG", "MDB", "NET", "ZS", "SHOP", "MELI", "SE", "APP", "RDDT",
]


@dataclass
class Stage1Candidate:
    """Stage 1 quant evaluation result for a candidate ticker."""
    ticker: str
    price: float
    dollar_volume_m: float
    sma_50: float
    sma_200: float
    rsi: float
    momentum_20d: float
    trend_aligned: bool
    quant_score: float                     # 0.0 - 10.0 scale
    passed_filters: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PyramidScreenResult:
    """Complete results from the Two-Stage Pyramid Screen."""
    stage1_total_scanned: int
    stage1_candidates: List[Dict[str, Any]]
    stage2_approved: List[Dict[str, Any]]
    admitted_to_universe: List[str]
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PyramidScreenerService:
    """
    Two-Stage Pyramid Screener Engine.
    兩階段金字塔初篩器：Stage 1 純量化過濾，Stage 2 深度品質把關。
    """

    def __init__(
        self,
        user_id: str,
        market_data_service: Optional[MarketDataService] = None,
        quality_gate: Optional[QualityGateService] = None,
        ticker_repo: Optional[TickerUniverseRepository] = None,
    ):
        self.user_id = resolve_user_id(user_id)
        self.market = market_data_service or MarketDataService(user_id=self.user_id)
        self.quality_gate = quality_gate or QualityGateService(user_id=self.user_id, market_data_service=self.market)
        self.repo = ticker_repo or TickerUniverseRepository()
        self.settings = SettingsService(user_id=self.user_id)

    async def run_stage1_quant_screen(
        self,
        candidate_pool: Optional[List[str]] = None,
        top_n: Optional[int] = None,
    ) -> List[Stage1Candidate]:
        """
        Stage 1: High-speed deterministic quant screen.
        第一階段：純量化指標快速篩選與動量排序。
        """
        pool = candidate_pool or EXPANDED_UNIVERSE_POOL
        # Deduplicate and normalize
        unique_pool = list(dict.fromkeys(c.strip().upper() for c in pool if c.strip()))

        # Read configurable thresholds
        min_price = 5.0
        try:
            min_vol_m = float(self.settings.get_setting("pyramid_screener_min_dollar_volume_m", 10.0))
        except Exception:
            min_vol_m = 10.0

        try:
            top_limit = top_n or int(self.settings.get_setting("pyramid_screener_top_candidates", 12))
        except Exception:
            top_limit = 12

        candidates: List[Stage1Candidate] = []

        # Batch fetch price data
        try:
            price_map = await self.market.get_current_prices(unique_pool)
        except Exception as e:
            logger.warning("PyramidScreener: Error fetching batch prices: %s", e)
            price_map = {}

        for ticker in unique_pool:
            price = float(price_map.get(ticker) or 0.0)
            if price <= 0:
                continue

            # Fetch technical indicators
            tech = self.market.get_technical_indicators(ticker) or {}
            sma_dict = tech.get("sma", {}) if isinstance(tech.get("sma"), dict) else {}
            sma_50 = float(sma_dict.get("sma_50") or price)
            sma_200 = float(sma_dict.get("sma_200") or price)
            rsi = float(tech.get("rsi") or 50.0)

            # Daily volume & momentum estimation
            fin = self.market.get_financials(ticker) or {}
            avg_volume = float(fin.get("averageDailyVolume10Day") or fin.get("volume") or 1_000_000)
            dollar_vol_m = (avg_volume * price) / 1e6

            # 20-day momentum (price relative to sma_50)
            momentum_20d = ((price - sma_50) / sma_50 * 100.0) if sma_50 > 0 else 0.0

            reasons: List[str] = []
            passed = True

            # Filter 1: Penny stock / minimum price
            if price < min_price:
                passed = False
                reasons.append(f"Price ${price:.2f} < ${min_price:.2f}")

            # Filter 2: Liquidity / dollar volume
            if dollar_vol_m < min_vol_m:
                passed = False
                reasons.append(f"Dollar volume ${dollar_vol_m:.1f}M < ${min_vol_m:.1f}M")

            # Filter 3: Severe downtrend exclusion (price collapsed > 25% below 200 SMA)
            if sma_200 > 0 and price < (sma_200 * 0.75):
                passed = False
                reasons.append(f"Severe breakdown: Price ${price:.2f} < 75% of SMA200 (${sma_200:.2f})")

            # Filter 4: Extreme RSI exhaustion (> 85 or < 25)
            if rsi > 85.0 or rsi < 25.0:
                passed = False
                reasons.append(f"Extreme RSI condition: {rsi:.1f}")

            trend_aligned = (price >= sma_50 >= sma_200)

            # Quant Score Formulation (0.0 - 10.0 scale)
            # Factors: Trend alignment (3.0 pts), RSI sweet-spot (2.5 pts), Momentum (2.5 pts), Liquidity (2.0 pts)
            score = 0.0
            if trend_aligned:
                score += 3.0
            elif price >= sma_50:
                score += 1.8
            elif price >= sma_200:
                score += 1.0

            # RSI sweet spot (45 - 65)
            if 45.0 <= rsi <= 65.0:
                score += 2.5
            elif 35.0 <= rsi <= 75.0:
                score += 1.5
            else:
                score += 0.5

            # Momentum bonus
            if 2.0 <= momentum_20d <= 15.0:
                score += 2.5
            elif -2.0 <= momentum_20d < 2.0:
                score += 1.8
            elif momentum_20d > 15.0:
                score += 1.5
            else:
                score += 0.5

            # Liquidity bonus (> $50M daily is top tier)
            if dollar_vol_m >= 50.0:
                score += 2.0
            elif dollar_vol_m >= 20.0:
                score += 1.5
            else:
                score += 1.0

            quant_score = round(min(10.0, max(0.0, score)), 2)

            if passed:
                reasons.append(f"Quant score {quant_score:.2f} (Trend={trend_aligned}, RSI={rsi:.1f}, Vol=${dollar_vol_m:.1f}M)")

            candidates.append(
                Stage1Candidate(
                    ticker=ticker,
                    price=price,
                    dollar_volume_m=dollar_vol_m,
                    sma_50=sma_50,
                    sma_200=sma_200,
                    rsi=rsi,
                    momentum_20d=momentum_20d,
                    trend_aligned=trend_aligned,
                    quant_score=quant_score,
                    passed_filters=passed,
                    reasons=reasons,
                )
            )

        # Sort only passing candidates by quant_score descending
        passing_candidates = [c for c in candidates if c.passed_filters]
        passing_candidates.sort(key=lambda x: x.quant_score, reverse=True)

        return passing_candidates[:top_limit]

    async def run_full_pyramid_screen(
        self,
        candidate_pool: Optional[List[str]] = None,
        top_n: Optional[int] = None,
        auto_admit: bool = False,
    ) -> PyramidScreenResult:
        """
        Run the complete Two-Stage Pyramid Screen.
        Stage 1 (Quant Filter) -> Stage 2 (Deep Quality Gate) -> Optional Admission.
        """
        pool = candidate_pool or EXPANDED_UNIVERSE_POOL
        logger.info(
            "PyramidScreener: Starting Stage 1 quant screen on %d candidates for user %s",
            len(pool), self.user_id
        )

        stage1_elites = await self.run_stage1_quant_screen(candidate_pool=pool, top_n=top_n)
        logger.info("PyramidScreener: Stage 1 yielded %d elite candidates", len(stage1_elites))

        # Stage 2: Concurrent Deep Quality Gate Evaluation on Top N
        semaphore = asyncio.Semaphore(4)
        stage2_results: List[QualityAssessment] = []

        async def eval_gate(sym: str) -> Optional[QualityAssessment]:
            async with semaphore:
                try:
                    return await self.quality_gate.evaluate_ticker(sym)
                except Exception as ex:
                    logger.warning("PyramidScreener Stage 2 error evaluating %s: %s", sym, ex)
                    return None

        tasks = [eval_gate(cand.ticker) for cand in stage1_elites]
        gathered = await asyncio.gather(*tasks)

        for assessment in gathered:
            if assessment and assessment.passed:
                stage2_results.append(assessment)

        # Sort stage 2 approved by overall score descending
        stage2_results.sort(key=lambda a: a.overall_score, reverse=True)

        admitted_tickers: List[str] = []

        # Optional Admission to TickerUniverse
        if auto_admit and stage2_results:
            current_active = self.repo.get_all(self.user_id, status="active")
            active_set = {t["ticker"].upper() for t in current_active}

            for assessment in stage2_results:
                sym = assessment.ticker.upper()
                if sym in active_set:
                    continue

                fin = self.market.get_financials(sym) or {}
                company_name = str(fin.get("shortName") or fin.get("longName") or sym)
                sector = str(fin.get("sector") or "")
                industry = str(fin.get("industry") or "")

                ok = self.repo.upsert(
                    self.user_id,
                    sym,
                    company_name=company_name,
                    sector=sector,
                    industry=industry,
                    status="active",
                )
                if ok:
                    self.repo.add_log(
                        self.user_id,
                        sym,
                        "pyramid_admitted",
                        "PyramidScreenerService",
                        reasoning=(
                            f"Pyramid Screener Admitted: Overall Quality {assessment.overall_score:.2f}, "
                            f"Fund: {assessment.fundamental_score:.1f}, Tech: {assessment.technical_score:.1f}"
                        ),
                        old_status="",
                        new_status="active",
                    )
                    admitted_tickers.append(sym)
                    logger.info("PyramidScreener: Auto-admitted %s to universe", sym)

        return PyramidScreenResult(
            stage1_total_scanned=len(pool),
            stage1_candidates=[c.to_dict() for c in stage1_elites],
            stage2_approved=[a.to_dict() for a in stage2_results],
            admitted_to_universe=admitted_tickers,
        )
