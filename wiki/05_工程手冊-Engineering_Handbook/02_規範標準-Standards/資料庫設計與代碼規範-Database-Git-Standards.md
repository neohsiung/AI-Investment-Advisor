### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-17 | v4.0.0 | **Full Migration to PostgreSQL**: pgvector, NUMERIC, and Hybrid ORM strategy. | Neo |
| 2026-02-14 | v3.1.0 | Added "Safe-SQL-Only" principle and hybrid strategy. | Neo |
| 2024-01-04 | v1.0.0 | Initial Release | Neo |

---

<a id="zh"></a>

## 🇹🇼 資料庫設計與代碼規範 (v4.0)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，定義了系統持久層的物理設計、代碼風格與協作規範。v4.0 正式由 SQLite 全面遷移至 PostgreSQL。

### 1. 資料庫物理設計 (Database Design)

#### 1.1 核心資料表與優化類型

| 資料表 | 欄位 | 類型與約束 | 描述 |
| :--- | :--- | :--- | :--- |
| **`users`** | `id` | `UUID` (PK) | 使用 `uuid-ossp` 生成唯一識別碼。 |
| | `preferences` | `JSONB` | 支援 Indexable 的偏好設定儲存。 |
| **`transactions`** | `quantity`, `price` | `NUMERIC(18, 8)` | 確保金融計算 100% 精度，避免 FLOAT 誤差。 |
| | `raw_data` | `JSONB` | 儲存原始券商 API 回傳，帶 GIN 索引。 |
| | `trade_date` | `DATE` | 交易執行日期，非文字格式。 |
| **`memory_embeddings`**| `embedding` | `vector(1536)` | **pgvector** 原生向量嵌入。 |
| | `metadata` | `JSONB` | 記憶標籤與來源鏈結。 |

#### 1.2 混合儲存策略 (Hybrid Strategy)
- **ORM Admin 層**: 針對 *Entities* (Users, Settings, Logs) 使用 SQLAlchemy ORM。優點：簡化對象管理、開發效率高。
- **Raw SQL Performance 層**: 針對 *Data Tracks* (Transactions, Memory) 使用 Raw SQL 或 SQLAlchemy Core。優點：極致控制、優化大規模彙算與向量檢索。

#### 1.3 非功能性要求 (NFR)
- **資安唯一原則 (Safe-SQL-Only)**: 所有 Raw SQL 必須使用 **參數化查詢**。嚴禁使用 f-strings 或字串拼接。
    - *正確範例*: `conn.execute(text("... WHERE id = :id"), {"id": val})`
    - *參考規範*: 詳見 [底層通信協議](底層通信協議-Agent-Mesh-Protocols) 的 SQL 注入防護。
- **事務一致性**: 所有 Batch Import 必須滿足 Atomic 特性，失敗即 Full Rollback。
- **備份策略**: 定期由 Cloud SQL 觸發備份，或使用 `pg_dump` 於本地進行快照。

### 2. 代碼規範 (Coding Best Practices)
本專案遵循 **Google Python Style Guide** (繁體中文/英文 雙語規範)：
- **註解要求**: 所有 Docstrings 必須雙語，英文在上，中文在下。
- **類型標註**: 函式定義強制要求 Type Hints。
- **縮進**: 統一使用 4 個空格。
- **異步處理**: 針對 I/O 密集型操作 (如通知、行情抓取) 優先考慮非同步架構。

### 3. Git 協作與提交 (Git Standards)
- **提交規範**: 遵循 [Conventional Commits](https://www.conventionalcommits.org/)。
- **雙語要求**: 強制要求 `Subject` 為雙語，以利於全球協作。
    - **範例**: `feat(db): implement pgvector for hybrid memory | 導入 pgvector 支援混合記憶`

---

<a id="en"></a>

## 🇺🇸 Database & Git Standards (v4.0)

This document defines the physical design of the persistence layer, coding style, and collaboration standards. v4.0 marks the full transition from SQLite to PostgreSQL.

### 1. Database Specifications

#### 1.1 Core Tables & Optimized Types

| Table | Columns | Type/Constraint | Description |
| :--- | :--- | :--- | :--- |
| **`users`** | `id` | `UUID` (PK) | Generated via `uuid-ossp`. |
| | `preferences` | `JSONB` | Indexable JSON storage. |
| **`transactions`** | `quantity`, `price` | `NUMERIC(18, 8)` | 100% precision for financial calculations. |
| | `raw_data` | `JSONB` | Raw API payloads with GIN indexing. |
| **`memory_embeddings`**| `embedding` | `vector(1536)` | Native **pgvector** embeddings. |

#### 1.2 Hybrid Storage Strategy
- **ORM Admin Layer**: SQLAlchemy ORM for entities (Users, Settings, Logs) to simplify object mapping.
- **Raw SQL Performance Layer**: Raw SQL or SQLAlchemy Core for performance-sensitive tracks (Transactions, Memory) to ensure maximum throughput and vector search optimization.

#### 1.3 Non-Functional Requirements (NFR)
- **Safe-SQL-Only**: Mandatory use of **parameterized queries** for all Raw SQL. No f-strings or concatenation.
- **Transactional Integrity**: Batch imports must be atomic (ACID compliant).
- **Backup**: Automated backups via cloud provider or `pg_dump`.

### 2. Code Quality & Standards
Adhering to the **Google Python Style Guide**:
- **Bilingual Docs**: Mandatory ZH/EN docstrings for all classes and functions.
- **Type Hinting**: Required for all function signatures.
- **Async I/O**: Prioritized for network-bound operations.

### 3. Git Workflow
- **Pattern**: [Conventional Commits](https://www.conventionalcommits.org/).
- **Bilingual Subjects**: `Type(Scope): Subject in EN | Subject in ZH`.

## 🔗 Bidirectional Links
- **Architect View**: [System Landscape](System-Landscape)
- **Dev Guide**: [Environment Setup](Environment-Local-Dev)
- **Handbook**: [Wiki Standard](Wiki-Standard)
