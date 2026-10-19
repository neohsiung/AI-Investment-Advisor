"""ORM for `charter_events` (alembic 032). Lives here, not in models.py, because models.py is over the size ratchet;
src.data.models re-exports it so ``from src.data.models import CharterEvent`` and Base.metadata both see it.
`charter_events`（遷移 032）的 ORM；models.py 已超過行數棘輪，故放此處並由 models.py 重新匯出。
"""
from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Index, Integer, JSON, String, func

from src.data.models import Base


class CharterEvent(Base):
    """Append-only audit log of the change engine (verdict / apply / rollback / degrade / ...). 變更引擎的僅追加稽核紀錄。"""
    __tablename__ = 'charter_events'

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)
    kind = Column(String(16), nullable=False)
    key = Column(String(128))
    payload_json = Column(JSON)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("kind IN ('verdict', 'apply', 'rollback', 'freeze', 'resume', 'degrade', 'digest', 'drill', "
                        "'enable')", name='ck_charter_events_kind'),
        Index('ix_charter_events_user_kind_created', 'user_id', 'kind', 'created_at'),
    )
