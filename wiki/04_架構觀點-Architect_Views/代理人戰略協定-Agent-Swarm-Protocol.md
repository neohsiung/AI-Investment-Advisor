# 代理人戰略協定與認知授權 (Agent Swarm Protocol & Cognitive Mandates)

## 1. 概述 (Overview)
**代理人蜂群架構 (Agent Swarm Architecture)** 將投資顧問從線性流程轉變為由專業代理人組成的協作生態系統。每個代理人都在嚴格的「認知授權 (Cognitive Mandate)」下運作，並通過結構化的「投資委員會協定 (IC Protocol)」進行互動，以解決衝突並綜合出高確信度的洞察。

The **Agent Swarm Architecture** transforms the investment advisor from a linear pipeline into a collaborative ecosystem of specialized agents. Each agent operates under a strict "Cognitive Mandate" and interacts via a structured "IC Protocol" (Investment Committee) to resolve conflicts and synthesize high-conviction insights.

### 🏛️ 架構圖 (Architecture Diagram)

```mermaid
graph TD
    user((User)) -->|Triggers| CIO[CIO Agent]
    CIO -->|Broadcast| SWARM{Agent Swarm}
    
    subgraph "Swarm Intelligence"
        MACRO[Macro Strategist]
        FUND[Fundamental Analyst]
        SENT[Sentiment Analyst]
        TECH[Technical Analyst]
    end
    
    SWARM -->|Request| MACRO
    SWARM -->|Request| FUND
    SWARM -->|Request| SENT
    SWARM -->|Request| TECH
    
    MACRO -->|Signal| AGG[Aggregation Layer]
    FUND -->|Signal| AGG
    SENT -->|Signal| AGG
    TECH -->|Signal| AGG
    
    AGG -->|Conflict Matrix| CIO
    CIO -->|Reasoning (R.P.A.)| DECISION[Final Decision]
```

## 2. 蜂群角色 (Agent Swarm Roles)

### 2.1 首席投資官 (Chief Investment Officer, CIO)
*   **認知授權 (Cognitive Mandate)**: 「綜合者與仲裁者 (Synthesizer & Arbitrator)」
*   **職責 (Responsibility)**:
    *   整合多模態輸入 (宏觀、基本面、情緒、技術面)。
    *   使用 **衝突解決矩陣 (Conflict Resolution Matrix)** 解決分歧。
    *   管理投資組合風險與最終決策。
    *   **安全迴路 (Safety Fallback)**: 若績效服務失效，自動觸發「等權重裁決 (Equal Weight Arbitration)」與「最大槓桿限制 (Max Leverage 0.95x)」。
    *   **產出**: 最終投資報告與再平衡指令。
    *   Integrates multi-modal inputs (Macro, Fundamental, Sentiment, Technical).
    *   Resolves conflicts using the **Conflict Resolution Matrix**.
    *   Manages portfolio risk and final decision-making.
    *   **Safety Fallback**: Triggers "Equal Weight Arbitration" and "Max Leverage 0.95x" if Performance Service fails.
    *   **Output**: Final Investment Report & Rebalancing Orders.

### 2.2 宏觀策略師 (Macro Strategist)
*   **認知授權 (Cognitive Mandate)**: 「週期架構師 (Cycle Architect)」
*   **職責 (Responsibility)**:
    *   識別當前市場週期 (例如：週期末段、衰退、復甦)。
    *   分析利率、通膨與地緣政治流向。
    *   **產出**: 由上而下的資產配置觀點 (Risk-On vs. Risk-Off)。
    *   Identifies the current market cycle (e.g., Late Cycle, Recession, Recovery).
    *   Analyzes rates, inflation, and geopolitical flows.
    *   **Output**: Top-down Asset Allocation Views (Risk-On vs. Risk-Off).

### 2.3 基本面分析師 (Fundamental Analyst)
*   **認知授權 (Cognitive Mandate)**: 「由下而上偵探 (Bottom-Up Detective)」
*   **職責 (Responsibility)**:
    *   分析公司財報、護城河與估值。
    *   識別高品質的複利機器與價值陷阱。
    *   **產出**: 個股投資論述 (買入/賣出/持有)。
    *   Analyzes company financials, moats, and valuation.
    *   Identifies quality compounders and value traps.
    *   **Output**: Company-specific Investment Theses (Buy/Sell/Hold).

### 2.4 情緒分析師 (Sentiment Analyst)
*   **認知授權 (Cognitive Mandate)**: 「行為計量分析師 (Behavioral Quant)」
*   **職責 (Responsibility)**:
    *   分析市場心理、新聞情緒與散戶活動。
    *   識別反向訊號與群眾狂熱/恐慌。
    *   **產出**: 情緒分數與行為警示。
    *   Analyzes market psychology, news sentiment, and retail activity.
    *   Identifies contrarian signals and crowd euphoria/panic.
    *   **Output**: Sentiment Scores and Behavioral Flags.

## 3. 投資委員會協定 (IC Protocol)
**IC 協定** 規範了代理人如何互動以達成共識。
The **IC Protocol** governs how agents interact to reach a consensus.

1.  **每日健康檢查 (Daily Health Check)**:
    *   **觸發**: CIO 於開盤時發起。
    *   **行動**: 代理人檢查各自的儀表板 (宏觀利率、特定個股、情緒指標)。
    *   **匯報**: 代理人提交「每日簡報」給 CIO。
    *   **Trigger**: CIO initiates at market open.
    *   **Action**: Agents check their specific dashboards (Macro rates, specific tickers, sentiment gauges).
    *   **Reporting**: Agents submit a "Daily Brief" to the CIO.

2.  **衝突解決矩陣 (Conflict Resolution Matrix)**:
    *   當代理人意見分歧時，CIO 根據當前體制 (Regime) 進行加權：
        *   **財報季 (Earnings Season)**: 基本面 > 技術面 > 宏觀。
        *   **危機/修正期 (Crisis/Correction)**: 宏觀 > 技術面 > 基本面。
        *   **泡沫/狂熱期 (Bubble/Mania)**: 情緒 > 技術面 > 基本面。
    *   When agents disagree, the CIO weighs them based on the current regime:
        *   **Earnings Season**: Fundamental > Technical > Macro.
        *   **Crisis/Correction**: Macro > Technical > Fundamental.
        *   **Bubble/Mania**: Sentiment > Technical > Fundamental.

3.  **思維鏈強制 (Thought Chain Enforcement)**:
    *   所有代理人必須遵循 **R.P.A. 迴圈**:
        *   **推理 (Reasoning)**: 「為什麼會發生這種情況？」(因果連結)
        *   **計畫 (Plan)**: 「接下來需要什麼資訊？」(工具選擇)
        *   **行動 (Action)**: 「執行工具/產生輸出。」
    *   All agents must follow the **R.P.A. Loop**:
        *   **Reasoning**: "Why is this happening?" (Causal Links)
        *   **Plan**: "What information do I need next?" (Tool Selection)
        *   **Action**: "Execute tool/Generate output."

## 4. MCP 整合策略 (MCP Integration Strategy)
*   **個人工具箱 (Personal Toolbox)**: 每個代理人擁有專屬的本地 MCP 伺服器，用於內部工具 (計算機、專用啟發式函數)。
*   **共享服務 (Shared Services)**: 代理人透過中央 MCP 服務存取共享數據服務 (市場數據、新聞)。
*   **A2A 通訊 (A2A Comm)**: 代理人透過 CIO 的協調進行「訊息傳遞」 (初期採軸輻式模型，後續移轉至網狀網路)。
*   **Personal Toolbox**: Each agent has a dedicated local MCP server for internal tools (Calculator, specialized heuristic functions).
*   **Shared Services**: Agents access shared data services (Market Data, News) via the central MCP Service.
*   **A2A Comm**: Agents "message" each other via the CIO's orchestration (Hub-and-Spoke model initially, moving to Mesh later).
