# 產品演進藍圖 (Evolutionary Roadmap)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v3.6.1 | **Milestone Update**: Test覆蓋 75%✅, Channel Adapters完成, 當前階段明確標記 | Neo |
| 2026-02-15 | v3.6 | Leverage Engine & Transitioned to Agile Iterative Methodology | Neo |
| 2026-02-14 | v3.5 | Added Institutional-Grade Execution & 4D Sentinel delivery | Neo |
| 2026-01-01 | v3.3 | Multi-Broker & Risk limits | Neo |

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 產品演進藍圖 (v4.0)

本藍圖定義了本系統從「基礎記帳工具」進化為「自主決策生命體」的發展路徑。

### 1. 總體願景與目標 (Vision & Goals)
- **願景**: 只要將資金存入，系統即會自主完成研究、對沖、交易與資產保護，無須人類干預。
- **目標**: 追求超越標普 500 的風險調整後收益 (Alpha > 0, Sharpe > 1.2)。
- **v4.0 核心理念**: **Role × Multi-Agent** — 每個角色保持其領域職責不變，背後由多個追求效率與正確性的 Sub-Agent 群體驅動。
- **演化驅動**: **自動共同復盤 (Auto-Retrospective)** — 系統不僅執行決策，更會自主審核決策成效並修正策略權重。

### 2. 演進里程碑 (Milestones)

#### 🚀 階段 A (2025): 基礎建設 - 確定性基礎 (已達成)
- **核心功能**: 
    - 實作 0 幻覺的確定性分析引擎。
    - 建立 [資料庫設計](資料庫設計與代碼規範-Database-Git-Standards) 與初步 ETL 流程。
- **成功指標**: 計算誤差率 = 0%；Google OAuth 登入成功率 100%。

#### 🚀 階段 B (2026 Q1): 智能分層 (已達成 - v3.3)
- **核心功能**: 
    - **混合分析架構 (Hybrid Tiered)**: 實作 "Deep Research" 報告模式 (表格與精準引用)。
    - **任務規劃引擎**: [Task Planning Engine](../04_架構觀點-Architect_Views/任務規劃與執行引擎-Task-Planning-Engine.md) 實作多模型動態路由。
    - **多券商架構**: 整合 Etoro, Futu, IBKR。
- **技術需求**: Tavily Search, Gemini 1.5 Pro, MCP Integration (Foundation).
- **成功指標**: 
  - [x] 測試覆蓋率 **75%** ✅ (2026-02-15 達成)
  - [x] 報告生成穩定性 99.9% ✅

#### 🚀 階段 B+ (2026 Q2): 哨兵與評議會 (v3.4/v3.5 - Sentinel & Council)
- **核心功能**: 實現 System 1 (快思) 與 System 2 (慢想) 的認知架構。
    - **主動監控 (Sentinel)**: [哨兵架構](../04_架構觀點-Architect_Views/哨兵與評議會架構-Sentinel-Council-Architecture.md) 實現 7x24 市場事件監聽。
    - **4D 多維觸發**: VIX 體制 / 持倉異動 / 加權新聞 / 宏觀指標。
    - **加權風險關鍵字 (Weighted Risk Keywords)**: DB 驅動的 30+ 種子關鍵字 (5 類別)，加權評分 + 命中追蹤 + 復盤機制。Settings UI 管理。
    - **Tavily 標準管線**: 每日工作流自動消費 Tavily 配額進行網路研究。
    - **深度評議 (Council)**: 針對每一檔持倉執行碎形辯論 (Fractal Debate)。
- **技術需求**: Asyncio Event Loop, Sentinel Service, RiskKeywordRepository, Tavily API.
- **成功指標**: 
  - [x] 主動警報延遲 < 2分鐘 ✅
  - [x] 交互指令回應率 100% ✅
  - [x] 測試覆蓋 481+ passed ✅

#### 🚀 階段 B++ (2026 Q3): 機構級執行與 OpenClaw (v3.5 - Institutional Execution)
- **核心功能**: 深度整合 IBKR 與智能執行。
    - **由 IBKR 驅動的資產擴展**: 支援期貨與選擇權 (Futures & Options)。
    - **智能訂單路由 (SOR)**: 自動選擇最佳執行券商 (Fee-aware Router)。
    - **全持倉分析 (OpenClaw)**: Map-Reduce 架構突破 5 檔限制，支援併發分析。
    - **高級風控**: Value-at-Risk (VaR) 與壓力測試。
- **技術需求**: ib_insync, SQLite-Vec, LaneManager.
- **成功指標**: 滑價 (Slippage) < 0.1%；併發分析 50+ 檔股票。

#### 🚀 階段 C (2026 Q4): 智能體集群經濟 — Role × Multi-Agent (Agent Swarm Economy)

##### 演進迭代路徑 (Iterative Evolution Path)

**📍 當前階段: v3.6 (2026-02 完成) ✅**

*   **迭代: 確定性與通路強化 (v3.6) ✅ COMPLETED**:
    - **成就**: 
      - [x] **槓桿引擎 (Leverage Engine)**: 精確計算淨權益 (Net Equity) 與貸款 (Loan)
      - [x] **測試覆蓋率**: 從 74% → **75%** (513+ tests, -68 missed statements)
      - [x] **Channel Adapters**: 實現 `EmailAdapter`, `LineAdapter`, `WebAdapter` 解耦通道邏輯
      - [x] **Risk Keywords**: DB-driven weighted keyword system with UI management
    - **文檔**: `src/services/analytics_service.py` (Leverage calculations)
    - **架構**: Adapter pattern in `src/infrastructure/channels/`

**📍 下一階段: v3.7-v3.8 (規劃中)**

*   **迭代: 通路完善與適應性計算 (v3.7) - NEXT**:
    - **重點**: 完善 Channel Adapter pattern 並實現 **Role × Multi-Tier Agents** 架構
    - **計劃任務**:
      - [ ] **Multi-Tier Agent 架構 (Role × 3-Tier Parallel)**:
        - **核心理念**: 每個 Agent Role 背後有 3 個等級的 Sub-Agents **並行執行**
        - **三層級定義**:
          - 🚀 **Advanced (戰略)**: 核心模型 (Claude Opus, Gemini Pro) - 深度分析、關鍵決策
          - 🧠 **Smart (智囊)**: 分析模型 (GPT-4, Gemini Pro) - 平衡速度與質量
          - ⚡ **Fast (前鋒)**: 速度模型 (Gemini Flash, GPT-3.5) - 快速初篩、低成本探索
        - **並行機制**: 同一任務由 3 tier agents 同時執行，透過 voting/fusion 機制整合結果
        - **範例**: `FundamentalAgent` 分析財報時：
          - Advanced tier → 深度估值建模
          - Smart tier → 財務比率分析
          - Fast tier → 快速風險掃描
          - 三者並行完成後，由 `RoleSwarmBase` 匯聚結果
      - [ ] **Tier Selection Logic**:
        - 不同事項/階段動態分配 tier 權重
        - 高風險決策 → Advanced tier 權重 ↑
        - 探索性研究 → Fast tier 權重 ↑
        - 日常監控 → Smart tier 主導
      - [ ] **Channel Abstraction完善**: 
        - [ ] 統一 `IChannelAdapter` 介面定義
        - [ ] 實現 Webhook 通道 adapter
        - [ ] 添加 Discord/Telegram 支援（可選）
      - [ ] **配置驅動**: 所有 adapter 從 DB settings 動態載入
    - **技術需求**: Multi-tier orchestration, Voting/Fusion algorithms, Cost-aware routing
    - **預估時間**: 3-4 weeks
    - **成功指標**: 
      - Token 消耗降低 20-30% (Fast tier 承擔初篩工作)
      - 決策質量提升 (3-tier voting validation)
      - 平均響應速度提升 30% (Fast tier 先行返回)

*   **迭代: 事件驅動與主動防禦 (v3.8)**:
    - **重點**: 實踐 Inbound Webhooks 與 Sentinel 4D 觸發器全面自動化
    - **計劃任務**:
      - [ ] **Webhook Event Loop**: 
        - [ ] FastAPI webhook endpoints (TradingView, Broker alerts)
        - [ ] Event validation & authentication
        - [ ] Async event dispatch to Sentinel
      - [ ] **Sentinel 全自動化**:
        - [ ] 4D trigger 完全獨立運行（無需手動觸發）
        - [ ] Auto-escalation: 高嚴重性事件自動觸發 Council review
        - [ ] Event history logging & analytics
      - [ ] **主動防禦機制**:
        - [ ] Auto-hedging on portfolio stress
        - [ ] Emergency liquidation protocol
    - **技術需求**: FastAPI, asyncio, webhook signatures
    - **預估時間**: 3-4 weeks
    - **成功指標**:
      - Webhook → Action latency < 30s
      - Zero manual trigger for daily monitoring
      - 100% event traceability

**📍 未來階段: v3.9+ (Swarm 基礎)**

*   **迭代: 併發基礎與 Swarm 框架 (v3.9)**:
    - **重點**: 建立編排基底 (`SwarmOrchestrator`) + 整合 Multi-Tier Agent 架構
    - **核心組件**:
      - [ ] **SwarmOrchestrator 基底** (支援 Multi-Tier):
        ```python
        class SwarmOrchestrator:
            async def dispatch(self, task, sub_agents, tier_weights) -> List[Result]
            async def aggregate(self, results, fusion_strategy) -> FinalResult
            async def parallel_execute(self, agents_by_tier) -> TieredResults
            def handle_timeout(self, agent_id) -> RetryStrategy
        ```
      - [ ] **RoleSwarmBase 抽象類別** (整合 3-Tier):
        - Fan-out: 任務分解到 Sub-Agents **× 3 Tiers** 並行
        - Tier-aware execution: Advanced/Smart/Fast 同時執行
        - Fan-in: 匯聚 Multi-tier 結果 (Voting/Weighted fusion)
        - Error handling: 單一 Sub-Agent 失敗不阻斷整體
      - [ ] **Pilot 1: Fundamental Swarm (3-Tier)**:
        - `FundamentalAgent` → 3 Sub-Agents × 3 Tiers = **9 parallel executions**:
          - `RevenueExtractor` × [Advanced 🚀, Smart 🧠, Fast ⚡]
          - `RiskFactorScanner` × [Advanced 🚀, Smart 🧠, Fast ⚡]
          - `ValuationModeler` × [Advanced 🚀, Smart 🧠, Fast ⚡]
        - **範例流程**:
          1. 任務輸入: 分析 AAPL 財報
          2. Fan-out: 9 個 agents 並行啟動
          3. Fast tier 先完成 (30s) → 初步結論
          4. Smart tier 完成 (60s) → 詳細分析
          5. Advanced tier 完成 (120s) → 深度洞察
          6. Fusion: 整合 3-tier 結果，加權產出最終報告
      - [ ] **Pilot 2: Sentiment Swarm (3-Tier)**:
        - `SentimentAgent` → 2 Sub-Agents × 3 Tiers = **6 parallel executions**
        - Fast tier 快速揃描新聞標題 + Advanced tier 深度情感分析
    - **技術需求**: `asyncio.gather`, timeout handling, task queues, voting algorithms
    - **預估時間**: 5-7 weeks (含 3-tier 整合)
    - **成功指標**:
      - 財報分析時間降低 60% (Fast tier 先行輸出)
      - 決策準確度提升 15% (Multi-tier validation)
      - Sub-Agent 失敗率 < 5%
      - 所有 Pilot 通過 E2E 測試

*   **迭代: 自動復盤與 Alpha 優化 (v3.9.5)**:
    - **重點**: 實作 `RetrospectiveAgent` 每日進行決策歸因 (P&L Attribution)
    - **詳細規劃**:
      - [ ] **Attribution Engine**:
        - 每筆交易追蹤: Agent建議權重 → 實際執行 → P&L結果
        - 計算每個 Agent 的貢獻度 (Contribution Attribution)
      - [ ] **Weight Calibration**:
        - 自動調整 Agent 信心權重基於歷史表現
        - 低表現 Agent 降權，高表現 Agent 加權
      - [ ] **Reality Check Protocol**:
        - 定期將預測 vs 實際對帳
        - 生成 drift report (模型預測偏離實際)
    - **技術需求**: SQLite analytics queries, weight adjustment algo
    - **預估時間**: 3-4 weeks
    - **成功指標**:
      - 每日自動生成 attribution report
      - Agent weights 動態調整驗證
      - Sharpe ratio 提升 10%+

*   **迭代: 全面集群與自主演化 (v4.0)**:
    - **重點**: 多模態聯合優化、CIO Swarm 三層驗證機制、策略自主變異
    - **核心功能**:
      - [ ] **Full Agent Swarm Expansion**: Momentum, Macro, Risk Swarms
      - [ ] **CIO Swarm**: Three-layer decisio validation
      - [ ] **Engineer Swarm**: Auto code generation & backtesting
      - [ ] **Multimodal Analysis**: Vision + Text joint optimization
      - [ ] **Alpha-Seeking**: Genetic algorithm for strategy mutation
    - **技術需求**: KubeRay, FinRL, Vision models
    - **預估時間**: 8-12 weeks
    - **成功指標**: 完整 v4.0 里程碑達成

##### � 迭代里程碑 (Milestone: Swarm Foundation & Pilot)

| 交付項目 | 說明 |
| :--- | :--- |
| `SwarmOrchestrator` 基底類別 | 統一的 Sub-Agent 編排框架，支援 `asyncio.gather` 併發 + 超時 + 重試。 |
| `RoleSwarmBase` 抽象類別 | 各角色 Swarm 的共用基底：任務拆解 → 分發 → 匯聚 (Fan-out / Fan-in)。 |
| **Pilot 1: Fundamental Swarm** | `FundamentalAgent` → 3 Sub-Agents: `RevenueExtractor`, `RiskFactorScanner`, `ValuationModeler`。併發分析一份財報。 |
| **Pilot 2: Sentiment Swarm** | `SentimentAgent` → 2 Sub-Agents: `NewsScanner`, `SocialPulse`。併發蒐集新聞與社群情緒。 |

##### � 迭代里程碑 (Milestone: Full Swarm Expansion)

| 交付項目 | 說明 |
| :--- | :--- |
| **Momentum Swarm** | `MomentumAgent` → `TrendDetector`, `PatternRecognizer`, `VolumeAnalyst`。 |
| **Macro Swarm** | `MacroAgent` → `FedWatcher`, `YieldCurveAnalyst`, `GeoPoliticalScanner`。 |
| **Risk Swarm** | `RiskAgent` → `PortfolioStressTester`, `CorrelationMonitor`, `TailRiskCalculator`。 |
| **Adaptive Compute (Toggle)** | 整合自適應算力：平靜市場使用 Flash Sub-Agent，劇烈波動時升級至 Think Sub-Agent。 |

##### � 迭代里程碑 (Milestone: Command Layer & Integration)

| 交付項目 | 說明 |
| :--- | :--- |
| **CIO Swarm** | `CIOAgent` → `StrategyPlanner`, `AllocationOptimizer`, `DecisionValidator`。三層驗證最終決策。 |
| **Engineer Swarm** | `SystemEngineerAgent` → `CodeGenerator`, `BacktestRunner`, `FactorMiner`。自主演化策略基底。 |
| **關鍵路徑優化** | 監控最慢 Sub-Agent (Critical Path)，動態分配資源加速。 |
| **Auto-Retrospective** | `RetrospectiveAgent` → `AttributionAnalyzer`, `RealityChecker`。將決策與現實 P&L 對帳。 |
| **多模態聯合優化** | 視覺 (K線圖) + 文本 (財報) 的 Joint Optimization。 |
| **全系統壓測 & 上線** | 端對端整合測試：50+ 檔股票併發分析、Swarm 容錯回退驗證。 |

- **技術需求**: 分散式 **KubeRay** 運算集群、`asyncio` 併發控制、FinRL 模擬環境。
- **成功指標**:
    - 夏普比率 > 1.5
    - 研究任務端對端延遲降低 400%
    - Token 消耗降低 30% (Toggle)
    - 最大回撤 < 10%

#### 📌 角色 × 多層級群體 對照表 (Role × Multi-Tier Agent Mapping)

**架構**: 每個 Role → N Sub-Agents × 3 Tiers (Advanced 🚀 / Smart 🧠 / Fast ⚡)

| 現有角色 (Role) | Sub-Agents (每個×3 Tiers) | 並行數 | 效益 |
| :--- | :--- | :---: | :--- |
| `CIOAgent` | `StrategyPlanner` · `AllocationOptimizer` · `DecisionValidator` | 9 | 三層驗證 + 多速度決策 |
| `FundamentalAgent` | `RevenueExtractor` · `RiskFactorScanner` · `ValuationModeler` | 9 | 財報分析時間 ÷ 3，Fast tier 先行輸出 |
| `MomentumAgent` | `TrendDetector` · `PatternRecognizer` · `VolumeAnalyst` | 9 | 多維度技術面 × 3 層深度 |
| `MacroAgent` | `FedWatcher` · `YieldCurveAnalyst` · `GeoPoliticalScanner` | 9 | 併發監控 × 快速預警 (Fast tier) |
| `RiskAgent` | `PortfolioStressTester` · `CorrelationMonitor` · `TailRiskCalculator` | 9 | 並行壓力測試 × 分層風險評估 |
| `SentimentAgent` | `NewsScanner` · `SocialPulse` | 6 | 即時情緒 (Fast) + 深度分析 (Advanced) |
| `SystemEngineerAgent` | `CodeGenerator` · `BacktestRunner` · `FactorMiner` | 9 | 快速迭代 (Fast) + 深度驗證 (Advanced) |

**Tier 職責分工**:
- 🚀 **Advanced**: 關鍵決策、深度分析、複雜建模 (高成本高質量)
- 🧠 **Smart**: 日常分析、平衡質量與速度 (中等成本)
- ⚡ **Fast**: 初篩、快速揃描、低風險探索 (低成本高速度)

**Fusion 機制**:
- **Voting**: 三層級投票決定最終方向
- **Weighted**: 根據任務複雜度調整 tier 權重
- **Progressive**: Fast tier 先輸出初步結論，Advanced tier 補充深度洞察

---

<a id="en"></a>

## 🇺🇸 Evolutionary Roadmap (v4.0)

### 1. Vision
Transforming from a tool into an autonomous "Wealth Organism" that researches and trades with zero human intervention.

**v4.0 Core Principle — Role × Multi-Agent**: Each existing Agent role retains its domain responsibility. Behind it, a swarm of specialized Sub-Agents works in parallel, maximizing efficiency and correctness.

### 2. Evolutionary Milestones

#### Phase A-B: Foundation (Completed)
- Deterministic analysis, Multi-broker integration, basic Plan-Execute logic.

#### Phase B+: Cognitive Layer (Completed - v3.5)
- **Sentinel & Council**: System 1 (Fast) & System 2 (Slow) architecture.
- **Weighted Keywords**: Active threat detection via DB-driven scoring.

#### Phase B++: Execution & Abstraction (Active Iteration - v3.6/v3.7)
- [x] **Leverage Engine (v3.6)**: Precise NLV calculation and position auditing.
- [ ] **Channel Adapters (v3.7)**: Decoupling core logic from LINE/Web via Adapter pattern.
- [ ] **Adaptive Compute**: Tiered model routing based on confidence.

#### Phase C: Swarm & Retrospective (Future Iteration - v3.8+)
- Transition from Serial to **Parallel Swarm Execution**.
- **Milestones**: `SwarmOrchestrator`, **Auto-Retrospective Protocol** (Decision vs. Reality), weight calibration.

#### Phase D: Alpha-Seeking Organism (v4.0 Target)
- **Engineer Swarm**: Self-improving strategies via genetic algorithms.
- **Alpha Mastery**: Consistent outperformance vs Benchmarks (SPY).
- **Multimodal**: Native K-line visual analysis.

## 🔗 Bidirectional Links
- **Core Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **Future Specs**: [Future Roadmap Specs](未來演進規格-Future-Roadmap-Specs)
- **Automation Specs**: [Future Roadmap Specs](01_規格書-Specs/未來演進規格-Future-Roadmap-Specs)
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
