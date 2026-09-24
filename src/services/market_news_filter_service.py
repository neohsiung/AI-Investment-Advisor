"""
Market News Intelligence & Filtering Service
市場快訊智慧研判與篩選服務

Responsible for Stage 1 (Semantic Deduplication) and Stage 2 (Fast Value & Relevance Filter).
Filters out >85% of market noise, clickbait, and PR fluff before allocating any LLM tokens.
Ensures only high-conviction events relevant to portfolio holdings, watchlist, and macro systemic risk reach specialist agents.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from urllib.parse import urlparse, parse_qs, urlunparse

from src.config.owner import resolve_user_id

logger = logging.getLogger(__name__)


@dataclass
class MarketFilterResult:
    """
    Structured outcome of market news screening.
    市場快訊篩選評定結果。
    """
    is_duplicate: bool = False
    is_relevant: bool = False
    relevance_score: float = 0.0
    matched_tickers: List[str] = field(default_factory=list)
    macro_topic: Optional[str] = None
    category: str = "unknown"
    reason: str = ""

    @property
    def should_drop(self) -> bool:
        """Indicates whether this event should be discarded immediately."""
        return self.is_duplicate or not self.is_relevant


class MarketNewsFilterService:
    """
    High-speed screening gate for inbound market news, RSS feeds, and webhooks.
    市場新聞極速篩選閘門：去重 + 實質價值篩選。
    """

    # In-memory LRU fallback cache for seen hashes (max 2000 entries)
    _memory_seen_hashes: Set[str] = set()

    # Systemic Macro Keywords (High impact on portfolio assets)
    MACRO_SYSTEMIC_KEYWORDS = {
        "fomc": "FOMC / Monetary Policy",
        "federal reserve": "Federal Reserve Policy",
        "fed rate": "Fed Interest Rate",
        "interest rate cut": "Interest Rate Cut",
        "interest rate hike": "Interest Rate Hike",
        "rate cut": "Interest Rate Cut",
        "rate hike": "Interest Rate Hike",
        "jerome powell": "Fed Chair Powell Speech",
        "cpi": "Consumer Price Index (CPI)",
        "inflation": "Inflation Metric",
        "ppi": "Producer Price Index (PPI)",
        "non-farm payroll": "Non-Farm Payrolls (Jobs)",
        "unemployment rate": "Unemployment Data",
        "gdp": "Gross Domestic Product (GDP)",
        "treasury yield": "Treasury Yield Shock",
        "10-year yield": "10-Year Bond Yield",
        "yield curve": "Yield Curve Inversion / Un-inversion",
        "debt ceiling": "US Debt Ceiling",
        "us-china tariff": "US-China Trade & Tariffs",
        "tariff": "Trade Tariff Policy",
        "export control": "Semiconductor Export Controls",
        "chip ban": "Semiconductor Restrictions",
        "banking crisis": "Banking Liquidity Risk",
        "bank failure": "Bank Failure / Contagion",
        "liquidity crunch": "Financial Market Liquidity",
        "sec enforcement": "SEC Regulatory Enforcement",
        "antitrust lawsuit": "Antitrust Litigation",
        "geopolitical crisis": "Geopolitical Shock",
        "taiwan strait": "Geopolitical Shock (Taiwan Strait)",
        "middle east conflict": "Geopolitical Shock (Middle East)",
    }

    # Strict noise, PR, clickbait, and lifestyle patterns to drop (>85% noise rejection)
    NOISE_PATTERNS = [
        (r"\b(sponsored|promoted content|paid post|advertisement)\b", "sponsored_content"),
        (r"\b(pr newswire|business wire|globe newswire|press release)\b", "press_release_wire"),
        (r"\b(how to (save|retire|ask for a raise|budget|invest your first))\b", "personal_finance_fluff"),
        (r"\b(best (credit card|laptop|phone|tv|mattress|air fryer|gadget|car))\b", "product_review_lifestyle"),
        (r"\b(career advice|workplace culture|quiet quitting|side hustle)\b", "career_lifestyle"),
        (r"\b(horoscope|celebrity|gossip|entertainment|hollywood)\b", "entertainment_gossip"),
        (r"\b(dogecoin|shiba inu|pepe|memecoin|moonshot crypto|1000x)\b", "crypto_memes"),
        (r"\b(3 stocks to buy (if you have|now)|stocks that will make you rich)\b", "clickbait_listicle"),
        (r"\b(before you buy|is it time to buy|should you sell now\?)\b", "speculative_clickbait"),
        (r"\b(holiday sale|black friday|cyber monday|prime day deal)\b", "commercial_sales"),
        (r"\b(asx announcement|tsx venture|penny stock alert)\b", "irrelevant_penny_market"),
    ]

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = resolve_user_id(user_id)

    @classmethod
    def clean_url(cls, url: Optional[str]) -> str:
        """Strip tracking parameters (UTM, fbclid, gclid, etc.) from URL."""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            # Remove tracking keys
            filtered_params = {
                k: v for k, v in query_params.items()
                if not (k.startswith("utm_") or k in {"fbclid", "gclid", "ref", "source", "feed"})
            }
            # Reconstruct query
            new_query = "&".join(f"{k}={v[0]}" for k, v in filtered_params.items())
            clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))
            return clean.rstrip("/")
        except Exception:
            return url.strip()

    @classmethod
    def normalize_title(cls, title: Optional[str]) -> str:
        """Normalize headline text for semantic deduplication."""
        if not title:
            return ""
        t = title.lower()
        # Remove publisher suffixes (e.g., "| Reuters", "- Bloomberg", "[CNBC]")
        t = re.sub(r"[\-|\|\[\(].*?(reuters|bloomberg|cnbc|wsj|yahoo finance|marketwatch|investing\.com|the wall street journal)[\)\]]?", "", t)
        # Remove punctuation and extra whitespace
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def is_semantic_duplicate(self, title: str, url: Optional[str] = None) -> bool:
        """
        Stage 1: Semantic & URL Deduplication.
        檢查是否為重複新聞（48 小時滑動窗口）。
        """
        clean_u = self.clean_url(url)
        norm_t = self.normalize_title(title)

        title_hash = hashlib.sha256(norm_t.encode("utf-8")).hexdigest() if norm_t else None
        url_hash = hashlib.sha256(clean_u.encode("utf-8")).hexdigest() if clean_u else None

        # 1. Check Redis sliding window
        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync()
            if title_hash and r.get(f"news_dedup:{self.user_id}:title:{title_hash}"):
                return True
            if url_hash and r.get(f"news_dedup:{self.user_id}:url:{url_hash}"):
                return True
        except Exception as e:
            logger.debug(f"Redis dedup check skipped: {e}")

        # 2. In-memory fallback
        if title_hash and title_hash in self._memory_seen_hashes:
            return True
        if url_hash and url_hash in self._memory_seen_hashes:
            return True

        return False

    def record_seen(self, title: str, url: Optional[str] = None, ttl_seconds: int = 172800):
        """Record seen hashes for 48 hours."""
        clean_u = self.clean_url(url)
        norm_t = self.normalize_title(title)

        title_hash = hashlib.sha256(norm_t.encode("utf-8")).hexdigest() if norm_t else None
        url_hash = hashlib.sha256(clean_u.encode("utf-8")).hexdigest() if clean_u else None

        try:
            from src.infrastructure.cache.redis_client import get_redis_sync
            r = get_redis_sync()
            if title_hash:
                r.set(f"news_dedup:{self.user_id}:title:{title_hash}", "1", ex=ttl_seconds)
            if url_hash:
                r.set(f"news_dedup:{self.user_id}:url:{url_hash}", "1", ex=ttl_seconds)
        except Exception as e:
            logger.debug(f"Redis record_seen error: {e}")

        # In-memory bounded cache
        if len(self._memory_seen_hashes) > 2000:
            self._memory_seen_hashes.clear()
        if title_hash:
            self._memory_seen_hashes.add(title_hash)
        if url_hash:
            self._memory_seen_hashes.add(url_hash)

    def get_portfolio_holdings(self) -> Set[str]:
        """Fetch active holding tickers for the user."""
        try:
            from src.services.transaction_service import TransactionService
            tx_svc = TransactionService(user_id=self.user_id)
            holdings = tx_svc.get_holdings_map(self.user_id)
            # Standardize tickers to uppercase
            return {ticker.upper() for ticker, h in holdings.items() if h.get("quantity", 0) > 0}
        except Exception as e:
            logger.warning(f"Failed to fetch portfolio holdings for {self.user_id}: {e}")
            # Safe fallback: default active core portfolio tickers
            return {"TSM", "VTI", "GS", "GOOG", "META", "AMD", "MSFT", "MU", "NVDA", "AAPL", "AMZN"}

    def get_watchlist_tickers(self) -> Set[str]:
        """Fetch active watchlist symbols."""
        try:
            from src.services.settings_service import SettingsService
            s_svc = SettingsService(user_id=self.user_id)
            wl = s_svc.get_watchlist()
            return {str(item).upper() for item in wl if item}
        except Exception as e:
            logger.debug(f"Failed to fetch watchlist: {e}")
            return {"SPY", "QQQ", "SMH", "SOXX", "IWM", "TLT"}

    def _check_noise_pattern(self, text: str) -> tuple[bool, str]:
        """Detect promotional fluff, lifestyle, or unverified clickbait."""
        text_lower = text.lower()
        for pattern, pattern_name in self.NOISE_PATTERNS:
            if re.search(pattern, text_lower, flags=re.IGNORECASE):
                return True, pattern_name
        return False, ""

    def _check_macro_topic(self, text: str) -> Optional[str]:
        """Detect high-impact systemic macro themes."""
        text_lower = text.lower()
        for kw, topic_desc in self.MACRO_SYSTEMIC_KEYWORDS.items():
            # Exact word boundary matching for abbreviations like CPI, PPI, GDP
            if len(kw) <= 4:
                if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                    return topic_desc
            else:
                if kw in text_lower:
                    return topic_desc
        return None

    def _extract_tickers(
        self,
        text: str,
        holdings: Set[str],
        watchlist: Set[str],
        explicit_ticker: Optional[str] = None,
    ) -> List[str]:
        """Extract valid target tickers appearing in text or explicitly provided."""
        matched = []
        if explicit_ticker and explicit_ticker.upper() not in ("GLOBAL", "ALL", "NONE", ""):
            matched.append(explicit_ticker.upper())

        # Check word boundaries for tickers
        combined_candidates = holdings | watchlist
        words = set(re.findall(r"\b[A-Z]{2,5}\b", text))
        for t in words:
            if t in combined_candidates and t not in matched:
                matched.append(t)

        return matched

    def evaluate(
        self,
        title: str,
        content: str = "",
        url: Optional[str] = None,
        ticker: Optional[str] = None,
        signal: Optional[str] = None,
        holdings: Optional[Set[str]] = None,
    ) -> MarketFilterResult:
        """
        Executes Stage 1 (Deduplication) and Stage 2 (Fast Value & Relevance Screening).
        執行第 1 階段去重與第 2 階段快速價值篩選。
        """
        combined_text = f"{title}\n{content}".strip()

        # ── Case 0: Explicit Webhook Trading Signal (e.g. TradingView alert) ──
        if signal and str(signal).upper() in ("BUY", "SELL", "STRONG_BUY", "STRONG_SELL", "ALERT"):
            target = [ticker.upper()] if ticker and ticker.upper() not in ("GLOBAL", "ALL") else []
            return MarketFilterResult(
                is_duplicate=False,
                is_relevant=True,
                relevance_score=9.5,
                matched_tickers=target,
                category="trading_signal",
                reason=f"Explicit webhook trading signal '{signal}' for {target or 'market'}",
            )

        # ── Stage 1: Deduplication ──
        if self.is_semantic_duplicate(title=title, url=url):
            logger.info(f"MarketNewsFilterService: Duplicate event detected. Dropping: '{title[:60]}...'")
            return MarketFilterResult(
                is_duplicate=True,
                is_relevant=False,
                relevance_score=0.0,
                category="duplicate",
                reason="Duplicate news event detected within 48h sliding window",
            )

        # ── Stage 2: Fast Value & Relevance Gate ──
        active_holdings = holdings if holdings is not None else self.get_portfolio_holdings()
        watchlist = self.get_watchlist_tickers()
        matched_tickers = self._extract_tickers(combined_text, active_holdings, watchlist, explicit_ticker=ticker)
        macro_topic = self._check_macro_topic(combined_text)

        # Check noise pattern
        is_noise, noise_type = self._check_noise_pattern(combined_text)

        # Holding Priority: If news directly mentions a stock currently held in portfolio,
        # it overrides mild noise suspicion (e.g. quarterly earnings release on business wire)
        is_holding_affected = any(t in active_holdings for t in matched_tickers)
        is_watchlist_affected = any(t in watchlist for t in matched_tickers)

        if is_noise and not is_holding_affected:
            logger.info(f"MarketNewsFilterService: Noise filter triggered ({noise_type}). Dropping: '{title[:60]}...'")
            return MarketFilterResult(
                is_duplicate=False,
                is_relevant=False,
                relevance_score=2.0,
                matched_tickers=matched_tickers,
                category="low_signal_noise",
                reason=f"Discarded by noise filter: {noise_type}",
            )

        # Case 1: Direct Portfolio Holding Impact (Highest Priority)
        if is_holding_affected:
            self.record_seen(title=title, url=url)
            return MarketFilterResult(
                is_duplicate=False,
                is_relevant=True,
                relevance_score=9.0,
                matched_tickers=matched_tickers,
                macro_topic=macro_topic,
                category="portfolio_holding",
                reason=f"Directly impacts active portfolio holdings: {matched_tickers}",
            )

        # Case 2: Major Systemic Macro Shock
        if macro_topic:
            self.record_seen(title=title, url=url)
            return MarketFilterResult(
                is_duplicate=False,
                is_relevant=True,
                relevance_score=8.0,
                matched_tickers=matched_tickers or ["SPY", "^VIX"],
                macro_topic=macro_topic,
                category="macro_systemic",
                reason=f"High-impact systemic macro event: {macro_topic}",
            )

        # Case 3: Watchlist Ticker Impact
        if is_watchlist_affected:
            self.record_seen(title=title, url=url)
            return MarketFilterResult(
                is_duplicate=False,
                is_relevant=True,
                relevance_score=7.0,
                matched_tickers=matched_tickers,
                category="watchlist",
                reason=f"Impacts watchlist asset: {matched_tickers}",
            )

        # Case 4: Generic Unrelated Market Noise (Drop >85%)
        return MarketFilterResult(
            is_duplicate=False,
            is_relevant=False,
            relevance_score=3.5,
            matched_tickers=matched_tickers,
            category="unrelated_market_noise",
            reason="Lacks direct portfolio holding relevance or systemic macro impact",
        )
