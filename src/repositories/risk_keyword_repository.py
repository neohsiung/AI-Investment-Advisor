"""
Risk Keyword Repository — CRUD + Hit Tracking
風險關鍵字資料存取層 — CRUD + 命中追蹤

Follows Repository Pattern (see ADR-002).
遵循儲存庫模式。
"""
import uuid
import logging
import datetime
from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict
from sqlalchemy import text
from src.data.database import BaseRepository, get_db_engine
from src.domain.entities import RiskKeyword, RiskCategory

logger = logging.getLogger(__name__)

# Default seed keywords with weights (used on first init)
# 預設種子關鍵字與權重 (首次初始化時使用)
DEFAULT_KEYWORDS = [
    ("lawsuit", 0.9, "legal"),
    ("sec investigation", 0.9, "legal"),
    ("fraud", 0.9, "legal"),
    ("indictment", 0.85, "legal"),
    ("antitrust", 0.7, "legal"),
    ("bankruptcy", 0.9, "financial"),
    ("default", 0.8, "financial"),
    ("credit downgrade", 0.85, "financial"),
    ("downgrade", 0.7, "financial"),
    ("debt restructuring", 0.75, "financial"),
    ("recall", 0.7, "operational"),
    ("data breach", 0.75, "operational"),
    ("layoff", 0.6, "operational"),
    ("ceo resignation", 0.7, "operational"),
    ("supply chain disruption", 0.65, "operational"),
    ("sanctions", 0.75, "geopolitical"),
    ("tariff", 0.7, "geopolitical"),
    ("trade war", 0.7, "geopolitical"),
    ("war", 0.65, "geopolitical"),
    ("embargo", 0.7, "geopolitical"),
    ("crash", 0.85, "market"),
    ("margin call", 0.8, "market"),
    ("delisted", 0.9, "market"),
    ("short squeeze", 0.65, "market"),
    ("bubble", 0.6, "market"),
    ("訴訟", 0.9, "legal"),
    ("調查", 0.7, "legal"),
    ("詐欺", 0.9, "legal"),
    ("破產", 0.9, "financial"),
    ("降評", 0.7, "financial"),
    ("召回", 0.7, "operational"),
    ("裁員", 0.6, "operational"),
    ("資安事件", 0.75, "operational"),
    ("制裁", 0.75, "geopolitical"),
    ("關稅", 0.7, "geopolitical"),
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

class RiskKeywordRepositoryImpl(BaseRepository, IRiskKeywordRepository):
    """
    Implementation of IRiskKeywordRepository using SQLAlchemy.
    使用 SQLAlchemy 實作的 IRiskKeywordRepository。
    """

    def __init__(self, db_path: str = None, engine: Any = None):
        """
        Initialize the repository.
        初始化儲存庫。
        """
        BaseRepository.__init__(self, engine or get_db_engine(db_path))

    def seed_defaults(self) -> None:
        """
        Insert default keywords if table is empty.
        若表為空則插入預設關鍵字。
        """
        with self.engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM risk_keywords")).scalar()
            
            if count > 0:
                logger.info(f"Risk keywords table already has {count} entries, skipping seed.")
                return
            
            for keyword, weight, category in DEFAULT_KEYWORDS:
                conn.execute(
                    text("""
                        INSERT INTO risk_keywords (id, keyword, weight, category, hit_count, is_active, created_at)
                        VALUES (:id, :keyword, :weight, :category, 0, 1, :created_at)
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "keyword": keyword,
                        "weight": weight,
                        "category": category,
                        "created_at": datetime.datetime.now(),
                    }
                )
            logger.info(f"Seeded {len(DEFAULT_KEYWORDS)} default risk keywords.")

    def get_all(self, active_only: bool = False) -> List[RiskKeyword]:
        """
        Get all keywords (ORM-eligible but using Core for performance).
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
        return RiskKeyword(
            id=kw_id, keyboard=keyword, weight=weight,
            category=RiskCategory(category), hit_count=0, is_active=True, created_at=now
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
        Find keywords that haven't triggered in N days.
        取得過期的關鍵字。
        """
        with self.engine.connect() as conn:
            is_sqlite = 'sqlite' in str(conn.engine.url)
            if is_sqlite:
                query = text("""
                    SELECT * FROM risk_keywords 
                    WHERE is_active = 1 AND (
                        last_hit_date IS NULL OR 
                        julianday('now') - julianday(last_hit_date) > :days
                    )
                    ORDER BY hit_count ASC
                """)
            else:
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
        """
        Convert a DB row to a RiskKeyword entity.
        將資料列轉換為實體。
        """
        try:
            # SQLAlchemy Row supports attribute access
            category_str = row.category if hasattr(row, 'category') else row[3]
            cat = RiskCategory(category_str) if category_str else RiskCategory.CUSTOM
        except ValueError:
            cat = RiskCategory.CUSTOM
            
        return RiskKeyword(
            id=row.id if hasattr(row, 'id') else row[0],
            keyword=row.keyword if hasattr(row, 'keyword') else row[1],
            weight=row.weight if hasattr(row, 'weight') else row[2],
            category=cat,
            hit_count=row.hit_count if hasattr(row, 'hit_count') else row[4],
            last_hit_date=row.last_hit_date if hasattr(row, 'last_hit_date') else row[5],
            is_active=bool(row.is_active if hasattr(row, 'is_active') else row[6]),
            created_at=row.created_at if hasattr(row, 'created_at') else row[7],
        )

# Legacy alias
RiskKeywordRepository = RiskKeywordRepositoryImpl
