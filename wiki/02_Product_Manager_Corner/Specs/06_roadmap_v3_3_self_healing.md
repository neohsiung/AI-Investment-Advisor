# Roadmap v3.3 Spec: Crisis Autopilot (Self-Healing System)

> **[⬅️ Back to Roadmap](../產品藍圖-Roadmap.md)**

**Status**: Planned (Jun 2026)
**Core Value**: Sleep-Well Investing
**Tech Stack**: FinRL, Ray, Kubernetes

---

## [Chinese] 產品規格與技術框架

### 1. 產品規格 (Product Specification)

#### 1.1 用戶痛點 (The User Problem)
市場狀況會改變 (例如：牛市 -> 滯脹)。去年有效的策略今年可能會失敗 (「策略衰退」)。投資者在崩盤時會恐慌並在底部賣出。

#### 1.2 解決方案：危機自動駕駛 (The Solution: "Crisis Autopilot")
一個能夠檢測市場體制變化並自動「修復」其策略的自主系統。它作為防禦盾牌，在用戶恐慌拋售 **之前** 啟動。

#### 1.3 關鍵功能 (Key Features)
*   **體制偵測器 (Regime Detector)**: 自動將市場分類為 4 個象限 (通膨/通縮，成長/衰退)。
*   **自動切換防禦 (Auto-Switching Defense)**:
    *   *正常模式*: 60/40 股/債。
    *   *危機模式*: 自動輪轉至黃金 (GLD)、短期公債 (SHV) 或反向 ETF。
*   **神經型態自癒 (Neuromorphic Self-Healing)**: 當策略回撤超過 5% 時，系統會在夜間自動「重新訓練」自己以適應新的波動率。

### 2. 技術框架：FinRL 與分散式訓練 (FinRL & Distributed Training)

#### 2.1 "健身房" 概念 (The "Gym" Concept)
我們不能用真錢測試新策略。我們需要一個「飛行模擬器」(Gym)。

*   **架構流程**:
    1.  **數據源 (Data Feed)**: v3.2 輸出的 **高信度結構化信號 (JSON Signals)** 與 **深度分析數據** 輸入 `FinRL` 環境。
    2.  **模擬 Gym (Simulation Gym)**: Agent 在虛擬股市中交易歷史數據。
    3.  **體制層 (Regime Layer)**: 非監督式學習模型 (HMM 或 K-Means) 將市場數據聚類為不同體制。

#### 2.2 分散式自癒 (Distributed Self-Healing with Ray on Kubernetes)
當觸發「自癒」時：
1.  **觸發 (Trigger)**: 投資組合回撤 > 5%。
2.  **啟動 (Spin-Up)**: Kubernetes 啟動 **Ray Cluster** (KubeRay)。
3.  **分散式訓練 (Distributed Training)**: `Ray Train` 生成 100 個工作 Agent。每個 Agent 嘗試策略的細微變異 (超參數調整)。
4.  **選擇 (Selection)**: 選擇在當前體制下 **夏普比率 (Sharpe Ratio)** 最高的 Agent。
5.  **熱抽換 (Hot-Swap)**: 實盤交易機器人將其模型權重更新為新的「已修復」版本。

#### 2.3 技術堆疊 (Tech Stack)
*   **FinRL**: 金融深度強化學習庫。
*   **Ray**: 用於擴展 AI 和 Python 應用程序的框架。
*   **KubeRay**:在庫伯與提斯 (Kubernetes) 上管理 Ray 集群的 Operator。
*   **Redis**: 用於實時信號的高性能狀態管理。

---

## [English] Product Spec & Technical Framework

### 1. Product Specification

#### 1.1 The User Problem
Market conditions change (e.g., Bull Market -> Stagflation). A strategy that worked last year will fail this year ("Strategy Decay"). Investors panic during crashes and sell at the bottom.

#### 1.2 The Solution: "Crisis Autopilot"
An autonomous system that detects market regime shifts and automatically "heals" its strategies. It acts as a defensive shield that activates *before* the user panic-sells.

#### 1.3 Key Features
*   **Regime Detector**: Automatically classifies the market into 4 quadrants (Inflation/Deflation, Growth/Recession).
*   **Auto-Switching Defense**:
    *   *Normal Mode*: 60/40 Stocks/Bonds.
    *   *Crisis Mode*: Automatically rotates to Gold (GLD), Short-Term Treasuries (SHV), or Inverse ETFs.
*   **Neuromorphic Self-Healing**: When a strategy's drawdown exceeds 5%, the system automatically "retrains" itself overnight to adapt to the new volatility.

### 2. Technical Framework: FinRL & Distributed Training

#### 2.1 The "Gym" Concept
We cannot test new strategies with real money. We need a "Flight Simulator" (Gym).

*   **Architecture Flow**:
    1.  **Data Feed**: Consumes **High-Fidelity Structured Signals (JSON)** and **Deep Analysis Data** from v3.2.
    2.  **Simulation Gym**: A virtual stock market where agents trade historical data.
    3.  **Regime Layer**: An unsupervised learning model (HMM or K-Means) clusters market data into regimes.

#### 2.2 Distributed Self-Healing (Ray on Kubernetes)
When "Self-Healing" is triggered:
1.  **Trigger**: Portfolio Drawdown > 5%.
2.  **Spin-Up**: Kubernetes launches a **Ray Cluster** (KubeRay).
3.  **Distributed Training**: `Ray Train` spawns 100 worker agents. Each agent tries a slight variation of the strategy (Hyperparameter Tuning).
4.  **Selection**: The agent with the best *Sharpe Ratio* in the current regime is selected.
5.  **Hot-Swap**: The live trading bot updates its model weights to the new "Healed" version.

#### 2.3 Tech Stack
*   **FinRL**: Deep Reinforcement Learning library for Finance.
*   **Ray**: Framework for scaling AI and Python applications.
*   **KubeRay**: Operator to manage Ray clusters on Kubernetes.
*   **Redis**: High-performance state management for live signals.
