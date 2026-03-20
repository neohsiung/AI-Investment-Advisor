# 交易系統架構 (Trading Architecture)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-03-20 | v6.0 | Added: Position Sizing Guard (NLV% + Cash clamp), Post-Trade DB Sync, Cash-High structured prompt | Antigravity |
| 2026-02-27 | v3.0 | Added: Dynamic Confidence Threshold, Interactive Approval Request (Option A), Sentinel scoring refactoring | Antigravity |
| 2026-02-21 | v2.0 | Updated: eToro Official API migration, IBKR skeleton, BrokerType enum expansion | Neo |
| 2026-02-14 | v1.0 | Initial Release: Multi-Broker Architecture | Neo |

---

本文件詳述了 v5.0 的多券商交易架構。系統透過與 Broker 無關的介面 (`IBroker`)，支援 eToro (官方 API)、Futu (富途) 與 IBKR (盈透證券) 的整合。`BrokerType` 列舉涵蓋 `ETORO`、`FUTU`、`IBKR`、`US_GENERIC` 與 `MOCK`。
This document details the v5.0 Multi-Broker Trading Architecture. The system supports integration with eToro (Official API), Futu, and IBKR via a broker-agnostic interface (`IBroker`). `BrokerType` enum covers `ETORO`, `FUTU`, `IBKR`, `US_GENERIC`, and `MOCK`.

## 1. 架構概觀 (Architecture Overview)

系統採用 **Adapter Pattern** (適配器模式) 與 **Abstract Factory** (抽象工廠) 來隔離業務邏輯與券商實作。

The system uses the **Adapter Pattern** and **Abstract Factory** to isolate business logic from broker implementations.

```mermaid
graph TD
    User((User)) -->"|Settings| DB[""(PostgreSQL")]
    Workflow[Workflow Service] -->"|Get Broker| Factory[BrokerFactory]"
    Scheduler[Scheduler Service] -->|Sync| Factory
    
    subgraph "Milestone 5: Automated Trading & Defense"
        ATS[AutomatedTradingService]
    end
    
    ATS -->|Check auto_trade_threshold| DB
    ATS -->"|Execute (Confidence >= Threshold)| Factory"
    ATS -->"|Request Approval (Confidence < Threshold)| User"

    Factory -->|Returns| Broker{IBroker}
    
    Broker <|..| Etoro[""EtoroService<br/>(Official API + Bridge Fallback")"]
    Broker <|..| Futu[""FutuService<br/>(futu-api / FutuOpenD")"]
    Broker <|..| IBKR[""IBKRService<br/>(TWS/Client Portal - Skeleton")"]
    
    subgraph "Infrastructure"
        Risk[RiskManager]
    end
    
    Etoro -->|Check Constraints| Risk
    Futu -->|Check Constraints| Risk
    IBKR -->|Check Constraints| Risk
```

## 2. 核心組件 (Core Components)

### 領域模型 (Domain Models) - `src/domain/trading.py`
定義了統一的資料結構：
Unified data structures:
*   **BrokerType** (Enum): `ETORO`, `FUTU`, `IBKR`, `US_GENERIC`, `MOCK`。
*   **Order**: 訂單 (Symbol, Action, Quantity, Price, OrderType, Leverage, Reason).
*   **Position**: 持倉 (Symbol, Quantity, OpenPrice, CurrentPrice, MarketValue, UnrealizedPnL, Leverage).
*   **Account**: 帳戶摘要 (BrokerType, AccountId, TotalEquity, AvailableCash, Currency, MaintenanceMargin, DayTradesRemaining).

### 介面定義 (Interface) - `src/domain/broker.py`
所有券商必須實作 `IBroker` 介面：
All brokers must implement the `IBroker` interface:
*   `get_name()` → 券商名稱
*   `get_account()` → 帳戶摘要
*   `get_positions()` → 當前持倉
*   `get_history(days)` → 交易歷史
*   `execute_order(order)` → 執行訂單
*   `sync_history()` → 同步歷史至本地 DB

### 風險管理 (Risk Manager) - `src/infrastructure/risk_manager.py`
集中式的風險控制中心，強制執行：
Centralized risk control enforcing:
1.  **每日交易限制 (Daily Trade Limits)** (Default: 10).
2.  **熔斷機制 (Circuit Breakers)**:
    *   連續虧損 (Consecutive Losses).
    *   深度回撤持倉 (Deep Drawdown Positions).

### 自動交易審批服務 (AutomatedTradingService) - `src/services/automated_trading_service.py`
串接 Agent 決策與 Broker 的中介層 (v6.0 更新)：
1. **信心閾值判斷 (Confidence Threshold)**: 系統從 `SettingsService` 動態讀取 `auto_trade_threshold` (1-10)。若 Agent 的交易提案 `confidence_score` **大於** 該閾值，則**免審批全自動下單**。
2. **互動式審核 (Approval Request)**: 若分數未達門檻，系統會透過全通路 (LINE/Email) 發送帶有 **[Approve/Reject] 互動式按鈕** 的審核請求通知。使用者可在 5 分鐘內手動批准執行，否則逾期失效。
3. **動態風險指標**: Sentinel 事件的緊急操作（如緊急清倉、避險）現在同樣使用設定檔中的動態分數，而非寫死的定值。
4. **[NEW v6.0] 持倉比例守衛 (Position Sizing Guard)**: BUY 訂單執行前，自動檢查：
    - 金額 ≤ `available_cash` (現金上限)
    - 金額 ≤ `NLV × max_single_position_pct` (預設 10%)
    - 金額 ≥ `min_trade_amount` (預設 $10 USD)
5. **[NEW v6.0] 交易後紀錄同步 (Post-Trade Sync)**: 成功交易後自動呼叫 `broker.sync_history()`，確保 DB 紀錄即時更新。

### 券商實作狀態 (Broker Implementation Status)

| 券商 | 服務檔案 | 狀態 | 說明 |
| :--- | :--- | :--- | :--- |
| **eToro** | `src/services/etoro_service.py` | ✅ Production | 已遷移至 **eToro Official Public API** (`https://public-api.etoro.com`)。支援 `api_key` + `user_key` 認證，保留本地 Bridge (`localhost:8000`) 作為 Legacy Fallback。憑證優先順序：參數 > DB > 環境變數。 |
| **Futu** | `src/services/futu_service.py` | ✅ Production | 透過 `futu-api` 連接 FutuOpenD。支援美股交易、持倉查詢與歷史同步。需本地或遠端運行 FutuOpenD。 |
| **IBKR** | `src/services/ibkr_service.py` | 🔧 Skeleton | TWS/Client Portal API 骨架實作。已定義完整 `IBroker` 介面方法，但核心邏輯為 placeholder。`BrokerFactory` 已支援 lazy import。 |

### BrokerFactory (`src/services/broker_factory.py`)
*   **動態實例化**: 根據 `preferred_broker` 設定或 `broker_type` 參數建立對應券商實例。
*   **快取機制**: 已建立的 Broker 實例會被快取，避免重複初始化。
*   **多券商啟用**: `get_enabled_brokers(user_id)` 可同時啟用多個券商 (透過 `enable_etoro`、`enable_futu`、`enable_ibkr` 設定)。
*   **Fallback**: 若無任何券商被啟用，預設啟用 eToro。

## 3. 擴充指南 (Extension Guide)

### 新增券商 (Adding a New Broker)
1.  在 `src/services/` 建立新服務 (例如 `new_broker_service.py`)。
2.  繼承並實作 `IBroker` 的所有抽象方法。
3.  在 `src/services/broker_factory.py` 的 `get_broker()` 中註冊新券商。
4.  在 `src/domain/trading.py` 的 `BrokerType` 列舉中新增對應類型。

### 配置 (Configuration)
使用者可透過 Dashboard 的 **"⚙️ 交易設定 (Trading Configuration)"** 面板進行設定：
Users can configure settings via the Dashboard's **"⚙️ Trading Configuration"** panel:

1.  **Preferred Broker** (etoro / futu / ibkr).
2.  **Risk Settings**:
    *   Max Daily Trades.
    *   Loss Streak Limit.
    *   Day Trades Remaining (PDT Rules).
3.  **[NEW v6.0] Position Sizing Settings**:
    *   `max_single_position_pct` — 單一標的最大持倉佔淨值比例 (預設 `0.10` = 10%).
    *   `min_trade_amount` — 最低交易金額 (預設 `10.0` USD).

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

### 4.4 預期效益與成果 (Expected Outcomes)
- **商業價值 (Business Value)**: Adapter Pattern 完全隔離了底層券商 API 邏輯，使得未來系統能達到「一鍵跨券商套利」與「資產無縫轉移」的商業願景，避免被單一交易商綁架。
- **性能指標 (Performance Target)**: 從觸發警告到下達 Auto-Hedging 指令，並透過 `IBroker` 實行委託，整體端對端延遲 (End-to-End Latency) 控制在 500ms 內。

---

## 5. 參考 (References)

*   [文件規範 (Wiki Standard)](文件規範-Wiki-Standard)
*   [底層通信協議 (Agent Mesh Protocols)](底層通信協議-Agent-Mesh-Protocols)
