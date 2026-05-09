from sqlalchemy import Column, String, Text, DateTime, Numeric, Integer, ForeignKey, JSON, Boolean, UniqueConstraint, CheckConstraint, Index, Date
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects import postgresql
import uuid
from pgvector.sqlalchemy import Vector


# NOTE: JSONB is PG-specific; on SQLite we fall back to plain JSON so local
# macOS dev (SQLite default) can still run migrations and tests.
def _JSONB():
    return JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

def _ARRAY(item_type):
    # On SQLite, we store arrays as JSON strings
    return JSON().with_variant(postgresql.ARRAY(item_type), "postgresql")

def _DOUBLE():
    # On SQLite, we use Numeric/Float
    return Numeric(asdecimal=False).with_variant(postgresql.DOUBLE_PRECISION(), "postgresql")

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
    last_hit_date = Column(Date)
    is_active = Column(Integer, default=1)
    source = Column(String, default='seed')
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


# ======================================================================
# Core Trading & Portfolio Models
# ======================================================================

class Transaction(Base):
    """
    `transactions` — Core ledger for all cash and asset movements.
    """
    __tablename__ = 'transactions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    trade_date = Column(Date, nullable=False, index=True)
    action = Column(String, nullable=False) # BUY, SELL, DIVIDEND, FEE, TAX, DEPOSIT, WITHDRAWAL
    quantity = Column(Numeric(18, 8), nullable=False)
    price = Column(Numeric(18, 8), nullable=False)
    fees = Column(Numeric(18, 8), default=0)
    amount = Column(Numeric(18, 8), nullable=False)
    currency = Column(String, default='USD')
    leverage = Column(Numeric(18, 8), default=1.0)
    source_file = Column(String) # e.g., 'etoro_export.csv', 'manual', 'ETORO_SYNC'
    entry_category = Column(String, default='trade') # trade, capital_flow, sync_adjustment
    raw_data = Column(_JSONB())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class PositionLot(Base):
    """
    `position_lots` — Tracks specific tax lots for O(1) avg_cost and PnL calculation.
    """
    __tablename__ = 'position_lots'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    ticker = Column(String, nullable=False)
    open_date = Column(String, nullable=False) # Kept as string to match existing schema
    close_date = Column(String)
    quantity = Column(postgresql.DOUBLE_PRECISION, nullable=False)
    open_price = Column(postgresql.DOUBLE_PRECISION, nullable=False)
    close_price = Column(postgresql.DOUBLE_PRECISION)
    leverage = Column(postgresql.DOUBLE_PRECISION, default=1.0)
    is_open = Column(Boolean, default=True)
    source_tx_id = Column(String, ForeignKey('transactions.id', ondelete='SET NULL'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_position_lots_user_open', 'user_id', 'is_open'),
        Index('idx_position_lots_user_ticker', 'user_id', 'ticker'),
    )

class DailySnapshot(Base):
    """
    `daily_snapshots` — Historical EOD account balances and performance metrics.
    """
    __tablename__ = 'daily_snapshots'
    
    date = Column(Date, primary_key=True)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    account_id = Column(String, primary_key=True, default='')
    total_nlv = Column(Numeric(18, 8))
    cash_balance = Column(Numeric(18, 8))
    invested_capital = Column(Numeric(18, 8))
    pnl = Column(Numeric(18, 8))
    total_tnv = Column(Numeric(18, 8), default=0)
    leverage_ratio = Column(Numeric(18, 8), default=0)
    conviction_level = Column(Numeric(18, 8), default=0)
    time_horizon = Column(String)

class PortfolioSnapshot(Base):
    """
    `portfolio_snapshots` — Redundant but used in some legacy views.
    """
    __tablename__ = 'portfolio_snapshots'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True)
    account_value = Column(Numeric(18, 2))
    cash = Column(Numeric(18, 2))
    invested = Column(Numeric(18, 2))
    portfolio_pl = Column(Numeric(18, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CashFlow(Base):
    """
    `cash_flows` — Records of capital injections and withdrawals.
    """
    __tablename__ = 'cash_flows'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), index=True)
    date = Column(Date)
    amount = Column(Numeric(18, 8))
    type = Column(String) # DEPOSIT, WITHDRAWAL
    description = Column(String)

# ======================================================================
# Agent Memory & Intelligence Models
# ======================================================================

class MemoryEmbedding(Base):
    """
    `memory_embeddings` — Long-term semantic memory for agents.
    """
    __tablename__ = 'memory_embeddings'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536)) # Standard OpenAI embedding size
    meta = Column("metadata", _JSONB(), default={})
    embedding_model = Column(String, default='text-embedding-ada-002')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

class CouncilMinute(Base):
    """
    `council_minutes` — Records of Agent Council deliberations and consensus.
    """
    __tablename__ = 'council_minutes'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    topic = Column(String)
    participants = Column(Text) # JSON list of agent names
    consensus = Column(Text)
    transcript = Column(Text)
    embedding = Column(Vector(1536))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ReportJob(Base):
    """
    `report_jobs` — Tracks the state of complex multi-stage report generation.
    """
    __tablename__ = 'report_jobs'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    report_type = Column(String, nullable=False)
    scheduled_date = Column(Date)
    status = Column(String, default='pending') # pending, running, completed, failed
    current_stage = Column(Integer, default=0)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    error_details = Column(_JSONB())
    report_id = Column(String) # Link back after creation
    checkpoint_data = Column(_JSONB())
    last_checkpoint_stage = Column(Integer)
    model_used = Column(String)
    cost_estimate = Column(_DOUBLE())
    tags = Column(_ARRAY(String))

class JobTelemetry(Base):
    """
    `job_telemetry` — Fine-grained timing and token usage for report job stages.
    """
    __tablename__ = 'job_telemetry'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String, ForeignKey('report_jobs.id', ondelete='CASCADE'), nullable=False, index=True)
    stage = Column(Integer)
    stage_name = Column(String)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    status = Column(String)
    model_used = Column(String)
    tokens_input = Column(Integer)
    tokens_output = Column(Integer)
    cost_usd = Column(_DOUBLE())
    error_code = Column(String)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    meta = Column("metadata", _JSONB(), default={})

class Report(Base):
    """
    `reports` — Generated analysis reports (Daily, Weekly, Monthly).
    """
    __tablename__ = 'reports'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    report_type = Column(String, nullable=False) # daily, weekly, monthly, thematic
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text)
    job_id = Column(String, ForeignKey('report_jobs.id', ondelete='SET NULL'), index=True)
    generation_model = Column(String)
    generation_cost_usd = Column(_DOUBLE())
    is_draft = Column(Boolean, default=False)
    embedding = Column(Vector(1536))
    meta = Column("metadata", _JSONB(), default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    published_at = Column(DateTime(timezone=True))

class Recommendation(Base):
    """
    `recommendations` — Specific trade or action recommendations from agents.
    """
    __tablename__ = 'recommendations'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    date = Column(DateTime(timezone=True), server_default=func.now())
    agent = Column(String, nullable=False)
    ticker = Column(String, nullable=False)
    signal = Column(String, nullable=False) # BUY, SELL, HOLD
    price_at_signal = Column(Numeric(18, 8))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CognitiveMemory(Base):
    """
    `cognitive_memories` — Medium-term structured storage for agent insights.
    """
    __tablename__ = 'cognitive_memories'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    agent_name = Column(String, nullable=False)
    memory_type = Column(String, nullable=False) # insight, conviction, lesson, summary
    content = Column(_JSONB(), nullable=False)
    importance = Column(Numeric(18, 8), default=0.5)
    source_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_cog_mem_user_type', 'user_id', 'memory_type'),
    )

class InvestmentSkill(Base):
    """
    `investment_skills` — Learned investment techniques and conditions.
    """
    __tablename__ = 'investment_skills'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    timeframe = Column(String)
    environment = Column(_JSONB(), default={})
    industry = Column(_JSONB(), default=[])
    technique = Column(Text)
    conditions = Column(_JSONB(), default={})
    source_article = Column(Text)
    source_type = Column(String, default='article')
    source_highlight_id = Column(String)
    merged_from = Column(_JSONB(), default=[])
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))
    is_active = Column(Integer, default=1)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SkillLearningConfig(Base):
    """
    `skill_learning_config` — Per-user configuration for skill learning.
    """
    __tablename__ = 'skill_learning_config'
    
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    merge_threshold = Column(Numeric(18, 8), default=0.70)
    max_token_budget = Column(Integer, default=2000)
    last_token_usage = Column(Integer, default=0)
    total_skills_count = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# ======================================================================
# System & Feedback Models
# ======================================================================

class WebPushSubscription(Base):
    """
    `web_push_subscriptions` — Browser push notification subscriptions.
    """
    __tablename__ = 'web_push_subscriptions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    subscription_json = Column(_JSONB(), nullable=False)
    device_info = Column(_JSONB(), default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AgentFeedback(Base):
    """
    `agent_feedback` — Direct feedback on agent responses for reinforcement learning.
    """
    __tablename__ = 'agent_feedback'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_name = Column(String, nullable=False)
    context_embedding = Column(Vector(1536))
    context_text = Column(Text)
    response_text = Column(Text)
    signal = Column(String)
    outcome_score = Column(Numeric(18, 8))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class AgentReview(Base):
    """
    `agent_reviews` — HR 360 reviews where agents review each other.
    """
    __tablename__ = 'agent_reviews'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reviewer = Column(String, nullable=False)
    reviewee = Column(String, nullable=False)
    score = Column(Integer, nullable=False)
    comment = Column(Text)
    context_hash = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class SchedulerLog(Base):
    """
    `scheduler_logs` — Logs for background job execution.
    """
    __tablename__ = 'scheduler_logs'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    job_name = Column(String, nullable=False)
    status = Column(String, nullable=False) # success, failed, running
    message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SentinelThreshold(Base):
    """
    `sentinel_thresholds` — Dynamic thresholds for risk management and alerts.
    Managed mostly via raw SQL in SentinelRepository for performance, but
    defined here so Alembic correctly tracks the schema.
    """
    __tablename__ = 'sentinel_thresholds'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    key = Column(String, unique=True, nullable=False)
    value = Column(Numeric(18, 8), nullable=False)
    last_optimized_by = Column(String)
    roi_hint = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
