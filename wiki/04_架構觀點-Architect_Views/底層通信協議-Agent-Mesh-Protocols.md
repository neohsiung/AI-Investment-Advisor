# 底層通信協議 (Agent Mesh Protocols)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 底層通信協議與 Agent Mesh (Internal Specs)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，詳細定義了 Agent Mesh 的通訊規範、安全性要求與工具調用協議。

### 1. 通訊框架 (Communication Framework)
系統採用雙層通訊架構，兼顧單機開發的便利性與分散式叢集的擴展性。
- **協定類型**: HTTP/1.1 + gRPC (內部)。
- **訊息格式**: JSON。

#### 1.1 雙模工具伺服器 (Dual-Mode MCP)
- **個人工具箱 (Local Mode)**: 每個 Agent 動態建立獨立的 `McpServer` 實例，用於 ReAct 迴圈中的即時運算（如股價獲取）。
- **微服務網格 (Service Mode)**: 獨立運行的 `mcp_service` FastAPI 容器，提供跨跨 Agent 共享的全局工具（如多源搜尋、報表歸檔）。

#### 1.2 訊息結構定義 (Protocol Schemas)

##### [NEW] 工具註冊 (Tool Registration)
```json
{
  "name": "string",
  "description": "string",
  "parameters": {
    "key": "type (str/int/float)",
    "description": "human readable"
  }
}
```

##### [NEW] Agent 間通訊 (Inter-Agent Message)
```json
{
  "sender": "string",
  "receiver": "string",
  "content": "markdown_string",
  "context": { "key": "any" }
}
```

### 2. 執行模型：ReAct 迴圈 (Execution Model: ReAct)
Agent 不僅僅是單次調用，而是透過 **Think-Act-Observe** 模式自主探索。

#### 2.1 思考-行動-觀察週期的邏輯 (Cycle Logic)
1.  **Think**: Agent 根據提示詞判斷是否需要外部工具。
2.  **Act**: LLM 輸出特定格式字串 `CALL: tool_name({"arg": "val"})`。
3.  **Observation**: 系統解析指令，執行 MCP 工具，並將結果以 `System: [Tool Output]` 形式回傳給 Agent 繼續思考。

#### 2.2 工具調用生命週期 (Tool Call Lifecycle)
```mermaid
sequenceDiagram
    participant Agent as Agent (BaseAgent)
    participant Local as Local MCP (Toolbox)
    participant Remote as MCP Microservice
    participant Logic as Business Service

    Agent->>Agent: Parse 'CALL:' from LLM
    alt Is Local Tool?
        Agent->>Local: execute(tool_name, args)
        Local->>Logic: internal call
    else Is Remote Tool?
        Agent->>Remote: POST /tools/call/
        Remote->>Logic: Distributed logic
    end
    Logic-->>Agent: JSON Result -> Observations
```

### 3. Agent 對 Agent 網格 (Agent-to-Agent Mesh)
本系統目前採用的 A2A 機制確保了任務的高度專業化與並行處理。

- **靜態實例 (Static Mode)**: 透過 `AgentFactory` 直接進行對等實體化調用。
- **訊息路由 (Message Mode)**: (v3.2+) 透過 `mcp_service/agents/message` 進行非同步任務分發，適合長耗時的研究任務。

### 2. 工具集詳細定義 (Toolset Specification)
所有工具均封裝於 [MCP 微服務](系統全景圖-System-Landscape) 中。

| 工具名稱 | 輸入參數 (Types) | 業務邏輯 / 數據源 |
| :--- | :--- | :--- |
| `get_current_price` | `ticker` (str) | [MarketDataService](服務層開發指南-Service-Layer-Blueprints) |
| `get_news` | `ticker` (str) | FMP / YFinance API |
| `get_financials` | `ticker` (str) | 基礎面數據聚合 |
| `search` | `query` (str) | Tavily / DuckDuckGo |

### 3. 安全與品質要求 (Security & Quality NFR)

- **預防 SQL 注入 (SQLi Prevention)**:
    - **強制規範**: 嚴禁在 Repo 層使用字串格式化拼接 SQL。
    - **範例**: `conn.execute("SELECT * FROM t WHERE id = ?", (id,))`。
- **機密管理 (Secrets Management)**:
    - 所有 API Keys 不得明文出現於日誌或代碼。
    - 採用 `Environment Repository` 模式加載加密變數。
- **HR 回饋協議**:
    - Agent 互相對報告品質評分 (1-5 分)，存儲於 `agent_reviews` 表。
    - 當平均評分 < 3.0 時，觸發 [Engineer Agent](核心系統規格-Core-System-Specs) 的 Prompt 重調。

### 4. 成功指標 (Success Metrics)
- **工具調用成功率**: > 99.5%。
- **注入漏洞發生率**: 0 (由 SAST `bandit` 保證)。

---

<a id="en"></a>

## 🇺🇸 Agent Mesh Protocols

### 1. Framework
Asynchronous MCP-based communication utilizing JSON payloads for inter-agent messages and tool execution.

### 2. Toolset Spec
Standardized interfaces for `get_current_price`, `get_news`, and `calculate_leverage`. Mathematical calculations are isolated in Python modules to prevent hallucinations.

### 3. Security (NFR)
- **SQLi**: Mandatory use of parameterized queries across all repositories.
- **Secrets**: Encrypted storage and environment-only loading.
- **HR Protocols**: 360-degree cross-agent scoring loop for automated prompt tuning.

### 4. Success Metrics
- **Tool Success Rate**: > 99.5%.
- **Zero-Injection Policy**: Verified by monthly SAST scans.

## 🔗 Bidirectional Links
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
- **PM Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **DB Design**: [Database Standards](資料庫設計與代碼規範-Database-Git-Standards)
