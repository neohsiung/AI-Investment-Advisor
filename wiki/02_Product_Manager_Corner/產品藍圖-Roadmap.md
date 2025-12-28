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

#### v3.2 辯證推理與適應性畫像 (Mar 2026)
*   **目標**: 透過對抗式集群與使用者建模提升決策品質。
*   **關鍵規格**:
    *   **對抗協議 (Adversarial Protocol)**: 多輪次的「辯論協議」，強制 `BullAgent` 與 `BearAgent` 交換論點。
    *   **加權共識機制 (Weighted Consensus)**: CIO Agent 使用 **貝葉斯模型平均 (Bayesian Model Averaging)** 或加權評分來聚合論點，而非單純摘要。
    *   **狀態式使用者畫像 (Stateful User Persona)**: 根據歷史互動日誌動態調整特定參數 (`risk_aversion`, `verbosity`)。

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

### 2026 Q1: Autonomous Evolution (Future)

#### v3.0 The Self-Correcting Loop (Jan 2026)
*   **Goal**: Transition to Algorithmic Prompt Optimization (APO).
*   **Key Specs**:
    *   **Prompt Optimization Pipeline (DSPy)**: Implement `DSPy.BootstrapFewShot` or similar teleprompters to auto-optimize system prompts using **Prediction Error** as the loss function.
    *   **Feedback Vector Store**: Store `(Prediction, Actual_Price_Action, Rationales)` tuples in `pgvector` to serve as dynamic few-shot examples.
    *   **Evaluation Framework**: Automated "Backtest-as-a-Service" running weekly to validate prompt effectiveness (Preventing **Catastrophic Forgetting**).

#### v3.1 Multi-Modal Perception (Feb 2026)
*   **Goal**: Direct ingestion of Visual Data (Charts) via VLMs.
*   **Key Specs**:
    *   **VLM Integration**: Integrate `Gemini-Pro-Vision` or `GPT-4o` to process raw OHLC Candle Charts images.
    *   **Chart Pattern Classifier**: Dedicated classification module for technical patterns (e.g., "Double Bottom", "Flag") returning **Confidence Scores**.
    *   **Visual Grounding**: Agents output coordinate bounding boxes to visually justify their analysis on the chart.

#### v3.2 Dialectical Reasoning & Adaptive Persona (Mar 2026)
*   **Goal**: Decision quality via Adversarial Swarm and User Modeling.
*   **Key Specs**:
    *   **Adversarial Protocol**: Multi-turn "Debate Protocol" where `BullAgent` and `BearAgent` exchange arguments.
    *   **Weighted Consensus Mechanism**: CIO Agent aggregates debate arguments using **Bayesian Model Averaging** or weighted scoring, rather than simple concatenation.
    *   **Stateful User Persona**: Dynamic adjustment of specific parameters (`risk_aversion`, `verbosity`) based on historical interaction logs.
