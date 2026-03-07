"""
Risk Keyword Repository — CRUD + Hit Tracking
風險關鍵字資料存取層 — CRUD + 命中追蹤

Follows Repository Pattern (see ADR-002).
遵循儲存庫模式。
"""
import uuid
import logging
import datetime
import typing
from abc import ABC, abstractmethod
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.domain.entities import RiskKeyword, RiskCategory

logger = logging.getLogger(__name__)

# Default seed keywords with weights (used on first init)
# 預設種子關鍵字與權重 (首次初始化時使用)
# Categories: legal, financial, operational, geopolitical, market, macro, sentiment, sector
DEFAULT_KEYWORDS = [
    # ─── LEGAL (法律風險) ───
    ("lawsuit", 0.9, "legal"),
    ("sec investigation", 0.9, "legal"),
    ("fraud", 0.9, "legal"),
    ("indictment", 0.85, "legal"),
    ("insider trading", 0.9, "legal"),
    ("class action", 0.8, "legal"),
    ("regulatory probe", 0.8, "legal"),
    ("antitrust", 0.7, "legal"),
    ("compliance violation", 0.75, "legal"),
    ("whistleblower", 0.7, "legal"),
    ("money laundering", 0.85, "legal"),
    ("patent infringement", 0.6, "legal"),
    ("訴訟", 0.9, "legal"),
    ("調查", 0.7, "legal"),
    ("詐欺", 0.9, "legal"),
    ("內線交易", 0.9, "legal"),
    ("集體訴訟", 0.8, "legal"),

    # ─── FINANCIAL (財務風險) ───
    ("bankruptcy", 0.9, "financial"),
    ("default", 0.8, "financial"),
    ("credit downgrade", 0.85, "financial"),
    ("downgrade", 0.7, "financial"),
    ("debt restructuring", 0.75, "financial"),
    ("earnings miss", 0.7, "financial"),
    ("revenue decline", 0.65, "financial"),
    ("guidance cut", 0.75, "financial"),
    ("dividend cut", 0.7, "financial"),
    ("write-off", 0.65, "financial"),
    ("impairment", 0.65, "financial"),
    ("liquidity warning", 0.8, "financial"),
    ("going concern", 0.9, "financial"),
    ("profit warning", 0.75, "financial"),
    ("破產", 0.9, "financial"),
    ("降評", 0.7, "financial"),
    ("財務預警", 0.8, "financial"),
    ("盈利下滑", 0.65, "financial"),
    ("下修財測", 0.75, "financial"),

    # ─── OPERATIONAL (營運風險) ───
    ("recall", 0.7, "operational"),
    ("data breach", 0.75, "operational"),
    ("cybersecurity incident", 0.8, "operational"),
    ("layoff", 0.6, "operational"),
    ("mass layoff", 0.75, "operational"),
    ("ceo resignation", 0.7, "operational"),
    ("cfo departure", 0.7, "operational"),
    ("supply chain disruption", 0.65, "operational"),
    ("factory shutdown", 0.7, "operational"),
    ("product defect", 0.65, "operational"),
    ("fda rejection", 0.8, "operational"),
    ("production halt", 0.7, "operational"),
    ("召回", 0.7, "operational"),
    ("裁員", 0.6, "operational"),
    ("資安事件", 0.75, "operational"),
    ("高管離職", 0.7, "operational"),
    ("停產", 0.7, "operational"),

    # ─── GEOPOLITICAL (地緣政治) ───
    ("sanctions", 0.75, "geopolitical"),
    ("tariff", 0.9, "geopolitical"),
    ("trade war", 0.85, "geopolitical"),
    ("war", 0.65, "geopolitical"),
    ("embargo", 0.7, "geopolitical"),
    ("rare earth exports", 0.85, "geopolitical"),
    ("invasion", 0.85, "geopolitical"),
    ("missile", 0.75, "geopolitical"),
    ("air strike", 0.8, "geopolitical"),
    ("nuclear", 0.8, "geopolitical"),
    ("coup", 0.75, "geopolitical"),
    ("ceasefire", 0.6, "geopolitical"),
    ("martial law", 0.8, "geopolitical"),
    ("blockade", 0.75, "geopolitical"),
    ("strait of hormuz", 0.8, "geopolitical"),
    ("taiwan strait", 0.85, "geopolitical"),
    ("south china sea", 0.7, "geopolitical"),
    ("nato", 0.5, "geopolitical"),
    ("制裁", 0.75, "geopolitical"),
    ("關稅", 0.9, "geopolitical"),
    ("稀土出口", 0.85, "geopolitical"),
    ("戰爭", 0.65, "geopolitical"),
    ("空襲", 0.8, "geopolitical"),
    ("台海", 0.85, "geopolitical"),
    ("封鎖", 0.75, "geopolitical"),
    ("政變", 0.75, "geopolitical"),

    # ─── MARKET (市場風險) ───
    ("crash", 0.85, "market"),
    ("margin call", 0.8, "market"),
    ("delisted", 0.9, "market"),
    ("short squeeze", 0.65, "market"),
    ("bubble", 0.6, "market"),
    ("flash crash", 0.85, "market"),
    ("circuit breaker", 0.85, "market"),
    ("trading halt", 0.8, "market"),
    ("bear market", 0.6, "market"),
    ("correction", 0.5, "market"),
    ("contagion", 0.8, "market"),
    ("bank run", 0.9, "market"),
    ("credit crunch", 0.85, "market"),
    ("black swan", 0.9, "market"),
    ("liquidity crisis", 0.85, "market"),
    ("崩盤", 0.85, "market"),
    ("熔斷", 0.85, "market"),
    ("停牌", 0.8, "market"),
    ("暴跌", 0.85, "market"),
    ("擠兌", 0.9, "market"),
    ("回補庫存", 0.7, "market"),

    # ─── MACRO (總經指標) ───
    ("rate hike", 0.75, "macro"),
    ("rate cut", 0.65, "macro"),
    ("quantitative easing", 0.6, "macro"),
    ("quantitative tightening", 0.7, "macro"),
    ("inflation surge", 0.8, "macro"),
    ("cpi above expectations", 0.75, "macro"),
    ("deflation", 0.7, "macro"),
    ("recession", 0.85, "macro"),
    ("stagflation", 0.8, "macro"),
    ("yield curve inversion", 0.8, "macro"),
    ("unemployment spike", 0.75, "macro"),
    ("gdp contraction", 0.8, "macro"),
    ("pmi below 50", 0.7, "macro"),
    ("fed pivot", 0.65, "macro"),
    ("debt ceiling", 0.75, "macro"),
    ("sovereign debt crisis", 0.85, "macro"),
    ("加息", 0.75, "macro"),
    ("降息", 0.65, "macro"),
    ("通膨", 0.8, "macro"),
    ("衰退", 0.85, "macro"),
    ("滯脹", 0.8, "macro"),
    ("殖利率倒掛", 0.8, "macro"),
    ("失業率飆升", 0.75, "macro"),
    ("量化緊縮", 0.7, "macro"),

    # ─── SENTIMENT (市場情緒) ───
    ("panic selling", 0.85, "sentiment"),
    ("capitulation", 0.8, "sentiment"),
    ("euphoria", 0.6, "sentiment"),
    ("fomo", 0.55, "sentiment"),
    ("risk-off", 0.7, "sentiment"),
    ("flight to safety", 0.7, "sentiment"),
    ("investor exodus", 0.75, "sentiment"),
    ("fund outflow", 0.7, "sentiment"),
    ("record inflow", 0.55, "sentiment"),
    ("extreme fear", 0.8, "sentiment"),
    ("extreme greed", 0.6, "sentiment"),
    ("vix spike", 0.75, "sentiment"),
    ("put-call ratio surge", 0.7, "sentiment"),
    ("恐慌拋售", 0.85, "sentiment"),
    ("避險", 0.7, "sentiment"),
    ("資金外逃", 0.75, "sentiment"),
    ("恐慌", 0.8, "sentiment"),
    ("投降式賣壓", 0.8, "sentiment"),

    # ─── SECTOR (板塊趨勢) ───
    ("ai chip shortage", 0.7, "sector"),
    ("semiconductor shortage", 0.75, "sector"),
    ("chip export ban", 0.85, "sector"),
    ("ev subsidy", 0.6, "sector"),
    ("ev sales decline", 0.65, "sector"),
    ("biotech breakthrough", 0.55, "sector"),
    ("drug approval", 0.6, "sector"),
    ("drug trial failure", 0.8, "sector"),
    ("clean energy policy", 0.55, "sector"),
    ("oil price shock", 0.8, "sector"),
    ("opec cut", 0.7, "sector"),
    ("fintech regulation", 0.65, "sector"),
    ("crypto crash", 0.75, "sector"),
    ("real estate crisis", 0.8, "sector"),
    ("ai regulation", 0.6, "sector"),
    ("半導體禁令", 0.85, "sector"),
    ("電動車補貼", 0.6, "sector"),
    ("油價暴漲", 0.8, "sector"),
    ("地產危機", 0.8, "sector"),
    ("藥物試驗失敗", 0.8, "sector"),
]

class IRiskKeywordRepository(ABC):
    """
    Interface for Risk Keyword Repository.
    風險關鍵字儲存庫介面。
    """
    @abstractmethod
    def seed_defaults(self) -> None:
        """Insert default keywords if table is empty."""
        pass

    @abstractmethod
    def get_all(self, active_only: bool = False) -> List[RiskKeyword]:
        """Get all keywords."""
        pass

    @abstractmethod
    def get_by_category(self, category: str) -> List[RiskKeyword]:
        """Get keywords by category."""
        pass

    @abstractmethod
    def add(self, keyword: str, weight: float = 0.5, category: str = "custom") -> RiskKeyword:
        """Add a new keyword."""
        pass

    @abstractmethod
    def update_weight(self, kw_id: str, new_weight: float) -> None:
        """Update keyword weight."""
        pass

    @abstractmethod
    def toggle_active(self, kw_id: str, is_active: bool) -> None:
        """Toggle active status."""
        pass

    @abstractmethod
    def delete(self, kw_id: str) -> None:
        """Delete a keyword."""
        pass

    @abstractmethod
    def record_hit(self, kw_id: str) -> None:
        """Record a keyword hit."""
        pass

    @abstractmethod
    def get_stale_keywords(self, days_threshold: int = 90) -> List[RiskKeyword]:
        """Get keywords with no hits or old hits."""
        pass

    @abstractmethod
    def get_top_keywords(self, limit: int = 10) -> List[RiskKeyword]:
        """Get top keywords by hit count."""
        pass

    @abstractmethod
    def close_session(self) -> None:
        """Close the database session."""
        pass

    @abstractmethod
    def add_if_not_exists(self, keyword: str, weight: float = 0.5,
                          category: str = "custom", source: str = "seed") -> bool:
        """Insert keyword if it doesn't exist. Returns True if inserted."""
        pass

    @abstractmethod
    def get_count(self, active_only: bool = True) -> int:
        """Get total keyword count."""
        pass

    @abstractmethod
    def prune_lowest(self, target_count: int, protected_source: str = "seed") -> int:
        """Delete lowest-weight keywords above target_count. Returns number deleted."""
        pass

class AlchemyRiskKeywordRepository(BaseRepository, IRiskKeywordRepository):
    """
    Implementation of IRiskKeywordRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IRiskKeywordRepository。
    """

    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        engine = engine or get_db_engine(db_path)
        BaseRepository.__init__(self, engine)

    def seed_defaults(self) -> None:
        """
        Insert default keywords, skipping any that already exist (by keyword text).
        插入預設關鍵字，跳過已存在的。使用 ON CONFLICT DO NOTHING 防止重複。
        """
        with self.engine.begin() as conn:
            inserted = 0
            for keyword, weight, category in DEFAULT_KEYWORDS:
                result = conn.execute(
                    text("""
                        INSERT INTO risk_keywords (id, keyword, weight, category, hit_count, is_active, created_at)
                        VALUES (:id, :keyword, :weight, :category, 0, 1, :created_at)
                        ON CONFLICT (keyword) DO NOTHING
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "keyword": keyword,
                        "weight": weight,
                        "category": category,
                        "created_at": datetime.datetime.now(),
                    }
                )
                if result.rowcount > 0:
                    inserted += 1
            if inserted > 0:
                logger.info(f"Seeded {inserted} new risk keywords (skipped {len(DEFAULT_KEYWORDS) - inserted} existing).")
            else:
                logger.info(f"All {len(DEFAULT_KEYWORDS)} default keywords already exist.")

    def get_all(self, active_only: bool = False) -> List[RiskKeyword]:
        """
        Get all keywords (PostgreSQL optimized).
        取得所有關鍵字。
        """
        with self.engine.connect() as conn:
            if active_only:
                query = text("SELECT * FROM risk_keywords WHERE is_active = 1 ORDER BY weight DESC")
            else:
                query = text("SELECT * FROM risk_keywords ORDER BY weight DESC")
            rows = conn.execute(query).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_by_category(self, category: str) -> List[RiskKeyword]:
        """
        Get keywords filtered by category.
        依類別篩選關鍵字。
        """
        with self.engine.connect() as conn:
            query = text("SELECT * FROM risk_keywords WHERE category = :cat ORDER BY weight DESC")
            rows = conn.execute(query, {"cat": category}).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def add(self, keyword: str, weight: float = 0.5, category: str = "custom") -> RiskKeyword:
        """
        Add a new keyword.
        新增關鍵字。
        """
        kw_id = str(uuid.uuid4())
        now = datetime.datetime.now()
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO risk_keywords (id, keyword, weight, category, hit_count, is_active, created_at)
                    VALUES (:id, :keyword, :weight, :category, 0, 1, :created_at)
                """),
                {"id": kw_id, "keyword": keyword, "weight": weight, "category": category, "created_at": now}
            )
        # Validate category or fallback to CUSTOM
        try:
            cat_enum = RiskCategory(category.lower()) if isinstance(category, str) else category
        except ValueError:
            cat_enum = RiskCategory.CUSTOM

        return RiskKeyword(
            id=kw_id, keyword=keyword, weight=weight,
            category=cat_enum, hit_count=0, is_active=True, created_at=now
        )

    def update_weight(self, kw_id: str, new_weight: float) -> None:
        """
        Update keyword weight.
        更新權重。
        """
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE risk_keywords SET weight = :w WHERE id = :id"),
                {"w": new_weight, "id": kw_id}
            )

    def toggle_active(self, kw_id: str, is_active: bool) -> None:
        """
        Enable or disable a keyword.
        啟用或停用關鍵字。
        """
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE risk_keywords SET is_active = :a WHERE id = :id"),
                {"a": 1 if is_active else 0, "id": kw_id}
            )

    def delete(self, kw_id: str) -> None:
        """
        Permanently delete a keyword.
        刪除關鍵字。
        """
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM risk_keywords WHERE id = :id"), {"id": kw_id})

    def record_hit(self, kw_id: str) -> None:
        """
        Increment hit_count and update last_hit_date.
        記錄命中。
        """
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE risk_keywords 
                    SET hit_count = hit_count + 1, last_hit_date = :date 
                    WHERE id = :id
                """),
                {"date": datetime.date.today().isoformat(), "id": kw_id}
            )

    def get_stale_keywords(self, days_threshold: int = 90) -> List[RiskKeyword]:
        """
        Find keywords that haven't triggered in N days (PostgreSQL).
        取得過期的關鍵字。
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT * FROM risk_keywords 
                WHERE is_active = 1 AND (
                    last_hit_date IS NULL OR 
                    CURRENT_DATE - CAST(last_hit_date AS DATE) > :days
                )
                ORDER BY hit_count ASC
            """)
                
            rows = conn.execute(query, {"days": days_threshold}).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_top_keywords(self, limit: int = 10) -> List[RiskKeyword]:
        """
        Get most frequently triggered keywords.
        取得熱門關鍵字。
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM risk_keywords ORDER BY hit_count DESC LIMIT :lim"),
                {"lim": limit}
            ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    @staticmethod
    def _row_to_entity(row: Any) -> RiskKeyword:
        if row is None:
            return None
        # Handle both SQLAlchemy Row and dictionary-like mapping
        try:
             # Try mapping first (SQLAlchemy 1.4/2.0)
             r = row._mapping
             
             try:
                 cat_val = r['category']
                 cat_enum = RiskCategory(cat_val.lower()) if isinstance(cat_val, str) else cat_val
             except (ValueError, KeyError):
                 cat_enum = RiskCategory.CUSTOM

             return RiskKeyword(
                 id=r['id'],
                 keyword=r['keyword'],
                 weight=float(r['weight']),
                 category=cat_enum,
                 hit_count=int(r['hit_count']),
                 last_hit_date=r.get('last_hit_date'),
                 is_active=bool(r['is_active']),
                 created_at=r['created_at']
             )
        except AttributeError:
             # Fallback to index-based for older versions or edge cases
             try:
                 cat_val = row[3]
                 cat_enum = RiskCategory(cat_val.lower()) if isinstance(cat_val, str) else cat_val
             except (ValueError, IndexError):
                 cat_enum = RiskCategory.CUSTOM

             return RiskKeyword(
                 id=row[0],
                 keyword=row[1],
                 weight=float(row[2]),
                 category=cat_enum,
                 hit_count=int(row[4]),
                 last_hit_date=row[5],
                 is_active=bool(row[6]),
                 created_at=row[7]
             )

    # ──────────────────────────────────────────
    # Discovery Support Methods
    # ──────────────────────────────────────────

    def add_if_not_exists(self, keyword: str, weight: float = 0.5,
                          category: str = "custom", source: str = "seed") -> bool:
        """
        Insert keyword if it doesn't exist (UPSERT). Returns True if inserted.
        若關鍵字不存在則新增。回傳 True 代表已新增。
        """
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO risk_keywords (id, keyword, weight, category, hit_count, is_active, source, created_at)
                    VALUES (:id, :keyword, :weight, :category, 0, 1, :source, :created_at)
                    ON CONFLICT (keyword) DO NOTHING
                """),
                {
                    "id": str(uuid.uuid4()),
                    "keyword": keyword.lower().strip(),
                    "weight": weight,
                    "category": category,
                    "source": source,
                    "created_at": datetime.datetime.now(),
                }
            )
            return result.rowcount > 0

    def get_count(self, active_only: bool = True) -> int:
        """
        Get total keyword count.
        取得關鍵字總數。
        """
        with self.engine.connect() as conn:
            q = "SELECT COUNT(*) FROM risk_keywords"
            if active_only:
                q += " WHERE is_active = 1"
            return conn.execute(text(q)).scalar() or 0

    def prune_lowest(self, target_count: int, protected_source: str = "seed") -> int:
        """
        Delete lowest-weight non-protected keywords to bring total down to target_count.
        刪除最低權重的非保護來源關鍵字，使總數降至目標數。
        Returns number of keywords deleted.
        """
        current = self.get_count(active_only=True)
        if current <= target_count:
            return 0

        to_delete = current - target_count
        with self.engine.begin() as conn:
            # Get IDs of lowest-weight non-protected keywords
            rows = conn.execute(
                text("""
                    SELECT id FROM risk_keywords
                    WHERE is_active = 1
                      AND (source IS NULL OR source != :protected)
                    ORDER BY weight ASC, hit_count ASC
                    LIMIT :limit
                """),
                {"protected": protected_source, "limit": to_delete}
            ).fetchall()

            if not rows:
                return 0

            ids = [r[0] for r in rows]
            # Delete one by one with parameterized query (cross-DB safe)
            for kw_id in ids:
                conn.execute(
                    text("DELETE FROM risk_keywords WHERE id = :id"),
                    {"id": kw_id}
                )
            logger.info(f"Pruned {len(ids)} lowest-weight keywords (target: {target_count}).")
            return len(ids)
