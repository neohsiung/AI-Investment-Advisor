"""
Risk Keyword Repository — CRUD + Hit Tracking
風險關鍵字資料存取層 — CRUD + 命中追蹤

Follows Repository Pattern (see ADR-002).
"""
import uuid
import logging
from typing import List, Optional
from datetime import datetime, date

from sqlalchemy import text

from src.data.database import get_db_connection
from src.domain.entities import RiskKeyword, RiskCategory

logger = logging.getLogger(__name__)

# Default seed keywords with weights (used on first init)
# 預設種子關鍵字與權重 (首次初始化時使用)
DEFAULT_KEYWORDS = [
    # Legal (法律風險) — weight 0.9 (highest urgency)
    ("lawsuit", 0.9, "legal"),
    ("sec investigation", 0.9, "legal"),
    ("fraud", 0.9, "legal"),
    ("indictment", 0.85, "legal"),
    ("antitrust", 0.7, "legal"),
    # Financial (財務風險) — weight 0.85
    ("bankruptcy", 0.9, "financial"),
    ("default", 0.8, "financial"),
    ("credit downgrade", 0.85, "financial"),
    ("downgrade", 0.7, "financial"),
    ("debt restructuring", 0.75, "financial"),
    # Operational (營運風險) — weight 0.65
    ("recall", 0.7, "operational"),
    ("data breach", 0.75, "operational"),
    ("layoff", 0.6, "operational"),
    ("ceo resignation", 0.7, "operational"),
    ("supply chain disruption", 0.65, "operational"),
    # Geopolitical (地緣政治) — weight 0.7
    ("sanctions", 0.75, "geopolitical"),
    ("tariff", 0.7, "geopolitical"),
    ("trade war", 0.7, "geopolitical"),
    ("war", 0.65, "geopolitical"),
    ("embargo", 0.7, "geopolitical"),
    # Market (市場風險) — weight 0.8
    ("crash", 0.85, "market"),
    ("margin call", 0.8, "market"),
    ("delisted", 0.9, "market"),
    ("short squeeze", 0.65, "market"),
    ("bubble", 0.6, "market"),
    # Chinese keywords (中文關鍵字) — mirror weights
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


class RiskKeywordRepository:
    """
    Repository for Risk Keywords with CRUD + Analytics.
    風險關鍵字資料庫操作 (新增/讀取/更新/刪除 + 分析)。
    """

    def __init__(self, db_path=None):
        self.db_path = db_path

    def _get_conn(self):
        return get_db_connection(self.db_path)

    # ──────────────────────────────────────────
    # Seed (First Init)
    # ──────────────────────────────────────────

    def seed_defaults(self):
        """
        Insert default keywords if table is empty.
        若表為空則插入預設關鍵字。
        """
        with self._get_conn() as conn:
            count = conn.execute(
                text("SELECT COUNT(*) FROM risk_keywords")
            ).scalar()
            
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
                        "created_at": datetime.now().isoformat(),
                    }
                )
            conn.commit()
            logger.info(f"Seeded {len(DEFAULT_KEYWORDS)} default risk keywords.")

    # ──────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────

    def get_all(self, active_only: bool = False) -> List[RiskKeyword]:
        """Get all keywords, optionally filtered by active status."""
        with self._get_conn() as conn:
            if active_only:
                rows = conn.execute(
                    text("SELECT * FROM risk_keywords WHERE is_active = 1 ORDER BY weight DESC")
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM risk_keywords ORDER BY weight DESC")
                ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_by_category(self, category: str) -> List[RiskKeyword]:
        """Get keywords filtered by category."""
        with self._get_conn() as conn:
            rows = conn.execute(
                text("SELECT * FROM risk_keywords WHERE category = :cat ORDER BY weight DESC"),
                {"cat": category}
            ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def add(self, keyword: str, weight: float = 0.5, category: str = "custom") -> RiskKeyword:
        """Add a new keyword. Returns the created entity."""
        kw_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            conn.execute(
                text("""
                    INSERT INTO risk_keywords (id, keyword, weight, category, hit_count, is_active, created_at)
                    VALUES (:id, :keyword, :weight, :category, 0, 1, :created_at)
                """),
                {"id": kw_id, "keyword": keyword, "weight": weight, "category": category, "created_at": now}
            )
            conn.commit()
        return RiskKeyword(
            id=kw_id, keyword=keyword, weight=weight,
            category=RiskCategory(category), hit_count=0, is_active=True, created_at=now
        )

    def update_weight(self, kw_id: str, new_weight: float):
        """Update keyword weight."""
        with self._get_conn() as conn:
            conn.execute(
                text("UPDATE risk_keywords SET weight = :w WHERE id = :id"),
                {"w": new_weight, "id": kw_id}
            )
            conn.commit()

    def toggle_active(self, kw_id: str, is_active: bool):
        """Enable or disable a keyword."""
        with self._get_conn() as conn:
            conn.execute(
                text("UPDATE risk_keywords SET is_active = :a WHERE id = :id"),
                {"a": 1 if is_active else 0, "id": kw_id}
            )
            conn.commit()

    def delete(self, kw_id: str):
        """Permanently delete a keyword."""
        with self._get_conn() as conn:
            conn.execute(
                text("DELETE FROM risk_keywords WHERE id = :id"),
                {"id": kw_id}
            )
            conn.commit()

    # ──────────────────────────────────────────
    # Hit Tracking (命中追蹤)
    # ──────────────────────────────────────────

    def record_hit(self, kw_id: str):
        """Increment hit_count and update last_hit_date."""
        with self._get_conn() as conn:
            conn.execute(
                text("""
                    UPDATE risk_keywords 
                    SET hit_count = hit_count + 1, last_hit_date = :date 
                    WHERE id = :id
                """),
                {"date": date.today().isoformat(), "id": kw_id}
            )
            conn.commit()

    # ──────────────────────────────────────────
    # Analytics / Review (復盤)
    # ──────────────────────────────────────────

    def get_stale_keywords(self, days_threshold: int = 90) -> List[RiskKeyword]:
        """
        Find keywords that haven't triggered in N days (候選清除名單).
        Returns keywords with no hits or last_hit_date older than threshold.
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                text("""
                    SELECT * FROM risk_keywords 
                    WHERE is_active = 1 AND (
                        last_hit_date IS NULL OR 
                        julianday('now') - julianday(last_hit_date) > :days
                    )
                    ORDER BY hit_count ASC
                """),
                {"days": days_threshold}
            ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_top_keywords(self, limit: int = 10) -> List[RiskKeyword]:
        """Get most frequently triggered keywords."""
        with self._get_conn() as conn:
            rows = conn.execute(
                text("SELECT * FROM risk_keywords ORDER BY hit_count DESC LIMIT :lim"),
                {"lim": limit}
            ).fetchall()
            return [self._row_to_entity(row) for row in rows]

    # ──────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────

    @staticmethod
    def _row_to_entity(row) -> RiskKeyword:
        """Convert a DB row to a RiskKeyword entity."""
        try:
            cat = RiskCategory(row[3]) if row[3] else RiskCategory.CUSTOM
        except ValueError:
            cat = RiskCategory.CUSTOM
        return RiskKeyword(
            id=row[0],
            keyword=row[1],
            weight=row[2] or 0.5,
            category=cat,
            hit_count=row[4] or 0,
            last_hit_date=row[5],
            is_active=bool(row[6]),
            created_at=row[7],
        )
