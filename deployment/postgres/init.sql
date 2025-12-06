-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fees REAL DEFAULT 0,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    source_file TEXT,
    raw_data TEXT
);

-- Positions Table
CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    current_price REAL,
    market_value REAL,
    unrealized_pl REAL
);

-- CashFlow Table
CREATE TABLE IF NOT EXISTS cash_flows (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    type TEXT NOT NULL,
    description TEXT
);

-- Recommendations Table (For Refinement Loop)
CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    agent TEXT NOT NULL,
    ticker TEXT NOT NULL,
    signal TEXT NOT NULL,
    price_at_signal REAL,
    outcome_score INTEGER DEFAULT 0
);

-- Reports Table (For Dashboard & History)
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT
);

-- Daily Snapshots Table
CREATE TABLE IF NOT EXISTS daily_snapshots (
    date TEXT PRIMARY KEY,
    total_nlv REAL,
    cash_balance REAL,
    invested_capital REAL,
    pnl REAL
);

-- Scheduler Logs Table
CREATE TABLE IF NOT EXISTS scheduler_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT,
    job_name TEXT,
    status TEXT,
    message TEXT
);

-- Settings Table
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Prompt History Table
CREATE TABLE IF NOT EXISTS prompt_history (
    id TEXT PRIMARY KEY,
    timestamp TEXT,
    target_agent TEXT,
    reason TEXT,
    original_prompt TEXT,
    new_prompt TEXT,
    diff_content TEXT
);
