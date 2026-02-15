# 資料庫架構文件 (Database Schema Documentation)

本文件是 **AI Investment Advisor (v3.1)** 資料庫架構的單一真實來源 (Single Source of Truth)。
系統同時支援 **SQLite** (本地端) 與 **PostgreSQL** (雲端/生產環境)。

This document serves as the single source of truth for the **AI Investment Advisor (v3.1)** database schema.
The system supports both **SQLite** (Local) and **PostgreSQL** (Cloud/Production).

## 實體關係圖 (Entity Relationship Diagram - DBML)

```dbml
// Use a DBML viewer like dbdocs.io to visualize

Table users {
  id text [pk]
  email text [unique, not null]
  name text
  created_at text
  last_login text
}

Table transactions {
  id text [pk]
  user_id text [ref: > users.id]
  ticker text [not null]
  trade_date text [not null]
  action text [not null, note: 'BUY, SELL, DIVIDEND']
  quantity real [not null]
  price real [not null]
  fees real [default: 0]
  amount real [not null]
  currency text [default: 'USD']
  source_file text
  raw_data text
}

Table positions {
  user_id text [pk, ref: > users.id]
  ticker text [pk]
  quantity real [not null]
  avg_cost real [not null]
  current_price real
  market_value real
  unrealized_pl real
  
  indexes {
    (user_id, ticker) [pk]
  }
}

Table cash_flows {
  id text [pk]
  user_id text [ref: > users.id]
  date text [not null]
  amount real [not null]
  type text [not null]
  description text
}

Table recommendations {
  id text [pk]
  user_id text [ref: > users.id]
  date text [not null]
  agent text [not null]
  ticker text [not null]
  signal text [not null, note: 'BUY, SELL, HOLD']
  price_at_signal real
  outcome_score integer [default: 0]
}

Table reports {
  id text [pk]
  user_id text [ref: > users.id]
  date text [not null]
  content text [not null]
  summary text
}

Table daily_snapshots {
  date text [pk]
  user_id text [pk, ref: > users.id]
  total_nlv real
  cash_balance real
  invested_capital real
  pnl real
  total_tnv real [default: 0]
  leverage_ratio real [default: 0]

  indexes {
    (date, user_id) [pk]
  }
}

Table settings {
  key text [pk]
  user_id text [pk, ref: > users.id]
  value text
  
  indexes {
    (key, user_id) [pk]
  }
}

Table scheduler_logs {
  id text [pk]
  timestamp text
  job_name text
  status text
  message text
}

Table prompt_history {
  id text [pk]
  user_id text [ref: > users.id]
  timestamp text
  target_agent text
  reason text
  original_prompt text
  new_prompt text
  diff_content text
}

Table event_logs {
  id text [pk]
  timestamp text
  source text [note: 'webhook/news, process/daily_scan']
  level text [note: 'INFO, WARNING, CRITICAL']
  title text
  content text
  metadata text [note: 'JSON']
  processed_by text
}

Table manual_inputs {
  id text [pk]
  date text
  user_id text [ref: > users.id]
  input_type text [note: 'PDF, TEXT, URL']
  content text
  status text [note: 'PENDING, PROCESSED, FAILED']
  assigned_agent text
}

Table agent_knowledge {
  id text [pk]
  agent_name text
  topic text
  summary text
  source_ref text
  timestamp text
  ttl_date text
  vector_id text
}

Table agent_states {
  id text [pk]
  agent_name text
  last_input_hash text
  last_run_time text
  last_output text
}

Table agent_feedback {
  id text [pk]
  agent_name text
  context_embedding vector(1536) [note: 'SQLite uses TEXT']
  context_text text
  response_text text
  outcome_score real
  timestamp text
}
```

## 詳細資料定義 (Detailed Schema Definitions)

### 1. users (使用者)
系統使用者與驗證元資料。
System users and authentication metadata.


| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `id` | TEXT | 主鍵 (Primary Key - UUID) | 唯一使用者識別碼 (Unique user identifier)。 |
| `email` | TEXT | 唯一電子郵件 (Unique Email Address) | 用於登入與識別 (Used for login and identification)。 |
| `name` | TEXT | 顯示名稱 (Display Name) | 使用者全名 (User's full name)。 |
| `created_at` | TEXT | 建立時間 (Creation Timestamp) | ISO8601 格式。 |
| `last_login` | TEXT | 最後登入時間 (Last Login Timestamp) | |

**索引 (Indexes):**
*   `sqlite_autoindex_users_1` (主鍵 PRIMARY KEY)
*   `sqlite_autoindex_users_2` (唯一索引 UNIQUE `email`)

---

### 2. transactions (交易紀錄)
所有買賣與財務操作的歷史紀錄。
Historical record of all buy/sell and financial actions.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `id` | TEXT | 主鍵 (Primary Key - UUID) | |
| `user_id` | TEXT | 外鍵 (Foreign Key - `users.id`) | 交易擁有者 (Owner of transaction)。 |
| `ticker` | TEXT | 代號 (Symbol) | 例如 'AAPL', 'Cash'。 |
| `trade_date` | TEXT | 交易日期 (Date of trade) | YYYY-MM-DD。 |
| `action` | TEXT | 交易類型 (Transaction Type) | 'BUY', 'SELL', 'DIVIDEND' (股息), 'DEPOSIT' (入金)。 |
| `quantity` | REAL | 數量 (Quantity) | 正數 (Positive number)。 |
| `price` | REAL | 單價 (Unit Price) | 每股價格 (Price per share)。 |
| `fees` | REAL | 手續費 (Commission/Fees) | |
| `amount` | REAL | 總金額 (Total Amount) | `(qty * price) + fees` (依據流向的正負號)。 |
| `currency` | TEXT | 幣別 (Currency Code) | 預設 'USD'。 |
| `source_file` | TEXT | 來源檔案 (Origin Filename) | 用於 CSV 匯入審計 (For CSV import auditing)。 |
| `raw_data` | TEXT | 原始資料 (Raw JSON) | 用於除錯的完整列資料 (Full row data for debugging)。 |

**索引 (Indexes):**
*   `sqlite_autoindex_transactions_1` (主鍵 PRIMARY KEY)

---

### 3. positions (持倉部位)
基於交易紀錄計算出的當前持倉。
Aggregated current holdings based on transactions.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `user_id` | TEXT | 複合主鍵 (Composite Primary Key) | 外鍵 (Foreign Key `users.id`)。 |
| `ticker` | TEXT | 複合主鍵 (Composite Primary Key) | 代號 (Symbol)。 |
| `quantity` | REAL | 總數量 (Total Quantity) | 淨持股數 (Net held shares)。 |
| `avg_cost` | REAL | 平均成本 (Average Cost Basis) | 加權平均成本 (Weighted average cost)。 |
| `current_price` | REAL | 市價 (Market Price) | 最後取得價格 (Last fetched price)。 |
| `market_value` | REAL | 市值 (Market Value) | `quantity * current_price`。 |
| `unrealized_pl` | REAL | 未實現損益 (Unrealized P&L) | `market_value - (quantity * avg_cost)`。 |

**索引 (Indexes):**
*   `sqlite_autoindex_positions_1` (複合主鍵 Composite PK `user_id`, `ticker`)

---

### 4. recommendations (投資建議)
由 AI Agent 生成的訊號。
Signals generated by AI Agents.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `id` | TEXT | 主鍵 (Primary Key - UUID) | |
| `user_id` | TEXT | 外鍵 (Foreign Key) | |
| `date` | TEXT | 訊號日期 (Signal Date) | YYYY-MM-DD。 |
| `agent` | TEXT |來源 Agent (Source Agent) | 例如 'Momentum', 'CIO'。 |
| `ticker` | TEXT | 目標資產 (Target Asset) | 'SPY', 'AAPL'。 |
| `signal` | TEXT | 動作 (Action) | 'BUY', 'SELL', 'HOLD'。 |
| `price_at_signal` | REAL | 參考價格 (Reference Price) | 生成時的價格 (Price at time of generation)。 |
| `outcome_score` | INTEGER | 績效分數 (Performance Score) | 後續更新 (0=未知, 1=贏, -1=輸)。 |

**索引 (Indexes):**
*   `sqlite_autoindex_recommendations_1` (主鍵 PRIMARY KEY)


---

### 5. reports (報告)
系統生成的 Markdown 報告存檔。
Stored Markdown reports generated by the system.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `id` | TEXT | 主鍵 (Primary Key - UUID) | |
| `user_id` | TEXT | 外鍵 (Foreign Key) | |
| `date` | TEXT | 報告日期 (Report Date) | |
| `content` | TEXT | 報告內容 (Report Body) | Markdown 格式。 |
| `summary` | TEXT | 摘要 (Short Summary) | |

**索引 (Indexes):**
*   `sqlite_autoindex_reports_1` (主鍵 PRIMARY KEY)

---

### 6. daily_snapshots (每日快照)
用於圖表繪製的歷史每日績效指標。
Historical daily performance metrics for charting.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `date` | TEXT | 複合主鍵 (Composite PK) | YYYY-MM-DD。 |
| `user_id` | TEXT | 複合主鍵 (Composite PK) | |
| `total_nlv` | REAL | 淨算總值 (Net Liquidation Value) | 總資產 (Total Assets)。 |
| `cash_balance` | REAL | 現金餘額 (Cash) | |
| `invested_capital`| REAL | 投入資本 (Cost Basis) | 總投資金額 (Total invested amount)。 |
| `pnl` | REAL | 每日損益 (Daily P&L) | |
| `total_tnv` | REAL | 確認淨值 (Total Net Value) | 確認後淨值 (Confirmed Net Value)。 |
| `leverage_ratio` | REAL | 槓桿比率 (Leverage) | 負債/權益比率 (Debt / Equity ratio)。 |

**索引 (Indexes):**
*   `sqlite_autoindex_daily_snapshots_1` (複合主鍵 Composite PK `date`, `user_id`)

---

### 7. settings (設定)
使用者特定與系統全域設定。
User-specific and System-wide configuration.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `key` | TEXT | 複合主鍵 (Composite PK) | 設定鍵值 (Setting Key)。 |
| `user_id` | TEXT | 複合主鍵 (Composite PK) | 'SYSTEM' 或使用者 UUID。 |
| `value` | TEXT | 設定值 (Setting Value) | 字串儲存 (String stored value)。 |

**索引 (Indexes):**
*   `sqlite_autoindex_settings_1` (複合主鍵 Composite PK `key`, `user_id`)

---

### 8. agent_states (代理人狀態)
Agent 的快取狀態，用於減少昂貴的重複呼叫。
Caching state for Agents to minimize expensive calls.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `id` | TEXT | 主鍵 (Primary Key) | 通常是 `AgentName` 或 `AgentName_ContextHash`。 |
| `agent_name` | TEXT | Agent 名稱 | |
| `last_input_hash` | TEXT | 上下文雜湊 (Context Hash) | 輸入上下文的 SHA256。 |
| `last_run_time` | TEXT | 執行時間 (ISO Timestamp) | |
| `last_output` | TEXT | 快取輸出 (Cached Output) | LLM 的回應內容。 |

**索引 (Indexes):**
*   `sqlite_autoindex_agent_states_1` (主鍵 PRIMARY KEY)

---

### 9. agent_feedback (代理人反饋)
優化器 Agent 的反饋迴圈資料。
Feedback loop data for the Optimizer Agent.

| 欄位 (Column) | 型別 (Type) | 定義 (Definition) | 備註 (Remarks) |
|---|---|---|---|
| `id` | TEXT | 主鍵 (Primary Key) | |
| `agent_name` | TEXT | 目標 Agent (Target Agent) | |
| `context_embedding`| VECTOR/TEXT| 向量嵌入 (Embedding) | PG 使用 `vector(1536)`，SQLite 使用 `TEXT`。 |
| `context_text` | TEXT | 輸入上下文 (Input Context) | |
| `response_text` | TEXT | 輸出回應 (Output) | |
| `outcome_score` | REAL | 結果分數 (Result Score) | 正規化 -1.0 到 1.0。 |
| `timestamp` | TEXT | 時間戳 (ISO Timestamp) | |

**索引 (Indexes):**
*   `sqlite_autoindex_agent_feedback_1` (主鍵 PRIMARY KEY)

---

### 10. 稽核與日誌表 (Audit and Logging tables)
`scheduler_logs` / `event_logs` / `manual_inputs` / `prompt_history` / `agent_knowledge`

| 資料表 (Table) | 鍵值 (Key Column) | 描述 (Description) |
|-------|------------|-------------|
| `scheduler_logs` | `id` | 記錄排程執行狀態 (Logs job execution status - START/COMPLETE/FAIL)。 |
| `event_logs` | `id` | 系統事件匯流排驗證日誌 (System-wide event bus validation logs)。 |
| `manual_inputs` | `id` | 追蹤手動上傳處理狀態 (Tracking manual upload processing status)。 |
| `prompt_history` | `id` | 追蹤 Engineer Agent 對 Prompt 的修改 (Tracks Engineer Agent modifications to prompts)。 |
| `agent_knowledge` | `id` | 儲存長期知識/摘要 (RAG) (Stores long-term knowledge/summaries)。 |
