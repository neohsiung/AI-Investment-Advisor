# AI Agent Swarm

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 AI Agent Swarm

### 1. Design Philosophy
**"Efficiency-Driven, Context-Aware Execution."**

#### 1.1 Dual Models (Tiered)
- **Flash Tier**: Gemini 2.0 Flash / GPT-4o-mini. Low cost. For daily scan `Light CIO`.
- **Deep Tier**: Gemini 1.5 Pro / o1-preview. High reasoning. For complex analysis `Deep CIO`.

#### 1.2 Passive Analysis
- Agents are **Event-Driven**.
- **Daily Routine**: Flash scan. No alerts unless Signal > Threshold.
- **Active Dispatch**: Only when `Deep CIO` commands.

### 2. Role Definitions

#### 2.1 Investment Team
| Role | Mode | Responsibility |
| :--- | :--- | :--- |
| **Light CIO** | Flash | Gatekeeper. Filters noise. |
| **Deep CIO** | Deep | Strategy Leader. Dispatches agents. |
| **Momentum** | Passive | Technicals (Price/Volume). |
| **Fundamental**| Passive | Financials (10-K). |
| **Macro** | Passive | Economics (Fed/Rates). |

#### 2.2 HR Team
| Role | Responsibility |
| :--- | :--- |
| **Engineer** | **Prompt Optimizer**. Monitors performance and tunes prompts. |

#### 2.3 Implementation (v1.1)
- **Agent Factory**: All agents are instantiated via `AgentFactory` to ensure consistent configuration (TTL, Cache) and dependency injection.
- **Thinking Process**: The user interface (`4_Advisor_Chat.py`) displays granular thinking steps (Dispatcher intent, Data fetching status).

---

<a id="traditional-chinese"></a>

## 🇹🇼 AI 代理人集群 (AI Agent Swarm)

### 1. 集群設計哲學 (Design Philosophy)
系統採用**「事件驅動架構 (Event-Driven)」**與**「上下文感知執行 (Context-Aware)」**，強調資源效率最大化。

#### 1.1 雙軌模型 (Tiered Models)
為了最大化成本效益，我們依據任務難度分配模型資源：
*   **Flash Tier (輕量級)**:
    *   **模型**: Google Gemini 2.0 Flash / GPT-4o-mini
    *   **任務**: 每日市場掃描、新聞過濾 (Light CIO)、簡單摘要。
    *   **特性**: 速度快、成本極低。
*   **Deep Tier (深度級)**:
    *   **模型**: Google Gemini 1.5 Pro / o1-preview
    *   **任務**: 複雜財報解讀、總體經濟推演、CIO 最終決策 (Deep CIO)。
    *   **特性**: 邏輯強、支援長文本 (Long Context)、成本較高。

#### 1.2 被動式分析 (Passive Analysis)
*   **Analyst Agents (Momentum/Fundamental/Macro)** 平時處於**被動模式**。
*   **Daily Routine**: 每日收盤後，使用 **Flash Tier** 掃描市場。若無重大異常 (Signal Strength < Threshold)，僅將數據寫入 Database，**不主動發送報告**給 CIO。
*   **Active Dispatch**: 唯有當 **Deep CIO** 明確發出指令 (例如：「分析 NVDA 昨晚的暴跌原因」) 時，Agent 才切換至 **Deep Tier** 進行深度研究。

### 2. 角色定義 (Role Definitions)

#### 2.1 投資顧問部 (The Investment Team)

| 角色 | 運作模式 (Mode) | 職責 (Responsibility) |
| :--- | :--- | :--- |
| **Light CIO (Router)** | **Always-On (Flash)** | **守門員**。過濾 Event Bus 上的新聞與數據，決定是否喚醒團隊。 |
| **Deep CIO (Leader)** | **On-Demand (Deep)** | **決策者**。制定資產配置，調派分析師，撰寫最終報告。 |
| **Momentum Agent** | Passive / Active | **技術面**。關注價格行為、成交量、RSI/MACD。 |
| **Fundamental Agent** | Passive / Active | **基本面**。關注財報 (10-K/10-Q)、營收成長、估值。 |
| **Macro Agent** | Passive / Active | **總體經濟**。關注聯準會政策、利率、地緣政治。 |

#### 2.2 人力資源部 (The HR Team)

| 角色 | 職責 (Responsibility) |
| :--- | :--- |
| **Engineer Agent** | **Prompt 優化師**。觀察分析結果的準確度，動態調整上述 Agent 的 System Prompt。例如發現 Momentum Agent 過於敏感，則修改 Prompt 提高訊號門檻。 |

#### 2.3 實作細節 (Implementation v1.1)
*   **Agent Factory**: 所有 Agent 皆透過 `AgentFactory` 統一建立，確保快取設定 (TTL) 與依賴注入的一致性。
*   **思維透明化 (Thinking Process)**: 在互動式介面 (`4_Advisor_Chat.py`) 中，系統會即時顯示 Dispatcher 的意圖判斷、數據搜集進度與各 Agent 的分析狀態。

