# 動態參數規範 (Dynamic Parameter Standards)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 動態參數規範 (Agent-Driven Heuristics)

本文件定義系統中數值參數（Heuristics）的管理標準，確保系統具備自適應與自優化能力。

### 1. 核心原則 (Core Philosophy)
- **非硬編碼 (No Hardcoding)**: 除了初始預設值外，所有影響決策的數值門檻必須存在於持久化層 (Database)。
- **Agent 擁有的變更權 (Agent Ownership)**: 具體角色（如 `RiskAgent`, `EngineerAgent`）有權根據「投資報酬率 (ROI)」與「復盤結果」動態修改參數。
- **可追溯性 (Traceability)**: 每一步變更必須記錄變更者 (Role)、原因 (Rationale) 與預期效果。

### 2. 定義範疇
- **預警門檻**: 如 VIX 觸發值、股價異動百分比。
- **風險權重**: 如 `RiskKeyword` 的評分權重。
- **算力分配**: 如不同情境對應的模型層級 (Advanced/Smart/Fast)。

### 3. 操作規範 (Operations)
- **初始化**: 程式碼內僅保留 `defaults` 用於首次啟動。
- **運行期**: `Service` 在任務開始前從 DB 載入最新參數。
- **優化模式**: `RetrospectiveAgent` 定期審計參數與 P&L 的相關性，並提案修改。

---

<a id="en"></a>

## 🇺🇸 Dynamic Parameter Standards

### 1. Vision
Transform static constants into "Living Metrics" managed by the Agent Swarm.

### 2. Compliance
- **Dynamic Retrieval**: All decision-making thresholds must be fetched from DB.
- **Role-based Calibration**: The `RiskAgent` calibrates risk limits; `EngineerAgent` calibrates computation efficiency.
- **Audit Log**: Every change must document the "Why" and the "ROI" expectation.

## 🔗 Bidirectional Links
- **Handbook**: [Engineering Handbook Intro](設計模式導讀-Design-Patterns-Intro)
- **Sentinel**: [Sentinel & Council Architecture](哨兵與評議會架構-Sentinel-Council-Architecture)
