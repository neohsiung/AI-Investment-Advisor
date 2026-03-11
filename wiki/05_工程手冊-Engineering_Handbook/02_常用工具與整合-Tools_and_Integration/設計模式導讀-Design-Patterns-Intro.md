# 設計模式導讀 (Design Patterns Introduction)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 設計模式導讀 (Architectural Foundation)

本手冊依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，旨在解釋本系統選擇特定設計模式的背後動機（ADR）及其帶來的技術優勢。

### 1. 架構願景與挑戰 (Problem & Vision)
- **挑戰**: AI 應用常因模型頻繁更新、資料庫切換與 Prompt 漂移而導致代碼腐化。
- **願景**: 建立一個「模型無關 (Model-Agnostic)」且「高可測試性 (Test-Driven)」的穩定系統。

### 2. 核心架構決策 (ADR - Architectural Decision Records)

| 編號 | 決策 (Decision) | 動機 (Problem) | 權衡分析與代價 (Tradeoffs & Rationale) |
| :--- | :--- | :--- | :--- |
| **ADR-001** | **Repository Pattern** | 原生 SQL 散落各處，難以 Unit Test。 | **優點**: 實現資料庫無關性。**代價**: 增加介面代碼量，但對長期維護極具價值。 |
| **ADR-002** | **Dependency Injection** | 靜態工廠導致強耦合，難以 Mock。 | **優點**: 極大提升測試覆蓋率。**評估**: 捨棄單例，換取靈活性。 |
| **ADR-003** | **Template Method** | Daily/Weekly Workflows 重複代碼率 > 60%。 | **優點**: 強制執行 HR 協議。**限制**: 子類別必須遵守骨架。 |
| **ADR-004** | **Factory Pattern** | Agent/Broker/Memory 建構邏輯複雜且分散。 | **優點**: 統一 `AgentFactory`/`BrokerFactory`/`MemoryFactory`。**代價**: 新增 Factory 類別。 |
| **ADR-005** | **Adapter Pattern** | Council 與 base Agent 介面不相容，券商 API 異質性高。 | **優點**: `CouncilAgentAdapter` 將 Council 包裝為 Agent 介面；Broker Services 將異質 API 統一為 `IBroker`。 |
| **ADR-006** | **Strategy Pattern** | 不同來源 (CSV, PDF, URL) 的資料攝取邏輯迥異，難以維護。 | **優點**: 實現攝取演算法的切換與擴展。**代價**: 需要管理多個 Strategy 類別。 |
| **ADR-007** | **Tiered Compute** | 不同任務情境對模型智商與速度需求不同。 | **優點**: 實現 Advanced/Smart/Fast 分層算力路由，兼顧成本與品質。 |
| **ADR-008** | **Dynamic Heuristics** | 硬編碼門檻導致系統難以在不同市場環境中自動優化。 | **優點**: 門檻值由 Agents 依照投資報酬率 (ROI) 與復盤結果動態微調。 |

### 3. 設計模式深度庫 (Pattern Deep Dives)
每一個模式都具備詳盡的 **Good vs. Bad** 對比與實作規範：
- **[工廠模式 (Factory Pattern)](設計模式-工廠-Factory-Pattern)**: 解決 Agent/Broker/Memory 初始化爬炒。
- **[存儲庫模式 (Repository Pattern)](設計模式-存儲庫-Repository-Pattern)**: 解決持久層方言問題。
- **[依賴注入 (DI Pattern)](設計模式-依賴注入-DI-Pattern)**: 解決可測試性問題。
- **[樣板方法 (Template Method)](設計模式-樣板方法-Template-Method)**: 解決流程重複問題。
- **[適配器模式 (Adapter Pattern)](設計模式-適配器-Adapter-Pattern)**: 異質介面統一化 (Council, Brokers, Notifications)。
- **[策略模式 (Strategy Pattern)](設計模式-策略-Strategy-Pattern)**: 多樣化資料攝取與演算法切換。
- **[智能體集群 (Swarm Patterns)](設計模式-智能體集群-Swarm-Patterns)**: 多 Agent 協作、並行分析與共識機制。
- **[動態參數規範 (Dynamic Heuristics)](動態參數規範-Dynamic-Parameter-Standards)**: 運算門檻的主動演進與自優化。

---

<a id="en"></a>

## 🇺🇸 Design Patterns Introduction

### 1. Vision & Challenges
Our goal is to build a **Model-Agnostic** and **Test-Driven** AI Advisor. Design patterns are used to ensure long-term maintainability against fast-evolving AI trends.

### 2. Core ADRs
- **ADR-001 (Repository)**: Decoupling SQL for better unit testing.
- **ADR-002 (DI)**: Constructor injection for easy LLM mocking.
- **ADR-003 (Template Method)**: Simplifying daily/weekly workflows.
- **ADR-004 (Factory)**: Centralizing Agent/Broker/Memory construction.
- **ADR-005 (Adapter)**: Unifying heterogeneous interfaces (Council, Brokers).
- **ADR-007 (Tiered Compute)**: Dynamic Advanced/Smart/Fast model routing.
- **ADR-008 (Dynamic Heuristics)**: Agent-driven thresholds via DB.

### 3. Deep Dive Series
- [Factory Pattern](設計模式-工廠-Factory-Pattern)
- [Repository Pattern](設計模式-存儲庫-Repository-Pattern)
- [DI Pattern](設計模式-依賴注入-DI-Pattern)
- [Template Method](設計模式-樣板方法-Template-Method)
- [Adapter Pattern](設計模式-適配器-Adapter-Pattern)
- [Strategy Pattern](設計模式-策略-Strategy-Pattern)
- [Swarm Patterns](設計模式-智能體集群-Swarm-Patterns)

## 🔗 Bidirectional Links
- **Standards**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
- **Dev Guide**: [Local Dev Setup](環境設定與本地開發-Environment-Local-Dev)
- **PM Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
