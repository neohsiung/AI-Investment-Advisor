# 交易系統架構 (Trading Architecture)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-14 | v1.0 | Initial Release: Multi-Broker Architecture | Neo |

---

本文件詳述了 v3.3 的多券商交易架構。系統透過與 Broker 無關的介面 (`IBroker`)，支援 Etoro、Futu (富途) 與通用美股券商的整合。
This document details the v3.3 Multi-Broker Trading Architecture. The system supports integration with Etoro, Futu, and generic US brokers via a broker-agnostic interface (`IBroker`).

## 1. 架構概觀 (Architecture Overview)

系統採用 **Adapter Pattern** (適配器模式) 與 **Abstract Factory** (抽象工廠) 來隔離業務邏輯與券商實作。

The system uses the **Adapter Pattern** and **Abstract Factory** to isolate business logic from broker implementations.

```mermaid
graph TD
    User((User)) -->|Settings| DB[(Database)]
    Workflow[Workflow Service] -->|Get Broker| Factory[Broker Factory]
    Scheduler[Scheduler Service] -->|Sync| Factory
    
    Factory -->|Returns| Broker{IBroker}
    
    Broker <|..| Etoro[EtoroService]
    Broker <|..| Futu[FutuService]
    Broker <|..| USBroker[USBrokerService]
    
    subgraph "Infrastructure"
        Risk[RiskManager]
    end
    
    Etoro -->|Check Constraints| Risk
    Futu -->|Check Constraints| Risk
    USBroker -->|Check Constraints| Risk
```

## 2. 核心組件 (Core Components)

### 領域模型 (Domain Models) - `src/domain/trading.py`
定義了統一的資料結構：
Unified data structures:
*   **Order**: 訂單 (Symbol, Action, Quantity, Price, Type).
*   **Position**: 持倉 (Symbol, Quantity, AvgPrice, PnL).
*   **Account**: 帳戶摘要 (Equity, Cash).

### 介面定義 (Interface) - `src/domain/broker.py`
所有券商必須實作 `IBroker` 介面：
All brokers must implement the `IBroker` interface:
*   `get_account()`
*   `get_positions()`
*   `execute_order(order)`
*   `sync_history()`

### 風險管理 (Risk Manager) - `src/infrastructure/risk_manager.py`
集中式的風險控制中心，強制執行：
Centralized risk control enforcing:
1.  **每日交易限制 (Daily Trade Limits)** (Default: 10).
2.  **熔斷機制 (Circuit Breakers)**:
    *   連續虧損 (Consecutive Losses).
    *   深度回撤持倉 (Deep Drawdown Positions).

## 3. 擴充指南 (Extension Guide)

### 新增券商 (Adding a New Broker)
1.  在 `src/services/` 建立新服務 (例如 `ibkr_service.py`)。
2.  繼承並實作 `IBroker`。
3.  在 `src/services/broker_factory.py` 註冊新券商。

### 配置 (Configuration)
使用者可透過 Dashboard 的 **"⚙️ 交易設定 (Trading Configuration)"** 面板進行設定：
Users can configure settings via the Dashboard's **"⚙️ Trading Configuration"** panel:

1.  **Preferred Broker** (etoro / futu / ibkr).
2.  **Risk Settings**:
    *   Max Daily Trades.
    *   Loss Streak Limit.

## 4. 貢獻與合規 (Contribution & Compliance)

為確保開源專案的安全性與一致性，所有新接入的券商平台必須遵循以下規範：
To ensure security and consistency, all new broker integrations must adhere to the following guidelines:

### 4.1 合規測試 (Compliance Testing)
提交 PR 前，必須通過合規性測試：
Before submitting a PR, integration must pass constraints testing:
1.  建立測試檔案 `tests/verify_broker_compliance.py` 並加入新 Broker 類別。
2.  執行測試：
    ```bash
    python3 tests/verify_broker_compliance.py
    ```
3.  **安全檢核 (Security Check)**:
    *   禁止在程式碼中硬編碼 (Hardcode) 任何 API Key、Secret 或密碼。
    *   敏感資訊必須透過環境變數或資料庫 `settings` 表讀取。
    *   建構子 `__init__` 不得包含敏感資訊的預設值。

### 4.2 配置標準 (Configuration Standards)
所有券商設定必須整合至 `settings` 資料表，並透過 `BrokerFactory` 動態讀取：
All broker settings must be integrated into the `settings` table and read dynamically via `BrokerFactory`:

*   **命名慣例**: `[broker_name]_[setting_key]` (e.g., `etoro_api_key`, `futu_host`).
*   **必要設定**:
    *   `preferred_broker`: 使用者選擇的主券商。
    *   `[broker]_auto_trade`: 該券商的自動交易開關。

### 4.3 風險控制 (Risk Control)
所有實作必須強制呼叫 `RiskManager`：
All implementations must strictly invoke `RiskManager`:
```python
#必須在 execute_order 前呼叫
if not self.risk_manager.check_constraints(user_id, history, positions):
    return {"status": "failed", "reason": "Risk Manager Blocked"}
```

---

## 5. 參考 (References)

*   [文件規範 (Wiki Standard)](../05_工程手冊-Engineering_Handbook/Standards/文件規範-Wiki-Standard.md)
*   [API 規格 (API Design)](../05_工程手冊-Engineering_Handbook/Standards/API-Design-Standards.md)
