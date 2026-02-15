# 產品演進藍圖 (Evolutionary Roadmap)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v3.6 | Transitioned to Agile Iterative Methodology (Milestone-based) | Neo |
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
- **成功指標**: 測試覆蓋率 > 75%；報告生成穩定性 99.9%。

#### 🚀 階段 B+ (2026 Q2): 哨兵與評議會 (v3.4/v3.5 - Sentinel & Council)
- **核心功能**: 實現 System 1 (快思) 與 System 2 (慢想) 的認知架構。
    - **主動監控 (Sentinel)**: [哨兵架構](../04_架構觀點-Architect_Views/哨兵與評議會架構-Sentinel-Council-Architecture.md) 實現 7x24 市場事件監聽。
    - **4D 多維觸發**: VIX 體制 / 持倉異動 / 加權新聞 / 宏觀指標。
    - **加權風險關鍵字 (Weighted Risk Keywords)**: DB 驅動的 30+ 種子關鍵字 (5 類別)，加權評分 + 命中追蹤 + 復盤機制。Settings UI 管理。
    - **Tavily 標準管線**: 每日工作流自動消費 Tavily 配額進行網路研究。
    - **深度評議 (Council)**: 針對每一檔持倉執行碎形辯論 (Fractal Debate)。
- **技術需求**: Asyncio Event Loop, Sentinel Service, RiskKeywordRepository, Tavily API.
- **成功指標**: 主動警報延遲 < 2分鐘；交互指令回應率 100%；測試覆蓋 405 passed。

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
*   **迭代: 確定性與通路強化 (v3.6-v3.7)**:
    - **重點**: 提升執行穩定性與通路解耦。
    - **進度**: [x] 槓桿引擎 (v3.6) 已上線；[ ] [研究與最佳實踐](05_工程手冊-Engineering_Handbook/研究與最佳實踐-Research-Best-Practices) Channel Adapter 模式研究中。
*   **迭代: 事件驅動與主動防禦 (v3.8)**:
    - **重點**: 實踐 Inbound Webhooks 與 Sentinel 4D 觸發器全面自動化。
*   **迭代: 併發基礎與 Swarm 框架 (v3.9)**:
    - **重點**: 建立編排基底 (`SwarmOrchestrator`)。
*   **迭代: 自動復盤與 Alpha 優化 (v3.9.5)**:
    - **重點**: 實作 `RetrospectiveAgent` 每日進行決策歸因 (P&L Attribution) 並修正 Agent 信心權重。
*   **迭代: 全面集群與自主演化 (v4.0)**:
    - **重點**: 多模態聯合優化、CIO Swarm 三層驗證機制、策略自主變異 (Alpha-Seeking)。

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

#### 📌 角色 × 群體 對照表 (Role × Multi-Agent Mapping)

| 現有角色 (Role) | Sub-Agents | 效益 |
| :--- | :--- | :--- |
| `CIOAgent` | `StrategyPlanner` · `AllocationOptimizer` · `DecisionValidator` | 三層驗證消除單點決策風險 |
| `FundamentalAgent` | `RevenueExtractor` · `RiskFactorScanner` · `ValuationModeler` | 財報分析時間 ÷ 3 |
| `MomentumAgent` | `TrendDetector` · `PatternRecognizer` · `VolumeAnalyst` | 覆蓋多維度技術面 |
| `MacroAgent` | `FedWatcher` · `YieldCurveAnalyst` · `GeoPoliticalScanner` | 併發監控宏觀信號 |
| `RiskAgent` | `PortfolioStressTester` · `CorrelationMonitor` · `TailRiskCalculator` | 併發壓力測試 |
| `SentimentAgent` | `NewsScanner` · `SocialPulse` | 即時情緒覆蓋率 ↑ |
| `SystemEngineerAgent` | `CodeGenerator` · `BacktestRunner` · `FactorMiner` | 自主策略因子進化 |

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
