# 記憶系統與 Redis 架構 (Memory System & Redis Architecture)

> **版本 (Version):** v3.2  
> **更新日期 (Last Updated):** 2026-01-14  
> **狀態 (Status):** Production Ready

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 1. 概述 (Overview)

v3.2 引入了基於 Redis 的高性能記憶系統 (`MemoryService`)，取代了原本的純文件或 SQLite 短期記憶。此架構支援 "Adaptive Compression" (自適應壓縮) 與 "Cross-Session Context" (跨會話上下文)，賦予 Agent 長期連續性的思維能力。

## 2. 架構設計 (Architecture Design)

### 2.1 記憶層級 (Memory Hierarchy)

*   **Short-Term Memory (Hot)**:
    *   **Storage**: Redis (In-Memory)
    *   **Scope**: 當前週期的執行上下文 (Execution Context)、最新的 5 則對話歷史。
    *   **TTL**: 24 小時 ~ 7 天。
*   **Long-Term Memory (Cold)**:
    *   **Storage**: SQLite / Postgres (Relational DB)
    *   **Scope**: 歷史報告 (Reports)、用戶偏好 (Preferences)、長期驗證的 Alpha 策略。
    *   **Retention**: 永久 (Until Archived)。

### 2.2 核心組件 (Core Components)

*   **MemoryService**: 
    *   提供統一介面 (`get_context`, `store_report`, `detect_conflicts`)。
    *   負責在 Redis 與 DB 之間進行數據同步與分層。
*   **RedisMemoryRepository**:
    *   Redis 適配器，處理連線池、序列化 (JSON) 與 TTL 管理。
*   **MemoryFactory**:
    *   支援後端切換 (Switchable Backend)，允許在開發環境 (SQLite) 與生產環境 (Redis) 間無縫切換。

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

## 🇺🇸 Memory System & Redis Architecture

### 1. Overview
v3.2 introduces a high-performance Redis-based `MemoryService`, replacing pure file or SQLite short-term memory. This architecture supports "Adaptive Compression" and "Cross-Session Context", enabling Agents to maintain long-term continuous thinking.

### 2. Architecture Design

#### 2.1 Memory Hierarchy
*   **Short-Term Memory (Hot)**:
    *   **Storage**: Redis (In-Memory).
    *   **Scope**: Current execution context, last 5 interactions.
    *   **TTL**: 24 hours ~ 7 days.
*   **Long-Term Memory (Cold)**:
    *   **Storage**: SQLite / Postgres.
    *   **Scope**: Historical reports, user preferences, long-term Alpha strategies.

#### 2.2 Core Components
*   **MemoryService**: Unified interface (`get_context`, `store_report`) managing sync/tiering.
*   **RedisMemoryRepository**: Adapter for connection pooling, JSON serialization, and TTL.
*   **MemoryFactory**: Switchable backend support for Dev/Prod parity.

### 3. Key Features

#### 3.1 Adaptive Compression
*   **Mechanism**: Triggered when Context Window exceeds 80%.
*   **Algorithm**: Retains recent 20% raw data, summarizes older 80% into vectors/bullet points.

#### 3.2 Conflict Detection
*   Retrieves last 3 days of history before generating new views.
*   Injects a `Consistency Warning` if today's view conflicts with yesterday's, forcing the Agent to justify the pivot.

### 4. Infrastructure

#### 4.1 Redis Deployment
*   **Image**: `redis:7-alpine`.
*   **Persistence**: RDB/AOF Enabled.
*   **Config**: Controlled via `MEMORY_BACKEND` and `REDIS_URL` env vars.
