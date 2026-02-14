# Etoro 整合指南 (Etoro Integration Guide)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-14 | v1.0 | Initial Release | Neo |

---

本指南詳述了如何與 Etoro 進行自動化交易與投資組合同步的整合方式。
This guide details the integration with Etoro for automated trading and portfolio synchronization.

## 1. 快速導航 (Quick Nav)

### 環境變數 (Environment Variables)
請確保 `.env` 中設定了以下變數：
Ensure the following environment variables are set in `.env`:
*   `ETORO_API_BASE_URL`: Etoro Bridge API 的基礎網址 (預設: `http://localhost:8000`)
    *   Base URL for the Etoro bridge/wrapper API (default: `http://localhost:8000`)

### 驗證連線 (Verification)
執行單元測試以確認連線與邏輯：
Run unit tests to verify connectivity and logic:
```bash
# 執行整合測試 (Run integration tests)
python3 tests/test_etoro_integration.py
```

---

## 2. 架構深挖 (Deep Dive)

### 服務層 (Service Layer)
*   **`src.services.etoro_service.EtoroService`**: 實作 `IBroker` 介面的 Etoro 適配器。
    *   Etoro adapter implementing the `IBroker` interface.
*   **`src.infrastructure.risk_manager.RiskManager`**: 集中管理所有風險限制。
    *   Centralized management of all risk constraints.

### 工作流整合 (Workflow Integration)
*   **Broker Factory**: 根據使用者設定 (`preferred_broker`) 動態載入 Etoro 服務。
    *   Dynamically loads Etoro service based on user settings.
*   **每日報告 (Daily Report)**:
    *   透過統一介面取得資產與狀態 (Fetches assets/status via unified interface).
    *   使用 `RiskManager` 檢查熔斷 (Checks constraints via `RiskManager`).

---

## 3. 配置與風險 (Configuration & Risk)

### 資料庫設定 (Database Settings)
可於 `settings` 資料表調整以下設定：
The following settings can be configured in the `settings` table:

| Key | Default | Description |
| --- | --- | --- |
| `ai_trading_enabled` | `true` | AI 交易總開關 (Master switch for AI trading). |
| `ai_max_daily_trades` | `10` | 每日最大交易次數 (Maximum daily trades). |
| `cb_loss_streak` | `3` | 熔斷機制：連續虧損次數限制 (Max consecutive losses). |
| `cb_holding_days` | `30` | 熔斷機制：虧損持倉天數限制 (Max holding days for losing position). |
| `cb_loss_pct` | `0.20` | 熔斷機制：虧損百分比門檻 (Loss percentage threshold). |
| `etoro_auto_trade` | `false` | 每日報告自動交易開關 (Enable/Disable automated daily execution). |
| `etoro_trade_amount` | `100` | 自動交易金額 (Fixed amount per trade). |

### 風險管理 (Risk Management - Circuit Breaker)
系統會在以下情況自動暫停 AI 交易：
The system automatically pauses AI trading if:
1.  **連續虧損 (Consecutive Losses)**: 連續 N 筆交易虧損。
    *   N consecutive trades result in a loss.
2.  **深度回撤 (Deep Drawdown)**: 持倉超過 N 天且虧損超過 N%。
    *   A position is held for > N days with > N% unrealized loss.

若需重置，請手動將設定中的 `ai_trading_enabled` 更新為 `true`。
To reset, manually update `ai_trading_enabled` to `true` in settings.

---

## 4. 參考 (References)

*   [文件規範 (Wiki Standard)](../05_工程手冊-Engineering_Handbook/Standards/文件規範-Wiki-Standard.md)
*   [API 規格 (API Design)](../05_工程手冊-Engineering_Handbook/Standards/API-Design-Standards.md)
