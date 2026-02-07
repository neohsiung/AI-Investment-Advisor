# OpenClaw 執行環境 (OpenClaw Runtime Environment)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**
> **最新版本 (Latest Version)**: 請參閱文件頂部的版本紀錄 (Iteration Record).

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-07 | v3.5 | Standardized naming and structure | Neo |
| 2026-02-07 | v3.4 | Initial Draft | Neo |

---

<a id="zh"></a>

## 🇹🇼 OpenClaw 執行環境 (Overview)

本文件概述了 "OpenClaw" 執行環境升級的架構藍圖。目標是將投資顧問系統從一組概率性的腳本，轉變為一個確定性、高可靠度的「智能體作業系統 (Agentic OS)」。

### 1. 核心架構：六層模型 (Six-Layer Model)

#### 第一層：存取與正規化 (輸入適配器)
*   **角色**：標準化來自 Line、Web 或 CLI 的輸入/輸出 (I/O)。
*   **組件**：`ChannelAdapter`
*   **邏輯**：所有的輸入必須產生一個標準化的 `Event` 物件，其中包含 `session_id` 和 `payload`。

#### 第二層：控制平面 (閘道與泳道隊列)
*   **角色**：管理併發 (Concurrency) 與會話狀態 (Session State)。
*   **組件**：`LaneManager`
*   **邏輯**：
    *   為記憶體中每個活躍的 `session_id` 分配一個 `Queue`。
    *   設定 `concurrency: 1` 確保每個用戶的請求按順序執行。

#### 第三層：認知執行環境 (Agent 迴圈)
*   **角色**：「大腦」的執行環境。
*   **組件**：`AgentRuntime` (重構後的 `BaseAgent`)
*   **邏輯**：
    *   **動態提示 (Dynamic Prompting)**：在每一回合 (Turn) 重新建構系統提示詞 (System Prompt)，注入以下內容：
        *   `TimeContext`：即時時間。
        *   `SkillRegistry`：來自 `SKILL.md` 的可用工具 XML 列表。
        *   `MemoryContext`：來自混合檢索的前 K 條相關事實 (Top-K Facts)。

#### 第四至六層：互動與記憶
*   **混合記憶體 (Hybrid Memory)**：
    *   **儲存**：SQLite (`sqlite-vec` + FTS5)。
    *   **融合演算法**：`Score = (Vector * 0.7) + (BM25 * 0.3)`。

### 2. 功能亮點：全投資組合評議會 (Map-Reduce)

為了解決「5 檔持股限制」的問題，每日評議會報告將執行 Map-Reduce 運算。

#### 第一階段：Map (分發)
*   **輸入**：用戶的投資組合 (例如 20 檔代碼)。
*   **流程**：
    1.  將代碼分為多個區塊 (Chunks)，例如每塊 5 檔。
    2.  針對每一檔代碼，生成一個 **子評議會 (Sub-Council)** (包含 動能 Agent + 基本面 Agent)。
    3.  **提示詞**：「分析 [Ticker]。嚴格輸出：SIGNAL (買入/賣出/持有) | RATIONALE (理由)」。

#### 第二階段：Reduce (聚合)
*   **輸入**：來自第一階段的 20 份迷你報告。
*   **流程**：
    1.  聚合為結構化摘要：
        ```text
        - NVDA: BUY (營收強勁)
        - TSLA: HOLD (波動過大)
        ...
        ```
    2.  檢查 Token 長度。如果過長，將評級為 "Neutral/Hold" 的標的濃縮為單行，並保留 "Alert" 標的的詳細資訊。

#### 第三階段：Synthesis (主席決策)
*   **輸入**：聚合後的摘要 + 宏觀市場背景。
*   **流程**：CIO Agent 執行最終的「辯論」提示詞，生成面向用戶的完整報告。

### 3. 安全與防護 (Safety)
*   **工具閘門 (Tool Gating)**：`SKILL.md` 定義作業系統需求。如果缺少 `curl` 或 `docker`，相關工具將不會加載。
*   **正則守衛 (Regex Guard)**：`rm -rf` 等危險指令將在提示詞層級被攔截。

---

<a id="en"></a>

## 🇺🇸 OpenClaw Runtime Environment

### 1. Executive Summary
OpenClaw transforms the Advisor into a deterministic Agentic OS.

### 2. Core Architecture (Six Layers)
*   **Layer 1 (Adapters)**: Standardizes I/O into `Event` objects.
*   **Layer 2 (Control Plane)**: `LaneManager` ensures sequential processing per user via `Lane Queue`.
*   **Layer 3 (Cognitive Runtime)**: `AgentRuntime` with dynamic prompting (Time, Skills, Memory).
*   **Layer 4-6 (Memory)**: Hybrid Search (`Vector` * 0.7 + `BM25` * 0.3).

### 3. Full Portfolio Council (Map-Reduce)
*   **Map**: Chunks portfolio (e.g., 5 tickers) and spawns parallel analysis tasks.
*   **Reduce**: Aggregates signals into a structured summary.
*   **Synthesize**: CIO Agent generates the final report from the summary.

### 4. Safety
*   **Tool Gating**: Validates OS dependencies for skills.
*   **Regex Guard**: Blocks dangerous shell commands.
