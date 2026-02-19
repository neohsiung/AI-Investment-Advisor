# 智能體集群模式 (Swarm Patterns)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 智能體集群 (Agentic Coordination)

本文件說明系統如何透過多個 Agent 的協作、並行分析與共識機制，達成高度自動化且精確的投資建議。

### 1. 核心模式：ReAct 迴圈
- **機制**: Think-Act-Observe。
- **實作**: 每個 Agent 在執行時，會根據當前上下文思考是否需要調用工具（Act），並在獲取結果後（Observe）更新認知。

### 2. 評議會共識機制 (Council Swarm)
- **願景**: 避免單一模型的偏見與幻覺。
- **實作**: 透過 `CouncilService` 發動分散式辯論。
    - **Step 1 (Parallel Analysis)**: 多個專家 Agent (Macro, Momentum, Value) 同步執行。
    - **Step 2 (Debate)**: 專家之間互相審核觀點。
    - **Step 3 (Consensus)**: CIO Agent 匯整所有證據鏈，產生最終決策。

### 3. Map-Reduce 持倉分析
- **情境**: 當用戶擁有大量持倉（例如 50+ 檔美股）時，單次上下文無法容納。
- **模式**:
    - **Map**: 將持倉拆分為多個小組，由多個子 Agent 並行分析。
    - **Reduce**: 匯整各組分析結果，產出整體組合的風險掃描。

---

<a id="en"></a>

## 🇺🇸 Swarm Patterns

### 1. ReAct Loop
- **Logic**: Think -> Act -> Observe. Each agent explores tools autonomously based on partial information.

### 2. Council Consensus
- **Parallelism**: Multiple specialized agents (Macro, Momentum, etc.) running in parallel to maximize information throughput.
- **Debate Layer**: Cross-agent critique to reduce hallucinations.

### 3. OpenClaw Map-Reduce
- **Scalability**: Chunking large portfolios into smaller groups for parallelized agentic processing, then aggregating results into a final risk report.

## 🔗 Bidirectional Links
- **Intro**: [Design Patterns Intro](設計模式導讀-Design-Patterns-Intro)
- **Sentinel Architecture**: [Sentinel & Council Architecture](哨兵與評議會架構-Sentinel-Council-Architecture)
- **Swarm Protocol**: [Agent Swarm Protocol](代理人戰略協定-Agent-Swarm-Protocol)
