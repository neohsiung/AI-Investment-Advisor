# AI Agent Swarm Specification (v3)

> **Status**: Draft
> **Version**: 1.0

## 1. Overview
The Agent Swarm consists of specialized agents collaborating to generate investment strategies. v3 introduces "Passive/Active" modes and "Model Tiering" (Flash vs Deep).

## 2. Agent Roles & Prompts

### 2.1 Momentum Agent
*   **Role**: Technical Analyst.
*   **Input**: Price history, Volume, RSI, MACD.
*   **Output**: Trend Analysis (Bullish/Bearish), Support/Resistance levels.
*   **Prompt**: `prompts/momentum_agent.txt`
    *   *Persona*: "You are a veteran technical trader...".
    *   *Constraint*: Must cite specific indicators.

### 2.2 Fundamental Agent
*   **Role**: Fundamental Analyst.
*   **Input**: Financial Statements (10-K, 10-Q), Earnings Call Transcripts (via Browser).
*   **Output**: Valuation (Undervalued/Overvalued), Growth Drivers, Risks.
*   **Prompt**: `prompts/fundamental_agent.txt`
    *   *Persona*: "You are a disciplined value investor (Buffett/Munger style)...".

### 2.3 Macro Agent
*   **Role**: Global Macro Strategist.
*   **Input**: FRED Data (GDP, CPI, Unemployment, Yield Curve).
*   **Output**: Economic Cycle Phase, Sector Rotation advice.
*   **Prompt**: `prompts/macro_agent.txt`
    *   *Persona*: "You are a Global Macro Strategist observing the Fed..."

### 2.4 CIO Agent (Chief Investment Officer)
*   **Role**: Portfolio Manager & Decision Maker.
*   **Input**: Reports from all above agents + User Portfolio State.
*   **Output**: Final Buy/Sell/Hold decisions, Asset Allocation changes.
*   **Prompt**: `prompts/cio_agent.txt`
    *   *Logic*: Weighs dissenting opinions. Prioritizes Capital Preservation.

## 3. Tool Utilization

### 3.1 MarketDataService (Enhancement)
*   Integrate `Alpha Vantage` for more granular data if needed.
*   Add `FRED` client for Macro Agent.

### 3.2 BrowserService (New)
*   **Purpose**: Fetch latest news/earnings transcripts when `yfinance` is insufficient.
*   **Implementation**: Headless Chrome (via simple `requests` + `BeautifulSoup` or `playwright` if needed, but keeping it simple first).

## 4. Interaction Flow (v3 Event-Driven)
1.  **Trigger**: Daily Market Close or Significant News.
2.  **Flash Scan**: Agents run in `Flash Mode` (cheap).
3.  **Filter**: `LightCIO` decides if a full report is needed.
4.  **Deep Dive**: If yes, `DeepCIO` dispatches specific "Deep Research" tasks to agents.
5.  **Synthesis**: Final report generated.
