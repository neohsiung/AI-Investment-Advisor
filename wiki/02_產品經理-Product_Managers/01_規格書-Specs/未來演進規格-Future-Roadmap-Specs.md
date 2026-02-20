# 未來演進規格 (Future Roadmap Specifications)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 未來演進規格書 (v4.0 — Agent Swarm Economy)

本文件描述了 Role × Multi-Agent 智能體集群經濟的技術深度與業務目標。

### 1. 問題與目標 (Problem & Goals)
- **核心挑戰**: 單體 Agent 模式下，每個角色以序列方式處理複雜研究任務（一份財報、一則宏觀事件），導致延遲瓶頸與單點決策風險。
- **目標**: 將每個 Agent 角色拆分為 **Role × Multi-Agent** — 角色不變，背後由專注 Sub-Agent 群體併發執行，追求效率與正確性。

### 2. 功能詳述 (Features & Functionality)

#### 2.1 v3.3 危機自動駕駛 (Crisis Autopilot)
- **目標**: 回撤控制 < 10%。
- **核心邏輯**: 
    - **體制偵測 (Regime Switching)**: 透過 HMM (隱藏馬可夫模型) 將市場分為「通膨/成長」、「衰退」等象限。
    - **自動化防禦**: 體制切換時，自動調整資產類別配比（從 Equity 轉向 Gold/Cash）。
- **UX Story**: 當標普 500 週跌幅超過 10% 時，系統主動發送「防禦體制已啟動」報告，並展示資產遷移路徑。

#### 2.2 v3.4 自適應算力 (Adaptive Compute - Toggle Algorithm)
- **目標**: 在不犧牲品質的前提下，降低 30% Token 消耗。
- **核心邏輯**:
    - **動態路由 (Dynamic Routing)**: 
        - **Fast Path**: 對於簡單的新聞過濾，使用 `gemini-2.0-flash-lite`。
        - **Think Path**: 對於複雜的財報解讀，使用 `gemini-2.0-pro-exp` 並開啟 `thinking_mode`。
    - **信心閾值**: 若 Fast Path 信心分數 < 0.8，自動升級至 Think Path。
- **待辦事項 (To-Do)**:
    - [ ] 實作 `RouterAgent`，根據複雜度分類器 (Complexity Classifier) 分發請求。

#### 2.3 v4.0 智能體集群 — Role × Multi-Agent (Agent Swarm Economy)

> **核心理念: 角色即核心、群體即效率。**

##### 2.3.1 Swarm Framework 基底設計

```
┌───────────────────────────────────────────────────────┐
│  SwarmOrchestrator (全域編排器)                          │
│  ├── 任務拆解 (Task Decomposition)                      │
│  ├── asyncio.gather 併發分發                             │
│  ├── Critical Path 監控 & 動態資源分配                    │
│  └── Fan-in 結果匯聚 & 衝突仲裁                          │
├───────────────────────────────────────────────────────┤
│  RoleSwarmBase (角色群體基底類別)                         │
│  ├── decompose(task) → List[SubTask]                  │
│  ├── dispatch(subtasks) → List[SubAgentResult]        │
│  └── aggregate(results) → RoleOutput                  │
└───────────────────────────────────────────────────────┘
```

- **`SwarmOrchestrator`**: 統一的 Sub-Agent 編排框架，支援 `asyncio.gather` 併發 + 超時 + 重試 + 熔斷。
- **`RoleSwarmBase`**: 各角色 Swarm 的抽象基底：任務拆解 (Fan-out) → 分發 → 匯聚 (Fan-in)。

##### 2.3.2 智能體集群演進路徑 (Evolution Path)

**里程碑: 基底層與首批 Pilot (Milestone: Foundation & Pilot)**
*   **目標**: 實作 `SwarmOrchestrator` 與異步並行機制。
*   **交付角色**:
    - **Fundamental Swarm**: `RevenueExtractor`, `RiskFactorScanner`, `ValuationModeler`。
    - **Sentiment Swarm**: `NewsScanner`, `SocialPulse`。

**里程碑: 全面 Swarm 化 (Milestone: Full Swarm Rollout)**
*   **目標**: 角色擴展與自適應算力整合。
*   - **交付角色**: Momentum (3), Macro (3), Risk (3) Swarms。

##### 2.3.3 自動共復盤協議 (Auto-Retrospective Protocol)
- **目標**: 實作決策對帳與 Agent 權重自動校準。
- **核心組件**: 
    - `RetrospectiveAgent`: 編排歸因任務。
    - `AttributionAnalyzer`: 執行 P&L 歸因 (Selection, Allocation, Timing)。
    - `StrategyRefiner`: 根據歸因結果修正 Agent 配置。
- **技術路徑**:
    - [ ] 實作日終/週終歸因觸發器。
    - [ ] 對接 `MarketDataService` 獲取真實基準回報。

#### 2.4 Alpha 優化與自主演化 (Alpha Optimization & Self-Evolution)
- **目標**: 追求超越標普 500 的超額收益。
- **技術需求**: 
    - **FinRL 模擬環境**: 讓 `Engineer Swarm` 在虛擬沙盒中測試新因子，且僅當 Alpha > 基準 5% 時才准予上線。
    - **Strategy Drift Sentinel**: 監控策略漂移。當回撤 (MDD) 超過 10% 或 Alpha 轉負時，強制暫停交易並啟動深度復盤。
- **多模態聯合優化**: K線圖 (視覺) + 財報文本的 Joint Optimization。

#### 2.4 多模態聯合優化 (Multimodal Joint Optimization)
- **目標**: 讓 AI 能像交易員一樣「看」懂 K 線圖。
- **核心邏輯**:
    - **Zero-Vision SFT**: 訓練模型寫出「能繪製該圖表」的 Python 代碼，藉此理解圖形結構。
    - **視覺強化學習**: 對齊視覺特徵與文本描述（如：「此處為頭肩頂結構」）。
- **待辦事項 (To-Do)**:
    ### 2.5 管道適配器架構 (Channel Adapter Architecture - v3.7)
- **目標**: 實作「一次邏輯，多端分發」。
- **介面定義**:
    - `IChannelAdapter`: 定義 `send_message`, `receive_command`, `authenticate`。
    - `LineAdapter`: 處理 LINE Message API 的 JSON 簽名與網址對應。
    - `WebAdapter`: 處理 Streamlit 端的 Session 狀態。

### 3. 技術要求 (Technical Requirements)

- **分散式運算**: 
    - 採用 **KubeRay** (Ray on Kubernetes)。
    - **架構**: Head Node 管理任務分發，Worker Nodes (Spots 實例) 執行並行回測。
- **併發框架**:
    - `asyncio.gather` + `asyncio.Semaphore` 控制併發度。
    - Sub-Agent 間透過 `asyncio.Queue` 通訊。
- **演化引擎**:
    - **MetaGPT 整合**: 用於自主代碼生成的代碼代理。
    - **遺傳演算法 (Genetic Algorithm)**: 用於邏輯片段的交叉 (Crossover) 與變異 (Mutation)。
- **數據湖 (Data Lake)**: 擴充至存儲非結構化社交媒體原始流以供情感演化。

### 4. 非功能性需求 (NFR)
- **可移植性**: 支援多雲 (AWS/GCP/Azure) 分散式混合部署。
- **安全性**: 針對自主生成的代碼執行沙盒 (Sandbox) 隔離運行。
- **容錯**: 單一 Sub-Agent 失敗不影響整體 Swarm 輸出 (Graceful Degradation)。

### 5. 成功指標 (Success Metrics)
| 指標 | 目標 |
| :--- | :--- |
| **Alpha** (超額報酬) | > 5% vs S&P 500 |
| **延遲改善** | 端對端研究任務延遲 ÷ 4 |
| **Token 效率** | 降低 30% (Toggle) |
| **最大回撤** | < 10% |
| **自我進化** | 每週自主有效新因子 > 1 |
| **復盤覆蓋率** | 100% 決策均需完成自動歸因 |

### 6. 發展迭代清單 (Milestone Checklist)

- [ ] **Milestone: Foundation** — Implement `SwarmOrchestrator`, Fundamental Swarm, Sentiment Swarm.
- [ ] **Milestone: Expansion** — Implement Momentum, Macro, Risk Swarms + Toggle integration.
- [ ] **Milestone: Integration** — Implement CIO Swarm, Engineer Swarm, Critical Path monitoring.
- [ ] **Milestone: Multimodal** — End-to-end stress test & Multimodal alignment.

---

<a id="en"></a>

## 🇺🇸 Future Roadmap Specifications (v4.0 — Agent Swarm Economy)

### 1. Problem & Goals
Single-agent serial processing creates latency bottlenecks and single-point decision risk. **Role × Multi-Agent** decomposes each role into parallel Sub-Agents for efficiency and correctness.

### 2. Features

#### 2.2 核心自動化特性 (Autonomous Lifecycle Features)
- **無限事件循環 (Infinite Event Loop)**: 建立具備長期記憶的守護進程，主動輪詢市場變化而非僅依賴 Cron。
- **全通路通知中樞 (Omni-Channel Notification Hub)**: 整合 Telegram/Slack/LINE，實現即時、雙向的「理財秘書」交互（如：推播警報並接收 "Yes/No" 執行指令）。
- **強化型向量記憶 (Enhanced Vector Memory)**: 透過 ChromaDB/PGVector 記住使用者的長期投資哲學與風險偏好漂移。
- **智能體技能標準化 (Standardized Skill Protocol)**: 全面落地 **Model Context Protocol (MCP)**，將所有工具模組化為獨立的 MCP Servers。

#### 2.3 Agent Swarm — Evolution Path

- **Milestone 1: Framework + Pilot**: `SwarmOrchestrator`, Fundamental Swarm, Sentiment Swarm.
- **Milestone 2: Full Rollout**: Momentum, Macro, Risk Swarms + Toggle integration.
- **Milestone 3: Command & Evolution**: CIO Swarm, Engineer Swarm, Critical Path optimizer, full stress test.

### 3. Technical Specs
- **Ray on K8s**: Distributed hyper-parameter searching.
- **Swarm Orchestrator**: `asyncio`-based dynamic agent spawning, fan-out/fan-in.
- **Retro-Logic**: Outcome-based agent weight calibration.
- **Fault Tolerance**: Graceful degradation on Sub-Agent failure.

### 4. Success Metrics
| Metric | Target |
| :--- | :--- |
| Alpha | > 5% vs S&P 500 |
| Latency | 4× reduction via parallel execution |
| Token Cost | 30% reduction via Toggle |
| Max Drawdown | < 10% |

## 🔗 Bidirectional Links
- **Core Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **Evolution Roadmap**: [Evolutionary Roadmap](產品演進藍圖-Evolutionary-Roadmap)

