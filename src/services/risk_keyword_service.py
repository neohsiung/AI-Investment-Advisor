"""
Risk Keyword Service — Cached keyword access + automated discovery & refine
風險關鍵字服務 — 快取關鍵字存取 + 自動探索與精煉

Design Principles:
- Single instance injected via DI (no scattered `AlchemyRiskKeywordRepository()` calls)
- In-memory cache with TTL to reduce DB round-trips
- 3-Source discovery: Reports (LLM), Webhook news (TF-IDF), Community trends (API)
- Automated refine: decay stale keywords, boost hot keywords
- Hard cap at MAX_KEYWORDS (1000), dynamic target (default 200)
"""
import logging
import time
import json
import re
from collections import Counter
from typing import List, Optional, Tuple, Dict, Any

from src.repositories.risk_keyword_repository import AlchemyRiskKeywordRepository
from src.domain.entities import RiskKeyword

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────
# Stopwords for TF-IDF filtering
# ──────────────────────────────────────────
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "because", "about", "this", "that", "these", "those",
    "and", "but", "or", "if", "while", "although", "until", "since",
    "it", "its", "he", "she", "they", "we", "you", "i", "me", "my",
    "your", "his", "her", "their", "our", "us", "him", "them",
    "what", "which", "who", "whom", "whose",
    "also", "still", "even", "now", "new", "said", "says", "get",
    "one", "two", "first", "last", "year", "years", "time", "way",
    "report", "reports", "today", "week", "month", "day", "market",
    "stock", "stocks", "company", "companies", "according", "data",
    "per", "via", "up", "down", "like", "well", "back", "set",
})


class RiskKeywordService:
    """
    Unified service for risk keyword operations.
    統一的風險關鍵字服務。

    Responsibilities:
    - Cached keyword retrieval (5-min TTL)
    - Text risk scoring using weighted keywords
    - 3-Source automated discovery (reports, webhook, trends)
    - Automated refine (stale decay / hot boost)
    - Hard cap management (max 1000, prune lowest)
    """

    CACHE_TTL_SECONDS = 300   # 5 minutes
    MAX_KEYWORDS = 1000       # Hard cap (overridable via Settings: keyword_max_count)
    DEFAULT_TARGET = 200      # Dynamic threshold (configurable via Settings: keyword_target_count)

    def __init__(self, repository: Optional[AlchemyRiskKeywordRepository] = None):
        self._repo = repository or AlchemyRiskKeywordRepository()
        self._cache: List[RiskKeyword] = []
        self._cache_timestamp: float = 0.0

    # ──────────────────────────────────────────
    # Cached Access
    # ──────────────────────────────────────────

    def get_active_keywords(self) -> List[RiskKeyword]:
        """
        Get active keywords with in-memory caching (TTL-based).
        取得有效關鍵字（含快取）。
        """
        now = time.time()
        if not self._cache or (now - self._cache_timestamp) > self.CACHE_TTL_SECONDS:
            try:
                self._cache = self._repo.get_all(active_only=True)
                self._cache_timestamp = now
                logger.debug(f"RiskKeywordService: Refreshed cache with {len(self._cache)} active keywords.")
            except Exception as e:
                logger.warning(f"RiskKeywordService: Cache refresh failed: {e}")
                if self._cache:
                    return self._cache
                return []
        return self._cache

    def invalidate_cache(self) -> None:
        """
        Force cache invalidation.
        強制清除快取。
        """
        self._cache = []
        self._cache_timestamp = 0.0

    # ──────────────────────────────────────────
    # Scoring
    # ──────────────────────────────────────────

    def contains_risk(self, text: str) -> bool:
        """
        Check if text contains any active risk keyword.
        檢查文本是否包含任何有效風險關鍵字。
        """
        keywords = self.get_active_keywords()
        if not keywords:
            fallback = ["crash", "plunge", "fraud", "bankruptcy", "暴跌", "崩盤"]
            return any(kw in text.lower() for kw in fallback)
        text_lower = text.lower()
        return any(kw.keyword.lower() in text_lower for kw in keywords)

    def score_text(self, text: str, record_hits: bool = True) -> Tuple[float, List[str]]:
        """
        Score text against all active keywords. Returns (total_weight, matched_keywords).
        對文本進行加權評分。回傳 (總權重, 命中關鍵字列表)。
        """
        keywords = self.get_active_keywords()
        matched: List[str] = []
        total_weight = 0.0
        text_lower = text.lower()

        for kw in keywords:
            if kw.keyword.lower() in text_lower:
                matched.append(kw.keyword)
                total_weight += kw.weight
                if record_hits and kw.id:
                    try:
                        self._repo.record_hit(kw.id)
                    except Exception as e:
                        logger.debug(f"Non-critical: hit recording failed for {kw.id}: {e}")

        return total_weight, matched

    def record_hit(self, kw_id: str) -> None:
        """
        Record a keyword hit.
        記錄關鍵字命中。
        """
        try:
            self._repo.record_hit(kw_id)
        except Exception as e:
            logger.warning(f"RiskKeywordService: Failed to record hit for {kw_id}: {e}")

    # ──────────────────────────────────────────
    # Discovery Orchestrator
    # ──────────────────────────────────────────

    def discover_and_refine(self, target: int = None) -> Dict[str, Any]:
        """
        Full lifecycle orchestrator: discover from 3 sources → insert → prune → refine.
        完整生命週期：3 來源探索 → 插入 → 修剪 → 精煉。

        Args:
            target: Dynamic keyword target count (default: DEFAULT_TARGET from Settings or 200)
        """
        target = target or self._get_target_count()
        result = {
            "discovered": {"reports": 0, "webhook": 0, "trends": 0},
            "inserted": 0,
            "pruned": 0,
            "refined": {"decayed": 0, "boosted": 0},
            "total_after": 0,
            "errors": [],
        }

        # 1. Seed defaults first
        self.seed_if_needed()

        # 2. Discover from 3 sources
        all_candidates: List[Tuple[str, float, str, str]] = []  # (keyword, weight, category, source)

        # Source A: Reports
        try:
            report_kws = self._discover_from_reports()
            result["discovered"]["reports"] = len(report_kws)
            all_candidates.extend(report_kws)
        except Exception as e:
            result["errors"].append(f"reports: {e}")
            logger.warning(f"Discovery from reports failed: {e}")

        # Source B: Webhook news / event logs
        try:
            webhook_kws = self._discover_from_webhook_news()
            result["discovered"]["webhook"] = len(webhook_kws)
            all_candidates.extend(webhook_kws)
        except Exception as e:
            result["errors"].append(f"webhook: {e}")
            logger.warning(f"Discovery from webhook news failed: {e}")

        # Source C: Community trends
        try:
            trend_kws = self._discover_from_community_trends()
            result["discovered"]["trends"] = len(trend_kws)
            all_candidates.extend(trend_kws)
        except Exception as e:
            result["errors"].append(f"trends: {e}")
            logger.warning(f"Discovery from community trends failed: {e}")

        # 3. Insert discovered (dedup via UPSERT)
        inserted = 0
        for kw, weight, category, source in all_candidates:
            if self._repo.add_if_not_exists(kw, weight, category, source):
                inserted += 1
        result["inserted"] = inserted

        # 4. Prune if over dynamic MAX
        max_kw = self._get_max_keywords()
        current = self._repo.get_count(active_only=True)
        if current > max_kw:
            result["pruned"] = self._repo.prune_lowest(max_kw, protected_source="seed")

        # 5. Refine weights (decay stale + boost hot)
        refine_result = self.refine()
        result["refined"] = {
            "decayed": refine_result["decayed"],
            "boosted": refine_result["boosted"],
        }

        result["total_after"] = self._repo.get_count(active_only=True)
        self.invalidate_cache()

        logger.info(
            f"RiskKeywordService.discover_and_refine(): "
            f"Discovered {sum(result['discovered'].values())} candidates, "
            f"Inserted {inserted}, Pruned {result['pruned']}, "
            f"Total: {result['total_after']}"
        )
        return result

    def _get_target_count(self) -> int:
        """
        Get dynamic target from Settings, fallback to DEFAULT_TARGET.
        從設定取得動態目標關鍵字數量。
        """
        try:
            from src.services.settings_service import SettingsService
            svc = SettingsService()
            val = svc.get_setting("keyword_target_count")
            if val:
                return min(int(val), self._get_max_keywords())
        except Exception:
            pass
        return self.DEFAULT_TARGET

    def _get_max_keywords(self) -> int:
        """
        Get dynamic max keyword cap from Settings, fallback to MAX_KEYWORDS.
        從設定取得動態最大關鍵字上限（Rule #8: 動態指標原則）。
        """
        try:
            from src.services.settings_service import SettingsService
            svc = SettingsService()
            val = svc.get_setting("keyword_max_count")
            if val:
                return int(val)
        except Exception:
            pass
        return self.MAX_KEYWORDS

    # ──────────────────────────────────────────
    # Source A: Reports (LLM batch extract)
    # ──────────────────────────────────────────

    def _discover_from_reports(self) -> List[Tuple[str, float, str, str]]:
        """
        Extract keywords from past week's reports via LLM batch call.
        從過去一週報告中透過 LLM 批次提取關鍵字。

        Cost: ~$0.005 per call (gpt-4o-mini, ~1000 tokens)
        """
        from src.data.database import get_db_connection
        from sqlalchemy import text

        conn = get_db_connection()
        try:
            rows = conn.execute(text("""
                SELECT content FROM reports
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY created_at DESC
                LIMIT 10
            """)).fetchall()
        except Exception as e:
            logger.warning(f"Failed to query reports: {e}")
            return []
        finally:
            conn.close()

        if not rows:
            logger.debug("No recent reports for keyword discovery.")
            return []

        # Concatenate and truncate to save tokens
        combined_text = "\n---\n".join(r[0][:800] for r in rows)[:4000]

        return self._extract_keywords_via_llm(combined_text, source="report")

    def _extract_keywords_via_llm(self, text_block: str, source: str) -> List[Tuple[str, float, str, str]]:
        """
        Use LLM (gpt-4o-mini) to extract financial risk keywords from text.
        使用 LLM 從文本中提取金融風險關鍵字。

        Returns list of (keyword, weight, category, source).
        """
        import litellm

        prompt = """You are a financial risk keyword extractor. 
From the following financial reports/news text, extract 10-30 important risk/investment keywords.

Rules:
- Only return keywords that are useful for monitoring financial risk, market sentiment, or sector trends
- Include both English and Traditional Chinese keywords
- Assign weight 0.3-0.8 based on significance
- Assign category from: legal, financial, operational, geopolitical, market, macro, sentiment, sector
- Return ONLY valid JSON array

Output format:
[{"keyword": "...", "weight": 0.5, "category": "market"}, ...]

Text:
"""
        try:
            response = litellm.completion(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt + text_block}],
                temperature=0.3,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            data = json.loads(content)

            # Handle both {"keywords": [...]} and [...] formats
            if isinstance(data, dict):
                items = data.get("keywords", data.get("results", []))
            elif isinstance(data, list):
                items = data
            else:
                return []

            results = []
            for item in items:
                kw = item.get("keyword", "").strip().lower()
                if len(kw) >= 2 and kw not in _STOPWORDS:
                    weight = max(0.3, min(0.8, float(item.get("weight", 0.5))))
                    cat = item.get("category", "market")
                    results.append((kw, weight, cat, source))

            logger.info(f"LLM extracted {len(results)} keywords from {source}.")
            return results

        except Exception as e:
            logger.warning(f"LLM keyword extraction failed: {e}")
            return []

    # ──────────────────────────────────────────
    # Source B: Webhook News (TF-IDF, zero cost)
    # ──────────────────────────────────────────

    def _discover_from_webhook_news(self) -> List[Tuple[str, float, str, str]]:
        """
        Extract keywords from recent event_logs via TF-IDF (zero LLM cost).
        從最近的事件日誌透過 TF-IDF 提取關鍵字（零 LLM 成本）。
        """
        from src.data.database import get_db_connection
        from sqlalchemy import text

        conn = get_db_connection()
        try:
            rows = conn.execute(text("""
                SELECT title, content FROM event_logs
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY created_at DESC
                LIMIT 50
            """)).fetchall()
        except Exception as e:
            logger.warning(f"Failed to query event_logs: {e}")
            return []
        finally:
            conn.close()

        if not rows:
            logger.debug("No recent event_logs for keyword discovery.")
            return []

        # Combine all text
        all_text = " ".join(f"{r[0] or ''} {r[1] or ''}" for r in rows).lower()

        return self._extract_keywords_tfidf(all_text, source="webhook")

    def _extract_keywords_tfidf(self, text_block: str, source: str,
                                top_n: int = 30) -> List[Tuple[str, float, str, str]]:
        """
        Simple TF-based keyword extraction (no external deps).
        簡易 TF 關鍵字提取（無外部依賴）。
        """
        # Get existing keywords to avoid duplicates
        existing = {kw.keyword.lower() for kw in self.get_active_keywords()}

        # Tokenize: extract 1-gram and 2-grams
        words = re.findall(r'[a-zA-Z\u4e00-\u9fff]{2,}', text_block)
        # 1-grams
        candidates = Counter()
        for w in words:
            w_lower = w.lower()
            if w_lower not in _STOPWORDS and w_lower not in existing and len(w_lower) >= 3:
                candidates[w_lower] += 1

        # 2-grams (more specific terms)
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}".lower()
            if all(w.lower() not in _STOPWORDS for w in [words[i], words[i+1]]):
                if bigram not in existing and len(bigram) >= 5:
                    candidates[bigram] += 1

        # Filter: at least 2 occurrences
        results = []
        for term, count in candidates.most_common(top_n):
            if count >= 2:
                # Weight based on frequency (normalized 0.3 - 0.6)
                weight = min(0.6, 0.3 + (count * 0.05))
                results.append((term, weight, "market", source))

        logger.info(f"TF-IDF extracted {len(results)} keywords from {source}.")
        return results

    # ──────────────────────────────────────────
    # Source C: Community Trends (ApeWisdom + Finnhub + pytrends)
    # ──────────────────────────────────────────

    def _discover_from_community_trends(self) -> List[Tuple[str, float, str, str]]:
        """
        Fetch trending topics from community/trend APIs (fallback chain).
        從社群/趨勢 API 取得熱門主題（Fallback 鏈）。

        Provider chain: ApeWisdom → Finnhub → pytrends
        """
        results: List[Tuple[str, float, str, str]] = []
        existing = {kw.keyword.lower() for kw in self.get_active_keywords()}

        # Provider 1: ApeWisdom (Reddit/WSB trending)
        try:
            ape_kws = self._fetch_apewisdom()
            for kw in ape_kws:
                if kw.lower() not in existing:
                    results.append((kw.lower(), 0.5, "sentiment", "trends"))
                    existing.add(kw.lower())
        except Exception as e:
            logger.debug(f"ApeWisdom fetch failed: {e}")

        # Provider 2: Finnhub market news (already in project, reuse API key)
        try:
            finn_kws = self._fetch_finnhub_trending()
            for kw in finn_kws:
                if kw.lower() not in existing:
                    results.append((kw.lower(), 0.5, "market", "trends"))
                    existing.add(kw.lower())
        except Exception as e:
            logger.debug(f"Finnhub trending fetch failed: {e}")

        # Provider 3: Google Trends (fallback)
        try:
            gt_kws = self._fetch_google_trends()
            for kw in gt_kws:
                if kw.lower() not in existing:
                    results.append((kw.lower(), 0.4, "sentiment", "trends"))
                    existing.add(kw.lower())
        except Exception as e:
            logger.debug(f"Google Trends fetch failed: {e}")

        logger.info(f"Community trends discovered {len(results)} new keywords.")
        return results

    def _fetch_apewisdom(self, limit: int = 20) -> List[str]:
        """
        Fetch trending tickers from ApeWisdom (Reddit/WSB/crypto).
        從 ApeWisdom 取得 Reddit/WSB 熱門 ticker。

        API: https://apewisdom.io/api/v1.0/filter/all-stocks/
        Free, no key required.
        """
        import httpx

        resp = httpx.get(
            "https://apewisdom.io/api/v1.0/filter/all-stocks/",
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])

        keywords = []
        for item in results[:limit]:
            ticker = item.get("ticker", "")
            name = item.get("name", "")
            if ticker and len(ticker) <= 5:
                keywords.append(ticker)
            if name and len(name) >= 3:
                keywords.append(name.lower())

        return keywords

    def _fetch_finnhub_trending(self, limit: int = 15) -> List[str]:
        """
        Fetch trending keywords from Finnhub market news headlines.
        從 Finnhub 市場新聞標題提取趨勢關鍵字。

        Reuses existing integrated API key.
        """
        import httpx
        import os

        api_key = os.getenv("FINNHUB_API_KEY", "")
        if not api_key:
            return []

        resp = httpx.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": api_key},
            timeout=10.0,
        )
        resp.raise_for_status()
        articles = resp.json()

        # Extract frequent terms from headlines
        all_titles = " ".join(a.get("headline", "") for a in articles[:30])
        words = re.findall(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)*', all_titles)

        counter = Counter()
        for w in words:
            w_lower = w.lower()
            if w_lower not in _STOPWORDS and len(w_lower) >= 3:
                counter[w_lower] += 1

        return [term for term, count in counter.most_common(limit) if count >= 2]

    def _fetch_google_trends(self, limit: int = 15) -> List[str]:
        """
        Fetch trending searches from Google Trends via pytrends (fallback).
        透過 pytrends 取得 Google 搜尋趨勢（Fallback）。
        """
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.debug("pytrends not installed, skipping Google Trends.")
            return []

        pytrends = TrendReq(hl='en-US', tz=480, timeout=(5, 10))
        keywords = []

        for region in ['united_states', 'taiwan']:
            try:
                df = pytrends.trending_searches(pn=region)
                if df is not None and not df.empty:
                    for term in df[0].tolist()[:limit]:
                        term_lower = str(term).lower().strip()
                        if len(term_lower) >= 2:
                            keywords.append(term_lower)
            except Exception as e:
                logger.debug(f"Google Trends {region} failed: {e}")

        return keywords[:limit]

    # ──────────────────────────────────────────
    # Refine (Automated Weight Adjustment)
    # ──────────────────────────────────────────

    def refine(self, stale_days: int = 90, decay_step: float = 0.1,
               boost_step: float = 0.05, top_n: int = 15) -> Dict[str, Any]:
        """
        Automated keyword weight refinement:
        - Stale keywords (no hit in N days): decay weight by step (min 0.1)
        - Hot keywords (top by hit_count): boost weight by step (max 1.0)

        自動化關鍵字權重調整。
        """
        result = {"decayed": 0, "boosted": 0, "errors": []}

        try:
            stale = self._repo.get_stale_keywords(days_threshold=stale_days)
            for kw in stale:
                new_weight = max(0.1, kw.weight - decay_step)
                if new_weight != kw.weight:
                    self._repo.update_weight(kw.id, new_weight)
                    result["decayed"] += 1

            top = self._repo.get_top_keywords(limit=top_n)
            for kw in top:
                if kw.hit_count > 0:
                    new_weight = min(1.0, kw.weight + boost_step)
                    if new_weight != kw.weight:
                        self._repo.update_weight(kw.id, new_weight)
                        result["boosted"] += 1

            self.invalidate_cache()

            logger.info(
                f"RiskKeywordService.refine(): "
                f"Decayed {result['decayed']} stale, "
                f"Boosted {result['boosted']} hot keywords."
            )

        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"RiskKeywordService.refine() failed: {e}", exc_info=True)

        return result

    def seed_if_needed(self) -> None:
        """Seed default keywords if needed. 必要時補齊預設關鍵字。"""
        try:
            self._repo.seed_defaults()
            self.invalidate_cache()
        except Exception as e:
            logger.warning(f"RiskKeywordService: Seed failed: {e}")
