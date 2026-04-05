from sqlalchemy import Column, String, Text, DateTime, Numeric, Integer, ForeignKey, JSON
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    preferences = Column(JSON, default={})
    meta = Column("metadata", JSON, default={}) # Rename to avoid conflict with Base.metadata
    subscription_id = Column(String, ForeignKey('subscription_plans.id', ondelete='SET NULL'), index=True)
    current_billing_cycle_start = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))

class SubscriptionPlan(Base):
    """
    Defines available subscription plans (Free, Pro, Enterprise) and their quotas [Phase 16].
    """
    __tablename__ = 'subscription_plans'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False) # e.g., 'Free', 'Pro', 'Enterprise'
    monthly_usd_limit = Column(Numeric(18, 2), default=0.0)
    allowed_tiers = Column(JSON, default=["nano", "fast"]) # e.g., ["nano", "fast", "smart"]
    max_parallel_agents = Column(Integer, default=2)
    features = Column(JSON, default={}) # e.g., {"proactive_alerts": false}
    created_at = Column(DateTime(timezone=True), server_default=func.now())

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

class PromptCache(Base):
    """
    Semantic Cache for LLM Prompts using pgvector [Phase 13].
    """
    __tablename__ = 'prompt_cache'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), index=True)
    prompt_hash = Column(String, index=True) # Exact match optimization
    prompt_text = Column(Text)
    embedding = Column(Vector(384)) # Default for all-MiniLM-L6-v2
    response_text = Column(Text)
    meta = Column("metadata", JSON, default={}) # Rename to avoid conflict with Base.metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class LLMUsageLog(Base):
    """
    Tracks LLM API usage and costs for financial audit and observability [Phase 14].
    """
    __tablename__ = 'llm_usage_logs'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='SET NULL'), index=True)
    agent_name = Column(String, index=True)
    provider = Column(String)
    model = Column(String) # Renamed from model_name
    tier = Column(String) # Added
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_cost_usd = Column(Numeric(18, 8), default=0) # Renamed from cost_usd
    meta = Column("metadata", JSON, default={}) # Standardized
    created_at = Column("timestamp", DateTime(timezone=True), server_default=func.now()) # Renamed column

class ResponseFeedback(Base):
    """
    Captures user feedback (👍/👎) for Reinforcement Learning from Human Feedback (RLHF) [Phase 18].
    """
    __tablename__ = 'response_feedback'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), index=True)
    prompt_hash = Column(String, index=True)
    agent_name = Column(String)
    vote = Column(Integer) # +1 for positive, -1 for negative
    comment = Column(Text)
    meta = Column("metadata", JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserCustomPrompt(Base):
    """
    Stores dynamically optimized system prompts per user and agent [Phase 18].
    These override the default static prompt files.
    """
    __tablename__ = 'user_custom_prompts'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), index=True)
    agent_name = Column(String, index=True)
    custom_prompt = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
