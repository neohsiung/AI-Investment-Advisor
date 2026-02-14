# 未來演進規格 (Future Roadmap Specifications)

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

##### 2.3.2 各角色分群推進計劃 (Monthly Rollout)

**🗓️ 2026 年 10 月 — 基底層 + Pilot**

| 角色 | Sub-Agents | 職責說明 |
| :--- | :--- | :--- |
| **Fundamental Swarm** | `RevenueExtractor` | 專注營收、毛利率數據擷取。 |
|  | `RiskFactorScanner` | 掃描風險因子 (負債比、訴訟、供應鏈)。 |
|  | `ValuationModeler` | DCF / PE 相對估值建模。 |
| **Sentiment Swarm** | `NewsScanner` | 即時新聞 API (Tavily) 情緒評分。 |
|  | `SocialPulse` | 社群平台 (Reddit/X) 情緒脈搏。 |

- 基礎工程: `SwarmOrchestrator`, `RoleSwarmBase`, 超時/重試機制, 單元測試基底。

**🗓️ 2026 年 11 月 — 全面 Swarm 化**

| 角色 | Sub-Agents | 職責說明 |
| :--- | :--- | :--- |
| **Momentum Swarm** | `TrendDetector` | 均線交叉、趨勢強度判定。 |
|  | `PatternRecognizer` | 經典型態偵測 (頭肩頂/雙底)。 |
|  | `VolumeAnalyst` | 量能分析與異常偵測。 |
| **Macro Swarm** | `FedWatcher` | 聯準會聲明解讀、利率路徑推估。 |
|  | `YieldCurveAnalyst` | 殖利率曲線形態分析 (正常/倒掛)。 |
|  | `GeoPoliticalScanner` | 地緣政治事件影響評估。 |
| **Risk Swarm** | `PortfolioStressTester` | 歷史情境壓力測試 (2008/2020)。 |
|  | `CorrelationMonitor` | 資產相關性動態監控。 |
|  | `TailRiskCalculator` | 尾部風險 (CVaR) 計算。 |

- 整合 Toggle Algorithm: 各 Sub-Agent 可獨立使用 Fast/Think 路徑。

**🗓️ 2026 年 12 月 — 頂層指揮 + 全系統整合**

| 角色 | Sub-Agents | 職責說明 |
| :--- | :--- | :--- |
| **CIO Swarm** | `StrategyPlanner` | 生成投資主題與策略假設。 |
|  | `AllocationOptimizer` | 基於各角色 Swarm 輸出的最優化資產配置。 |
|  | `DecisionValidator` | 三層驗證 (反駁 → 壓力測試 → 合規檢查)。 |
| **Engineer Swarm** | `CodeGenerator` | 基於 MetaGPT 的自主策略代碼生成。 |
|  | `BacktestRunner` | 並行回測新因子的歷史表現。 |
|  | `FactorMiner` | 遺傳演算法驅動的因子發掘與變異。 |

- **Critical Path 優化**: 監控最慢 Sub-Agent，動態分配更多資源。
- **多模態聯合優化**: K線圖 (視覺) + 財報文本的 Joint Optimization。
- **全系統壓測**: 端對端 50+ 股票併發、Swarm 容錯回退驗證。

#### 2.4 多模態聯合優化 (Multimodal Joint Optimization)
- **目標**: 讓 AI 能像交易員一樣「看」懂 K 線圖。
- **核心邏輯**:
    - **Zero-Vision SFT**: 訓練模型寫出「能繪製該圖表」的 Python 代碼，藉此理解圖形結構。
    - **視覺強化學習**: 對齊視覺特徵與文本描述（如：「此處為頭肩頂結構」）。
- **待辦事項 (To-Do)**:
    - [ ] 收集 1000 張標註好的技術型態圖表作為預訓練數據。

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

### 6. 待辦事項總覽 (Master To-Do)

- [ ] **10月** 實作 `SwarmOrchestrator` + `RoleSwarmBase`
- [ ] **10月** 實作 Fundamental Swarm (`RevenueExtractor` / `RiskFactorScanner` / `ValuationModeler`)
- [ ] **10月** 實作 Sentiment Swarm (`NewsScanner` / `SocialPulse`)
- [ ] **11月** 實作 Momentum Swarm (`TrendDetector` / `PatternRecognizer` / `VolumeAnalyst`)
- [ ] **11月** 實作 Macro Swarm (`FedWatcher` / `YieldCurveAnalyst` / `GeoPoliticalScanner`)
- [ ] **11月** 實作 Risk Swarm (`PortfolioStressTester` / `CorrelationMonitor` / `TailRiskCalculator`)
- [ ] **11月** 整合 Toggle Algorithm (Adaptive Compute) 至 Swarm 層
- [ ] **12月** 實作 CIO Swarm (`StrategyPlanner` / `AllocationOptimizer` / `DecisionValidator`)
- [ ] **12月** 實作 Engineer Swarm (`CodeGenerator` / `BacktestRunner` / `FactorMiner`)
- [ ] **12月** 實作 Critical Path 監控與動態資源分配
- [ ] **12月** 全系統端對端壓力測試 (50+ 併發)

---

<a id="en"></a>

## 🇺🇸 Future Roadmap Specifications (v4.0 — Agent Swarm Economy)

### 1. Problem & Goals
Single-agent serial processing creates latency bottlenecks and single-point decision risk. **Role × Multi-Agent** decomposes each role into parallel Sub-Agents for efficiency and correctness.

### 2. Features

#### 2.1 Crisis Autopilot & Toggle
- HMM-based regime detection with automatic defensive rebalancing.
- Toggle Algorithm: Fast/Think dynamic compute budget allocation.

#### 2.2 Agent Swarm — Monthly Rollout

| Month | Scope | Deliverables |
| :--- | :--- | :--- |
| **Oct 2026** | Framework + Pilot | `SwarmOrchestrator`, `RoleSwarmBase`, Fundamental Swarm (3), Sentiment Swarm (2) |
| **Nov 2026** | Full Rollout | Momentum (3), Macro (3), Risk (3) Swarms + Toggle integration |
| **Dec 2026** | Command Layer | CIO Swarm (3-stage verification), Engineer Swarm (auto-evolution), Critical Path optimizer, Multimodal, full stress test |

### 3. Technical Specs
- **Ray on K8s**: Distributed hyper-parameter searching.
- **Swarm Orchestrator**: `asyncio`-based dynamic agent spawning, fan-out/fan-in.
- **Toggle Router**: Confidence-based model routing per Sub-Agent.
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

