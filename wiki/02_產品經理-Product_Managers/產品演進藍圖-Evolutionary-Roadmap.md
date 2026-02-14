# 產品演進藍圖 (Evolutionary Roadmap)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-14 | v4.0 | Added Phase B+ v3.5 delivery: 4D Sentinel + Weighted Risk Keywords | Neo |
| 2026-02-14 | v4.0 | Redesigned Phase C/D: Agent Swarm as Role × Multi-Agent, monthly milestones targeting Q4 | Neo |
| 2026-02-14 | v3.5 | Added Institutional-Grade Execution & Risk Roadmap | Neo |
| 2026-01-01 | v3.3 | Updated for Multi-Broker & Risk limits | Neo |

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 產品演進藍圖 (v4.0)

本藍圖定義了本系統從「基礎記帳工具」進化為「自主決策生命體」的發展路徑。

### 1. 總體願景與目標 (Vision & Goals)
- **願景**: 只要將資金存入，系統即會自主完成研究、對沖、交易與資產保護，無須人類干預。
- **目標**: 追求超越標普 500 的風險調整後收益 (Sharpe > 1.2)。
- **v4.0 核心理念**: **Role × Multi-Agent** — 每個角色保持其領域職責不變，背後由多個追求效率與正確性的 Sub-Agent 群體驅動。

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

> **核心理念: 角色即核心、群體即效率。** 每一個現有 Agent 角色 (CIO, Analyst, Risk…) 不改變其對外職責，但內部拆分為多個專注子智能體 (Sub-Agents) 並行工作，追求正確性與速度。

##### 🗓️ 2026 年 10 月 — 基底層: Swarm Framework & 首批 Pilot

| 交付項目 | 說明 |
| :--- | :--- |
| `SwarmOrchestrator` 基底類別 | 統一的 Sub-Agent 編排框架，支援 `asyncio.gather` 併發 + 超時 + 重試。 |
| `RoleSwarmBase` 抽象類別 | 各角色 Swarm 的共用基底：任務拆解 → 分發 → 匯聚 (Fan-out / Fan-in)。 |
| **Pilot 1: Fundamental Swarm** | `FundamentalAgent` → 3 Sub-Agents: `RevenueExtractor`, `RiskFactorScanner`, `ValuationModeler`。併發分析一份財報。 |
| **Pilot 2: Sentiment Swarm** | `SentimentAgent` → 2 Sub-Agents: `NewsScanner`, `SocialPulse`。併發蒐集新聞與社群情緒。 |

##### 🗓️ 2026 年 11 月 — 角色擴展: 全面 Swarm 化

| 交付項目 | 說明 |
| :--- | :--- |
| **Momentum Swarm** | `MomentumAgent` → `TrendDetector`, `PatternRecognizer`, `VolumeAnalyst`。 |
| **Macro Swarm** | `MacroAgent` → `FedWatcher`, `YieldCurveAnalyst`, `GeoPoliticalScanner`。 |
| **Risk Swarm** | `RiskAgent` → `PortfolioStressTester`, `CorrelationMonitor`, `TailRiskCalculator`。 |
| **Adaptive Compute (Toggle)** | 整合自適應算力：平靜市場使用 Flash Sub-Agent，劇烈波動時升級至 Think Sub-Agent。 |

##### 🗓️ 2026 年 12 月 — 頂層指揮: CIO Swarm & 全系統整合

| 交付項目 | 說明 |
| :--- | :--- |
| **CIO Swarm** | `CIOAgent` → `StrategyPlanner`, `AllocationOptimizer`, `DecisionValidator`。三層驗證最終決策。 |
| **Engineer Swarm** | `SystemEngineerAgent` → `CodeGenerator`, `BacktestRunner`, `FactorMiner`。自主演化策略基底。 |
| **關鍵路徑優化** | 監控最慢 Sub-Agent (Critical Path)，動態分配資源加速。 |
| **多模態聯合優化** | 視覺 (K線圖) + 文本 (財報) 的 Joint Optimization，為 Momentum Swarm 加入圖形理解力。 |
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

### 2. Milestones
- **Phase A (2025) - Foundation**: Deterministic engine & secure DB (Completed).
- **Phase B (2026 Q1) - Intelligence**: Hybrid Tiered Analysis, Multi-Broker support (Completed).
- **Phase B+ (2026 Q2) - Sentinel (v3.5)**: 4D Multi-Trigger (VIX/Position/News/Macro), Weighted Risk Keywords (30+ seeds, DB scoring, hit tracking), Tavily standard pipeline, Fractal Debate. 405 tests.
- **Phase B++ (2026 Q3) - Institutional (v3.5)**: Deep IBKR integration, SOR, OpenClaw concurrency, VaR.
- **Phase C (2026 Q4) - Agent Swarm Economy**: Role × Multi-Agent decomposition.

### 3. Phase C Monthly Breakdown (2026 Q4)

| Month | Theme | Deliverables |
| :--- | :--- | :--- |
| **Oct** | Swarm Framework + Pilot | `SwarmOrchestrator`, `RoleSwarmBase`, Fundamental Swarm (3 sub-agents), Sentiment Swarm (2 sub-agents) |
| **Nov** | Full Swarm Rollout | Momentum / Macro / Risk Swarms, Toggle Algorithm (Adaptive Compute) integration |
| **Dec** | Command Layer + Integration | CIO Swarm (3-layer verification), Engineer Swarm (self-evolution), Critical Path optimizer, Multimodal Vision, full system stress test |

### 4. Role × Multi-Agent Mapping

| Role | Sub-Agents | Benefit |
| :--- | :--- | :--- |
| CIO | StrategyPlanner · AllocationOptimizer · DecisionValidator | Eliminates single-point decision risk |
| Fundamental | RevenueExtractor · RiskFactorScanner · ValuationModeler | 3× faster earnings analysis |
| Momentum | TrendDetector · PatternRecognizer · VolumeAnalyst | Multi-dimensional technical coverage |
| Macro | FedWatcher · YieldCurveAnalyst · GeoPoliticalScanner | Concurrent macro signal monitoring |
| Risk | StressTester · CorrelationMonitor · TailRiskCalculator | Parallel stress testing |
| Sentiment | NewsScanner · SocialPulse | Real-time sentiment coverage ↑ |
| Engineer | CodeGenerator · BacktestRunner · FactorMiner | Autonomous factor evolution |

## 🔗 Bidirectional Links
- **Core Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **Future Specs**: [Future Roadmap Specs](未來演進規格-Future-Roadmap-Specs)
- **Automation Specs**: [OpenClaw Automation Specs](OpenClaw自動化規格-OpenClaw-Automation-Spec)
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
