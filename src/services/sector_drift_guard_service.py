"""
Sector Drift Guard & Dynamic Theme Discovery Service
=====================================================
行業主題漂移守衛與自適應標的池動態擴展服務

核心功能：
1. 行業主題與熱點板塊動態探測 (Dynamic Theme & Hot Sector Discovery):
   - 根據 10 大核心行業主題（科技/半導體、金融、醫療保健、能源、工業、非必需消費、必需消費、公用事業、通訊、原物料）
     持續追蹤優質龍頭股與主題 Contenders，動態擴充候選池，擺脫靜態清單束縛。
2. 行業曝險與集中度分析 (Sector Distribution & HHI Metrics):
   - 評估當前活躍自選池 (Active Universe) 與實盤持倉 (Portfolio Positions) 之行業佔比。
   - 計算赫芬達爾-赫希曼指數 (HHI Index = sum(w_i^2)) 評估整體多角化分散水準。
   - 識別過度擁擠行業 (Over-concentrated) 與低覆蓋平衡行業 (Under-represented)。
3. 主題漂移守衛 (Sector Drift Guard):
   - 嚴格守衛行業集中度硬上限 (預設 30%，警告線 25%)。
   - 在標的池准入 (Admission) 與輪動 (Rotation) 時實施防漂移把關：若新標的加入會導致該行業超標，則阻斷並轉向推薦低配行業優質標的。
4. 行業剩餘額度檢驗 (Sector Headroom Calculation):
   - 精確計算特定標的所屬行業在不突破上限的前提下，所能容納之最大資金金額與權重上限。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from src.config.owner import resolve_user_id

logger = logging.getLogger("SectorDriftGuardService")

# Comprehensive curated mapping of US market sectors and key blue-chip thematic leaders
SECTOR_THEME_LEADERS: Dict[str, List[str]] = {
    "Technology": [
        "AAPL", "MSFT", "NVDA", "TSM", "GOOGL", "AVGO", "CRM", "AMD", "QCOM", "ORCL",
        "NOW", "ADBE", "INTC", "AMAT", "LRCX", "PANW", "MU", "SNPS", "CDNS",
    ],
    "Financials": [
        "JPM", "V", "MA", "BAC", "WFC", "MS", "GS", "BLK", "AXP", "C", "CB", "SPGI", "PGR", "MMC",
    ],
    "Healthcare": [
        "LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN", "ISRG", "BMY", "GILD", "VRTX",
    ],
    "Consumer Discretionary": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "BKNG", "TJX", "CMG", "LULU",
    ],
    "Consumer Staples": [
        "WMT", "PG", "COST", "PEP", "KO", "PM", "CL", "MO", "MDLZ", "TGT", "STZ",
    ],
    "Industrials": [
        "CAT", "GE", "UNP", "HON", "RTX", "BA", "LMT", "DE", "UPS", "ETN", "WM", "GD",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "WMB",
    ],
    "Utilities & Clean Energy": [
        "NEE", "SO", "DUK", "CEG", "VST", "AEP", "SRE", "XEL", "ED",
    ],
    "Materials": [
        "LIN", "SHW", "APD", "ECL", "FCX", "NEM", "CTVA", "DOW",
    ],
    "Communication Services": [
        "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR",
    ],
}


class SectorDriftStatus(str, Enum):
    """Status indicating sector concentration and drift severity."""
    BALANCED = "BALANCED"                   # All sectors <= warning threshold (e.g. 25%)
    DRIFT_WARNING = "DRIFT_WARNING"         # One or more sectors > warning threshold but <= hard cap
    DRIFT_BREACH = "DRIFT_BREACH"           # One or more sectors > hard cap (e.g. 30%)


@dataclass
class SectorDistribution:
    """Metrics quantifying sector concentration and portfolio balance."""
    sector_counts: Dict[str, int] = field(default_factory=dict)
    sector_weights: Dict[str, float] = field(default_factory=dict)
    total_items: int = 0
    hhi_index: float = 0.0                  # Sum of squared weights [0.0 ~ 1.0]
    over_concentrated_sectors: List[str] = field(default_factory=list)
    warning_sectors: List[str] = field(default_factory=list)
    under_represented_sectors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector_counts": self.sector_counts,
            "sector_weights": {k: round(v, 4) for k, v in self.sector_weights.items()},
            "total_items": self.total_items,
            "hhi_index": round(self.hhi_index, 4),
            "over_concentrated_sectors": self.over_concentrated_sectors,
            "warning_sectors": self.warning_sectors,
            "under_represented_sectors": self.under_represented_sectors,
        }


@dataclass
class SectorDriftReport:
    """Consolidated diagnostic report on sector exposures and drift prevention."""
    status: SectorDriftStatus
    max_limit_pct: float
    warning_limit_pct: float
    distribution: SectorDistribution
    recommendations: List[str] = field(default_factory=list)
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "max_limit_pct": round(self.max_limit_pct, 4),
            "warning_limit_pct": round(self.warning_limit_pct, 4),
            "distribution": self.distribution.to_dict(),
            "recommendations": self.recommendations,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class PortfolioSectorReport:
    """Consolidated diagnostic report on real portfolio holdings sector concentration."""
    status: SectorDriftStatus
    hhi_index: float
    max_limit_pct: float
    warning_limit_pct: float
    sector_values: Dict[str, float] = field(default_factory=dict)
    sector_weights: Dict[str, float] = field(default_factory=dict)
    nlv_sector_weights: Dict[str, float] = field(default_factory=dict)
    over_concentrated_sectors: List[str] = field(default_factory=list)
    warning_sectors: List[str] = field(default_factory=list)
    under_represented_sectors: List[str] = field(default_factory=list)
    holdings_metrics: List[Dict[str, Any]] = field(default_factory=list)
    total_stock_value: float = 0.0
    total_equity: float = 0.0
    stock_ratio_pct: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "hhi_index": round(self.hhi_index, 4),
            "max_limit_pct": round(self.max_limit_pct, 4),
            "warning_limit_pct": round(self.warning_limit_pct, 4),
            "sector_values": {k: round(v, 2) for k, v in self.sector_values.items()},
            "sector_weights": {k: round(v, 4) for k, v in self.sector_weights.items()},
            "nlv_sector_weights": {k: round(v, 4) for k, v in self.nlv_sector_weights.items()},
            "over_concentrated_sectors": self.over_concentrated_sectors,
            "warning_sectors": self.warning_sectors,
            "under_represented_sectors": self.under_represented_sectors,
            "holdings_metrics": self.holdings_metrics,
            "total_stock_value": round(self.total_stock_value, 2),
            "total_equity": round(self.total_equity, 2),
            "stock_ratio_pct": round(self.stock_ratio_pct, 2),
            "recommendations": self.recommendations,
            "evaluated_at": self.evaluated_at,
        }


class SectorDriftGuardService:
    """
    Guards against sector concentration risk, alerts on theme drift,
    and dynamically scouts thematic leaders across under-represented market sectors.
    """

    DEFAULT_MAX_SECTOR_EXPOSURE = 0.30      # 30.0% hard cap
    DEFAULT_WARNING_SECTOR_EXPOSURE = 0.25  # 25.0% warning threshold

    def __init__(
        self,
        user_id: Optional[str] = None,
        settings_service: Optional[Any] = None,
        repo: Optional[Any] = None,
        market: Optional[Any] = None,
    ):
        try:
            self.user_id = resolve_user_id(user_id) if user_id else "default_user"
        except Exception:
            self.user_id = user_id or "default_user"

        self.settings_service = settings_service
        self.repo = repo
        self.market = market

    def _get_setting(self, key: str, default: Any) -> Any:
        if self.settings_service:
            try:
                val = getattr(self.settings_service, "get_setting", None)
                if callable(val):
                    try:
                        res = val(key)
                    except TypeError:
                        res = val(key, default)
                elif hasattr(self.settings_service, "get"):
                    try:
                        res = self.settings_service.get(self.user_id, key)
                    except TypeError:
                        res = self.settings_service.get(key)
                else:
                    res = None
                if res is not None:
                    return type(default)(res) if default is not None else res
            except Exception as e:
                logger.debug(f"Failed to read setting '{key}': {e}")
        return default

    @property
    def max_sector_limit(self) -> float:
        # Check specific sector guard cap first, fallback to risk manager setting
        specific_cap = self._get_setting("sector_concentration_cap_pct", None)
        if specific_cap is not None:
            return float(specific_cap)
        return float(self._get_setting("risk_max_sector_exposure", self.DEFAULT_MAX_SECTOR_EXPOSURE))

    @property
    def warning_sector_limit(self) -> float:
        return float(self._get_setting("sector_drift_warning_pct", self.DEFAULT_WARNING_SECTOR_EXPOSURE))

    @property
    def warning_limit_pct(self) -> float:
        return self.warning_sector_limit

    @property
    def is_enabled(self) -> bool:
        return bool(self._get_setting("enable_sector_drift_guard", True))

    @property
    def portfolio_hhi_breach_threshold(self) -> float:
        return float(self._get_setting("portfolio_hhi_breach_threshold", 0.25))

    @property
    def tech_concentration_cap_pct(self) -> float:
        return float(self._get_setting("tech_sector_concentration_cap_pct", 0.30))

    @property
    def is_cross_sector_injection_enabled(self) -> bool:
        return bool(self._get_setting("enable_cross_sector_momentum_injection", True))

    @property
    def cross_sector_injection_quota_pct(self) -> float:
        return float(self._get_setting("cross_sector_injection_quota_pct", 0.35))

    def resolve_ticker_sector(self, ticker: str, fallback_sector: str = "Unknown") -> str:
        """Resolve sector classification for a ticker from repo or market data."""
        clean_ticker = (ticker or "").upper().strip()
        if not clean_ticker:
            return fallback_sector

        # 1. Check known theme dictionary
        for sector_name, tickers in SECTOR_THEME_LEADERS.items():
            if clean_ticker in tickers:
                return sector_name

        # 2. Check DB repository
        if self.repo:
            try:
                rec = self.repo.get(self.user_id, clean_ticker) if hasattr(self.repo, "get") else None
                if rec and rec.get("sector"):
                    return str(rec["sector"]).strip()
            except Exception as e:
                logger.debug(f"Repo sector lookup error for {clean_ticker}: {e}")

        # 3. Check MarketDataService financials
        if self.market:
            try:
                info = self.market.get_financials(clean_ticker) or {}
                sec = info.get("sector")
                if sec:
                    return str(sec).strip()
            except Exception as e:
                logger.debug(f"Market data sector lookup error for {clean_ticker}: {e}")

        return fallback_sector

    def analyze_universe_sectors(
        self,
        current_active: Optional[List[Dict[str, Any]]] = None,
        max_active_capacity: int = 8,
    ) -> SectorDriftReport:
        """
        Analyze sector concentration in the active universe pool.
        """
        active_items = current_active
        if active_items is None and self.repo:
            try:
                active_items = self.repo.get_all(self.user_id, status="active")
            except Exception as e:
                logger.warning(f"Error fetching active universe: {e}")
                active_items = []

        active_items = active_items or []
        total_active = len(active_items)

        sector_counts: Dict[str, int] = {}
        for item in active_items:
            ticker = getattr(item, "ticker", None) or (item.get("ticker", "") if isinstance(item, dict) else "")
            raw_sec = getattr(item, "sector", None) or (item.get("sector") if isinstance(item, dict) else None)
            sec = str(raw_sec).strip() if raw_sec else self.resolve_ticker_sector(ticker)
            sec = sec or "Unknown"
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

        denom = max(total_active, 1)
        sector_weights = {s: count / denom for s, count in sector_counts.items()}

        # Compute HHI concentration
        hhi = sum(w * w for w in sector_weights.values())

        max_cap = self.max_sector_limit
        warn_cap = self.warning_limit_pct

        # Over-concentration requires at least 2 stocks in the same sector (single stock is never crowded)
        over_concentrated = [
            s for s, w in sector_weights.items()
            if w > max_cap and s != "Unknown" and sector_counts[s] > 1
        ]
        warning_sectors = [
            s for s, w in sector_weights.items()
            if warn_cap < w <= max_cap and s != "Unknown" and sector_counts[s] > 1
        ]

        # Identify major market sectors absent or under-represented
        all_major_sectors = list(SECTOR_THEME_LEADERS.keys())
        under_represented = [s for s in all_major_sectors if sector_counts.get(s, 0) == 0]

        # Determine overall drift status
        if over_concentrated:
            status = SectorDriftStatus.DRIFT_BREACH
        elif warning_sectors:
            status = SectorDriftStatus.DRIFT_WARNING
        else:
            status = SectorDriftStatus.BALANCED

        recommendations = []
        if over_concentrated:
            for s in over_concentrated:
                recommendations.append(
                    f"行業集中度超標警告：{s} 佔比 {sector_weights[s]:.1%} (>{max_cap:.1%})，"
                    f"已暫停納入該板塊新標的，建議向低配板塊分散。"
                )
        elif warning_sectors:
            for s in warning_sectors:
                recommendations.append(
                    f"行業集中度接近上限：{s} 佔比 {sector_weights[s]:.1%} (>{warn_cap:.1%})，建議關注其他行業配置。"
                )
        if under_represented:
            top_rec = ", ".join(under_represented[:3])
            recommendations.append(f"推薦探索以下低配置或未涵蓋行業以提升多角化效益：{top_rec}")

        dist = SectorDistribution(
            sector_counts=sector_counts,
            sector_weights=sector_weights,
            total_items=total_active,
            hhi_index=hhi,
            over_concentrated_sectors=over_concentrated,
            warning_sectors=warning_sectors,
            under_represented_sectors=under_represented,
        )

        return SectorDriftReport(
            status=status,
            max_limit_pct=max_cap,
            warning_limit_pct=warn_cap,
            distribution=dist,
            recommendations=recommendations,
        )

    def can_admit_or_rotate(
        self,
        ticker: str,
        target_sector: Optional[str] = None,
        current_active_items: Optional[List[Dict[str, Any]]] = None,
        max_active_capacity: int = 8,
        displaced_ticker: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Check whether admitting or rotating `ticker` would breach the sector concentration cap.
        If displaced_ticker is provided (rotation), its sector count is decremented first.
        """
        if not self.is_enabled:
            return True, "Sector drift guard is disabled in settings"

        items = list(current_active_items or [])
        sec = target_sector or self.resolve_ticker_sector(ticker)

        # Count current sector distribution
        sec_counts: Dict[str, int] = {}
        for item in items:
            t_sym = getattr(item, "ticker", None) or (item.get("ticker", "") if isinstance(item, dict) else "")
            t_sym = str(t_sym).upper()
            if displaced_ticker and t_sym == displaced_ticker.upper():
                continue  # Displaced item will be removed
            raw_s = getattr(item, "sector", None) or (item.get("sector") if isinstance(item, dict) else None)
            s = str(raw_s).strip() if raw_s else self.resolve_ticker_sector(t_sym)
            sec_counts[s] = sec_counts.get(s, 0) + 1

        # Project new count if candidate is added
        projected_sector_count = sec_counts.get(sec, 0) + 1
        projected_total = sum(sec_counts.values()) + 1
        effective_capacity = max(projected_total, max_active_capacity)

        # Single stock in a sector is inherently non-concentrated
        if projected_sector_count <= 1:
            return True, f"符合行業分散門檻：[{sec}] 僅配置單一標的"

        projected_pct = projected_sector_count / effective_capacity
        limit = self.max_sector_limit

        if projected_pct > limit:
            reason = (
                f"阻斷加入活躍自選池：加入 {ticker} 後所屬行業 [{sec}] 預估佔比達 "
                f"{projected_pct:.1%} ({projected_sector_count}/{effective_capacity})，"
                f"超過單一行業集中度上限 {limit:.1%}。"
            )
            return False, reason

        return True, f"符合行業分散門檻：[{sec}] 預估佔比 {projected_pct:.1%} <= {limit:.1%}"

    def get_sector_headroom(
        self,
        ticker: str,
        current_positions: List[Any],
        total_nlv: float,
        max_sector_limit: Optional[float] = None,
    ) -> Tuple[float, float, str]:
        """
        Compute the remaining allocation headroom (dollars and weight percentage)
        for a ticker's sector before breaching the concentration cap.
        Returns: (headroom_dollars, headroom_pct, sector_name)
        """
        limit_pct = max_sector_limit or self.max_sector_limit
        sec = self.resolve_ticker_sector(ticker)

        if total_nlv <= 0 or limit_pct >= 1.0:
            return total_nlv, limit_pct, sec

        current_sector_value = 0.0
        for pos in current_positions:
            val = float(getattr(pos, "market_value", 0.0) or (pos.get("market_value", 0.0) if isinstance(pos, dict) else 0.0))
            sym = getattr(pos, "symbol", None) or getattr(pos, "ticker", None) or (pos.get("symbol") if isinstance(pos, dict) else None) or (pos.get("ticker") if isinstance(pos, dict) else None)
            if sym and self.resolve_ticker_sector(sym) == sec:
                current_sector_value += val

        max_allowed_sector_val = total_nlv * limit_pct
        headroom_dollars = max(0.0, max_allowed_sector_val - current_sector_value)
        headroom_pct = headroom_dollars / total_nlv if total_nlv > 0 else 0.0

        return headroom_dollars, round(headroom_pct, 4), sec

    def discover_theme_and_hot_sector_contenders(
        self,
        existing_tickers: Optional[Set[str]] = None,
        top_n_per_sector: int = 3,
        prioritize_underrepresented: bool = True,
        current_active: Optional[List[Any]] = None,
        candidate_pool: Optional[List[str]] = None,
        max_contenders: Optional[int] = None,
    ) -> List[str]:
        """
        Dynamically discover and propose blue-chip leaders across sectors.
        If prioritize_underrepresented is True, prioritizes sectors that are currently
        absent or under-represented in the user's active universe.
        """
        existing = set(existing_tickers or set())
        if candidate_pool:
            existing.update(candidate_pool)
        if current_active:
            for item in current_active:
                item_sym = getattr(item, "ticker", None) or (item.get("ticker", "") if isinstance(item, dict) else "")
                if item_sym:
                    existing.add(str(item_sym))

        clean_existing = {str(t).upper().strip() for t in existing if t}
        dist_report = self.analyze_universe_sectors(current_active=current_active)
        underrep_set = set(dist_report.distribution.under_represented_sectors)

        candidates: List[str] = []

        # Sort sector priorities: under-represented sectors first
        ordered_sectors = sorted(
            SECTOR_THEME_LEADERS.keys(),
            key=lambda s: 0 if s in underrep_set else 1,
        )

        for sec in ordered_sectors:
            leaders = SECTOR_THEME_LEADERS.get(sec, [])
            count = 0
            for sym in leaders:
                clean_sym = sym.upper().strip()
                if clean_sym not in clean_existing:
                    candidates.append(clean_sym)
                    clean_existing.add(clean_sym)
                    count += 1
                    if count >= top_n_per_sector:
                        break
            if max_contenders is not None and len(candidates) >= max_contenders:
                break

        if max_contenders is not None:
            return candidates[:max_contenders]
        return candidates

    def analyze_portfolio_holdings(
        self,
        positions: List[Any],
        total_equity: Optional[float] = None,
    ) -> PortfolioSectorReport:
        """
        Analyze sector concentration in real portfolio holdings.
        Computes exact market value by sector, weights relative to stock equity and total NLV,
        portfolio sector HHI index, and flags over-concentrated / under-represented sectors.
        """
        parsed_holdings: List[Dict[str, Any]] = []
        sector_values: Dict[str, float] = {}

        for p in positions or []:
            sym = (
                getattr(p, "symbol", None)
                or getattr(p, "ticker", None)
                or (p.get("symbol") if isinstance(p, dict) else None)
                or (p.get("ticker") if isinstance(p, dict) else None)
            )
            if not sym or str(sym).upper() in ("CASH", "USD"):
                continue
            sym = str(sym).upper()
            for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                if sym.endswith(suffix):
                    sym = sym[:-len(suffix)]

            val = float(
                getattr(p, "market_value", 0.0)
                or getattr(p, "amount", 0.0)
                or (p.get("market_value", 0.0) if isinstance(p, dict) else 0.0)
                or (p.get("amount", 0.0) if isinstance(p, dict) else 0.0)
            )
            if val <= 0:
                continue

            sec = self.resolve_ticker_sector(sym)
            sector_values[sec] = sector_values.get(sec, 0.0) + val
            parsed_holdings.append({
                "symbol": sym,
                "sector": sec,
                "market_value": val,
            })

        total_stock_val = sum(sector_values.values())
        effective_nlv = max(float(total_equity or total_stock_val), total_stock_val, 1.0)
        stock_ratio = (total_stock_val / effective_nlv * 100.0) if effective_nlv > 0 else 0.0

        # Stock-based weights (for asset concentration & HHI)
        denom_stock = max(total_stock_val, 1.0)
        sector_weights = {s: v / denom_stock for s, v in sector_values.items()}

        # NLV-based weights (for account-level exposure)
        nlv_weights = {s: v / effective_nlv for s, v in sector_values.items()}

        # Add weights to parsed holdings
        for h in parsed_holdings:
            h["weight_in_stocks"] = round(h["market_value"] / denom_stock, 4)
            h["weight_in_nlv"] = round(h["market_value"] / effective_nlv, 4)

        # HHI index across sectors
        hhi = sum(w * w for w in sector_weights.values()) if total_stock_val > 0 else 0.0

        max_cap = self.max_sector_limit
        warn_cap = self.warning_limit_pct
        hhi_thresh = self.portfolio_hhi_breach_threshold

        over_concentrated = []
        warning_sectors = []
        for s, w_stock in sector_weights.items():
            w_nlv = nlv_weights.get(s, 0.0)
            if (w_nlv > max_cap or w_stock > 0.50) and len(parsed_holdings) > 1:
                over_concentrated.append(s)
            elif (w_nlv > warn_cap or w_stock > 0.35) and len(parsed_holdings) > 1:
                warning_sectors.append(s)

        all_major = list(SECTOR_THEME_LEADERS.keys())
        under_represented = [s for s in all_major if sector_values.get(s, 0.0) == 0.0]

        if over_concentrated or (hhi > hhi_thresh and len(parsed_holdings) > 1):
            status = SectorDriftStatus.DRIFT_BREACH
        elif warning_sectors or (hhi > (hhi_thresh * 0.72) and len(parsed_holdings) > 1):
            status = SectorDriftStatus.DRIFT_WARNING
        else:
            status = SectorDriftStatus.BALANCED

        recommendations: List[str] = []
        if over_concentrated:
            for s in over_concentrated:
                recommendations.append(
                    f"實盤板塊過度集中警告：[{s}] 佔股票市值 {sector_weights[s]:.1%} (佔總淨值 {nlv_weights[s]:.1%})，"
                    f"HHI 指數高達 {hhi:.3f} (>{hhi_thresh:.2f})。建議啟動跨板塊自癒，暫停加碼該板塊。"
                )
        elif warning_sectors:
            for s in warning_sectors:
                recommendations.append(
                    f"實盤板塊集中度偏高：[{s}] 佔股票市值 {sector_weights[s]:.1%}，建議優先配置其他板塊。"
                )
        if under_represented:
            top_rec = ", ".join(under_represented[:3])
            recommendations.append(f"推薦探索以下低配置或未涵蓋行業以提升多角化效益：{top_rec}")

        return PortfolioSectorReport(
            status=status,
            hhi_index=hhi,
            max_limit_pct=max_cap,
            warning_limit_pct=warn_cap,
            sector_values=sector_values,
            sector_weights=sector_weights,
            nlv_sector_weights=nlv_weights,
            over_concentrated_sectors=over_concentrated,
            warning_sectors=warning_sectors,
            under_represented_sectors=under_represented,
            holdings_metrics=parsed_holdings,
            total_stock_value=total_stock_val,
            total_equity=effective_nlv,
            stock_ratio_pct=stock_ratio,
            recommendations=recommendations,
        )

    def discover_cross_sector_injection_contender(
        self,
        current_positions: Optional[List[Any]] = None,
        candidate_pool: Optional[List[str]] = None,
        total_equity: Optional[float] = None,
        excluded_tickers: Optional[Set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Scouts and returns the best non-tech blue-chip leader from an under-represented
        sector to de-concentrate the portfolio.
        Returns a dict: {"ticker": sym, "sector": sec, "role": role, "source": src}
        """
        report = self.analyze_portfolio_holdings(current_positions or [], total_equity=total_equity)
        under_represented = report.under_represented_sectors
        if not under_represented:
            sorted_sectors = sorted(report.sector_values.items(), key=lambda x: x[1])
            under_represented = [s[0] for s in sorted_sectors if s[0] != "Unknown"]

        target_sectors = [
            s for s in under_represented 
            if s not in ("Technology", "Communication Services")
        ]
        if not target_sectors:
            target_sectors = [
                s for s in list(SECTOR_THEME_LEADERS.keys())
                if s not in ("Technology", "Communication Services")
            ]

        held_syms = set()
        for p in current_positions or []:
            sym = (
                getattr(p, "symbol", None)
                or getattr(p, "ticker", None)
                or (p.get("symbol") if isinstance(p, dict) else None)
                or (p.get("ticker") if isinstance(p, dict) else None)
            )
            if sym:
                clean_sym = str(sym).upper()
                for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
                    if clean_sym.endswith(suffix):
                        clean_sym = clean_sym[:-len(suffix)]
                held_syms.add(clean_sym)

        skip_set = set(held_syms)
        if excluded_tickers:
            skip_set.update(str(s).upper() for s in excluded_tickers)

        db_candidates: List[Dict[str, Any]] = []
        if self.repo:
            try:
                db_candidates = self.repo.get_all(self.user_id, status="candidate")
            except Exception as e:
                logger.debug(f"Repo candidate lookup error: {e}")

        # Check candidate pool first
        for sec in target_sectors:
            for c in db_candidates:
                c_sym = str(c.get("ticker", "")).upper()
                c_sec = str(c.get("sector", "")).strip() or self.resolve_ticker_sector(c_sym)
                if c_sec == sec and c_sym not in skip_set:
                    return {
                        "ticker": c_sym,
                        "sector": sec,
                        "company_name": c.get("company_name", c_sym),
                        "role": f"跨板塊動能注入: {sec} 龍頭 ({c_sym}) 分散 HHI 自癒",
                        "source": "candidate_pool",
                    }

        # Fallback to curated theme leaders in SECTOR_THEME_LEADERS
        for sec in target_sectors:
            leaders = SECTOR_THEME_LEADERS.get(sec, [])
            for sym in leaders:
                sym_clean = sym.upper()
                if sym_clean not in skip_set:
                    return {
                        "ticker": sym_clean,
                        "sector": sec,
                        "company_name": sym_clean,
                        "role": f"跨板塊動能注入: {sec} 龍頭 ({sym_clean}) 分散 HHI 自癒",
                        "source": "curated_leaders",
                    }

        return None
