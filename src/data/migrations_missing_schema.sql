-- Missing Schema Tables and Columns Migration
-- Applied: April 13, 2026
-- Purpose: Complete database schema to match ORM models

-- 1. Create subscription_plans table (referenced by users.subscription_id)
CREATE TABLE IF NOT EXISTS subscription_plans (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    monthly_usd_limit NUMERIC(18, 2) DEFAULT 0.0,
    allowed_tiers JSON DEFAULT '["nano", "fast"]',
    max_parallel_agents INTEGER DEFAULT 2,
    features JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Add foreign key constraint if not already exists
-- (Handled by adding column, but constraint may need explicit creation)
ALTER TABLE users 
ADD CONSTRAINT fk_users_subscription_id 
FOREIGN KEY (subscription_id) REFERENCES subscription_plans(id) ON DELETE SET NULL
ON CONFLICT DO NOTHING;

-- 3. Create index on subscription_id for query performance
CREATE INDEX IF NOT EXISTS idx_users_subscription_id ON users(subscription_id);

-- 4. Create prompt_cache table (used by semantic caching)
CREATE TABLE IF NOT EXISTS prompt_cache (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt_hash TEXT,
    prompt_text TEXT,
    embedding vector(384),
    response_text TEXT,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_prompt_cache_user_id (user_id),
    INDEX idx_prompt_cache_hash (prompt_hash)
);

-- 5. Create llm_usage_logs table (if not exists with all columns)
CREATE TABLE IF NOT EXISTS llm_usage_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    agent_name TEXT,
    provider TEXT,
    model TEXT,
    tier TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(18, 8) DEFAULT 0,
    metadata JSON DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_llm_user_id (user_id),
    INDEX idx_llm_agent_name (agent_name)
);

-- 6. Create response_feedback table
CREATE TABLE IF NOT EXISTS response_feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    prompt_hash TEXT,
    agent_name TEXT,
    vote INTEGER,
    comment TEXT,
    metadata JSON DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_feedback_user_id (user_id)
);

-- 7. Create user_custom_prompts table
CREATE TABLE IF NOT EXISTS user_custom_prompts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_name TEXT,
    custom_prompt TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_custom_prompts_user_id (user_id),
    INDEX idx_custom_prompts_agent (agent_name)
);

-- Verify migration
SELECT 'Migration complete. Checking tables:';
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('subscription_plans', 'prompt_cache', 'llm_usage_logs', 'response_feedback', 'user_custom_prompts');
