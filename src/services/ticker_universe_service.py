"""
Ticker Universe Service
Business logic for user-specific persistent ticker pool management.
"""
from typing import List, Dict, Any, Optional
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
    ) -> Dict[str, Any]:
        """
        Add a ticker to the universe after verifying quality criteria.
        加入標的前強制審查品質（除非明確 bypass）。
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
        return self.add_ticker(ticker, company_name, sector, industry)

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

    # ── Universe Management ──

    def get_universe(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get ticker universe, optionally filtered by status."""
        return self.repo.get_all(self.user_id, status)

    def get_by_ticker(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get a single ticker entry."""
        return self.repo.get_by_ticker(self.user_id, ticker)

    def add_ticker(self, ticker: str, company_name: str = "",
                   sector: str = "", industry: str = "") -> Dict[str, Any]:
        """Add a new ticker to the universe (or reactivate if removed)."""
        ticker = ticker.upper()
        existing = self.repo.get_by_ticker(self.user_id, ticker)
        if existing:
            if existing["status"] == "removed":
                # Reactivate
                ok = self.repo.upsert(self.user_id, ticker,
                                      company_name=company_name,
                                      sector=sector, industry=industry,
                                      status="active")
                self.repo.add_log(self.user_id, ticker, "upgraded",
                                  "user", "Reactivated from removed",
                                  "removed", "active")
                return {"success": ok, "message": f"{ticker} reactivated" if ok else "Failed"}
            return {"success": True, "message": f"{ticker} already in universe"}
        ok = self.repo.upsert(self.user_id, ticker,
                              company_name=company_name,
                              sector=sector, industry=industry,
                              status="active")
        self.repo.add_log(self.user_id, ticker, "added",
                          "user", "Manually added", "", "active")
        return {"success": ok, "message": f"{ticker} added" if ok else "Failed"}

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
        Implements risk-parity adjusted confidence weighting:
          w_i = (c_i × (1 + μ_i) / σ_i) / Σ(c_j × (1 + μ_j) / σ_j)

        Constraints:
          - Min position: 3%
          - Max position: 25%
          - Sector cap: 40%
          - Cash buffer implied: targets sum to ≤95%
        """
        active = self.repo.get_all(self.user_id, status="active")
        if not active:
            return {"success": False, "message": "No active tickers in universe", "targets": []}

        # Gather latest research confidence for each ticker
        ticker_scores = {}
        for t in active:
            ticker = t["ticker"]
            research = self.repo.get_research(self.user_id, ticker, limit=5)
            if research:
                scores = [float(r["confidence_score"]) for r in research if r.get("confidence_score")]
                ticker_scores[ticker] = {
                    "confidence": max(scores) if scores else 0.5,
                    "expected_return": float(max(
                        (r.get("expected_return") or 0.0) for r in research
                    )) or 0.05,
                    "sector": t.get("sector", ""),
                }
            else:
                ticker_scores[ticker] = {
                    "confidence": 0.5,
                    "expected_return": 0.05,
                    "sector": t.get("sector", ""),
                }

        # Risk-parity adjusted confidence weight
        # w_i_raw = c_i × (1 + μ_i)  (volatility-adjusted via confidence dampening on high-vol names)
        numerator = {}
        total = 0.0
        for ticker, info in ticker_scores.items():
            # Adjust: high confidence (>0.7) gets full weight, low confidence (<0.35) gets 50%
            confidence_boost = 1.0 if info["confidence"] >= 0.7 else (0.5 + info["confidence"])
            num = confidence_boost * (1 + info["expected_return"])
            numerator[ticker] = num
            total += num

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

        # Position limits, sector cap and target invested fraction now come from
        # the settings registry (config/settings_schema.yaml, group `allocation`)
        # instead of being module constants. The shape of the optimizer is the
        # kind of thing a low-code operator should be able to tune; before this
        # it required editing Python and redeploying.
        #
        # 這四個原本是模組常數，調整最佳化器的形狀必須改 Python 並重新部署；
        # 現在改讀設定註冊表。
        MIN_POS = float(self.settings_service.get_setting("alloc_min_position"))
        MAX_POS = float(self.settings_service.get_setting("alloc_max_position"))
        SECTOR_CAP = float(self.settings_service.get_setting("alloc_sector_cap"))
        TARGET_SUM = float(self.settings_service.get_setting("alloc_target_sum"))

        if MIN_POS > MAX_POS:
            # A caller could otherwise produce an empty feasible set and get
            # silently-zero weights out of the clamp below.
            # 否則 clamp 會產生空的可行區間，靜默輸出全零權重。
            logger.warning(
                "alloc_min_position (%.3f) exceeds alloc_max_position (%.3f); "
                "falling back to the schema defaults for this run.",
                MIN_POS, MAX_POS,
            )
            from src.config.settings_schema import schema_default
            MIN_POS = float(schema_default("alloc_min_position"))
            MAX_POS = float(schema_default("alloc_max_position"))

        for ticker in raw_weights:
            raw_weights[ticker] = max(MIN_POS, min(MAX_POS, raw_weights[ticker]))

        # Sector concentration: cap at 40%
        sector_capped = dict(raw_weights)
        for ticker, info in ticker_scores.items():
            sector = info["sector"]
            if sector and sector_weights.get(sector, 0) > SECTOR_CAP:
                # Reduce this ticker's weight proportionally
                ratio = SECTOR_CAP / sector_weights[sector]
                sector_capped[ticker] = raw_weights[ticker] * ratio

        # Normalize to TARGET_SUM (95% → 5% cash buffer)
        actual = sum(sector_capped.values())
        targets = []
        if actual > 0:
            self.repo.clear_targets(self.user_id)
            for ticker, w in sector_capped.items():
                norm_w = w / actual * TARGET_SUM
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
                })

        self.repo.add_log(self.user_id, "ALL", "optimized",
                          "system", f"Re-optimized {len(targets)} targets (risk-parity, sector cap {SECTOR_CAP:.0%})")
        return {"success": True, "message": f"Optimized {len(targets)} allocations", "targets": targets}

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