from sqlalchemy import Column, String, Text, DateTime, Numeric, Integer, ForeignKey, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    preferences = Column(JSON, default={})
    meta = Column("metadata", JSON, default={}) # Rename to avoid conflict with Base.metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))

class UserIdentity(Base):
    """
    Stores multiple identity providers (Email, LINE, Telegram, Phone) linked to a single UUID user.
    """
    __tablename__ = 'user_identities'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    provider = Column(String, nullable=False) # 'email', 'line', 'telegram', 'phone'
    identifier = Column(String, nullable=False) # the actual email, line_id, etc.
    is_primary = Column(Integer, default=0) # 1 for primary, 0 for secondary
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Setting(Base):
    __tablename__ = 'settings'
    
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    key = Column(String, primary_key=True)
    value = Column(JSON)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class EventLog(Base):
    __tablename__ = 'event_logs'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='SET NULL'))
    event_type = Column(String, nullable=False)
    severity = Column(String)
    title = Column(String, nullable=False)
    content = Column(Text)
    meta = Column("metadata", JSON, default={}) # Rename to avoid conflict with Base.metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ChannelVerification(Base):
    __tablename__ = 'channel_verifications'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String)
    channel = Column(String)
    channel_user_id = Column(String)
    code = Column(String)
    status = Column(String, default='pending')
    error_message = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class RiskKeyword(Base):
    __tablename__ = 'risk_keywords'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    keyword = Column(String, nullable=False)
    weight = Column(Numeric(18, 8), default=0.5)
    category = Column(String, default='custom')
    hit_count = Column(Integer, default=0)
    last_hit_date = Column(String)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
