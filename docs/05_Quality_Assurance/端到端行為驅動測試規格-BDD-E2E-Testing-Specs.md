---
title: 端到端行為驅動測試規格 (BDD E2E Testing Specs)
description: 以 BDD (行為驅動開發) Given-When-Then 語義定義全系統端到端業務場景驗收標準與自動化測試案例。
tags: [bdd, e2e, testing, gherkin, qa, verification]
---

# 端到端行為驅動測試規格 (BDD E2E Testing Specs)

> **導航跳轉 (Navigation)**: [Wiki 首頁 (Home)](../Home.md) | [產品需求規格總綱](../00_Product_Strategy/產品需求規格總綱-PRD-Master-System-Specs.md) | 系統可觀測性與通知規範

### 版本紀錄 (Version History)
| 日期 (Date) | 版本 (Version) | 變更說明 (Description) | 作者 (Author) |
| :--- | :--- | :--- | :--- |
| 2026-09-20 | v1.0.0 | 初版 BDD 規格發布，以 Gherkin 語意規範條件裁決、零外洩脫敏、DAG 與成本治理之端到端驗收標準 | QA Team |

---

### 角色導引 (Persona Guide)
- **目標受眾 (Target Audience)**: 🧪 **BDD / QA 測試工程師 (QA & Verification Engineer)**
- **閱讀時間 (Reading Time)**: 約 4 分鐘 (Approx. 4 mins)
- **文件目的 (Purpose)**: 提供全業務場景之 Given-When-Then 行為驗收標準，對應實體端到端測試套件 `tests/e2e/test_bdd_e2e_scenarios.py`。

---

## 🇹🇼 繁體中文 (Traditional Chinese)

### 1. BDD 核心原則與通用語彙

本測試規格以使用者與產品視角出發，將所有端到端流程表述為行為劇本：
- **Given (前提條件)**：系統初始狀態、市場指標或資料庫前置條件。
- **When (觸發事件)**：使用者操作、市場行情突變或外部 Webhook 輸入。
- **Then (預期結果)**：系統可觀測行為、業務決策輸出、安全性保障或稽核存證。

---

### 2. 五大核心功能 BDD 驗收劇本

#### Feature 1: 毫秒級條件裁決與雙門檻避險 (Reflex Arbiter & Dual-Threshold)

```gherkin
Feature: 市場黑天鵝事件之毫秒級條件裁決與避險
  As an 獨立投資人
  I want 系統在市場極端崩跌時於 200 毫秒內做出風控裁決
  So that 能夠避免慢思模型延遲造成的巨大滑點損失

  Scenario: 極端市場波動觸發 P0 自動避險
    Given 市場指標 VIX >= 30 且標的即時回撤幅度超過 5%
    When Sentinel 哨兵將行情特徵傳遞予 ArbiterClient 進行條件裁決
    Then 裁決結果為 "P0" (最高優先級避險)
    And 校準置信度 (Confidence) >= 0.96
    And 端到端裁決延遲 <= 200 ms
    And 系統產出對應決策之不可篡改 SHA-256 稽核存證

  Scenario: 邊界置信度自動升級至 System 2 慢思覆核
    Given 裁決結果之置信度落於 0.70 至 0.95 區間
    When ArbiterClient 偵測到置信度未達自動平倉閾值
    Then 系統自動將決策升級至 CIO 評議會 (is_escalated = True)
    And 喚醒 System 2 深度推理模型召開辯論
    And 前端顯示 [深思審核中] 決策可解釋性徽章
```

#### Feature 2: 零資料外洩特徵脫敏 (Zero-Leakage Data Sanitization)

```gherkin
Feature: 外部 LLM 請求之零資料外洩安全防護
  As a 資安與合規稽核員
  I want 確保任何送往外部雲端的 Payload 完全去識別化
  So that 個人資產規模與機密憑證永無外洩風險

  Scenario: 原始持倉狀態脫敏外發
    Given 原始狀態中包含真實 "account_id"、"portfolio_cash" 與 API 私鑰字串
    When 資料進入 HighAssuranceSanitizer 脫敏器
    Then "account_id" 與 "portfolio_cash" 欄位被徹底移除
    And 實體部位數值轉換為正規化無維度相對權重比例
    And 所有命中正則之 API 金鑰被遮罩替換為 "[REDACTED_SECRET]"
    And 計算脫敏狀態之 SHA-256 雜湊值記錄於審計日誌
```

#### Feature 3: 宣告式工作流編排與無環 DAG 檢驗 (Declarative Workflow DAG)

```gherkin
Feature: 宣告式 YAML 工作流完整性與依賴拓撲
  As a 量化策略師
  I want 確保所有工作流設定檔形成合法的有向無環圖 (DAG)
  So that 背景任務排程執行不會陷入死循環或依賴缺失

  Scenario: 驗證全系統工作流設定檔合法性
    Given 目錄 "config/workflows/" 下的所有 YAML 流程定義
    When 經由 WorkflowLoader 進行拓撲排序與語法解析
    Then 所有工作流圖無循環依賴 (Cycle-free)
    And 每個節點引用的依賴節點皆在同圖內有明確定義
```

#### Feature 4: 運算成本預算方案治理 (Cost Profiles Governance)

```gherkin
Feature: 運算成本方案約束與階層調配
  As a 單機自架運維者
  I want 透過設定檔約束每月 LLM 巡檢與調用費用
  So that 能在有限預算下維持系統最優防禦表現

  Scenario: 切換至 Frugal 節約方案
    Given 使用者選擇 "Frugal" 運算成本方案
    When CostProfileService 載入設定
    Then 背景巡檢頻率自動調整為低頻
    And 優先指派免費 NVIDIA NIM 或本地 Ollama 階層
    And 單月預算上限鎖定於 $5.00 USD 以內
```

---

## 🇬🇧 English

### 1. BDD Acceptance Scenarios
This specification defines end-to-end behavior across 4 primary features:
1. **Reflex Arbiter**: Sub-200ms P0 hedging under extreme volatility and seamless System 2 escalation.
2. **Zero-Leakage Sanitizer**: Strict PII/secret scrubbing and SHA-256 state hashing.
3. **Workflow DAG**: Acyclic dependency validation for all declarative YAML pipelines.
4. **Cost Governance**: Budget enforcement across Frugal, Balanced, and Aggressive profiles.

---

### 參考資源 (References)
- **相關需求文檔 (Related Documents)**:
  - [Wiki 首頁 (Home)](../Home.md)
  - [產品需求規格總綱 (Master PRD)](../00_Product_Strategy/產品需求規格總綱-PRD-Master-System-Specs.md)
  - 條件裁決引擎產品規格 (PRD Reflex-Arbiter)
  - 零外洩資料脫敏架構 (Zero-Leakage Sanitizer)
- **自動化測試代碼 (Test Implementations)**:
  - BDD 端到端測試套件: [tests/e2e/test_bdd_e2e_scenarios.py](../../tests/e2e/test_bdd_e2e_scenarios.py)
  - 裁決客戶端單元測試: [tests/test_arbiter_client.py](../../tests/test_arbiter_client.py)
