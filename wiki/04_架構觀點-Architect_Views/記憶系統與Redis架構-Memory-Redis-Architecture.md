# 記憶系統與 Redis 架構 (Memory System & Redis Architecture)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-21 | v4.6 | Unified version, confirmed PostgreSQL primary & AgentLLMProvider integration | Neo |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |
| 2026-02-19 | v4.2 | Three-tier memory architecture (Hot/Warm/Cold) established | Neo |

> **版本 (Version):** v4.6
> **更新日期 (Last Updated):** 2026-02-21
> **狀態 (Status):** Production Optimized

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 1. 概述 (Overview)

v4.6 延續三層式記憶架構：Hot (Redis)、Warm (PostgreSQL) 與 Cold (原始文件)。核心回應快取 (`ResponseCache`) 與高頻 Session 狀態由 Redis 承載，持久化記憶（RAG、用戶偏好）由 PostgreSQL 承載。SQLite 已完全從 `src/` 中移除，確保生產環境的高一致性與可擴展性。`MemoryFactory` 預設使用 `alchemy` (PostgreSQL) 後端，並透過 `AgentLLMProvider` 整合 Agent 進行摘要與矛盾檢測。

## 2. 架構設計 (Architecture Design)

### 2.1 記憶層級 (Memory Hierarchy)

*   **Hot Memory (Cache Tier)**:
    - **Storage**: Redis
    - **Scope**: LLM 回應快取 (`ResponseCache`)、高頻存取的 Session 狀態。
    - **TTL**: 24 小時 ~ 7 天。
*   **Warm Memory (Persistent Tier)**:
    - **Storage**: PostgreSQL (pgvector)
    - **Scope**: RAG 記憶、Reranking 候選、用戶長期偏好。
    - **Retention**: 永久。
*   **Cold Memory (Source Tier)**:
    - **Storage**: CSV / 原始文件。
    - **Scope**: 最初攝取數據來源。

### 2.2 核心組件 (Core Components)

*   **MemoryService** (`src/services/memory_service.py`):
    *   提供統一介面 (`get_context`, `store_report`, `check_contradictions`)。
    *   透過 `IMemoryRepository` (`src/domain/interfaces.py`) 與 `ILLMProvider` 介面解耦，支援依賴注入。
    *   內建 **Adaptive Compression**：根據模型 Token 上限的 20% 自動壓縮歷史記憶。
*   **RedisMemoryRepository** (`src/repositories/redis_memory_repository.py`):
    *   Redis 適配器，處理連線池、序列化 (JSON) 與 TTL 管理。
*   **HybridMemory** (`src/infrastructure/memory/memory_manager.py`):
    *   統一的 PostgreSQL + pgvector 記憶子系統，支援向量嵌入搜尋與全文關鍵字搜尋 (FTS/BM25)。
    *   **加權融合檢索 (Weighted Score Fusion)**: 捨棄倒數排名融合 (RRF)，採用純量加權 (e.g. `0.7 * Cosine + 0.3 * BM25`)，以保留精準相似度的絕對信號梯度，確保股票代號等冰冷關鍵字與語義知識能被 100% 準確召回。
    *   保留 SQLite 相容性僅供測試環境使用。
*   **MemoryFactory** (`src/services/memory_factory.py`):
    - **狀態**: 不再支援 SQLite 切換。透過 `MEMORY_BACKEND` 環境變數選擇後端：
      - `alchemy` (預設): 使用 `AlchemyMemoryRepository` (PostgreSQL) 作為主持久層。
      - `redis`: 使用 `RedisMemoryRepository` 作為替代選項。
    - 自動注入 `AgentLLMProvider` 提供摘要與矛盾檢測的 LLM 能力。
*   **AgentLLMProvider** (`src/infrastructure/agent_llm_provider.py`):
    *   實作 `ILLMProvider` 介面，將現有 Agent (Engineer) 適配為 MemoryService 的 LLM 服務提供者。
    *   提供 `summarize()` 與 `check_contradictions()` 方法。

## 3. 關鍵特性 (Key Features)

### 3.1 壓縮前靜默沖洗與自適應壓縮 (Pre-Compaction Flush & Adaptive Compression)
*   **觸發機制**: 不等到 Token Overflow，系統會設立「壓縮安全墊 (Reserve Floor)」，當 Session Context 即將逼近上限 (e.g. 達模型上限 80% 或剩餘 4000 tokens) 時觸發。
*   **靜默沖洗 (Pre-Compaction Flush)**: 在清除舊對話前，Gateway 或者 Workflow 引擎會安插一次「無感知」的 Agent 推理，指示 Agent 將進行中的重要狀態與關鍵字寫入持久化資料庫 (PostgreSQL 或 `MEMORY.md` 狀態日誌)，回覆 `NO_REPLY`。
*   **算法**: 完成沖洗存檔後，保留最近 20% 的原始訊息，並將其餘 80% 快取轉存為 "Summary Vector" 封存，清空主工作區流。確保高長度對話中的決策與長文背景絕不遺失。

### 3.2 Conflict Detection (矛盾檢測)
*   每次生成新觀點 (View) 前，系統會自動檢索歷史記憶 (Latest 3 Days)。
*   若今日觀點 (e.g., Bearish) 與昨日 (e.g., Bullish) 存在顯著衝突，**MemoryService** 會注入 `Consistency Warning`，強制 Agent 解釋轉折原因。

## 4. 基礎設施 (Infrastructure)

### 4.1 Redis Deployment
*   **Container**: `redis:7-alpine`
*   **Port**: 6379
*   **Persistence**: RDB/AOF Enabled (Volume Mount: `redis_data`)
*   **Deployment**: 
    *   Local: Docker Compose (`investment_advisor_redis`)
    *   Prod: Kubernetes Deployment (`k8s/redis-deployment.yaml`)

### 4.2 Configuration
*   **Env Vars**:
    *   `REDIS_URL=redis://redis:6379/0`

---

<a id="en"></a>

## 🇺🇸 Memory System & Redis Architecture (v4.6)

### 1. Overview
v4.6 continues the Three-Tier Memory Architecture: Hot (Redis), Warm (PostgreSQL), and Cold (Raw Files). The core `ResponseCache` and high-frequency session states are handled by Redis, while persistent memories (RAG, user preferences) are stored in PostgreSQL. SQLite has been completely removed from `src/` to ensure production-grade consistency and scalability. `MemoryFactory` defaults to `alchemy` (PostgreSQL) backend and integrates `AgentLLMProvider` for summarization and contradiction detection.

### 2. Architecture Design

#### 2.1 Memory Hierarchy (3-Tier Strategy)
*   **🚀 Hot Memory (Cache Tier)**:
    - **Storage**: Redis.
    - **Scope**: LLM `ResponseCache`, high-access session context.
    - **TTL**: 24 hours ~ 7 days.
*   **🧠 Warm Memory (Persistent Tier)**:
    - **Storage**: PostgreSQL (pgvector).
    - **Scope**: RAG embeddings, long-term user preferences, historical reports.
    - **Retention**: Permanent.
*   **❄️ Cold Memory (Source Tier)**:
    - **Storage**: CSV / Local raw files.
    - **Scope**: Original data ingestion sources.

#### 2.2 Core Components
*   **MemoryService**: Unified interface (`get_context`, `store_report`, `check_contradictions`) managing tiering logic with adaptive compression (20% of model token limit).
*   **RedisMemoryRepository**: Adapter for connection pooling, serialization, and TTL management.
*   **HybridMemory**: Unified PostgreSQL + pgvector memory subsystem combining vector embeddings with Full-Text Keyword Search (FTS/BM25). Uses **Weighted Score Fusion** (discarding Reciprocal Rank Fusion) with explicit scalar weighting (e.g. 70% Cosine, 30% BM25) to preserve absolute signal strength for precision matching of stock tickers and error codes.
*   **MemoryFactory**: Purged SQLite support; defaults to `alchemy` (PostgreSQL) for persistent repositories. Injects `AgentLLMProvider` for LLM-powered summarization and contradiction detection.
*   **AgentLLMProvider**: Adapts existing Agents (Engineer) to provide `ILLMProvider` services for MemoryService.

### 3. Key Features

#### 3.1 Pre-Compaction Flush & Adaptive Compression
*   **Mechanism**: Triggered silently prior to overflowing (e.g. Context Window reaches 80% or threshold of 4000 tokens remaining).
*   **Pre-Compaction Flush**: Instead of randomly forgetting, a silent agent logic injects a "Save state" request, storing remaining mission-critical context to DB / `MEMORY.md`, returning `NO_REPLY` before clearing out the context.
*   **Algorithm**: Retains recent 20% raw data, caches older 80% into "Summary Vector" archives, clearing the primary workspace buffer.

#### 3.2 Conflict Detection
*   Retrieves last 3 days of history (Warm Tier) before generating new views.
*   Injects a `Consistency Warning` if today's view conflicts with yesterday's.

### 4. Infrastructure

#### 4.1 Redis Deployment
*   **Image**: `redis:7-alpine`.
*   **Persistence**: RDB/AOF Enabled.
*   **Deployment**: Support for Docker Compose (Local) and Kubernetes (Prod).

#### 4.2 Configuration
*   **Env Vars**: `REDIS_URL`, `MEMORY_BACKEND` (now strictly `alchemy` or `redis`).
