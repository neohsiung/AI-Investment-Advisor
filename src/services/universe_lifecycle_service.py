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
            is_pinned = bool(item.get("is_pinned", False))
            if is_pinned:
                logger.info(
                    "[PINNED] Skipping eviction check for user-designated active ticker %s.",
                    ticker,
                )
                continue

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

    async def evolve_candidate_pool(
        self,
        max_candidates: Optional[int] = None,
        candidate_pool: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically evolve the candidate pool to maintain top N (e.g. 30) reserve candidates.
        Performs competitive ranking ('汰弱留強'):
        1. Gathers candidate contenders (existing DB candidates, pyramid screener quant top N, ETF holdings, discovery).
        2. Evaluates contenders through Stage 1 & Stage 2 Quality Gate.
        3. Prunes weak candidates from DB (failed hard gates or pushed out of top N).
        4. Upserts and retains the top N strongest candidates in ticker_universe with status='candidate'.
        動態演化候選池（汰弱留強）：多維度評估候選股，淘汰落後者，收斂並保留 Top 30 儲備標的。
        """
        try:
            max_candidates = max_candidates or int(self.settings.get_setting("universe_max_candidate_tickers"))
        except Exception:
            max_candidates = 30

        current_active = self.repo.get_all(self.user_id, status="active")
        active_set: Set[str] = {t["ticker"].upper() for t in current_active}

        current_candidates = self.repo.get_all(self.user_id, status="candidate")
        current_cand_map: Dict[str, Dict[str, Any]] = {c["ticker"].upper(): c for c in current_candidates}

        # 1. Build Contenders Pool
        candidates_to_check: Set[str] = set()

        # A. Always include existing DB candidates
        candidates_to_check.update(current_cand_map.keys())

        # B. Custom candidate pool if passed
        if candidate_pool:
            candidates_to_check.update(c.upper() for c in candidate_pool if c)

        # C. Pyramid screener Stage 1 quant screen
        use_pyramid = True
        try:
            use_pyramid = str(self.settings.get_setting("pyramid_screener_enabled", True)).lower() in ("true", "1")
        except Exception:
            use_pyramid = True

        if use_pyramid:
            try:
                from src.services.pyramid_screener_service import PyramidScreenerService
                screener = PyramidScreenerService(
                    user_id=self.user_id,
                    market_data_service=self.market,
                    quality_gate=self.quality_gate,
                    ticker_repo=self.repo,
                )
                elites = await screener.run_stage1_quant_screen(top_n=max(40, max_candidates + 10))
                for cand in elites:
                    candidates_to_check.add(cand.ticker.upper())
                logger.info("UniverseLifecycle: Pyramid screener injected %d elite candidates", len(elites))
            except Exception as ps_err:
                logger.warning("UniverseLifecycle: Pyramid screener failed (%s); falling back to default pool", ps_err)

        # D. Default pool baseline
        candidates_to_check.update(DEFAULT_CANDIDATE_POOL)

        # E. S&P ETF holdings
        try:
            spy_holdings = self.market.get_etf_holdings("SPY")
            for h in spy_holdings[:25]:
                symbol = h.get("symbol") or h.get("ticker")
                if symbol:
                    candidates_to_check.add(symbol.upper())
        except Exception as etfe:
            logger.debug("ETF holdings lookup skipped: %s", etfe)

        # F. Dynamic AI ticker discovery
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
            logger.debug("Lifecycle dynamic ticker discovery skipped: %s", de)

        # Exclude active tickers
        eligible_candidates = [c for c in candidates_to_check if c not in active_set and c]

        # 2. Evaluate candidates concurrently
        semaphore = asyncio.Semaphore(4)

        async def eval_contender(sym: str) -> Optional[QualityAssessment]:
            async with semaphore:
                try:
                    return await self.quality_gate.evaluate_ticker(sym)
                except Exception as ex:
                    logger.warning("Error evaluating candidate contender %s: %s", sym, ex)
                    return None

        tasks = [eval_contender(sym) for sym in eligible_candidates]
        gathered = await asyncio.gather(*tasks)

        # Filter out hard gate failures (penny stocks, severely illiquid)
        valid_assessments: List[QualityAssessment] = []
        for a in gathered:
            if a and a.hard_gates_passed:
                valid_assessments.append(a)

        # Sort contenders by overall_score descending
        valid_assessments.sort(key=lambda x: x.overall_score, reverse=True)

        # 3. Select Top N Winners for Candidate Pool
        winners = valid_assessments[:max_candidates]
        winner_symbols = {w.ticker.upper() for w in winners}

        # 4. 汰弱 (Pruning of weak candidates from DB)
        pruned = []
        for sym, cand_item in current_cand_map.items():
            if sym not in winner_symbols:
                # Check if this candidate was designated/pinned by the user
                if cand_item.get("is_pinned"):
                    logger.info(
                        "[PINNED] Retaining user-designated candidate ticker %s despite ranking outside top %d",
                        sym, max_candidates
                    )
                    continue

                ok = self.repo.remove(self.user_id, sym, reason=f"Pruned from candidate pool: ranked outside top {max_candidates}")
                if ok:
                    self.repo.add_log(
                        self.user_id,
                        sym,
                        "candidate_pruned",
                        "UniverseLifecycleService",
                        reasoning=f"Pruned from candidate pool: ranked outside top {max_candidates}",
                        old_status="candidate",
                        new_status="removed",
                    )
                    pruned.append(sym)
                    logger.info("Pruned weak candidate %s from candidate pool", sym)

        # 5. 留強 (Retaining & Upserting Top N Candidates into DB)
        admitted_new = []
        retained = []
        for assessment in winners:
            ticker = assessment.ticker.upper()
            fin = self.market.get_financials(ticker) or {}
            company_name = str(fin.get("shortName") or fin.get("longName") or ticker)
            sector = str(fin.get("sector") or "")[:100]
            industry = str(fin.get("industry") or "")[:100]

            is_new = ticker not in current_cand_map
            is_pinned = bool(current_cand_map.get(ticker, {}).get("is_pinned", False))

            ok = self.repo.upsert(
                self.user_id,
                ticker,
                company_name=company_name,
                sector=sector,
                industry=industry,
                status="candidate",
                is_pinned=is_pinned,
            )
            if ok:
                if is_new:
                    self.repo.add_log(
                        self.user_id,
                        ticker,
                        "candidate_admitted",
                        "UniverseLifecycleService",
                        reasoning=f"Admitted to top {max_candidates} candidate pool with score {assessment.overall_score:.2f}",
                        old_status="",
                        new_status="candidate",
                    )
                    admitted_new.append({
                        "ticker": ticker,
                        "company_name": company_name,
                        "sector": sector,
                        "score": assessment.overall_score,
                    })
                else:
                    retained.append({
                        "ticker": ticker,
                        "company_name": company_name,
                        "sector": sector,
                        "score": assessment.overall_score,
                    })

        logger.info(
            "Candidate pool evolution complete: %d retained (New: %d, Retained: %d, Pruned: %d)",
            len(winners), len(admitted_new), len(retained), len(pruned)
        )

        return {
            "success": True,
            "max_capacity": max_candidates,
            "total_evaluated": len(valid_assessments),
            "candidate_count": len(winners),
            "admitted_new_count": len(admitted_new),
            "retained_count": len(retained),
            "pruned_count": len(pruned),
            "admitted_new": admitted_new,
            "retained": retained,
            "pruned": pruned,
            "top_candidates": [
                {
                    "ticker": w.ticker,
                    "score": w.overall_score,
                    "passed": w.passed,
                    "fundamental": w.fundamental_score,
                    "technical": w.technical_score,
                    "liquidity": w.liquidity_score,
                }
                for w in winners
            ],
        }

    async def evolve_active_pool(
        self,
        max_active: Optional[int] = None,
        rotation_hurdle: Optional[float] = None,
        max_rotations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Review and evolve active pool through competitive rotation (汰弱留強).
        Compares unpinned active tickers with top candidates from the candidate pool.
        If a top candidate outclasses the lowest unpinned active ticker by at least rotation_hurdle:
        1. Demotes the underperforming active ticker to 'candidate' (or 'removed' if score < eviction threshold).
        2. Promotes the top candidate to 'active'.
        User-designated (is_pinned=True) active tickers are 100% immune to rotation/eviction.
        活躍池動態汰弱留強：審查未鎖定之活躍股與候選股之品質利差，動態進行優勝劣汰輪動。
        """
        try:
            max_active = max_active or int(self.settings.get_setting("universe_max_active_tickers"))
        except Exception:
            max_active = 8

        try:
            rotation_hurdle = (
                rotation_hurdle
                if rotation_hurdle is not None
                else float(self.settings.get_setting("universe_rotation_hurdle"))
            )
        except Exception:
            rotation_hurdle = 1.5

        try:
            max_rotations = (
                max_rotations
                if max_rotations is not None
                else int(self.settings.get_setting("universe_max_rotations_per_cycle"))
            )
        except Exception:
            max_rotations = 2

        try:
            eviction_threshold = float(self.settings.get_setting("universe_eviction_threshold"))
        except Exception:
            eviction_threshold = 4.0

        current_active = self.repo.get_all(self.user_id, status="active")
        pinned_active = [t for t in current_active if t.get("is_pinned")]
        unpinned_active = [t for t in current_active if not t.get("is_pinned")]

        if not unpinned_active:
            logger.info(
                "UniverseLifecycle: All %d active tickers are user-designated (is_pinned=True). No active rotation eligible.",
                len(pinned_active),
            )
            return {
                "success": True,
                "rotations": [],
                "rotation_count": 0,
                "total_active": len(current_active),
                "pinned_active_count": len(pinned_active),
                "unpinned_active_count": 0,
                "message": "All active tickers are user-designated (pinned). No rotation eligible.",
            }

        # 1. Evaluate unpinned active tickers
        evaluated_unpinned = []
        for item in unpinned_active:
            sym = item["ticker"].upper()
            try:
                assessment = await self.quality_gate.evaluate_ticker(sym)
                evaluated_unpinned.append((item, assessment))
            except Exception as e:
                logger.warning("Error evaluating active ticker %s during active pool evolution: %s", sym, e)

        if not evaluated_unpinned:
            return {
                "success": True,
                "rotations": [],
                "rotation_count": 0,
                "total_active": len(current_active),
                "pinned_active_count": len(pinned_active),
                "unpinned_active_count": len(unpinned_active),
                "message": "No active tickers could be evaluated.",
            }

        # Sort unpinned active tickers ascending by overall score (weakest first)
        evaluated_unpinned.sort(key=lambda pair: pair[1].overall_score)

        # 2. Fetch and evaluate top candidates
        candidates = self.repo.get_all(self.user_id, status="candidate")
        cand_assessments: List[QualityAssessment] = []

        semaphore = asyncio.Semaphore(4)

        async def eval_cand(sym: str) -> Optional[QualityAssessment]:
            async with semaphore:
                try:
                    return await self.quality_gate.evaluate_ticker(sym)
                except Exception as ex:
                    logger.warning("Error evaluating candidate %s: %s", sym, ex)
                    return None

        tasks = [eval_cand(c["ticker"].upper()) for c in candidates]
        cand_results = await asyncio.gather(*tasks)
        for ca in cand_results:
            if ca and ca.hard_gates_passed and ca.passed:
                cand_assessments.append(ca)

        # Sort candidates descending by overall score (strongest first)
        cand_assessments.sort(key=lambda a: a.overall_score, reverse=True)

        # 3. Competitive Rotation (汰弱留強)
        rotations = []
        cand_idx = 0

        for active_item, active_assessment in evaluated_unpinned:
            if len(rotations) >= max_rotations:
                break
            if cand_idx >= len(cand_assessments):
                break

            top_candidate = cand_assessments[cand_idx]
            active_sym = active_item["ticker"].upper()
            cand_sym = top_candidate.ticker.upper()
            active_score = active_assessment.overall_score
            cand_score = top_candidate.overall_score

            # Check if candidate score outclasses active score by hurdle
            if (cand_score - active_score) >= rotation_hurdle:
                new_status = "removed" if active_score < eviction_threshold else "candidate"
                demote_reason = (
                    f"Rotated from active: Outclassed by candidate {cand_sym} "
                    f"(Score {active_score:.2f} vs {cand_score:.2f}, hurdle {rotation_hurdle:.2f})"
                )
                self.repo.upsert(self.user_id, active_sym, status=new_status)
                self.repo.add_log(
                    self.user_id,
                    active_sym,
                    "active_rotated_out",
                    "UniverseLifecycleService",
                    reasoning=demote_reason,
                    old_status="active",
                    new_status=new_status,
                )

                fin = self.market.get_financials(cand_sym) or {}
                company_name = str(fin.get("shortName") or fin.get("longName") or cand_sym)
                sector = str(fin.get("sector") or "")[:100]
                industry = str(fin.get("industry") or "")[:100]

                self.repo.upsert(
                    self.user_id,
                    cand_sym,
                    company_name=company_name,
                    sector=sector,
                    industry=industry,
                    status="active",
                )
                promote_reason = (
                    f"Promoted to active replacing {active_sym} "
                    f"(Score {cand_score:.2f} vs {active_score:.2f}, hurdle {rotation_hurdle:.2f})"
                )
                self.repo.add_log(
                    self.user_id,
                    cand_sym,
                    "active_rotated_in",
                    "UniverseLifecycleService",
                    reasoning=promote_reason,
                    old_status="candidate",
                    new_status="active",
                )

                rotations.append({
                    "demoted_ticker": active_sym,
                    "demoted_score": round(active_score, 2),
                    "demoted_to": new_status,
                    "promoted_ticker": cand_sym,
                    "promoted_score": round(cand_score, 2),
                    "score_delta": round(cand_score - active_score, 2),
                })
                logger.info(
                    "Competitive rotation: %s (score %.2f) -> %s; %s (score %.2f) -> active",
                    active_sym, active_score, new_status, cand_sym, cand_score
                )
                cand_idx += 1

        summary = (
            f"Active pool evolution complete: {len(rotations)} rotated "
            f"({len(pinned_active)} pinned protected, {len(unpinned_active)} unpinned reviewed)"
        )
        logger.info(summary)
        return {
            "success": True,
            "message": summary,
            "rotations": rotations,
            "rotation_count": len(rotations),
            "total_active": len(current_active),
            "pinned_active_count": len(pinned_active),
            "unpinned_active_count": len(unpinned_active),
        }

    async def screen_and_admit_candidates(
        self,
        candidate_pool: Optional[List[str]] = None,
        max_active: Optional[int] = None,
        min_quality_score: Optional[float] = None,
        regime_adjustment: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Screen candidates against the quality gate and admit top-scoring ones up to capacity.
        篩選市場候選標的，依照綜合品質評分由高至低擇優納入活躍自選池，直至額滿。
        """
        try:
            max_active = max_active or int(self.settings.get_setting("universe_max_active_tickers"))
        except Exception:
            max_active = 8

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
            logger.info("Active universe at maximum capacity (%d/%d). No admissions to active.", len(active_set), max_active)
            return []

        # 2. Build candidate pool
        candidates_to_check: Set[str] = set()
        if candidate_pool:
            candidates_to_check.update(c.upper() for c in candidate_pool)
        else:
            # Check DB candidates first
            db_candidates = self.repo.get_all(self.user_id, status="candidate")
            for c in db_candidates:
                candidates_to_check.add(c["ticker"].upper())

            # Check if pyramid screener is enabled
            use_pyramid = True
            try:
                use_pyramid = str(self.settings.get_setting("pyramid_screener_enabled", True)).lower() in ("true", "1")
            except Exception:
                use_pyramid = True

            if use_pyramid:
                try:
                    from src.services.pyramid_screener_service import PyramidScreenerService
                    screener = PyramidScreenerService(
                        user_id=self.user_id,
                        market_data_service=self.market,
                        quality_gate=self.quality_gate,
                        ticker_repo=self.repo,
                    )
                    elites = await screener.run_stage1_quant_screen(top_n=20)
                    for cand in elites:
                        candidates_to_check.add(cand.ticker.upper())
                except Exception as ps_err:
                    logger.warning("UniverseLifecycle: Pyramid screener failed (%s); falling back to default pool", ps_err)

            if not candidates_to_check:
                candidates_to_check.update(DEFAULT_CANDIDATE_POOL)

        eligible_candidates = [c for c in candidates_to_check if c not in active_set]

        # 3. Evaluate candidates concurrently
        semaphore = asyncio.Semaphore(4)
        assessments: List[QualityAssessment] = []

        async def eval_one(sym: str) -> Optional[QualityAssessment]:
            async with semaphore:
                try:
                    return await self.quality_gate.evaluate_ticker(sym)
                except Exception as ex:
                    logger.warning("Error evaluating candidate %s: %s", sym, ex)
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
            ticker = assessment.ticker.upper()
            fin = self.market.get_financials(ticker) or {}
            company_name = str(fin.get("shortName") or fin.get("longName") or ticker)
            sector = str(fin.get("sector") or "")[:100]
            industry = str(fin.get("industry") or "")[:100]

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
                    f"Auto-admitted to active: Score {assessment.overall_score:.2f} "
                    f"(Fund: {assessment.fundamental_score:.1f}, Tech: {assessment.technical_score:.1f}, "
                    f"Liq: {assessment.liquidity_score:.1f}). Sector: {sector}"
                )
                self.repo.add_log(
                    self.user_id,
                    ticker,
                    "auto_admitted",
                    "UniverseLifecycleService",
                    reasoning=log_reasoning,
                    old_status="candidate" if ticker in candidates_to_check else "",
                    new_status="active",
                )
                admitted.append({
                    "ticker": ticker,
                    "company_name": company_name,
                    "sector": sector,
                    "score": assessment.overall_score,
                    "admitted_at": datetime.now(timezone.utc).isoformat(),
                })
                logger.info("Admitted %s into active universe with score %.2f", ticker, assessment.overall_score)

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
        3. Review and evict degraded active tickers (< 4.0 or broken hard gates).
        4. Evolve candidate pool: maintain Top 30 reserve candidates (汰弱留強).
        5. Admit top qualified candidates to active up to capacity (e.g. 8).
        執行標的池生命週期演化循環：偵測宏觀環境、淘汰劣質活躍標的、汰弱留強擴充候選池、補入空缺活躍標的。
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
                    "candidate_count": len(self.repo.get_all(self.user_id, status="candidate")),
                }
        except Exception as se:
            logger.warning("Failed to read universe_auto_refresh_enabled setting: %s", se)

        try:
            max_active = int(self.settings.get_setting("universe_max_active_tickers"))
        except Exception:
            max_active = 8

        # 1. Macro Regime Detection
        regime = await self.detect_macro_regime()

        # 2. Evict degraded active tickers (< 4.0 or penny stock, unpinned only)
        evicted = await self.review_and_evict_active_tickers()

        # 3. Dynamic Candidate Pool Evolution (汰弱留強 -> Top 30, protecting pinned candidates)
        candidate_evolution = await self.evolve_candidate_pool(candidate_pool=candidate_pool)

        # 4. Dynamic Active Pool Competitive Rotation (汰弱留強 -> replace outclassed unpinned active with top candidate)
        active_evolution = await self.evolve_active_pool(max_active=max_active)

        # 5. Screen & admit new candidates to active pool if slots available
        admitted = await self.screen_and_admit_candidates(
            candidate_pool=candidate_pool,
            max_active=max_active,
            regime_adjustment=regime.quality_score_adjustment,
        )

        current_active = self.repo.get_all(self.user_id, status="active")
        current_candidates = self.repo.get_all(self.user_id, status="candidate")

        summary_message = (
            f"Lifecycle run completed [{regime.regime}]. "
            f"Active: {len(current_active)}/{max_active} (Evicted: {len(evicted)}, Rotated: {active_evolution.get('rotation_count', 0)}, Admitted: {len(admitted)}). "
            f"Candidates: {len(current_candidates)}/30 (Admitted: {candidate_evolution.get('admitted_new_count', 0)}, Pruned: {candidate_evolution.get('pruned_count', 0)})."
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
            "rotations": active_evolution.get("rotations", []),
            "active_evolution": active_evolution,
            "admitted": admitted,
            "candidate_evolution": candidate_evolution,
            "active_count": len(current_active),
            "candidate_count": len(current_candidates),
        }

