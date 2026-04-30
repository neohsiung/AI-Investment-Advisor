"""
Database migration for Gamma Strategy cost tracking.
Adds cost_attribution_logs table for per-request cost tracking.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Migration script for Alembic
# Usage: alembic upgrade head

def upgrade():
    """Create cost_attribution_logs table."""
    op = sa.create_table(
        'cost_attribution_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('agent_name', sa.String(255), nullable=True),
        sa.Column('cognitive_layer', sa.String(50), nullable=True),
        sa.Column('model_used', sa.String(255), nullable=True),
        sa.Column('provider', sa.String(100), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=True),
        sa.Column('input_cost_usd', sa.Numeric(10, 8), nullable=True),
        sa.Column('output_cost_usd', sa.Numeric(10, 8), nullable=True),
        sa.Column('total_cost_usd', sa.Numeric(10, 8), nullable=True),
        sa.Column('request_text', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('duration_seconds', sa.Numeric(10, 3), nullable=True),
        sa.Column('cache_hit', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for common queries
    sa.create_index(
        'idx_user_timestamp',
        'cost_attribution_logs',
        ['user_id', 'timestamp'],
        postgresql_using='btree'
    )
    
    sa.create_index(
        'idx_cognitive_layer',
        'cost_attribution_logs',
        ['cognitive_layer'],
        postgresql_using='btree'
    )
    
    sa.create_index(
        'idx_total_cost_desc',
        'cost_attribution_logs',
        ['total_cost_usd'],
        postgresql_using='btree'
    )
    
    sa.create_index(
        'idx_timestamp',
        'cost_attribution_logs',
        ['timestamp'],
        postgresql_using='btree'
    )


def downgrade():
    """Drop cost_attribution_logs table."""
    op = sa.drop_table('cost_attribution_logs')


# Raw SQL migration alternative (for manual execution)
SQL_CREATE = """
CREATE TABLE IF NOT EXISTS cost_attribution_logs (
    id SERIAL PRIMARY KEY,
    request_id UUID UNIQUE NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(255),
    cognitive_layer VARCHAR(50),
    model_used VARCHAR(255),
    provider VARCHAR(100),
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    input_cost_usd NUMERIC(10, 8),
    output_cost_usd NUMERIC(10, 8),
    total_cost_usd NUMERIC(10, 8),
    request_text TEXT,
    response_text TEXT,
    timestamp TIMESTAMP DEFAULT NOW(),
    duration_seconds NUMERIC(10, 3),
    cache_hit BOOLEAN DEFAULT FALSE,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_user_timestamp 
    ON cost_attribution_logs(user_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_cognitive_layer 
    ON cost_attribution_logs(cognitive_layer);

CREATE INDEX IF NOT EXISTS idx_total_cost_desc 
    ON cost_attribution_logs(total_cost_usd DESC);

CREATE INDEX IF NOT EXISTS idx_timestamp 
    ON cost_attribution_logs(timestamp DESC);

-- Create view for weekly summaries
CREATE OR REPLACE VIEW weekly_cost_summary AS
SELECT 
    DATE_TRUNC('week', timestamp) as week,
    user_id,
    cognitive_layer,
    COUNT(*) as request_count,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(total_tokens) as total_tokens,
    SUM(total_cost_usd) as total_cost,
    AVG(duration_seconds) as avg_latency,
    COUNT(*) FILTER (WHERE cache_hit = true) as cache_hits
FROM cost_attribution_logs
GROUP BY week, user_id, cognitive_layer;

-- Create view for daily summaries
CREATE OR REPLACE VIEW daily_cost_summary AS
SELECT 
    DATE(timestamp) as date,
    user_id,
    cognitive_layer,
    COUNT(*) as request_count,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(total_tokens) as total_tokens,
    SUM(total_cost_usd) as total_cost,
    AVG(duration_seconds) as avg_latency
FROM cost_attribution_logs
GROUP BY date, user_id, cognitive_layer;
"""

SQL_DROP = """
DROP VIEW IF EXISTS daily_cost_summary CASCADE;
DROP VIEW IF EXISTS weekly_cost_summary CASCADE;
DROP TABLE IF EXISTS cost_attribution_logs CASCADE;
"""

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "drop":
        print("SQL for dropping tables:")
        print(SQL_DROP)
    else:
        print("SQL for creating tables:")
        print(SQL_CREATE)
