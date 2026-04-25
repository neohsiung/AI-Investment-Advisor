from sqlalchemy import Column, String, Text, DateTime, Numeric, Integer, ForeignKey, JSON, Boolean, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects import postgresql
import uuid
from pgvector.sqlalchemy import Vector


# NOTE: JSONB is PG-specific; on SQLite we fall back to plain JSON so local
# macOS dev (SQLite default) can still run migrations and tests.
def _JSONB():
    return JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

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


# ======================================================================
# LLM Multi-Provider Multi-Model tables (Phase A)
# Design: docs/architecture/multi_provider_multi_model_design.md §3
# ======================================================================

class LLMProvider(Base):
    """
    `llm_providers` — Provider instance owned by a user (or SYSTEM).
    Describes "which provider implementation + credentials" the user has
    configured; decoupled from Model / Tier binding.
    """
    __tablename__ = 'llm_providers'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    provider_code = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    base_url = Column(Text, nullable=True)
    encrypted_api_key = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    extra_config = Column(_JSONB(), nullable=False, default=dict)
    health_status = Column(String, nullable=True)
    health_detail = Column(_JSONB(), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'provider_code', 'display_name',
                         name='uq_llm_providers_user_code_name'),
        Index('ix_llm_providers_user_enabled', 'user_id', 'enabled'),
        Index('ix_llm_providers_provider_code', 'provider_code'),
    )


class LLMModel(Base):
    """
    `llm_models` — Model instance owned by a Provider. Tier / Override
    reference this table via FK (never embed model strings).
    """
    __tablename__ = 'llm_models'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(String, ForeignKey('llm_providers.id', ondelete='RESTRICT'), nullable=False)
    model_code = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    capability_tool_calling = Column(Boolean, nullable=False, default=False)
    capability_vision = Column(Boolean, nullable=False, default=False)
    capability_json_mode = Column(Boolean, nullable=False, default=False)
    capability_streaming = Column(Boolean, nullable=False, default=True)
    capability_embeddings = Column(Boolean, nullable=False, default=False)
    context_window = Column(Integer, nullable=True)
    input_cost_per_1k = Column(Numeric(12, 6), nullable=True)
    output_cost_per_1k = Column(Numeric(12, 6), nullable=True)
    source = Column(String, nullable=False, default='manual')
    raw_discovery = Column(_JSONB(), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('provider_id', 'model_code', name='uq_llm_models_provider_code'),
        CheckConstraint("source IN ('manual', 'auto_discovered', 'seed')",
                        name='chk_llm_models_source'),
        Index('ix_llm_models_provider_enabled', 'provider_id', 'enabled'),
        Index('ix_llm_models_enabled', 'enabled'),
    )


class LLMTierBinding(Base):
    """
    `llm_tier_bindings` — Tier (nano/fast/smart/advanced) → primary Model FK
    + fallback Model FK array. Only references, never embeds.
    """
    __tablename__ = 'llm_tier_bindings'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    tier = Column(String, nullable=False)
    primary_model_id = Column(String, ForeignKey('llm_models.id', ondelete='RESTRICT'), nullable=False)
    # NOTE: fallback_model_ids is a JSON array of model UUIDs (logical FK;
    # validated at application layer because PostgreSQL can't FK JSONB elements).
    fallback_model_ids = Column(_JSONB(), nullable=False, default=list)
    per_candidate_config = Column(_JSONB(), nullable=False, default=dict)
    budget_aware = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'tier', name='uq_llm_tier_bindings_user_tier'),
        CheckConstraint("tier IN ('nano', 'fast', 'smart', 'advanced')",
                        name='chk_llm_tier_bindings_tier'),
        Index('ix_llm_tier_bindings_primary_model', 'primary_model_id'),
    )


class LLMAgentOverride(Base):
    """
    `llm_agent_overrides` — Per-agent / per-user model override.
    Allows specific agents (e.g. CIO, SkillRouter) to bypass the default
    Tier binding and use a custom primary + fallback chain.

    Design: docs/architecture/multi_provider_multi_model_design.md §3.4
    """
    __tablename__ = 'llm_agent_overrides'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    agent_name = Column(String(100), nullable=False)
    # override_tier: if set, use this tier's chain instead of primary_model_id
    override_tier = Column(String(20), nullable=True)
    # primary_model_id: if set, overrides the tier's primary model
    primary_model_id = Column(
        String,
        ForeignKey('llm_models.id', ondelete='RESTRICT'),
        nullable=True,
    )
    # fallback_model_ids: ordered JSON array of model UUIDs (logical FK)
    fallback_model_ids = Column(_JSONB(), nullable=True, default=list)
    forbid_local = Column(Boolean, nullable=False, default=False)
    forbid_fallback = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'agent_name', name='uq_llm_agent_overrides_user_agent'),
        CheckConstraint(
            "override_tier IN ('nano', 'fast', 'smart', 'advanced') OR override_tier IS NULL",
            name='chk_llm_agent_overrides_tier',
        ),
        Index('ix_llm_agent_overrides_user_id', 'user_id'),
        Index('ix_llm_agent_overrides_agent_name', 'agent_name'),
        Index('ix_llm_agent_overrides_primary_model', 'primary_model_id'),
    )
