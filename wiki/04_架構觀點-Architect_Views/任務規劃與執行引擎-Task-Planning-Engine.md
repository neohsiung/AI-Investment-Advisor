# 任務規劃與執行引擎 (Task Planning & Execution Engine)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**
> **最新版本 (Latest Version)**: 請參閱文件頂部的版本紀錄 (Iteration Record).

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-07 | v3.3 | Updated Report Synthesis Logic (Integrated Pattern) | Neo |
| 2026-01-14 | v3.2 | Initial Release with TaskPlanningService | Neo |

---

<a id="zh"></a>

## 🇹🇼 任務規劃與執行引擎 (Overview)

任務規劃與執行引擎是 v3 系列架構的核心組件，旨在解耦「目標設定」與「任務執行」。透過引入 `TaskPlanningService` 與 `LiteLLM` 多模型路由架構，系統能夠根據任務複雜度動態選擇最佳 AI 模型，並生成結構化的執行計劃 (DAG)。

### 1. 核心組件 (Core Components)

#### 1.1 任務規劃服務 (TaskPlanningService)
負責將高層次的用戶目標 (Goal) 分解為可執行的任務序列 (Task Sequence)。
*   **Goal Decomposition**: 將 "Generate Weekly Report" 分解為 "Macro Analysis", "Sector Rotation" 等子任務。
*   **Complexity Scoring**: 根據任務描述評估複雜度 (1-10)。
*   **Model Tiering**: 根據複雜度分配模型層級 (Fast, Smart, Advanced)。

#### 1.2 多模型路由架構 (LiteLLM Architecture)
系統透過 `LiteLLM` 統一介面，支援多模型混合調用策略：
*   **Tier 1: Fast (e.g., Gemini-Flash)**: Sentinel 監控、新聞過濾。
*   **Tier 2: Smart (e.g., GPT-4o)**: 程式碼生成、資料綜合。
*   **Tier 3: Advanced (e.g., Claude-3.5-Sonnet)**: 複雜推理、Gap Filling 策略、Alpha 生成。

### 2. 工作流與數據流 (Workflow & Data Flow)

#### 2.1 標準週報生成流程 (Standard Weekly Workflow)

1.  **Plan Phase**:
    *   `WeeklyWorkflow` 調用 `TaskPlanningService` 生成標準化 `TaskPlan`。
2.  **Execute Phase**:
    *   **Macro Agent**: 分析市場週期。
    *   **CIO Agent (Sector Mode)**: 制定板塊輪動策略。
    *   **Council (Map-Reduce)**: 發動分散式 `Analysts` 對持倉與候選名單進行深度掃描。
3.  **Synthesize Phase (Integrated Pattern)**:
    *   **Assembly**: `BaseWorkflow._assemble_integrated_report` 負責將詳細的辯論過程 (Detailed Analysis) 注入報告。
    *   **Refinement**: `CIOAgent.polish_report` 執行最終潤飾，確保行動指令表 (Actionable Orders) 的格式正確且包含持倉權重。

### 3. 關鍵機制 (Key Mechanisms)

#### 3.1 Gap Filling Logic (補倉邏輯)
*   **觸發條件**: Active Holdings Count < 15。
*   **執行路徑**: Macro (Cycle) -> Sector (Theme) -> Fundamental (Quality) -> Technical (Entry)。

#### 3.2 Swarm Insights (蜂群洞察)
*   整合 Momentum (動能)、Sentiment (情緒) 與 Fundamental (基本面) 的多維度訊號。
*   CIO Agent 作為最終仲裁者 (Arbiter)，解決不同 Agent 間的觀點衝突。

---

<a id="en"></a>

## 🇺🇸 Task Planning & Execution Engine

### 1. Overview
The Task Planning & Execution Engine decouples "Goal Setting" from "Task Execution" via `TaskPlanningService` and `LiteLLM` routing.

### 2. Core Components
*   **TaskPlanningService**: Decomposes goals into task sequences (DAGs) and assigns complexity scores.
*   **LiteLLM Routing**: Tiers models (Fast, Smart, Advanced) for optimal cost/performance.

### 3. Workflow & Data Flow
#### Standard Weekly Workflow
1.  **Plan Phase**: Generate `TaskPlan`.
2.  **Execute Phase**: Macro Analysis -> Sector Rotation -> Council Analysis (Map-Reduce).
3.  **Synthesize Phase (Integrated Pattern)**:
    *   **Assembly**: Injects detailed transcripts into the final report via `_assemble_integrated_report`.
    *   **Refinement**: CIO applies `polish_report` for formatting and readability (Editor Mode).

### 4. Key Mechanisms
*   **Gap Filling**: Triggered when active holdings < 15.
*   **Swarm Insights**: Cross-agent signal integration with CIO arbitration.
