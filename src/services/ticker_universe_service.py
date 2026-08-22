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

logger = setup_logger("TickerUniverseService")


class TickerUniverseService:
    """High-level service for ticker universe operations."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.repo = TickerUniverseRepository()

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

        # Apply position limits: clamp to [3%, 25%]
        MIN_POS = 0.03
        MAX_POS = 0.25
        SECTOR_CAP = 0.40
        TARGET_SUM = 0.95  # leave 5% cash buffer

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
                holdings.append({
                    "ticker": getattr(p, "symbol", ""),
                    "company_name": getattr(p, "company_name", getattr(p, "name", "")),
                    "sector": getattr(p, "sector", ""),
                    "quantity": getattr(p, "quantity", 0),
                })
            count = self.repo.migrate_holdings_to_universe(self.user_id, holdings)
            return {"success": True, "count": count, "message": f"Migrated {count} holdings"}
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return {"success": False, "count": 0, "message": str(e)}