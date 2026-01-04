# Functional Specification: Adaptive Agent System

## Version History
| Version | Date | Description | Author |
| :--- | :--- | :--- | :--- |
| v5.0 | 2025-12-13 | **Adaptive System Update**: Added Smart Freshness, Model Tiering, HR Protocol, and Interactive Dispatcher. | AI Assistant |


> [English](#english) | [Traditional Chinese](#traditional-chinese)

## English
The Adaptive Agent System (Stage 5) introduces intelligence layer enhancements to optimize cost, improve responsiveness, and enable interactive user engagement.

## 2. Core Features

### 2.1 Smart Freshness & Cost Efficiency
- **Goal**: Reduce unnecessary LLM calls (tokens) when input data is unchanged.
- **Mechanism**:
    - **Hashing**: Each agent computes `SHA256(Input Context)`.
    - **State Tracking**: `agent_states` table stores `last_input_hash`, `last_run_time`, `last_output`.
    - **Logic**:
        - If `Current Hash == Last Hash`, Agent returns `last_output` from DB.
        - If difference detected, Agent runs LLM and updates DB.
- **Granularity**:
    - Momentum/Fundamental: Keyed by `Ticker` (e.g., `Momentum_AAPL`).
    - Macro/CIO: Global Key.

### 2.2 Model Tiering (Hybrid Intelligence)
- **Goal**: Balance performance and cost.
- **Tiers**:
    1.  **SMART Tier**: High reasoning capability.
        -   **Models**: Gemini 1.5 Pro, GPT-4o.
        -   **Agents**: CIO, Macro, Fundamental, System Engineer.
    2.  **FAST Tier**: High speed, low cost.
        -   **Models**: Gemini 1.5 Flash, GPT-4o-mini.
        -   **Agents**: Momentum, Dispatcher.
- **Configuration**: Managed via `Settings` page.

### 2.3 HR Protocol (Self-Evolution)
- **Goal**: Detect zombie/inactive agents.
- **Logic**:
    - CIO receives `Agent Status` (list of last run times) in its context.
    - **Rule**: If `Last Run > 7 Days`, CIO output contains `[HR_REQUEST] Replace Agent: {Name}`.
    - **Action**: System Engineer parses this tag and logs a replacement request (future: auto-generate new prompt).

### 2.4 Interactive Advisor (Dispatcher)
- **Goal**: Allow users to "Talk" to the system.
- **UI**: `src/pages/4_Advisor_Chat.py`.
- **Dispatcher Agent**:
    - Input: Natural Language (e.g., "Analyze NVDA earnings").
    - Output: JSON `{"agents": ["Fundamental"], "tickers": ["NVDA"]}`.
    - Flow: Dispatcher -> System invokes Agents -> Display results.

## 3. Architecture Transition
- **Hybrid Serverless**:
    - **Batch Analysis**: Run via Cloud Run Jobs (Serverless Batch).
    - **Interactive UI**: Run via Cloud Run Service (Scale-to-Zero) or Local Streamlit.
    - **State**: Centralized in Cloud SQL (PostgreSQL).

## 4. User Manual Updates
- **Settings**: New section for Model Tiering Config.
- **Chat**: New page usage.

---

<a id="traditional-chinese"></a>

## 1. 概述 (Overview)
自適應代理系統 (Adaptive Agent System - Stage 5) 引入了智能層增強功能，旨在優化成本、提高響應速度並實現互動式用戶參與。

## 2. 核心功能 (Core Features)

### 2.1 智慧新鮮度與成本效益 (Smart Freshness)
- **目標**: 當輸入數據未變更時，減少不必要的 LLM 調用 (節省 Token)。
- **機制**:
    - **雜湊比對 (Hashing)**: 每個 Agent 計算 `SHA256(Input Context)`。
    - **狀態追蹤**: `agent_states` 資料表存儲 `last_input_hash`, `last_run_time`, `last_output`。
    - **邏輯**:
        - 若 `當前 Hash == 上次 Hash`，Agent 直接從資料庫返回 `last_output`。
        - 若檢測到差異，Agent 執行 LLM 並更新資料庫。
- **細緻度**:
    - Momentum/Fundamental: 以 `Ticker` 為鍵 (例如 `Momentum_AAPL`)。
    - Macro/CIO: 全局鍵 (Global Key)。

### 2.2 模型分級 (Model Tiering)
- **目標**: 平衡性能與成本。
- **分級**:
    1.  **SMART Tier (智囊團)**: 高推理能力。
        -   **模型**: Gemini 1.5 Pro, GPT-4o。
        -   **適用 Agent**: CIO (投資長), Macro (總經), Fundamental (基本面), System Engineer (工程師)。
    2.  **FAST Tier (前鋒)**: 高速、低成本。
        -   **模型**: Gemini 1.5 Flash, GPT-4o-mini。
        -   **適用 Agent**: Momentum (動能), Dispatcher (調度員)。
- **設定**: 透過 `Settings` 頁面管理。

### 2.3 HR 協議 (自我進化)
- **目標**: 偵測殭屍/不活躍的 Agent。
- **邏輯**:
    - CIO 在其 Context 中接收 `Agent Status` (最後運行時間列表)。
    - **規則**: 若 `Last Run > 7 Days`，CIO 輸出包含 `[HR_REQUEST] Replace Agent: {Name}`。
    - **行動**: System Engineer 解析此標籤並記錄替換請求 (未來功能: 自動生成新 Prompt)。

### 2.4 互動式顧問 (Dispatcher)
- **目標**: 允許使用者與系統「對話」。
- **介面**: `src/pages/4_Advisor_Chat.py`.
- **Dispatcher Agent**:
    - 輸入: 自然語言 (例如 "分析 NVDA 財報")。
    - 輸出: JSON `{"agents": ["Fundamental"], "tickers": ["NVDA"]}`。
    - 流程: 調度員 -> 系統調用 Agents -> 顯示結果。

## 3. 架構轉型 (Architecture Transition)
- **混合無伺服器 (Hybrid Serverless)**:
    - **批次分析**: 透過 Cloud Run Jobs (Serverless Batch) 執行。
    - **互動式 UI**: 透過 Cloud Run Service (Scale-to-Zero) 或本地 Streamlit 執行。
    - **狀態**: 集中於 Cloud SQL (PostgreSQL)。

## 4. 使用者手冊更新
- **設定**: 新增模型分級設定章節。
- **聊天**: 新增頁面使用說明。
