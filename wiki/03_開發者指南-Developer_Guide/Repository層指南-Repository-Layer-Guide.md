# Repository 層完整指南 (Repository Layer Guide)

### 版本紀錄 (Version History)

| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-03-11 | v1.7 | **B2C Multi-Tenant**: `SettingsRepository` 新增 API Key 使用者映射功能。`UserRepository` 強化 C 端註冊與身分連結。 | Antigravity |
| 2026-03-08 | v1.6 | **Security & Multi-Account**: 全面落實 **Rule #10 (Safe-SQL-Only)**，消除 SQL 注入風險。`SnapshotRepository` 支援 `account_id` 隔離與正規化。 | Antigravity |
| 2026-03-07 | v1.5 | **Verification Updates**: `VerificationRepository` 新增 `get_any_pending_verification` 與 `get_pending_verification`。 | Antigravity |
| 2026-03-05 | v1.4 | **Rule #10 & #1 & #12**: 全面參數化 SQL Interval。修正 `IMemoryRepository` 路徑至 `domain/interfaces.py`。 | Antigravity |
| 2026-03-05 | v1.3 | **Keyword Discovery**: `RiskKeywordRepository` 新增 `add_if_not_exists`、`get_count`、`prune_lowest` 方法。`source` 欄位追蹤關鍵字來源。 | Antigravity |
| 2026-02-28 | v1.2 | **QMD Retrieval Engine (Phase 2)**: Added BM25 text rank, temporal decay, and simulated MMR deduping to `VectorRepository`. | Agent |
| 2026-02-28 | v1.1 | **Audit Update**: `prompt_history` 加入 `user_id` 欄位以支援多使用者審計 | Antigravity |
| 2026-02-21 | v1.0 | 初版：完整記錄 17 個 Repository 的介面、實作與職責 | Antigravity |

---

<a id="zh"></a>

## 🇹🇼 Repository 層概覽

Repository 層是本專案 **Clean Architecture** 的核心資料存取層，負責將所有資料庫操作封裝在統一的介面之後。每個 Repository 遵循 **介面隔離原則 (ISP)**，定義 `I{Name}Repository` 抽象介面，再由 `Alchemy{Name}Repository` 提供 SQLAlchemy 實作。

### 設計模式與原則

| 模式 | 說明 |
| :--- | :--- |
| **Repository Pattern** | 將資料存取邏輯與業務邏輯分離，Service 層僅依賴介面 |
| **Interface Segregation** | 每個 Repository 定義獨立的 `ABC` 介面 (`I*Repository`) |
| **Dependency Injection** | Service 層透過建構子注入 Repository 實例 |
| **Upsert Pattern** | 大量使用 `ON CONFLICT ... DO UPDATE` 實現冪等寫入 |
| **BaseRepository** | 所有 Alchemy 實作繼承自 `BaseRepository`，統一管理 Engine 與 Session |

### 架構圖 (Architecture Diagram)

```mermaid
graph TB
    subgraph Service Layer
        CS[CouncilService]
        SS[SettingsService]
        TS[TransactionService]
        NS[NotificationService]
        SentS[SentinelService]
        MS[MemoryService]
    end

    subgraph Repository Layer
        AR[AgentRepository]
        ASR[AgentStateRepository]
        DR[DataRepository]
        FR[FeedbackRepository]
        MDR[MarketDataRepository]
        MR[MemoryRepository]
        RMR[RedisMemoryRepository]
        PR[PromptRepository]
        RR[ReportRepository]
        RKR[RiskKeywordRepository]
        SenR[SentinelRepository]
        SetR[SettingsRepository]
        SnR[SnapshotRepository]
        TR[TransactionRepository]
        UR[UserRepository]
        VR[VectorRepository]
        VerR[VerificationRepository]
    end

    subgraph Infrastructure
        PG["(PostgreSQL")]
        Redis["(Redis")]
        YF[yfinance API]
    end

    CS --> VR
    CS --> FR
    SS --> SetR
    TS --> TR
    TS --> SnR
    SentS --> SenR
    MS --> MR
    MS --> RMR

    AR --> PG
    ASR --> PG
    DR --> PG
    FR --> PG
    PR --> PG
    RR --> PG
    RKR --> PG
    SenR --> PG
    SetR --> PG
    SnR --> PG
    TR --> PG
    UR --> PG
    VR --> PG
    VerR --> PG
    MR --> PG
    RMR --> Redis
    MDR --> YF
```

### BaseRepository 基礎類別

位於 [`src/data/database.py`](database.py:17)，提供：

- **Engine 管理**：透過全域 Engine Cache 避免重複建立連線
- **Session 管理**：使用 `scoped_session` 提供執行緒安全的 ORM Session
- **JSONB 工具**：`_get_json_extract()` 提供 PostgreSQL JSONB 路徑提取
- **向量距離**：`_get_vector_distance()` 提供 pgvector 距離計算

---

## 📋 Repository 完整清單 (Complete Repository Catalog)

### 1. AgentRepository — 代理人績效儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/agent_repository.py`](agent_repository.py) |
| **介面** | `IAgentRepository` |
| **實作** | `AlchemyAgentRepository` |
| **資料表** | `agent_performance` |
| **職責** | 追蹤代理人權重、成功/失敗次數、平均延遲 |

**核心方法**：

- `get_agent_weight(agent_name, default)` — 取得代理人目前權重
- `update_performance(agent_name, tier, success, latency, weight_delta)` — 更新績效指標（Upsert）
- `get_top_agents(tier, limit)` — 依權重排序取得高績效代理人

---

### 2. AgentStateRepository — 代理人狀態儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/agent_state_repository.py`](agent_state_repository.py) |
| **介面** | `IAgentStateRepository` |
| **實作** | `AlchemyAgentStateRepository` |
| **資料表** | `agent_states` |
| **職責** | 儲存代理人執行上下文的最後已知狀態，用於冪等性檢查 |

**核心方法**：

- `get_state(agent_id)` — 取得 `(last_input_hash, last_output)` 元組
- `save_state(agent_id, agent_name, input_hash, output)` — Upsert 執行狀態

---

### 3. DataRepository — 資料預覽儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/data_repository.py`](data_repository.py) |
| **介面** | `IDataRepository` |
| **實作** | `AlchemyDataRepository` |
| **職責** | 提供 Dashboard 資料表預覽功能，含白名單驗證。依據 **Rule #10** 使用參數化 SQL 處理時間區間。 |

**核心方法**：

- `get_table_preview(table_name, user_id, limit)` — 取得資料表預覽（白名單：`transactions`, `daily_snapshots`, `cash_flows`, `positions`, `reports`, `settings`, `prompt_history`）

---

### 4. FeedbackRepository — 回饋與同儕審查儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/feedback_repository.py`](feedback_repository.py) |
| **介面** | `IFeedbackRepository` |
| **實作** | `AlchemyFeedbackRepository` |
| **資料表** | `agent_feedback`, `agent_reviews` |
| **職責** | 儲存經驗訓練範例與 HR 360 同儕審查 |

**核心方法**：

- `save(example: FeedbackExample)` — 儲存回饋範例
- `get_training_examples(agent_name, min_score, limit)` — 取得訓練範例
- `add_review(reviewer, reviewee, score, comment)` — 新增同儕審查
- `get_reviews_for_agent(agent_name)` — 取得代理人收到的回饋
- `get_reviews_by_agent(agent_name)` — 取得代理人給出的回饋

---

### 5. MarketDataRepository — 市場數據儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/market_data_repository.py`](market_data_repository.py) |
| **介面** | `IMarketDataRepository` |
| **實作** | `AlchemyMarketDataRepository` |
| **資料來源** | yfinance API（外部） |
| **職責** | 從外部 API 獲取即時價格、歷史數據、新聞與基本面資訊 |

**核心方法**：

- `fetch_current_prices(tickers)` — 批次取得最新收盤價
- `fetch_history(ticker, period, days)` — 取得歷史 OHLCV 數據
- `fetch_news(ticker, limit)` — 取得標的新聞
- `fetch_info(ticker)` — 取得基本面資訊

> ⚠️ 此 Repository 不繼承 `BaseRepository`，因為它不存取資料庫，而是封裝外部 API 呼叫。

---

### 6. MemoryRepository — 記憶儲存庫（SQL 實作）

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/memory_repository.py`](memory_repository.py) |
| **介面** | `IMemoryRepository`（定義於 `src/domain/interfaces.py`，遵循 **Rule #1**） |
| **實作** | `AlchemyMemoryRepository` |
| **資料表** | `reports` |
| **職責** | 儲存與檢索報告記憶項目（SQL 版本） |

**核心方法**：

- `get_recent_reports(user_id, report_type, limit)` — 取得近期報告
- `save_report(item: ReportMemoryItem)` — 儲存報告記憶

---

### 7. RedisMemoryRepository — 記憶儲存庫（Redis 實作）

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/redis_memory_repository.py`](redis_memory_repository.py) |
| **介面** | `IMemoryRepository` |
| **實作** | `RedisMemoryRepository` |
| **資料來源** | Redis（Hash + Sorted Set） |
| **職責** | 適用於 K8s 微服務環境的共享代理人記憶 |

**核心方法**：

- `save_report(item)` — 使用 Hash 儲存內容，Sorted Set 建立時間索引（90 天 TTL）
- `get_recent_reports(user_id, report_type, limit)` — 使用 `ZREVRANGE` 取得最新報告

**Redis Key 結構**：

```
memory:report:{user_id}:{report_type}:content:{date}  → Hash (報告內容)
memory:report:{user_id}:{report_type}:index            → Sorted Set (時間索引)
```

---

### 8. PromptRepository — 提示詞變更記錄儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/prompt_repository.py`](prompt_repository.py) |
| **介面** | `IPromptRepository` |
| **實作** | `AlchemyPromptRepository` |
| **資料表** | `prompt_history` |
| **職責** | 記錄代理人提示詞的變更歷史（審計追蹤） |

**核心方法**：

- `log_change(agent_name, reason, old_prompt, new_prompt, diff, user_id)` — 記錄提示詞變更（含 `user_id` 審計）

---

### 9. ReportRepository — 報告儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/report_repository.py`](report_repository.py) |
| **介面** | `IReportRepository` |
| **實作** | `AlchemyReportRepository` |
| **資料表** | `reports` |
| **職責** | 取得使用者的最新報告（DataFrame 格式） |

**核心方法**：

- `get_latest_reports(user_id, limit)` — 取得最新報告（含 `TIMESTAMPTZ` 支援）

---

### 10. RiskKeywordRepository — 風險關鍵字儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/risk_keyword_repository.py`](risk_keyword_repository.py) |
| **介面** | `IRiskKeywordRepository` |
| **實作** | `AlchemyRiskKeywordRepository` |
| **資料表** | `risk_keywords` |
| **職責** | 風險關鍵字的 CRUD 操作與命中追蹤 |

**核心方法**：

- `seed_defaults()` — 插入預設關鍵字（含中英文，涵蓋 8 大類別，UPSERT 模式）
- `get_all(active_only)` / `get_by_category(category)` — 查詢關鍵字
- `add(keyword, weight, category)` — 新增關鍵字
- `add_if_not_exists(keyword, weight, category, source)` — UPSERT 單一關鍵字，含來源追蹤
- `get_count(active_only)` — 取得有效關鍵字總數
- `prune_lowest(target_count, protected_source)` — 刪除最低權重關鍵字至目標數
- `update_weight(kw_id, new_weight)` / `toggle_active(kw_id, is_active)` — 更新
- `record_hit(kw_id)` — 記錄命中
- `get_stale_keywords(days_threshold)` / `get_top_keywords(limit)` — 分析

---

### 11. SentinelRepository — 哨兵閾值與警報儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/sentinel_repository.py`](sentinel_repository.py) |
| **介面** | `ISentinelRepository` |
| **實作** | `AlchemySentinelRepository` |
| **資料表** | `sentinel_thresholds`, `event_logs` |
| **職責** | 管理動態閾值、重複警報檢測、警報記錄 |

**核心方法**：

- `get_all_thresholds()` / `update_threshold(key, value, reviewer, rationale)` — 閾值管理
- `seed_defaults(defaults)` — 種子預設閾值
- `is_duplicate_alert(title, content, hours, signal_id)` — 重複警報檢測（JSONB 優化）
- `get_last_signal_value(signal_id)` — 取得訊號最後記錄值
- `log_alert(title, content, metadata)` — 記錄警報至 `event_logs`

---

### 12. SettingsRepository — 設定儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/settings_repository.py`](settings_repository.py) |
| **介面** | `ISettingsRepository` |
| **實作** | `AlchemySettingsRepository`（ORM 模式） |
| **資料表** | `settings`（透過 ORM `Setting` Model） |
| **職責** | 使用者與全域設定的 CRUD |

**核心方法**：

- `get(user_id, key, default)` / `set(user_id, key, value)` — 單一設定讀寫
- `find_user_by_webhook_secret(secret)` — **[v1.7]** 核心動態路由：透過 Webhook API Key 找出對應的使用者 UUID。
- `get_all(user_id)` — 取得使用者所有設定
- `get_global()` — 取得全域設定（`user_id` 為 NULL 或 `'system'`）
- `get_by_prefix(prefix)` — 依前綴查詢設定

---

### 13. SnapshotRepository — 每日快照儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/snapshot_repository.py`](snapshot_repository.py) |
| **介面** | `ISnapshotRepository` |
| **實作** | `AlchemySnapshotRepository` |
| **資料表** | `daily_snapshots` |
| **職責** | 儲存與查詢每日投資組合快照（NLV、現金、PnL、槓桿） |

**核心方法**：

- `get_history_by_user(user_id, account_id)` — 取得所有快照（DataFrame），支援多帳號隔離與 **Rule #10** 安全查詢。
- `get_latest_by_user(user_id, account_id)` — 取得最新快照，支援多帳號隔離與 **Rule #10** 安全查詢。
- `save_snapshot(user_id, date, nlv, cash_balance, invested_capital, pnl, total_tnv, leverage_ratio, conviction_level, time_horizon, account_id)` — Upsert 快照（含 `inf`/`nan` 清理與帳號標識）。`account_id` 若為 `None` 會自動正規化為 `""`。

---

### 14. TransactionRepository — 交易儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/transaction_repository.py`](transaction_repository.py) |
| **介面** | `ITransactionRepository` |
| **實作** | `AlchemyTransactionRepository` |
| **資料表** | `transactions`, `daily_snapshots`, `cash_flows` |
| **職責** | 交易記錄的完整 CRUD、持倉計算、現金流與槓桿管理。遵循 **Rule #10**，所有 SQL 查詢均使用參數化與靜態字面量。 |

**核心方法**：

- `get_all_by_user(user_id)` / `get_all_by_user_df(user_id)` — 取得交易記錄
- `get_active_tickers(user_id)` — 取得持有中的標的
- `add(user_id, ticker, date, action, quantity, price, fees, leverage)` — 新增交易
- `delete(user_id, transaction_id)` — 刪除交易
- `get_holdings(user_id)` / `get_holdings_summary(user_id)` — 持倉查詢
- `get_latest_leverage(user_id)` — 取得最新槓桿比率
- `get_cash_flow_sum(user_id)` / `get_cash_balance(user_id)` — 現金流計算
- `calculate_net_invested_capital(user_id)` — 計算淨投入資本
- `get_leverage_summary(user_id)` — 槓桿摘要

---

### 15. UserRepository — 使用者與身分儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/user_repository.py`](user_repository.py) |
| **介面** | `IUserRepository` |
| **實作** | `AlchemyUserRepository` |
| **資料表** | `users`, `user_identities` |
| **職責** | 使用者管理與多身分連結（Email、LINE、Telegram 等） |

**核心方法**：

- `get_by_id(user_id)` — 依 UUID 查詢使用者
- `get_by_identity(provider, identifier)` — 透過任何身分解析使用者（JOIN `user_identities`）
- `link_identity(user_id, provider, identifier, is_primary)` — 連結新身分
- `create_user(email, name)` — 建立使用者並自動連結主要 Email 身分
- `get_identities(user_id)` — 取得使用者所有身分

---

### 16. VectorRepository — 向量儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/vector_repository.py`](vector_repository.py) |
| **介面** | `IVectorRepository` |
| **實作** | `AlchemyVectorRepository` |
| **資料表** | `memory_embeddings`, `council_minutes` |
| **職責** | 向量嵌入的儲存與相似度搜尋（PGVector 專用） |

**核心方法**：

- `add_memory(user_id, category, content, embedding, metadata)` — 新增記憶嵌入
- `search_memory(user_id, embedding, query_text, top_k, threshold)` — **QMD 混合搜尋**：結合向量相似度 (`<=>` Cosine) 與 全文檢索 (`ts_rank` BM25)，使用公式 `(0.7 * Vector + 0.3 * BM25) * Temporal Decay` 並加入重複性過濾 (Simulated MMR)。
- `add_council_minute(user_id, session_id, topic, participants, consensus, transcript, embedding)` — 記錄議會會議
- `search_similar_minutes_by_embedding(embedding, limit, threshold)` — 搜尋相似議會記錄

> ⚠️ 向量搜尋在 SQLite 環境下會自動跳過（測試相容性）。

---

### 17. VerificationRepository — 驗證儲存庫

| 項目 | 說明 |
| :--- | :--- |
| **檔案** | [`src/repositories/verification_repository.py`](verification_repository.py) |
| **介面** | `IVerificationRepository` |
| **實作** | `AlchemyVerificationRepository`（ORM 模式） |
| **資料表** | `channel_verifications`（透過 ORM `ChannelVerification` Model） |
| **職責** | 管理頻道驗證流程（建立、查詢、狀態更新） |

**核心方法**：

- `create_verification(user_id, channel, channel_user_id, code, expires_at)` — 建立驗證記錄
- `get_by_code(channel, code)` — 依代碼查詢待處理驗證
- `get_pending_verification(user_id, channel)` — 取得特定頻道未過期的待處理驗證 (v1.5)
- `get_any_pending_verification(user_id)` — 取得任何頻道未過期的待處理驗證 (v1.5)
- `update_status(verification_id, status, error_message)` — 更新驗證狀態

---

<a id="en"></a>

## 🇺🇸 Repository Layer Guide (English)

### Design Philosophy

The Repository Layer implements the **Repository Pattern** as defined in ADR-002, providing a clean abstraction over all data access operations. Key principles:

1. **Interface Segregation**: Each repository defines an `I*Repository` ABC interface
2. **Single Responsibility**: Each repository manages exactly one domain aggregate
3. **BaseRepository Inheritance**: All SQL-backed repositories inherit from `BaseRepository` for unified Engine/Session management
4. **PostgreSQL Optimization**: Upsert via `ON CONFLICT`, JSONB queries, and pgvector cosine similarity
5. **Dual Implementation**: `IMemoryRepository` has both SQL (`AlchemyMemoryRepository`) and Redis (`RedisMemoryRepository`) implementations

### Repository-to-Service Mapping

| Repository | Primary Consumer(s) |
| :--- | :--- |
| `AgentRepository` | `AgentFactory`, `HRService` |
| `AgentStateRepository` | `BaseAgent` (idempotency check) |
| `DataRepository` | `DashboardService` |
| `FeedbackRepository` | `ExperienceReplayService`, `HRService` |
| `MarketDataRepository` | `MarketDataService` |
| `MemoryRepository` | `MemoryService` |
| `RedisMemoryRepository` | `MemoryService` (K8s mode) |
| `PromptRepository` | `RefinementService` |
| `ReportRepository` | `ReportingService` |
| `RiskKeywordRepository` | `RiskKeywordService`, `SentinelService` |
| `SentinelRepository` | `SentinelService` |
| `SettingsRepository` | `SettingsService` |
| `SnapshotRepository` | `PerformanceService` |
| `TransactionRepository` | `TransactionService` |
| `UserRepository` | `NotificationService`, `InteractionService` |
| `VectorRepository` | `CouncilService`, `MemoryManager` |
| `VerificationRepository` | `VerificationService` |

## 🔗 相關文件 (Related Documents)

- **設計模式**: [[設計模式-存儲庫-Repository-Pattern]]
- **服務層**: [[服務層開發指南-Service-Layer-Blueprints]]
- **資料模型**: [[資料與領域模型-Data-Domain-Models]]
- **記憶架構**: [[記憶系統與Redis架構-Memory-Redis-Architecture]]
- **配置管理**: [[配置管理架構-Configuration-Management]]
