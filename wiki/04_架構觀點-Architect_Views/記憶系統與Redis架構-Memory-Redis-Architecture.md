# 記憶系統與 Redis 架構 (Memory System & Redis Architecture)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


> **版本 (Version):** v4.2  
> **更新日期 (Last Updated):** 2026-02-19  
> **狀態 (Status):** Production Optimized

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 1. 概述 (Overview)

v4.2 正式確立了三層式記憶架構：Hot (Redis)、Warm (PostgreSQL) 與 Cold (原始文件)。核心回應快取 (`ResponseCache`) 與高頻 Session 狀態由 Redis 承載，持久化記憶（RAG、用戶偏好）由 PostgreSQL 承載。SQLite 已完全從 `src/` 中移除，確保生產環境的高一致性與可擴展性。

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

*   **MemoryService**:
    *   提供統一介面 (`get_context`, `store_report`, `detect_conflicts`)。
    *   負責在 Redis 與 DB 之間進行數據同步與分層。
*   **RedisMemoryRepository**:
    *   Redis 適配器，處理連線池、序列化 (JSON) 與 TTL 管理。
*   **MemoryFactory**:
    - **狀態**: 不再支援 SQLite 切換。預設使用 `alchemy` (PostgreSQL) 作為 Memory Repository 的主持久層，`redis` 適合作為向量搜索的另一個選項。

## 3. 關鍵特性 (Key Features)

### 3.1 Adaptive Compression (自適應壓縮)
*   **機制**: 當 Context Window 超過 80% Token 上限時，自動觸發壓縮演算法。
*   **算法**: 保留最近 20% 的原始訊息，並將其餘 80% 摘要為 "Summary Vector" 或條列式重點。
*   **目的**: 防止 Token Overflow，同時保留關鍵歷史脈絡。

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

## 🇺🇸 Memory System & Redis Architecture (v4.2)

### 1. Overview
v4.2 establishes a Three-Tier Memory Architecture: Hot (Redis), Warm (PostgreSQL), and Cold (Raw Files). The core `ResponseCache` and high-frequency session states are handled by Redis, while persistent memories (RAG, user preferences) are stored in PostgreSQL. SQLite has been completely removed from `src/` to ensure production-grade consistency and scalability.

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
*   **MemoryService**: Unified interface (`get_context`, `store_report`) managing tiering logic.
*   **RedisMemoryRepository**: Adapter for connection pooling, serialization, and TTL management.
*   **MemoryFactory**: Purged SQLite support; defaults to `alchemy` (PostgreSQL) for persistent repositories.

### 3. Key Features

#### 3.1 Adaptive Compression
*   **Mechanism**: Triggered when Context Window exceeds 80%.
*   **Algorithm**: Retains recent 20% raw data, summarizes older 80% into vectors/bullet points.

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
