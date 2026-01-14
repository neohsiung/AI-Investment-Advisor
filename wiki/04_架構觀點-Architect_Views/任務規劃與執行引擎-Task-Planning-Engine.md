# 任務規劃與執行引擎 (Task Planning & Execution Engine)

> **版本 (Version):** v3.2  
> **更新日期 (Last Updated):** 2026-01-14  
> **狀態 (Status):** Production Ready

## 1. 概述 (Overview)

任務規劃與執行引擎是 v3.2 架構的核心組件，旨在解耦「目標設定」與「任務執行」。透過引入 `TaskPlanningService` 與 `LiteLLM` 多模型路由架構，系統能夠根據任務複雜度動態選擇最佳 AI 模型，並生成結構化的執行計劃 (DAG)。

## 2. 核心組件 (Core Components)

### 2.1 任務規劃服務 (TaskPlanningService)

負責將高層次的用戶目標 (Goal) 分解為可執行的任務序列 (Task Sequence)。

*   **職責**:
    *   **Goal Decomposition**: 將 "Generate Weekly Report" 分解為 "Macro Analysis", "Sector Rotation", "Gap Filling" 等子任務。
    *   **Complexity Scoring**: 根據任務描述評估複雜度 (1-10)。
    *   **Model Tiering**: 根據複雜度分配模型層級 (Fast, Smart, Advanced)。

### 2.2 多模型路由架構 (LiteLLM Architecture)

系統透過 `LiteLLM` 統一介面，支援多模型混合調用策略：

*   **Tier 1: Fast (Claude-3-Haiku / Gemini-Flash)**
    *   用途: Sentiment Analysis, News Filtering, Text Summarization
    *   特點: 低延遲、低成本。
*   **Tier 2: Smart (GPT-4o / Gemini-Pro)**
    *   用途: Code Generation, Data Synthesis, Sector Analysis
    *   特點: 平衡推理能力與速度。
*   **Tier 3: Advanced (Claude-3.5-Sonnet / o1-preview)**
    *   用途: Complex Reasoning, Gap Filling Strategy, Alpha Generation
    *   特點: 最高推理能力，用於關鍵決策。

## 3. 工作流與數據流 (Workflow & Data Flow)

### 3.1 標準週報生成流程 (Standard Weekly Workflow)

1.  **Plan Phase**:
    *   `WeeklyWorkflow` 調用 `TaskPlanningService`。
    *   生成標準化 `TaskPlan` (包含 Gap Filling 邏輯判斷)。
2.  **Execute Phase**:
    *   **Macro Agent**: 分析市場週期 (Input: Macro Data -> Output: Market Phase)。
    *   **CIO Agent (Sector Mode)**: 根據 Market Phase 制定板塊輪動策略 (Output: Target Sectors)。
    *   **CIO Agent (Gap Filling)**: 若持倉 < 15，執行補倉篩選 (Output: Alpha Candidates)。
    *   **Fundamental Agent**: 對持倉與候選名單進行深度掃描 (Deep Dive)。
    *   **Technical**: 確認進場點。
3.  **Synthesize Phase**:
    *   將所有 `RESULT_` 匯總，由 CIO Agent 生成最終報告。

## 4. 關鍵機制 (Key Mechanisms)

### 4.1 Gap Filling Logic (補倉邏輯)
*   **觸發條件**: Active Holdings Count < 15。
*   **執行路徑**: Macro (Cycle) -> Sector (Theme) -> Fundamental (Quality) -> Technical (Entry)。
*   **目的**: 確保投資組合始終維持足夠的分散度與 Alpha 潛力。

### 4.2 Swarm Insights (蜂群洞察)
*   整合 Momentum Agent (動能)、Sentiment Agent (情緒) 與 Fundamental Agent (基本面) 的多維度訊號。
*   CIO Agent 作為最終仲裁者 (Arbiter)，解決不同 Agent 間的觀點衝突 (e.g., 基本面看多但技術面看空)。
