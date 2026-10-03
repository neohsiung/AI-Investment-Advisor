"""
Ticker Universe Service
Business logic for user-specific persistent ticker pool management.
"""
import math
from typing import List, Dict, Any, Optional, Tuple
from src.repositories.ticker_universe_repository import (
    TickerUniverseRepository,
    UNIVERSE_UPDATABLE_FIELDS,
)
from src.services.portfolio_aggregator_service import PortfolioAggregatorService
from src.utils.logger import setup_logger
from src.config.owner import resolve_user_id

logger = setup_logger("TickerUniverseService")


class TickerUniverseService:
    """High-level service for ticker universe operations."""

    def __init__(self, user_id: str):
        self.user_id = resolve_user_id(user_id)
        self.repo = TickerUniverseRepository()
        self._settings = None

    @property
    def settings_service(self):
        """
        Lazily constructed so building this service stays free of DB work — the
        allocation optimizer is the only path that needs settings.
        延遲建立，讓本服務的建構不觸及資料庫。
        """
        if self._settings is None:
            from src.services.settings_service import SettingsService

            self._settings = SettingsService(user_id=self.user_id)
        return self._settings

    @property
    def quality_gate(self):
        """Lazily constructed quality gate service."""
        if not hasattr(self, "_quality_gate") or self._quality_gate is None:
            from src.services.quality_gate_service import QualityGateService
            self._quality_gate = QualityGateService(user_id=self.user_id)
        return self._quality_gate

    @property
    def lifecycle_service(self):
        """Lazily constructed universe lifecycle service."""
        if not hasattr(self, "_lifecycle_service") or self._lifecycle_service is None:
            from src.services.universe_lifecycle_service import UniverseLifecycleService
            self._lifecycle_service = UniverseLifecycleService(
                user_id=self.user_id,
                repo=self.repo,
                quality_gate=self.quality_gate,
            )
        return self._lifecycle_service

    @property
    def market_data_service(self):
        """Lazily constructed market data service."""
        if not hasattr(self, "_market_data") or self._market_data is None:
            try:
                from src.services.market_data_service import MarketDataService
                self._market_data = MarketDataService(user_id=self.user_id)
            except Exception as e:
                logger.debug(f"Failed to instantiate MarketDataService: {e}")
                self._market_data = None
        return self._market_data

    def calculate_ticker_returns(self, ticker: str, days: int = 60) -> List[float]:
        """
        Calculate daily percentage returns for a ticker over the specified window.
        Returns: r_t = (p_t - p_{t-1}) / p_{t-1}.
        """
        try:
            mds = getattr(self, "market_data_service", None)
            if mds:
                ohlcv = mds.get_ohlcv(ticker, days=days)
                closes = ohlcv.get("close", []) if ohlcv else []
                if closes and len(closes) >= 5:
                    import pandas as pd
                    series = pd.Series(closes, dtype=float)
                    daily_returns = series.pct_change().dropna().tolist()
                    return [float(r) for r in daily_returns if pd.notna(r)]
        except Exception as e:
            logger.debug(f"Could not compute daily returns for {ticker}: {e}")
        return []

    def calculate_ticker_volatility(self, ticker: str, days: int = 60, default_vol: float = 0.25) -> float:
        """
        Calculate 60-day annualized return volatility:
        sigma_i = std(daily_returns_60d) * sqrt(252)
        """
        try:
            rets = self.calculate_ticker_returns(ticker, days=days)
            if len(rets) >= 10:
                import numpy as np
                std = float(np.std(rets, ddof=1))
                if std > 0:
                    annualized_vol = std * math.sqrt(252)
                    return round(annualized_vol, 4)
        except Exception as e:
            logger.debug(f"Could not compute historical volatility for {ticker}: {e}")
        return default_vol

    def calculate_ticker_beta(
        self,
        ticker: str,
        spy_returns: Optional[List[float]] = None,
        days: int = 60,
        default_beta: float = 1.0,
    ) -> float:
        """
        Calculate 60-day market beta against S&P 500 (SPY):
        beta_i = Cov(r_i, r_spy) / Var(r_spy)
        """
        try:
            if spy_returns is None:
                spy_returns = self.calculate_ticker_returns("SPY", days=days)

            r_ticker = self.calculate_ticker_returns(ticker, days=days)
            if len(r_ticker) >= 10 and len(spy_returns) >= 10:
                import numpy as np
                min_len = min(len(r_ticker), len(spy_returns))
                y = np.array(r_ticker[-min_len:], dtype=float)
                x = np.array(spy_returns[-min_len:], dtype=float)
                var_x = float(np.var(x, ddof=1))
                if var_x > 1e-7:
                    cov_xy = float(np.cov(y, x, ddof=1)[0, 1])
                    beta = cov_xy / var_x
                    return round(max(0.1, min(3.0, beta)), 4)
        except Exception as e:
            logger.debug(f"Could not compute market beta for {ticker}: {e}")
        return default_beta

    def build_correlation_clusters(
        self,
        tickers: List[str],
        ticker_returns_map: Optional[Dict[str, List[float]]] = None,
        threshold: float = 0.70,
        days: int = 60,
    ) -> Tuple[Dict[str, Dict[str, float]], List[List[str]]]:
        """
        Build Pearson correlation matrix and identify high-correlation clusters (connected components).
        Two tickers belong to the same cluster if Pearson correlation >= threshold.
        """
        if not tickers:
            return {}, []

        if ticker_returns_map is None:
            ticker_returns_map = {t: self.calculate_ticker_returns(t, days=days) for t in tickers}

        import numpy as np
        corr_matrix: Dict[str, Dict[str, float]] = {t: {t: 1.0} for t in tickers}
        adj: Dict[str, set] = {t: set() for t in tickers}

        for i in range(len(tickers)):
            t_i = tickers[i]
            r_i = ticker_returns_map.get(t_i, [])
            for j in range(i + 1, len(tickers)):
                t_j = tickers[j]
                r_j = ticker_returns_map.get(t_j, [])
                corr = 0.40  # Default moderate correlation if insufficient historical data
                if len(r_i) >= 10 and len(r_j) >= 10:
                    min_len = min(len(r_i), len(r_j))
                    arr_i = np.array(r_i[-min_len:], dtype=float)
                    arr_j = np.array(r_j[-min_len:], dtype=float)
                    std_i = float(np.std(arr_i, ddof=1))
                    std_j = float(np.std(arr_j, ddof=1))
                    if std_i > 1e-6 and std_j > 1e-6:
                        c = float(np.corrcoef(arr_i, arr_j)[0, 1])
                        if not np.isnan(c):
                            corr = c

                corr = round(max(-1.0, min(1.0, corr)), 4)
                corr_matrix[t_i][t_j] = corr
                corr_matrix.setdefault(t_j, {})[t_i] = corr

                if corr >= threshold:
                    adj[t_i].add(t_j)
                    adj[t_j].add(t_i)

        visited = set()
        clusters: List[List[str]] = []
        for t in tickers:
            if t not in visited:
                comp = []
                queue = [t]
                visited.add(t)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in sorted(adj.get(curr, [])):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                comp.sort()
                clusters.append(comp)

        clusters.sort(key=lambda c: (-len(c), c[0] if c else ""))
        return corr_matrix, clusters

    def apply_cluster_caps(
        self,
        weights: Dict[str, float],
        clusters: List[List[str]],
        cluster_cap: float = 0.30,
    ) -> Dict[str, float]:
        """
        Cap total weight of any multi-ticker high-correlation cluster at cluster_cap.
        If sum_{t in cluster} w_t > cluster_cap, scale all cluster members down proportionally.
        """
        capped_weights = dict(weights)
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            cluster_sum = sum(capped_weights.get(t, 0.0) for t in cluster)
            if cluster_sum > cluster_cap and cluster_sum > 0:
                ratio = cluster_cap / cluster_sum
                logger.info(
                    "High-correlation cluster %s total weight (%.1f%%) exceeds cluster cap (%.1f%%). "
                    "Scaling down by factor %.3f",
                    cluster,
                    cluster_sum * 100.0,
                    cluster_cap * 100.0,
                    ratio,
                )
                for t in cluster:
                    if t in capped_weights:
                        capped_weights[t] = capped_weights[t] * ratio
        return capped_weights

    async def evaluate_ticker_quality(self, ticker: str) -> Dict[str, Any]:
        """Evaluate a ticker against the quality gate."""
        assessment = await self.quality_gate.evaluate_ticker(ticker)
        return assessment.to_dict()

    async def add_ticker_with_quality_gate(
        self,
        ticker: str,
        company_name: str = "",
        sector: str = "",
        industry: str = "",
        bypass_quality_check: bool = False,
        is_pinned: bool = True,
    ) -> Dict[str, Any]:
        """
        Add a ticker to the universe after verifying quality criteria.
        加入標的前強制審查品質（除非明確 bypass）。手動加入預設設為用戶指定標的（is_pinned=True）。
        """
        ticker = ticker.upper().strip()
        if not bypass_quality_check:
            assessment = await self.quality_gate.evaluate_ticker(ticker)
            if not assessment.passed:
                reason_summary = "; ".join(assessment.reasons) or "Did not meet quality thresholds"
                return {
                    "success": False,
                    "message": f"Quality Gate Rejected: {ticker} failed criteria: {reason_summary}",
                    "assessment": assessment.to_dict(),
                }
        return self.add_ticker(ticker, company_name, sector, industry, is_pinned=is_pinned)

    async def run_lifecycle_evolution(
        self,
        candidate_pool: Optional[List[str]] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Run a full cycle of universe lifecycle evolution.
        執行標的池生命週期演化循環。
        """
        return await self.lifecycle_service.run_lifecycle_cycle(candidate_pool=candidate_pool, force=force)

    async def evolve_candidates(
        self,
        max_candidates: Optional[int] = None,
        candidate_pool: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Evolve candidate pool through competitive ranking (汰弱留強).
        執行候選池動態演化（汰弱留強），收斂並維護 Top N 儲備標的。
        """
        return await self.lifecycle_service.evolve_candidate_pool(
            max_candidates=max_candidates,
            candidate_pool=candidate_pool
        )

    async def evolve_active(
        self,
        max_active: Optional[int] = None,
        rotation_hurdle: Optional[float] = None,
        max_rotations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Evolve active pool through competitive rotation (汰弱留強).
        執行活躍池動態汰弱留強：未鎖定之落後活躍標的與候選池強者競爭輪替。
        """
        return await self.lifecycle_service.evolve_active_pool(
            max_active=max_active,
            rotation_hurdle=rotation_hurdle,
            max_rotations=max_rotations,
        )

    async def run_pyramid_screen(
        self,
        candidate_pool: Optional[List[str]] = None,
        top_n: Optional[int] = None,
        auto_admit: bool = False,
    ) -> Dict[str, Any]:
        """
        Run two-stage pyramid screener.
        執行兩階段金字塔初篩器。
        """
        from src.services.pyramid_screener_service import PyramidScreenerService
        screener = PyramidScreenerService(
            user_id=self.user_id,
            quality_gate=self.quality_gate,
            ticker_repo=self.repo,
        )
        res = await screener.run_full_pyramid_screen(
            candidate_pool=candidate_pool,
            top_n=top_n,
            auto_admit=auto_admit,
        )
        return res.to_dict()

    # ── Universe Management ──

    def get_universe(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get ticker universe, optionally filtered by status."""
        return self.repo.get_all(self.user_id, status)

    def get_by_ticker(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get a single ticker entry."""
        return self.repo.get_by_ticker(self.user_id, ticker)

    def add_ticker(self, ticker: str, company_name: str = "",
                   sector: str = "", industry: str = "",
                   is_pinned: bool = True) -> Dict[str, Any]:
        """Add a new ticker to the universe (or reactivate if removed). Defaults to user-designated (is_pinned=True)."""
        ticker = ticker.upper()
        existing = self.repo.get_by_ticker(self.user_id, ticker)
        if existing:
            if existing["status"] == "removed":
                # Reactivate
                ok = self.repo.upsert(self.user_id, ticker,
                                      company_name=company_name,
                                      sector=sector, industry=industry,
                                      status="active",
                                      is_pinned=is_pinned)
                self.repo.add_log(self.user_id, ticker, "upgraded",
                                  "user", "Reactivated from removed",
                                  "removed", "active")
                return {"success": ok, "message": f"{ticker} reactivated" if ok else "Failed"}
            # If already in universe, ensure pin status is preserved or updated
            if is_pinned and not existing.get("is_pinned"):
                self.repo.set_pin(self.user_id, ticker, True)
            return {"success": True, "message": f"{ticker} already in universe"}
        ok = self.repo.upsert(self.user_id, ticker,
                              company_name=company_name,
                              sector=sector, industry=industry,
                              status="active",
                              is_pinned=is_pinned)
        self.repo.add_log(self.user_id, ticker, "added",
                          "user", "Manually added (user-designated)", "", "active")
        return {"success": ok, "message": f"{ticker} added" if ok else "Failed"}

    def set_ticker_pin(self, ticker: str, is_pinned: bool) -> Dict[str, Any]:
        """Set user-designated pin status for a ticker."""
        ticker = ticker.upper()
        ok = self.repo.set_pin(self.user_id, ticker, is_pinned)
        msg = f"{ticker} {'pinned (user-designated, immune to rotation/eviction)' if is_pinned else 'unpinned (eligible for dynamic rotation)'}"
        return {"success": ok, "message": msg if ok else f"Failed to update pin status for {ticker}"}

    def update_ticker(self, ticker: str, **kwargs) -> Dict[str, Any]:
        """Update ticker metadata (company_name, sector, industry, status)."""
        # Same allowlist the repository enforces, imported rather than
        # restated — two copies of a security boundary drift apart quietly.
        # 直接引用 repository 的白名單，不再各留一份副本。
        safe = {k: v for k, v in kwargs.items() if k in UNIVERSE_UPDATABLE_FIELDS}
        if not safe:
            return {"success": False, "message": "No valid fields to update"}
        ticker = ticker.upper()
        if "status" in safe:
            old = self.repo.get_by_ticker(self.user_id, ticker)
            old_status = old["status"] if old else ""
            self.repo.add_log(self.user_id, ticker, "status_change",
                              "user", f"Status: {old_status} → {safe['status']}",
                              old_status, safe["status"])
        ok = self.repo.upsert(self.user_id, ticker, **safe)
        return {"success": ok, "message": f"{ticker} updated" if ok else "Failed"}

    def remove_ticker(self, ticker: str, reason: str = "") -> Dict[str, Any]:
        """Soft-delete a ticker from the universe."""
        ticker = ticker.upper()
        ok = self.repo.remove(self.user_id, ticker, reason)
        if ok:
            self.repo.add_log(self.user_id, ticker, "removed",
                              "user", reason or "User removed", "active", "removed")
        return {"success": ok, "message": f"{ticker} removed" if ok else "Failed"}

    # ── Research ──

    def get_research(self, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get research records for a ticker."""
        return self.repo.get_research(self.user_id, ticker, limit)

    def submit_research(self, ticker: str, agent_name: str, research_type: str,
                        confidence_score: float, **kwargs) -> Dict[str, Any]:
        """Submit a research record from an agent."""
        ticker = ticker.upper()
        ok = self.repo.add_research(
            self.user_id, ticker, agent_name, research_type,
            confidence_score,
            target_weight=kwargs.get("target_weight"),
            expected_return=kwargs.get("expected_return"),
            risk_score=kwargs.get("risk_score"),
            thesis=kwargs.get("thesis", ""),
            risks=kwargs.get("risks"),
            data_sources=kwargs.get("data_sources"),
            raw_analysis=kwargs.get("raw_analysis"),
        )
        return {"success": ok, "message": f"Research submitted for {ticker}" if ok else "Failed"}

    # ── Target Allocations ──

    def get_targets(self) -> List[Dict[str, Any]]:
        """Get current target allocations."""
        return self.repo.get_target_allocations(self.user_id)

    def optimize_allocations(self) -> Dict[str, Any]:
        """
        Recalculate target allocations using confidence-weighted optimization.
        Implements risk-parity adjusted confidence weighting with portfolio volatility targeting:
          Score_i = c_i × (1 + μ_i)
          Score_adj = Score_i / max(σ_i, 0.10)
          w_i_raw = Score_adj / Σ(Score_adj)

        Constraints:
          - Min position: 3% (alloc_min_position)
          - Max position: 20% (alloc_max_position)
          - Sector cap: 40% (alloc_sector_cap)
          - Target portfolio volatility scaling: if σ_p > σ_target, scale equity down and retain difference as cash
        """
        active = self.repo.get_all(self.user_id, status="active")
        if not active:
            return {"success": False, "message": "No active tickers in universe", "targets": []}

        # Gather latest research confidence, returns, historical volatility, and beta for each ticker
        spy_returns = self.calculate_ticker_returns("SPY", days=60)
        returns_map: Dict[str, List[float]] = {}
        ticker_scores = {}
        for t in active:
            ticker = t["ticker"]
            research = self.repo.get_research(self.user_id, ticker, limit=5)
            rets = self.calculate_ticker_returns(ticker, days=60)
            returns_map[ticker] = rets

            # Volatility (60-day annualized)
            vol = t.get("volatility_60d") or t.get("volatility")
            if vol is None:
                vol = self.calculate_ticker_volatility(ticker, days=60, default_vol=0.25)

            # Beta (60-day against SPY)
            beta = t.get("beta_60d") or t.get("beta")
            if beta is None:
                beta = self.calculate_ticker_beta(ticker, spy_returns=spy_returns, days=60, default_beta=1.0)

            if research:
                scores = [float(r["confidence_score"]) for r in research if r.get("confidence_score")]
                ticker_scores[ticker] = {
                    "confidence": max(scores) if scores else 0.5,
                    "expected_return": float(max(
                        (r.get("expected_return") or 0.0) for r in research
                    )) or 0.05,
                    "volatility": float(vol) if vol and float(vol) > 0 else 0.25,
                    "beta": float(beta) if beta and float(beta) > 0 else 1.0,
                    "sector": t.get("sector", ""),
                }
            else:
                ticker_scores[ticker] = {
                    "confidence": 0.5,
                    "expected_return": 0.05,
                    "volatility": float(vol) if vol and float(vol) > 0 else 0.25,
                    "beta": float(beta) if beta and float(beta) > 0 else 1.0,
                    "sector": t.get("sector", ""),
                }

        # Risk-parity adjusted confidence weight:
        # Score_adj = (confidence_boost * (1 + μ_i)) / max(σ_i, 0.10)
        numerator = {}
        total = 0.0
        for ticker, info in ticker_scores.items():
            confidence_boost = 1.0 if info["confidence"] >= 0.7 else (0.5 + info["confidence"])
            base_score = confidence_boost * (1.0 + info["expected_return"])
            vol = max(info.get("volatility", 0.25), 0.10)
            score_adj = base_score / vol
            numerator[ticker] = score_adj
            total += score_adj

        if total == 0:
            return {"success": False, "message": "All confidence scores are zero", "targets": []}

        # Initial unconstrained weights
        raw_weights = {}
        sector_weights = {}
        for ticker, num in numerator.items():
            raw_w = num / total
            raw_weights[ticker] = raw_w
            sector = ticker_scores[ticker]["sector"]
            sector_weights[sector] = sector_weights.get(sector, 0.0) + raw_w

        MIN_POS = float(self.settings_service.get_setting("alloc_min_position"))
        MAX_POS = float(self.settings_service.get_setting("alloc_max_position"))
        SECTOR_CAP = float(self.settings_service.get_setting("alloc_sector_cap"))
        CLUSTER_CAP = float(self.settings_service.get_setting("alloc_cluster_cap", 0.30))
        CORR_THRESH = float(self.settings_service.get_setting("alloc_correlation_cluster_threshold", 0.70))
        TARGET_BETA = float(self.settings_service.get_setting("alloc_target_beta", 0.90))
        TARGET_SUM = float(self.settings_service.get_setting("alloc_target_sum"))
        MAX_HOLDINGS = int(self.settings_service.get_setting("alloc_max_holdings", 10))
        TARGET_VOLATILITY = float(self.settings_service.get_setting("alloc_target_volatility", 0.14))

        if MIN_POS > MAX_POS:
            logger.warning(
                "alloc_min_position (%.3f) exceeds alloc_max_position (%.3f); "
                "falling back to the schema defaults for this run.",
                MIN_POS, MAX_POS,
            )
            from src.config.settings_schema import schema_default
            MIN_POS = float(schema_default("alloc_min_position"))
            MAX_POS = float(schema_default("alloc_max_position"))

        # Portfolio concentration: Top-K conviction selection to prevent fragmentation
        if MAX_HOLDINGS > 0 and len(raw_weights) > MAX_HOLDINGS:
            sorted_by_conviction = sorted(raw_weights.keys(), key=lambda t: raw_weights[t], reverse=True)
            top_tickers = set(sorted_by_conviction[:MAX_HOLDINGS])
            evicted_tickers = [t for t in sorted_by_conviction if t not in top_tickers]
            logger.info(
                "Concentrating allocations: keeping Top %d tickers (%s), excluded %d lower-ranked (%s)",
                MAX_HOLDINGS,
                ", ".join(sorted_by_conviction[:MAX_HOLDINGS]),
                len(evicted_tickers),
                ", ".join(evicted_tickers),
            )
            raw_weights = {t: raw_weights[t] for t in top_tickers}
            sub_total = sum(raw_weights.values())
            if sub_total > 0:
                raw_weights = {t: w / sub_total for t, w in raw_weights.items()}

            sector_weights = {}
            for ticker, raw_w in raw_weights.items():
                sec = ticker_scores[ticker]["sector"]
                sector_weights[sec] = sector_weights.get(sec, 0.0) + raw_w

        for ticker in raw_weights:
            raw_weights[ticker] = max(MIN_POS, min(MAX_POS, raw_weights[ticker]))

        # Sector concentration: cap at SECTOR_CAP
        sector_capped = dict(raw_weights)
        for ticker in raw_weights:
            sector = ticker_scores[ticker]["sector"]
            if sector and sector_weights.get(sector, 0) > SECTOR_CAP:
                ratio = SECTOR_CAP / sector_weights[sector]
                sector_capped[ticker] = raw_weights[ticker] * ratio

        # M2: High-Correlation Clustering & Cluster Cap
        corr_matrix, clusters = self.build_correlation_clusters(
            list(sector_capped.keys()),
            ticker_returns_map=returns_map,
            threshold=CORR_THRESH,
        )
        cluster_capped = self.apply_cluster_caps(
            sector_capped,
            clusters,
            cluster_cap=CLUSTER_CAP,
        )

        # Normalize preliminary weights to sum to 1.0 to assess portfolio annualized volatility & beta
        actual = sum(cluster_capped.values())
        if actual <= 0:
            return {"success": False, "message": "Failed to compute valid allocation weights", "targets": []}

        prelim_weights = {ticker: w / actual for ticker, w in cluster_capped.items()}

        # Estimate portfolio annualized volatility:
        # sigma_p = sqrt(sum_i (w_i * sigma_i)^2 + 2 * sum_{i < j} w_i * w_j * rho_ij * sigma_i * sigma_j)
        rho_default = 0.40
        variance_p = 0.0
        portfolio_tickers = list(prelim_weights.keys())
        for i, t_i in enumerate(portfolio_tickers):
            w_i = prelim_weights[t_i]
            v_i = ticker_scores[t_i].get("volatility", 0.25)
            variance_p += (w_i * v_i) ** 2
            for j in range(i + 1, len(portfolio_tickers)):
                t_j = portfolio_tickers[j]
                w_j = prelim_weights[t_j]
                v_j = ticker_scores[t_j].get("volatility", 0.25)
                pair_corr = corr_matrix.get(t_i, {}).get(t_j, rho_default)
                variance_p += 2.0 * w_i * w_j * pair_corr * v_i * v_j

        portfolio_volatility = math.sqrt(max(0.0, variance_p))

        # Target Volatility Scaling:
        vol_scale = 1.0
        if TARGET_VOLATILITY > 0 and portfolio_volatility > TARGET_VOLATILITY:
            vol_scale = min(1.0, TARGET_VOLATILITY / portfolio_volatility)
            logger.info(
                "Portfolio projected volatility (%.1f%%) exceeds target (%.1f%%). "
                "Applying volatility scaling factor: %.3f",
                portfolio_volatility * 100.0,
                TARGET_VOLATILITY * 100.0,
                vol_scale,
            )

        # M2: Estimate portfolio weighted market beta:
        portfolio_beta = sum(
            prelim_weights[t] * ticker_scores[t].get("beta", 1.0)
            for t in portfolio_tickers
        )

        # Target Beta Scaling:
        beta_scale = 1.0
        if TARGET_BETA > 0 and portfolio_beta > TARGET_BETA:
            beta_scale = min(1.0, TARGET_BETA / portfolio_beta)
            logger.info(
                "Portfolio projected market beta (%.2f) exceeds target (%.2f). "
                "Applying beta scaling factor: %.3f",
                portfolio_beta,
                TARGET_BETA,
                beta_scale,
            )

        # Effective risk scale factor (dual constraint: volatility & beta)
        effective_scale = min(vol_scale, beta_scale)
        effective_target_sum = TARGET_SUM * effective_scale

        # Map cluster IDs for multi-ticker clusters
        ticker_cluster_map = {}
        for idx, cluster in enumerate(clusters):
            if len(cluster) > 1:
                cid = f"cluster_{idx}"
                for t in cluster:
                    ticker_cluster_map[t] = cid

        # Normalize to effective_target_sum with strict ceiling of MAX_POS
        targets = []
        self.repo.clear_targets(self.user_id)
        for ticker, w in prelim_weights.items():
            raw_target_w = w * effective_target_sum
            norm_w = min(MAX_POS, round(raw_target_w, 4))
            info = ticker_scores[ticker]
            self.repo.upsert_target(
                self.user_id, ticker,
                target_weight=round(norm_w, 4),
                confidence_score=round(info["confidence"], 4),
                expected_return=round(info["expected_return"], 6),
                min_weight=MIN_POS,
                max_weight=MAX_POS,
            )
            targets.append({
                "ticker": ticker,
                "target_weight": round(norm_w, 4),
                "confidence_score": round(info["confidence"], 4),
                "expected_return": round(info["expected_return"], 6),
                "volatility_60d": round(info["volatility"], 4),
                "beta_60d": round(info.get("beta", 1.0), 4),
                "cluster_id": ticker_cluster_map.get(ticker),
            })

        self.repo.add_log(
            self.user_id, "ALL", "optimized",
            "system",
            f"Re-optimized {len(targets)} targets (risk-parity, port_vol {portfolio_volatility:.1%}, port_beta {portfolio_beta:.2f}, scale {effective_scale:.2f})"
        )
        return {
            "success": True,
            "message": f"Optimized {len(targets)} allocations",
            "targets": targets,
            "portfolio_volatility": round(portfolio_volatility, 4),
            "target_volatility": round(TARGET_VOLATILITY, 4),
            "volatility_scale_factor": round(vol_scale, 4),
            "portfolio_beta": round(portfolio_beta, 4),
            "target_beta": round(TARGET_BETA, 4),
            "beta_scale_factor": round(beta_scale, 4),
            "effective_scale_factor": round(effective_scale, 4),
            "correlation_clusters": clusters,
            "effective_target_sum": round(effective_target_sum, 4),
        }

    # ── Audit Logs ──

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get audit logs for the user."""
        return self.repo.get_logs(self.user_id, limit)

    # ── Migration ──

    async def migrate_from_holdings(self) -> Dict[str, Any]:
        """Migrate existing portfolio holdings into ticker_universe."""
        try:
            aggregator = PortfolioAggregatorService(user_id=self.user_id)
            portfolio = await aggregator.get_aggregated_portfolio()
            positions = portfolio.get("positions", [])
            holdings = []
            for p in positions:
                sym = getattr(p, "symbol", None) or (p.get("symbol", "") if isinstance(p, dict) else "")
                c_name = getattr(p, "company_name", getattr(p, "name", None)) or (p.get("company_name", p.get("name", "")) if isinstance(p, dict) else "")
                sec = getattr(p, "sector", None) or (p.get("sector", "") if isinstance(p, dict) else "")
                qty = getattr(p, "quantity", None) or (p.get("quantity", 0) if isinstance(p, dict) else 0)
                holdings.append({
                    "ticker": sym,
                    "company_name": c_name,
                    "sector": sec,
                    "quantity": qty,
                })
            count = self.repo.migrate_holdings_to_universe(self.user_id, holdings)
            return {"success": True, "count": count, "message": f"Migrated {count} holdings"}
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return {"success": False, "count": 0, "message": str(e)}