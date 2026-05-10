-- PostgreSQL version of memory tables (AUTOINCREMENT → SERIAL)
-- Create table for storing report history for MemoryService
CREATE TABLE IF NOT EXISTS report_memory (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    report_type TEXT NOT NULL, -- 'daily', 'weekly'
    report_date DATE NOT NULL,
    full_content TEXT,
    compressed_summary TEXT, -- Stores the compressed context (T-1, T-2 etc logic)
    key_findings JSONB, -- Structured key takeaways
    market_metrics JSONB, -- Captured metrics (e.g. VIX, SPX Level)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, report_type, report_date)
);

-- Create table for tracking task execution and costs
CREATE TABLE IF NOT EXISTS task_execution_log (
    id SERIAL PRIMARY KEY,
    plan_id TEXT, -- ID from ExecutionPlan
    task_name TEXT NOT NULL,
    task_type TEXT,
    complexity_score INTEGER,
    assigned_model TEXT,
    status TEXT, -- 'pending', 'running', 'completed', 'failed'
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    tokens_used INTEGER,
    cost_usd REAL,
    result_summary TEXT,
    error_message TEXT
);

-- Create indexes for performance
CREATE INDEX idx_report_memory_user_date ON report_memory(user_id, report_date);
CREATE INDEX idx_task_execution_status ON task_execution_log(status);
CREATE INDEX idx_task_execution_user ON task_execution_log(plan_id);
