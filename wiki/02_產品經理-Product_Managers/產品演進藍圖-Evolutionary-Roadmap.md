# 產品演進藍圖 (Evolutionary Roadmap)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 產品演進藍圖 (v3.1)

本藍圖定義了本系統從「基礎記帳工具」進化為「自主決策生命體」的發展路徑。

### 1. 總體願景與目標 (Vision & Goals)
- **願景**: 只要將資金存入，系統即會自主完成研究、對沖、交易與資產保護，無須人類干預。
- **目標**: 追求超越標普 500 的風險調整後收益 (Sharpe > 1.2)。

### 2. 演進里程碑 (Milestones)

#### 🚀 階段 A (2025): 基礎建設 - 確定性基礎 (已達成)
- **核心功能**: 
    - 實作 0 幻覺的確定性分析引擎。
    - 建立 [資料庫設計](資料庫設計與代碼規範-Database-Git-Standards) 與初步 ETL 流程。
- **成功指標**: 計算誤差率 = 0%；Google OAuth 登入成功率 100%。

#### 🚀 階段 B (2026 Q1-Q2): 智能分層 - 當前階段
- **核心功能**: 
    - **混合分析架構 (Hybrid Tiered)**: 將分析分為 API 篩選、JIT 深度研究等 3 個層級。
    - **自適應機制**: [核心系統規格](核心系統規格-Core-System-Specs) 中定義的智慧新鮮度與模型分級。
- **技術需求**: Tavily Search Service, Gemini 1.5 系列 API。
- **成功指標**: Token 消耗降低 40% 以上；P95 分析回應 < 30 秒。

#### 🚀 階段 C (2026 Q3): 危機自癒 - 規劃中
- **核心功能**: 核心細節見 [未來演進規格](未來演進規格-Future-Roadmap-Specs)。
    - **危機自動駕駛**: 體制切換 (Regime Switching) 偵測。
    - **FinRL 模擬**: 虛擬環境中的閉環策略優化。
- **技術需求**: 分散式 **KubeRay** 運算集群。
- **成功指標**: 最大回撤 (Max Drawdown) < 10%。

#### 🚀 階段 D (2027+): 演化智能 - 概念中
- **核心功能**: 自主代碼變異、個人家族辦公室模式。
- **成功指標**: 夏普比率 > 1.5。

---

<a id="en"></a>

## 🇺🇸 Evolutionary Roadmap

### 1. Vision
Transforming from a tool into an autonomous "Wealth Organism" that researches and trades with zero human intervention.

### 2. Milestones
- **Phase A (2025) - Foundation**: Deterministic engine & secure DB (Completed).
- **Phase B (2026 H1) - Intelligence**: [Core Specs](核心系統規格-Core-System-Specs) implementation. Hybrid Tiered Analysis and cost-saving adaptive logic (Current).
- **Phase C (2026 H2) - Anti-fragility**: [Future Roadmap](未來演進規格-Future-Roadmap-Specs). Crisis Autopilot and FinRL-based distributed learning via KubeRay.
- **Phase D (2027+) - Evolution**: Code-level self-mutation and Generative Alpha.

## 🔗 Bidirectional Links
- **Core Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **Future Specs**: [Future Roadmap Specs](未來演進規格-Future-Roadmap-Specs)
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
