# Product Roadmap

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 產品藍圖 (Product Roadmap)

### 目標 (Goal)
依據 Git 提交紀錄與實際交付的里程碑，紀錄 AI 投資顧問系統的真實發展路徑。

### 2025 Q4: 創始與雲端基礎 (已完成)

#### v1.0 初始發布 (2025/11/30)
*   **核心分析**: 實作 `Momentum Agent` (技術指標) 與 `Fundamental Agent` (價值投資)。
*   **資料層**: 建立基於 Strategy Pattern 的 `IngestorFactory`，支援客製化 CSV 匯入。
*   **分析引擎**: 開發 `LeverageCalculator` 與 `ROIEngine`，採用 **確定性數學** (TNV/NLV 邏輯)。
*   **介面**: 基礎 Streamlit 儀表板。

#### v1.1 雲端與安全性 (2025/12/06)
*   **基建**: Docker 化與 GCP Cloud Run 部署支援。
*   **Agent**: 新增 `System Engineer Agent` 與動態排程機制。
*   **安全**: 整合 Bandit 安全掃描與 License 合規檢查。
*   **文檔**: 發布部署指南與架構圖。

#### v1.2 SaaS 架構與在地化 (2025/12/07)
*   **安全**: 實作 **Google OAuth 2.0** 登入機制。
*   **架構**: Clean Architecture 重構 (Service/Agent/UI 分層)。
*   **體驗**: 介面全面中文化 (繁體中文支援)。
*   **文檔**: 文件系統大幅改版 (依角色分眾)。

### 2025 Dec: 自適應智能 (已完成)

#### v2.0 自適應系統 / Stage 5 (2025/12/13)
*   **效能**: **智慧新鮮度 (Smart Freshness)** (SHA256 Hash) 機制，降低 Token 成本。
*   **智能**: **模型分級 (Model Tiering)** 設定 (Smart vs Fast)。
*   **互動**: 新增 **Dispatcher Agent** (JSON 路由) 與「顧問聊天室」。
*   **演化**: **HR 協議 (HR Protocol)** 自動偵測並替換不活躍 Agent。
*   **維運**: Cloud SQL 自動化配置、升級 Python 3.11。

### 2026 Q1: 自主進化 (未來規劃)

#### 核心戰略：為何 AI 能帶來超額報酬？ (Why AI Beats Quant)
> 基於 OpenBB 與 Freqtrade 等開源專案的研究，我們推導出 AI 投資的核心優勢：
*   **資訊廣度 (Unstructured Data)**: 傳統量化僅能處理價格/財報數據 (Structured)，AI 能由新聞、社群、法說會錄音中提取 Alpha。**效率提升 100x** (30秒摘要 vs 10小時閱讀)。
*   **策略動態性 (Generative Policy)**: 傳統策略為靜態代碼 (Hard-coded)，AI 能根據市場體制 (Regime) 動態生成新策略代碼 (Generative Code)。
*   **持續進化 (Self-Adaptive)**: 借鑑 **FreqAI** 概念，系統具備「遺忘」與「再學習」能力，主動適應市場變遷。

#### v3.0 自我校正迴圈 (Jan 2026)
*   **目標**: 轉向演算法自動提示優化 (Algorithmic Prompt Optimization, APO)。
*   **關鍵規格**:
    *   **Prompt 優化管線 (DSPy)**: 實作 `DSPy.BootstrapFewShot` 或類似 Teleprompter，以 **預測誤差 (Prediction Error)** 為 Loss Function 自動優化 System Prompts。
    *   **回饋向量庫 (Feedback Vector Store)**: 使用 `pgvector` 儲存 `(預測, 實際走勢, 推理過程)` 當作動態 Few-Shot 範例。
    *   **評估框架 (Evaluation Framework)**: 自動化的 "Backtest-as-a-Service"，每週驗證優化效果 (防止 **災難性遺忘 Catastrophic Forgetting**)。

#### v3.1 多模態感知 (Feb 2026)
*   **目標**: 透過 VLM 直接攝取視覺數據 (圖表)。
*   **關鍵規格**:
    *   **VLM 整合**: 整合 `Gemini-Pro-Vision` 或 `GPT-4o` 直接處理 OHLC K 線圖影像。
    *   **圖型分類器 (Chart Classifier)**: 專用的技術型態分類模組 (如：雙底、旗型)，並返回 **信賴分數 (Confidence Scores)**。
    *   **視覺接地 (Visual Grounding)**: Agent 需輸出座標邊界框 (Bounding Boxes) 以視覺化解釋其分析焦點。

- **[NEW SECTION] 迭代式成長策略 (Iterative Growth Strategy)**
    - **核心理念 (Philosophy)**: 每一代版本都是下一代的**技術基石 (Technical Cornerstone)**。不跳級，確保可行性。
    - **階段一 (v3.2)**: **The Eyes (數據基石)**。建立 Visual RAG 以清洗數據。沒有乾淨數據，v3.3 的 RL 模型將無法運作 (Garbage In, Garbage Out)。
    - **階段二 (v3.3)**: **The Brain (決策引擎)**。在 v3.2 的數據基礎上，建立 RL 模擬環境 (Gym)。沒有模擬環境，v4.0 的 Agent 無法進行演化。
    - **階段三 (v4.0)**: **The DNA (自我演化)**。在 v3.3 的模擬環境中，導入遺傳演算法 (Genetic Algorithm)，實現策略的自我繁殖與優化。

#### v3.2 混合智能與深度價值 (Hybrid Intelligence & Deep Value) (Mar 2026 - In Progress)
> **[Spec 規格書: 05_roadmap_v3_2_visual_rag.md](Specs/05_roadmap_v3_2_visual_rag.md)**

*   **技術基石 (Dependency Focus)**: **Clean Data via Vision**.
    *   **財報誠實度掃描 (Chart-Truth Scanner)**: 利用 **ColPali** 提取結構化數據。這是 v3.3 訓練 RL 模型唯一的可靠數據來源，必須優先完成。
    *   **自主研究蜂群 (Autonomous Research Swarm)**: 建立多 Agent 協作框架。這是 v4.0 演化引擎的 "容器"，必須先穩定運作。

    *   **護城河分析 (Moat Analysis)**: 模仿大師邏輯，量化定性優勢，讓散戶擁有巴菲特等級的選股濾鏡。
*   **核心產品**:
    *   **深度研報生成 (Deep Research Generation)**: 自動產出長達 10 頁的機構級投資論文 (Investment Thesis)，包含風險評估、估值模型 (DCF/DDM) 與情境分析。

#### v3.3 宏觀對沖與動態配置 (Macro Hedging & Dynamic Allocation) (Jun 2026 - Planned)
> **[Spec 規格書: 06_roadmap_v3_3_self_healing.md](Specs/06_roadmap_v3_3_self_healing.md)**

*   **投資方法論 (Methodology)**: 專注於 **絕對報酬 (Absolute Returns)**，目標在空頭市場維持正收益。
    *   **總經體制變換 (Regime Switching)**: 整合 FRED 數據，自動判讀當前為「通膨/通縮」與「成長/衰退」四象限，動態調整股/債/原物料/現金比例。
    *   **神經型態自癒系統 (Neuromorphic Self-Healing)**: 當策略回撤超過閾值 (Drawdown > 5%)，系統自動啟動 **FinRL** 本地訓練場，生成 100 種變異策略並回測，熱抽換 (Hot-Swap) 失效的策略，實現「反脆弱」投資。
    *   **波動率目標 (Volatility Targeting)**: 當市場 VIX 指數飆升時，自動降低槓桿或總曝險 (De-leveraging) 以控制最大回撤 (Max Drawdown)。
*   **核心產品**:
    *   **危機盾牌 (Crisis Shield)**: 一鍵切換「防禦模式」，系統自動將高波動資產轉換為短債 (SHV) 或黃金 (GLD) ETF。
    *   **宏觀儀表板 (Macro Dashboard)**: 視覺化呈現當前經濟週期位置與建議配置。

#### v4.0 生成式佈局與超個人化 (Generative Allocation & Hyper-Personalization) (2026 Q4 - Concept)
> **[Spec 規格書: 07_roadmap_v4_0_evolution.md](Specs/07_roadmap_v4_0_evolution.md)**

*   **投資方法論 (Methodology)**: **生成式 Alpha (Generative Alpha)**，將自然語言轉化為量化策略。
    *   **語意因子建構**: 用戶輸入「投資具備高 ESG 分數且供應鏈不依賴單一國家的 EV 公司」，Agent 自動掃描供應鏈數據構建客製化 ETF。
    *   **演化式策略引擎 (Evolutionary Strategy Engine)**: 結合 **MetaGPT** 與 **遺傳演算法 (Genetic Algorithm)**，在模擬環境中讓 Agent 相互競爭、交配演化，自動誕生適應新市場的「基因 Alpha」。
    *   **AI 家族辦公室 (AI Family Office)**: 借鑑 **FinRobot** 的全方位理財架構，以軟體邊際成本提供跨資產類別 (股票、加密貨幣、房地產 REITs) 的整體財富規劃。
*   **核心產品**:
    *   **AI 家族辦公室 (AI Family Office)**: 跨資產類別 (股票、加密貨幣、房地產 REITs) 的整體財富規劃。
    *   **目標導向規劃 (Goal-based Investing)**: 針對「三年後買房」、「二十年後退休」等不同帳戶，提供動態下滑路徑 (Glide Path) 管理。

---

<a id="en"></a>

## 🇺🇸 Product Roadmap

### Goal
Define the factual development path of the AI Investment Advisor based on the project's git history and delivered milestones.

### 2025 Q4: Genesis & Cloud Foundation (Completed)

#### v1.0 Initial Launch (Nov 30, 2025)
*   **Core Analysis**: Implemented `Momentum Agent` (RSI/MACD) and `Fundamental Agent` (Value Investing).
*   **Data Layer**: Established `IngestorFactory` using Strategy Pattern to support customized CSV imports.
*   **Analytics Engine**: Developed `LeverageCalculator` and `ROIEngine` based on **Deterministic Math** (TNV/NLV logic).
*   **UI**: Basic Streamlit Dashboard.

#### v1.1 Cloud & Security (Dec 06, 2025)
*   **Infrastructure**: Dockerization and GCP Cloud Run deployment support.
*   **Agents**: Introduction of `System Engineer Agent` for self-optimization and Dynamic Scheduling.
*   **Security**: Integrated Bandit security scans and license compliance checks.
*   **Docs**: Released Deployment Guide and Architecture Diagrams.

#### v1.2 SaaS Architecture & Localization (Dec 07, 2025)
*   **Security**: Implemented **Google OAuth 2.0** for secure access.
*   **Architecture**: Refactored to "Clean Architecture" (Services/Agents/UI separation).
*   **Experience**: Full User Interface localization (English/Traditional Chinese).
*   **Docs**: Major documentation overhaul (User/PM/Dev/Arch separation).

### 2025 Dec: Adaptive Intelligence (Completed)

#### v2.0 Adaptive System / Stage 5 (Dec 13, 2025)
*   **Efficiency**: **Smart Freshness** (SHA256 Hash-based checks) to prevent redundant analysis.
*   **Intelligence**: **Model Tiering** (Smart vs Fast models) configuration for cost/performance balance.
*   **Interaction**: **Dispatcher Agent** (JSON routing) and "Advisor Chat" interface.
*   **Evolution**: **HR Protocol** to detect and replace inactive ("zombie") agents.
*   **Ops**: Cloud SQL automation, Python 3.11 upgrade, and CI/CD refinements.

### 2026 Q1: Autonomous Evolution (Future Vision)

#### Core Strategy: Why AI Beats Quant?
> Based on research into OpenBB and Freqtrade, we derived the core advantages of AI investing:
*   **Data Breadth (Unstructured Data)**: Traditional quants handle structured data (Price/Financials). AI extracts Alpha from news, social media, and earnings calls. **100x Efficiency** (30s summary vs 10hr reading).
*   **Strategy Dynamics (Generative Policy)**: Quants use static code. AI generates new strategy code dynamically based on market regimes.
*   **Continuous Evolution (Self-Adaptive)**: Leveraging **FreqAI** concepts, the system can "forget" and "relearn" to adapt to shifting markets.

> **Goal**: Build a self-learning investment bot targeting **Market Beat +10%** annually with minimal operational costs (Local Ops).

#### v3.0 Self-Correction Loop (Jan 2026 - Completed)
*   **Core Achievement**: Implemented **Refinement Engine** and **System Engineer Agent**.
*   **Key Features**:
    *   **Daily Self-Review**: System backtests past predictions and generates post-mortem reports.
    *   **Dynamic Parameter Tuning**: Engineer Agent adjusts Momentum/Sentiment Agent weights based on backtest results.
    *   **Automated Testing**: Established full PYTEST coverage (>75%) ensuring evolution doesn't break core logic.

#### v3.1 Multimodal Perception (Feb 2026 - Completed)
*   **Core Achievement**: Integrated unstructured data sources and visualization foundations.
*   **Key Features**:
    *   **Web Search Enhancement**: Integrated `duckduckgo-search` allowing Agents to actively query latest market news.
    *   **Multi-Factor Integration**: Combined Technical (Momentum), Fundamental (Value), and Sentiment for comprehensive decision making.
    *   **Localization**: Supported Docker/Local deployment, removing dependency on expensive all-in-one Cloud SaaS.

- **[NEW SECTION] Iterative Growth Strategy (The "Building Blocks")**
    - **Philosophy**: Each version is the **Technical Cornerstone** for the next. Ensure feasibility by not skipping steps.
    - **Phase 1 (v3.2)**: **The Eyes (Data Foundation)**. Build Visual RAG to clean data. Without this, v3.3's RL model fails (Garbage In, Garbage Out).
    - **Phase 2 (v3.3)**: **The Brain (Decision Engine)**. Build the RL Simulation (Gym) on top of v3.2's data. Without simulation, v4.0 cannot evolve.
    - **Phase 3 (v4.0)**: **The DNA (Evolution)**. Introduce Genetic Algorithms into v3.3's Gym to enable self-evolution.

#### v3.2 Hybrid Intelligence & Deep Value (Mar 2026 - In Progress)
> **[Deep Dive Spec: 05_roadmap_v3_2_visual_rag.md](Specs/05_roadmap_v3_2_visual_rag.md)**

*   **Dependency Focus**: **Clean Data via Vision**.
    *   **Chart-Truth Scanner**: Using **ColPali** to extract structured data. This "Ground Truth" is mandatory for training v3.3 models.
    *   **Autonomous Research Swarm**: Building the multi-agent framework that will serve as the "container" for v4.0 evolution.
    *   **Moat Analysis**: Quantifying qualitative advantages to give retail users a Buffet-like filter.
*   **Core Products**:
    *   **Deep Research Generation**: Automates the creation of 10-page institutional-grade Investment Theses, including risk assessment, valuation models (DCF/DDM), and scenario analysis.

#### v3.3 Macro Hedging & Dynamic Allocation (Jun 2026 - Planned)
> **[Deep Dive Spec: 06_roadmap_v3_3_self_healing.md](Specs/06_roadmap_v3_3_self_healing.md)**

*   **Methodology**: Focus on **Absolute Returns**, aiming for positive yields even in bear markets.
    *   **Regime Switching**: Integrates FRED data to automatically classify potential "Inflation/Deflation" and "Growth/Recession" quadrants, dynamically adjusting Equity/Bond/Commodity/Cash ratios.
    *   **Neuromorphic Self-Healing**: When strategy Drawdown > 5%, automatically spins up **FinRL** gym, generates/backtests 100 mutant strategies, and hot-swaps the failing one. "Antifragile" system.
    *   **Volatility Targeting**: Automatically deleverages or reduces exposure when Market VIX spikes to control Max Drawdown.
*   **Core Products**:
    *   **Crisis Shield**: One-click "Defense Mode" that automatically rotates volatile assets into Short-term Treasuries (SHV) or Gold (GLD) ETFs.
    *   **Macro Dashboard**: Visualizes current economic cycle position and recommended allocation.

#### v4.0 Generative Allocation & Hyper-Personalization (2026 Q4 - Concept)
> **[Deep Dive Spec: 07_roadmap_v4_0_evolution.md](Specs/07_roadmap_v4_0_evolution.md)**

*   **Methodology**: **Generative Alpha**, converting natural language into quantitative strategies.
    *   **Semantic Factor Construction**: User inputs "Invest in EV companies with high ESG scores and independent supply chains", Agent scans data to build a custom ETF.
    *   **Evolutionary Strategy Engine**: Combining **MetaGPT** with **Genetic Algorithms**, agents compete in simulation to breed superior "Genetic Alpha" strategies without human intervention.
    *   **AI Family Office**: Implementing **FinRobot**'s comprehensive wealth framework for cross-asset planning at low software marginal cost.
*   **Core Products**:
    *   **AI Family Office**: Holistic wealth planning across asset classes (Stocks, Crypto, REITs).
    *   **Goal-based Investing**: Dynamic Glide Path management for specific accounts like "House Fund (3 years)" or "Retirement (20 years)".
