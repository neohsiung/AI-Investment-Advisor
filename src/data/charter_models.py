"""ORM for `charter_events` (alembic 032) and `charter_state` (028, 033). Lives here, not in models.py, because models.py is over the size ratchet;
src.data.models re-exports it so ``from src.data.models import CharterEvent`` and Base.metadata both see it.
`charter_events`（遷移 032）與 `charter_state`（028／033）的 ORM；models.py 已超過行數棘輪，故放此處並由 models.py 重新匯出。
"""
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, Index, Integer, JSON, String, Text,
                        func, text)

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


class CharterState(Base):
    """`charter_state` — singleton row (id = 1): the engine's operating mode, the human stop flag and (033) the halt
    bookkeeping. 單列：引擎模式、人工停止旗標與（033）停機簿記。"""
    __tablename__ = 'charter_state'

    id = Column(Integer, primary_key=True)
    mode = Column(String(16), nullable=False, server_default=text("'dry_run'"))
    reason = Column(Text)
    since = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    human_stop = Column(Boolean, nullable=False, server_default=text("false"))
    clears_on = Column(Date)                        # 033: display only; auto-resume keys on the next watchdog pass
    breach_ids = Column(JSON)                       # 033: the K ids that caused the freeze
    resume_mode = Column(String(16))                # 033: the mode to restore on resume
    updated_at = Column(DateTime(timezone=True))    # 033: set explicitly by every writer

    __table_args__ = (
        CheckConstraint("id = 1", name='ck_charter_state_singleton'),
        CheckConstraint("mode IN ('dry_run', 'apply', 'tighten_only', 'frozen', 'human_stop')",
                        name='ck_charter_state_mode'),
    )
