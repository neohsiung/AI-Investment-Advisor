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

#### 2.2 v4.0 演化智能 (Evolutionary Intelligence)
- **目標**: 零人類干預的自主財富辦公室。
- **核心邏輯**:
    - **Prompt DNA**: 提示詞不只是文本，而是可被遺傳演算法 (GA) 優化的基因。
    - **自主因子挖掘**: 系統會自主撰寫 Python 代碼，回測新因子並將高 alpha 因子合併進核心庫。
- **UX Story**: 使用者可以用自然語言對系統說：「幫我尋找對抗火星殖民通膨的投資因子」，系統隨即啟動演化搜索工作流。

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
- **v3.3 Crisis Autopilot**: HMM-based regime detection and automated hedging transition.
- **v4.0 Evolutionary Office**: Goal-oriented code generation (MetaGPT) and Agent DNA evolution.

### 3. Technical Specs
- **Ray on K8s**: Distributed hyper-parameter and因子 searching.
- **Genetic Algorithms**: Prompt & Code snippet breeding.

### 4. Success Metrics
- **Alpha**: > 5% vs S&P 500.
- **Evolution Rate**: > 1 valid new factor discovered per week.

## 🔗 Bidirectional Links
- **Core Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **Evolution Roadmap**: [Evolutionary Roadmap](產品演進藍圖-Evolutionary-Roadmap)
