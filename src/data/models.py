from sqlalchemy import Column, String, Text, DateTime, Numeric, Integer, BigInteger, ForeignKey, JSON, Boolean, UniqueConstraint, CheckConstraint, Index, Date, desc, text
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

    # Added by 009_risk_keywords_unique because RiskKeywordRepository's
    # `INSERT ... ON CONFLICT (keyword)` was silently failing without it. The
    # baseline's inline UNIQUE was dropped by f9861a2caa12, so this is the only
    # one — the model just never declared it.
    # 009 補上的唯一約束（缺了會讓 ON CONFLICT (keyword) 靜默失效）；
    # baseline 那個已被 f9861a2caa12 移除，所以只有這一個。
    __table_args__ = (
        UniqueConstraint('keyword', name='uq_risk_keywords_keyword'),
    )

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
    # 768, not 1536: 006_council_embedding_768 narrowed the column to match the
    # local nomic-embed-text model used everywhere else in the stack. The DB has
    # been vector(768) since; only this declaration was left behind.
    # 006 已把欄位收窄為 vector(768) 以對齊本地 nomic-embed-text，DB 一直是 768，
    # 只有這行沒跟上。
    embedding = Column(Vector(768))
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


class EventQueue(Base):
    """
    `event_queue` — Tiered event queue for PAD event aggregation.

    Event ingestion → tier classification → INSERT into event_queue (silent).
    Agents pull pending events by tier + user_id in batch mode.
    Only P0+Actionable events trigger immediate user notification.
    """
    __tablename__ = 'event_queue'

    TIER_P0 = 'P0'  # Critical — immediate
    TIER_P1 = 'P1'  # Important — every 5-15 min
    TIER_P2 = 'P2'  # Routine — every 1-4 hours
    TIER_P3 = 'P3'  # Reference — daily/weekly

    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_ANALYZED = 'analyzed'
    STATUS_ARCHIVED = 'archived'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # No `index=True` on user_id or batch_id: it would auto-name the indexes
    # ix_event_queue_* , but 005_add_event_queue creates idx_event_queue_batch_id
    # and only a composite over user_id. Declaring them explicitly below keeps
    # the names matching what the database actually has.
    # 不用 index=True：它會自動命名成 ix_event_queue_*，但 005 建的是
    # idx_event_queue_batch_id，且 user_id 只有複合索引沒有單欄索引。
    user_id = Column(String, nullable=False)
    event_type = Column(String(50), nullable=False)
    content = Column(_JSONB(), nullable=False, default=dict)
    tier = Column(String(10), nullable=False, default=TIER_P2)
    priority = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default=STATUS_PENDING)
    batch_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('idx_event_queue_user_tier_status', 'user_id', 'tier', 'status'),
        Index('idx_event_queue_created_at', 'created_at'),
        Index('idx_event_queue_batch_id', 'batch_id'),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Raw-SQL-managed tables (migrations 007-017)
#
# These eleven tables are created by migrations and accessed exclusively through
# raw SQL — per AGENTS.md, "raw SQL for performance paths, ORM only for admin
# entities". The models below are therefore DECLARATIONS ONLY: nothing queries
# through them, and adding them changes no runtime behaviour.
#
# They exist for two reasons:
#   1. `alembic check` reflects the live schema and emits a drop_table for every
#      table with no matching model. Without these, the CI migration gate can
#      never pass.
#   2. scripts/init_db.py:64 builds a fresh database with
#      Base.metadata.create_all() and then stamps head. Before this, a
#      brand-new production install got none of these eleven tables and was
#      then marked as fully migrated. (Note this does NOT apply to
#      src/data/database.py's init_db(), a hand-written DDL script that never
#      calls create_all — which is why tests/conftest.py still creates
#      decision_outcomes by hand.)
#
# Type families matter and are easy to get wrong: the eight raw-SQL tables use
# PG TEXT (-> `Text`), while decision_outcomes / backtest_runs /
# backtest_equity_points were built with op.create_table and sa.String()
# (-> VARCHAR, so `String`). DESC indexes must spell out desc(), or autogenerate
# reports a remove+add pair every run.
#
# 這十一張表由 migration 建立、只透過 raw SQL 存取，以下純屬宣告：沒有任何查詢
# 走它們，加上去不改變 runtime 行為。目的一是讓 `alembic check` 不再誤判為
# drop_table，二是讓 init_db.py 的 create_all() 路徑不再漏建這些表。
# 型別家族容易寫錯：raw SQL 那八張用 PG TEXT，op.create_table 那三張是 VARCHAR。
# DESC 索引一定要寫出 desc()，否則每次都會產生 remove+add。
# ─────────────────────────────────────────────────────────────────────────────

class DecisionOutcome(Base):
    """`decision_outcomes` — alembic 007. P1 alpha-anchored decision memory."""
    __tablename__ = 'decision_outcomes'

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String)
    agent_name = Column(String, nullable=False)
    ticker = Column(String, nullable=False, index=True)
    signal = Column(String, nullable=False)
    price_at_decision = Column(Numeric(18, 8), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.current_timestamp())
    horizon_days = Column(Integer, nullable=False, server_default='5')
    resolved_at = Column(DateTime(timezone=True))
    realized_return_pct = Column(Numeric(10, 4))
    benchmark_return_pct = Column(Numeric(10, 4))
    alpha_pct = Column(Numeric(10, 4))
    lesson = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.current_timestamp())

    __table_args__ = (
        Index('ix_decision_outcomes_pending', 'resolved_at', 'decided_at'),
    )


class BacktestRun(Base):
    """`backtest_runs` — alembic 008."""
    __tablename__ = 'backtest_runs'

    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    ticker = Column(String, nullable=False, index=True)
    strategy_name = Column(String, nullable=False)
    initial_cash = Column(Numeric(18, 4), nullable=False)
    final_cash = Column(Numeric(18, 4), nullable=False)
    metrics = Column(_JSONB(), nullable=False)
    trades = Column(_JSONB(), nullable=False)
    params = Column(_JSONB())
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.current_timestamp())


class BacktestEquityPoint(Base):
    """`backtest_equity_points` — alembic 008. Equity curve for a run."""
    __tablename__ = 'backtest_equity_points'

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey('backtest_runs.id', ondelete='CASCADE'),
                    nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    # Stored as a string, not Date — matches the migration.
    date = Column(String)
    equity = Column(Numeric(18, 4), nullable=False)


class TaskRun(Base):
    """
    `task_runs` — alembic 010. Celery signal telemetry.

    Also created at runtime by src/infrastructure/task_telemetry.py:39; both
    use IF NOT EXISTS, so they coexist, but the DDL lives in two places.
    """
    __tablename__ = 'task_runs'

    id = Column(BigInteger, primary_key=True)
    task_name = Column(Text, nullable=False)
    task_id = Column(Text)
    status = Column(Text, nullable=False)
    error_class = Column(Text)
    error_snippet = Column(Text)
    duration_ms = Column(_DOUBLE())
    finished_at = Column(DateTime(timezone=True), nullable=False,
                         server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('success', 'soft_fail', 'failure')",
                        name='task_runs_status_check'),
        Index('idx_task_runs_name_time', 'task_name', desc('finished_at')),
        Index('idx_task_runs_status_time', 'status', desc('finished_at')),
    )


class ExpectedOutcome(Base):
    """`expected_outcomes` — alembic 011. Dead-man switch definitions."""
    __tablename__ = 'expected_outcomes'

    id = Column(BigInteger, primary_key=True)
    name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    target = Column(Text, nullable=False)
    max_gap_seconds = Column(Integer, nullable=False)
    enabled = Column(Boolean, nullable=False, server_default=text('true'))
    last_ok_at = Column(DateTime(timezone=True))
    last_alerted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    __table_args__ = (
        # Postgres auto-named the migration's inline UNIQUE; spell it out so the
        # names match. / migration 用的是 inline UNIQUE，PG 自動命名，這裡明寫。
        UniqueConstraint('name', name='expected_outcomes_name_key'),
        CheckConstraint("kind IN ('task_success', 'named_check')",
                        name='expected_outcomes_kind_check'),
    )


class AgentRule(Base):
    """`agent_rules` — alembic 012, extended by 014 and 018."""
    __tablename__ = 'agent_rules'

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Text, nullable=False)
    agent_name = Column(Text, nullable=False)
    rule_text = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default='active')
    version = Column(Integer, nullable=False, server_default='1')
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    # 014
    score = Column(_DOUBLE(), nullable=False, server_default='0')
    times_cited = Column(Integer, nullable=False, server_default='0')
    expires_at = Column(DateTime(timezone=True))
    embedding = Column(Vector(768))
    source_decision_id = Column(Text)
    # 018
    gate_status = Column(Text)
    gate_checked_at = Column(DateTime(timezone=True))
    gate_details = Column(_JSONB())

    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate','active','superseded','retired','rejected')",
            name='agent_rules_status_check'),
        # idx_agent_rules_lookup (012) and idx_agent_rules_active_lookup (014)
        # have identical column lists — 014 added the second without dropping
        # the first. Both are declared because alembic matches by name; dropping
        # the duplicate belongs in its own migration.
        # 兩個索引欄位完全相同（014 新增時沒刪掉 012 的）；alembic 按名字比對，
        # 所以兩個都要宣告，清理留待另一支 migration。
        Index('idx_agent_rules_lookup', 'user_id', 'agent_name', 'status'),
        Index('idx_agent_rules_active_lookup', 'user_id', 'agent_name', 'status'),
        Index('idx_agent_rules_candidate_lookup', 'user_id',
              postgresql_where=text("status = 'candidate'")),
    )


class RuleCitation(Base):
    """`rule_citations` — alembic 014. Which rules a decision actually used."""
    __tablename__ = 'rule_citations'

    id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey('agent_rules.id', ondelete='CASCADE'),
                     nullable=False)
    decision_id = Column(Text, nullable=False)
    applied = Column(Boolean, nullable=False, server_default=text('true'))
    alpha_pct = Column(_DOUBLE())
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    __table_args__ = (
        Index('idx_rule_citations_rule', 'rule_id'),
        Index('idx_rule_citations_decision', 'decision_id'),
    )


class InteractionFeedback(Base):
    """`interaction_feedback` — alembic 013, `ticker` added by 015."""
    __tablename__ = 'interaction_feedback'

    id = Column(BigInteger, primary_key=True)
    request_id = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False)
    decision = Column(Text, nullable=False)
    reason_code = Column(Text)
    free_text = Column(Text)
    responded_in_s = Column(_DOUBLE())
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    ticker = Column(Text)

    __table_args__ = (
        CheckConstraint("decision IN ('approved','rejected','expired')",
                        name='interaction_feedback_decision_check'),
        Index('idx_interaction_feedback_user', 'user_id', desc('created_at')),
        Index('idx_interaction_feedback_request', 'request_id'),
    )


class UserPreference(Base):
    """
    `user_preferences` — alembic 015. Derived preference profile.

    Natural PK on user_id, no surrogate id. Distinct from `users.preferences`,
    which is a JSON column on a different table.
    """
    __tablename__ = 'user_preferences'

    user_id = Column(Text, primary_key=True)
    risk_appetite_score = Column(_DOUBLE())
    sector_aversions = Column(_JSONB(), nullable=False)
    position_comfort = Column(_DOUBLE())
    summary_text = Column(Text)
    sample_size = Column(Integer, nullable=False, server_default='0')
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())


class RemediationLog(Base):
    """`remediation_log` — alembic 016. T1/T2/T3 self-repair audit trail."""
    __tablename__ = 'remediation_log'

    id = Column(BigInteger, primary_key=True)
    task_name = Column(Text, nullable=False)
    error_class = Column(Text, nullable=False)
    tier = Column(Text, nullable=False)
    action_taken = Column(Text, nullable=False)
    diagnosis = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    __table_args__ = (
        CheckConstraint("tier IN ('T1','T2','T3')", name='remediation_log_tier_check'),
        Index('idx_remediation_log_lookup', 'task_name', 'error_class',
              desc('created_at')),
    )


class ProductEvent(Base):
    """`product_events` — alembic 017. Opt-in telemetry, off by default."""
    __tablename__ = 'product_events'

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Text, nullable=False)
    event = Column(Text, nullable=False)
    props = Column(_JSONB(), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    __table_args__ = (
        Index('idx_product_events_lookup', 'event', desc('created_at')),
    )
