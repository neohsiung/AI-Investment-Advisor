"""baseline_v4_schema

Revision ID: 879480c2b31c
Revises: 
Create Date: 2026-04-05 13:27:08.554000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '879480c2b31c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # v5.3: Baseline Migration for V4 Schema
    # This migration creates all the tables found in the original init_db() script.
    
    # Enable Extensions
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "vector"'))

    # 1. Users table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        preferences JSONB DEFAULT '{}',
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMPTZ
    )
    """))

    # 2. Transactions table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        ticker TEXT NOT NULL,
        trade_date DATE NOT NULL,
        action TEXT NOT NULL,
        quantity NUMERIC(18, 8) NOT NULL,
        price NUMERIC(18, 8) NOT NULL,
        fees NUMERIC(18, 8) DEFAULT 0,
        amount NUMERIC(18, 8) NOT NULL,
        currency TEXT DEFAULT 'USD',
        source_file TEXT,
        raw_data JSONB,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 3. Memory Embeddings table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS memory_embeddings (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        embedding vector(1536),
        metadata JSONB DEFAULT '{}',
        embedding_model TEXT DEFAULT 'text-embedding-ada-002',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMPTZ
    )
    """))

    # 4. Settings table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        key TEXT NOT NULL,
        value JSONB,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, key)
    )
    """))

    # 5. Council Minutes table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS council_minutes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_id TEXT NOT NULL,
        topic TEXT,
        participants TEXT,
        consensus TEXT,
        transcript TEXT,
        embedding vector(1536),
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 6. Event Logs table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS event_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        event_type TEXT NOT NULL,
        severity TEXT,
        title TEXT NOT NULL,
        content TEXT,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 7. Reports table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        report_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding vector(1536),
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        published_at TIMESTAMPTZ
    )
    """))

    # 8. Schema Version table (Not strictly needed with Alembic but keeping for baseline)
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        description TEXT,
        applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 9. User Identities table
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS user_identities (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider TEXT NOT NULL,
        identifier TEXT NOT NULL,
        is_primary INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider, identifier)
    )
    """))

    # 10. Daily Snapshots
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS daily_snapshots (
        date DATE,
        user_id TEXT,
        account_id TEXT DEFAULT '',
        total_nlv NUMERIC(18, 8),
        cash_balance NUMERIC(18, 8),
        invested_capital NUMERIC(18, 8),
        pnl NUMERIC(18, 8),
        total_tnv NUMERIC(18, 8) DEFAULT 0,
        leverage_ratio NUMERIC(18, 8) DEFAULT 0,
        conviction_level NUMERIC(18, 8) DEFAULT 0,
        time_horizon TEXT,
        PRIMARY KEY (date, user_id, account_id)
    )
    """))

    # 11. Cash Flows
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS cash_flows (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        date DATE,
        amount NUMERIC(18, 8),
        type TEXT,
        description TEXT
    )
    """))

    # 12. Risk Keywords
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS risk_keywords (
        id TEXT PRIMARY KEY,
        keyword TEXT NOT NULL UNIQUE,
        weight NUMERIC(18, 8) DEFAULT 0.5,
        category TEXT DEFAULT 'custom',
        hit_count INTEGER DEFAULT 0,
        last_hit_date DATE,
        is_active INTEGER DEFAULT 1,
        source TEXT DEFAULT 'seed',
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 13. Channel Verifications
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS channel_verifications (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        channel TEXT,
        channel_user_id TEXT,
        code TEXT,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 14. Agent Feedback
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS agent_feedback (
        id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        context_embedding vector(1536),
        context_text TEXT,
        response_text TEXT,
        signal TEXT,
        outcome_score NUMERIC(18, 8),
        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 15. Agent Reviews
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS agent_reviews (
        id TEXT PRIMARY KEY,
        reviewer TEXT NOT NULL,
        reviewee TEXT NOT NULL,
        score INTEGER NOT NULL,
        comment TEXT,
        context_hash TEXT,
        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 16. Recommendations
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS recommendations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        agent TEXT NOT NULL,
        ticker TEXT NOT NULL,
        signal TEXT NOT NULL,
        price_at_signal NUMERIC(18, 8),
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 17. Scheduler Logs
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS scheduler_logs (
        id TEXT PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        job_name TEXT NOT NULL,
        status TEXT NOT NULL,
        message TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 18. Investment Skills
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS investment_skills (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT,
        timeframe TEXT,
        environment JSONB DEFAULT '{}',
        industry JSONB DEFAULT '[]',
        technique TEXT,
        conditions JSONB DEFAULT '{}',
        source_article TEXT,
        source_type TEXT DEFAULT 'article',
        source_highlight_id TEXT,
        merged_from JSONB DEFAULT '[]',
        usage_count INTEGER DEFAULT 0,
        last_used_at TIMESTAMPTZ,
        is_active INTEGER DEFAULT 1,
        version INTEGER DEFAULT 1,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 19. Skill Learning Config
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS skill_learning_config (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        merge_threshold NUMERIC(18, 8) DEFAULT 0.70,
        max_token_budget INTEGER DEFAULT 2000,
        last_token_usage INTEGER DEFAULT 0,
        total_skills_count INTEGER DEFAULT 0,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """))

    # 20. LLM Usage Logs
    op.execute(sa.text("""
    CREATE TABLE IF NOT EXISTS llm_usage_logs (
        id TEXT NOT NULL DEFAULT gen_random_uuid()::text PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        user_id TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        tier TEXT NOT NULL,
        prompt_tokens INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_cost_usd NUMERIC(18, 8) DEFAULT 0,
        metadata JSONB DEFAULT '{}'
    )
    """))


def downgrade() -> None:
    # Drop in reverse order
    op.execute(sa.text('DROP TABLE IF EXISTS llm_usage_logs'))
    op.execute(sa.text('DROP TABLE IF EXISTS skill_learning_config'))
    op.execute(sa.text('DROP TABLE IF EXISTS investment_skills'))
    op.execute(sa.text('DROP TABLE IF EXISTS scheduler_logs'))
    op.execute(sa.text('DROP TABLE IF EXISTS recommendations'))
    op.execute(sa.text('DROP TABLE IF EXISTS agent_reviews'))
    op.execute(sa.text('DROP TABLE IF EXISTS agent_feedback'))
    op.execute(sa.text('DROP TABLE IF EXISTS channel_verifications'))
    op.execute(sa.text('DROP TABLE IF EXISTS risk_keywords'))
    op.execute(sa.text('DROP TABLE IF EXISTS cash_flows'))
    op.execute(sa.text('DROP TABLE IF EXISTS daily_snapshots'))
    op.execute(sa.text('DROP TABLE IF EXISTS user_identities'))
    op.execute(sa.text('DROP TABLE IF EXISTS schema_version'))
    op.execute(sa.text('DROP TABLE IF EXISTS reports'))
    op.execute(sa.text('DROP TABLE IF EXISTS event_logs'))
    op.execute(sa.text('DROP TABLE IF EXISTS council_minutes'))
    op.execute(sa.text('DROP TABLE IF EXISTS settings'))
    op.execute(sa.text('DROP TABLE IF EXISTS memory_embeddings'))
    op.execute(sa.text('DROP TABLE IF EXISTS transactions'))
    op.execute(sa.text('DROP TABLE IF EXISTS users'))
