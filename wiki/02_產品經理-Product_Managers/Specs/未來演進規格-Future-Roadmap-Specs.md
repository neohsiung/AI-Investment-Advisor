# 未來演進規格 (Future Roadmap Specifications)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 未來演進規格書 (v3.3 & v4.0)

本文件描述了系統「反脆弱」與「自我進化」階段的技術深度與業務目標。

### 1. 問題與目標 (Problem & Goals)
- **核心挑戰**: 傳統 AI 策略在市場進入「黑天鵝」體制時通常會失效（策略衰退）。
- **目標**: 構建一個能自動偵測市場體制 (Regime) 並自主變異其代碼基底的「金融生命體」。

### 2. 功能詳述 (Features & functionality)

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

#### 2.3 v4.0 智能體集群 (Agent Swarm Economy)
- **目標**: 突破單體智能的序列處理瓶頸，實現並行研究。
- **核心邏輯 (PARL - Parallel Agent RL)**:
    - **編排器 (Orchestrator)**: 將「分析 Apple 財報」拆解為「營收數據」、「供應鏈風險」、「AI 資本支出」三個子任務。
    - **並行執行**: 同時啟動 3 個 Sub-Agents 進行搜尋與分析。
    - **關鍵路徑優化**: 監控最慢的子任務（Critical Path），並動態分配更多資源加速之。
- **待辦事項 (To-Do)**:
    - [ ] 設計 `SwarmOrchestrator` 類別，支援 `asyncio.gather` 併發控制。
    - [ ] 實作「關鍵路徑」監控儀表板。

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
- **演化引擎**:
    - **MetaGPT 整合**: 用於自主代碼生成的代碼代理。
    - **遺傳演算法 (Genetic Algorithm)**: 用於邏輯片段的交叉 (Crossover) 與變異 (Mutation)。
- **數據湖 (Data Lake)**: 擴充至存儲非結構化社交媒體原始流以供情感演化。

### 4. 非功能性需求 (NFR)
- **可移植性**: 支援多雲 (AWS/GCP/Azure) 分散式混合部署。
- **安全性**: 針對自主生成的代碼執行沙盒 (Sandbox) 隔離運行。

### 5. 成功指標 (Success Metrics)
- **Alpha**: 相較於大盤 (S&P 500) 超額報酬 > 5%。
- **自我進化效率**: 每週自主生成的有效新因子數量 > 1。

---

<a id="en"></a>

## 🇺🇸 Future Roadmap Specifications (v3.3 & v4.0)

### 1. Problem & Goals
Mitigating "Strategy Decay" in black-swan events through self-healing and code-level evolution.

### 2. Features
- **v3.3 Crisis Autopilot & Toggle**: HMM-based regime detection AND dynamic compute budget allocation (Fast vs Think models).
- **v4.0 Agent Swarm**: PARL architecture for parallel task execution and Critical Path optimization.

### 3. Technical Specs
- **Ray on K8s**: Distributed hyper-parameter searching.
- **Swarm Orchestrator**: `asyncio`-based dynamic agent spawning.
- **Toggle Router**: Confidence-based model routing.

### 4. Success Metrics
- **Alpha**: > 5% vs S&P 500.
- **Latency**: Critical path latency reduced by 50% via parallel execution.
- **Cost Efficiency**: 30% reduction in token costs via Toggle Algorithm.

## 🔗 Bidirectional Links
- **Core Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **Evolution Roadmap**: [Evolutionary Roadmap](產品演進藍圖-Evolutionary-Roadmap)
