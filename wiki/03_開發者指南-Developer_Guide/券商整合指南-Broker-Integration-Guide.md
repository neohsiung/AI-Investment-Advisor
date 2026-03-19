# 券商整合指南 (Broker Integration Guide)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-03-19 | v5.2  | **Dynamic Discovery**: Removed hardcoded eToro Instrument IDs; implemented dynamic resolution. | Antigravity |
| 2026-03-01 | v5.0  | **Tech Stack Modernization**: Removed `futu-api` to upgrade to OTel 1.39.1 & Protobuf 5.x. | Antigravity |
| 2026-02-15 | v3.6  | **Milestone**: Unified `BrokerFactory` implementation & stable Multi-Broker routing. | Neo |
| 2026-02-14 | v1.0  | Initial Release: Integrated Etoro, Futu, and IBKR guides | Neo |

---

本指南詳述了如何透過統一的 **`BrokerFactory`** 介面與支援券商 (Etoro, IBKR) 進行整合。系統會自動根據配置路由至正確的券商實作。

This guide details how to integrate with the supported brokers via the unified **`BrokerFactory`**, enabling automated execution through a single abstraction layer.

## 1. 快速導航 (Quick Nav)

### 支援券商一覽 (Supported Brokers)
| **Etoro** | Official Public API (REST) | 443 (HTTPS) | 模擬交易、跟單交易 (Copy Trading) |
| **IBKR (盈透)** | TWS API / IB Gateway | 7497 (Paper) / 7496 (Live) | 全球市場、機構級執行 |

---

## 2. Etoro 整合 (Etoro Integration)

本系統支援 eToro 官方 Public API。請按照以下步驟獲取認證憑證並設定環境。

### 2.1 官方 API 認證流程 (Step-by-Step)
1.  **進入設定**: 登入 eToro 帳戶，導航至 [Settings > Trading](https://www.etoro.com/settings/trading)。
2.  **建立金鑰**: 在 "Public API" 區塊點擊 **Create a New Key**。
3.  **配置預設屬性**: 
    - **Key Name**: 輸入識別名稱 (例如: `AI-Advisor-Prod`)。
    - **Permissions**: 
        - 選擇 `Read` (僅查詢持倉與歷史)。
        - 選擇 `Write` (若需 AI 自動執行對沖/交易)。
4.  **安全驗證**: 完成彈出的 2FA 驗證。
5.  **複製憑證**: 保存畫面上顯示的 `Public API Key` 與 `User Key`。
    > [!TIP]
    > **[NEW v5.2]** 系統現在支援 **動態標的解析 (Dynamic Resolution)**。您不再需要手動尋找或映射 Instrument ID。系統會自動透過標的代號 (e.g., `NVDA`, `COST`) 向 eToro 請求對應的內部 ID。
    > [!CAUTION]
    > 憑證僅顯示一次，請妥善保管。

### 2.2 系統設定 (Configuration)
在 `.env` 中加入以下資訊：
```bash
# eToro 官方 API 認證 (推薦)
ETORO_API_KEY=your_public_api_key
ETORO_USER_KEY=your_user_key

# 舊有 Bridge 模式 (選填，若未提供 API_KEY 則回退至此)
# ETORO_API_BASE_URL=http://localhost:8000
```

### 2.3 驗證 (Verification)
執行整合測試以確認連線與認證標頭：
```bash
python3 tests/test_etoro_api_auth.py
```

---

## 3. [DEPRECATED] Futu (富途) 整合 (Futu Integration)

> [!CAUTION]
> **已於 v5.0 移除 (Removed in v5.0)**
> 為了升級至最新的 OpenTelemetry 1.39.1 與 Protobuf 5.x，系統已移除 `futu-api` 依賴。
> `futu-api` remained on older Protobuf versions which blocked critical tech stack upgrades.

---

## 4. IBKR (盈透) 整合 (IBKR Integration)

### 4.1 安裝 TWS 或 Gateway
由於 IBKR 要求嚴格的安全認證，您必須運行 **Trader Workstation (TWS)** 或 **IB Gateway**。

1.  下載 [TWS Latest](https://www.interactivebrokers.com/en/trading/tws.php)。
2.  登入帳戶 (建議先使用 **Paper Trading** 模擬帳戶)。
3.  進入 **Global Configuration** -> **API** -> **Settings**:
    *   ✅ Enable ActiveX and Socket Clients
    *   ❌ Read-Only API (取消勾選以允許下單)
    *   **Socket Port**: `7497` (Paper) / `7496` (Live)
    *   **Trusted IPs**: 加入 `127.0.0.1`

### 4.2 程式碼整合 (Code Integration)
本系統目前使用 `ib_insync` (asyncio-based) 進行連接。`src/services/ibkr_service.py` 預設連接本地 TWS。

**設定參數**:
```bash
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
```

### 4.3 驗證 (Verification)
目前 IBKR 處於 Alpha 階段，您可以使用以下測試腳本驗證連線：
```bash
# 確保 TWS 已開啟並登入
python3 tests/test_ibkr_connection.py 
# (註: 需自行建立此測試或依賴 verify_broker_compliance.py)
```

---

## 5. 風險管理整合 (Risk Management)

所有券商的交易指令均會經過統一的 `RiskManager` 審查。

### 5.1 檢查邏輯
每次 `execute_order` 前，系統會檢查：
1.  **連續虧損 (Loss Streak)**: 是否超過 `cb_loss_streak` (預設 3 次)。
2.  **單日上限 (Daily Limit)**: 是否超過 `ai_max_daily_trades` (預設 10 筆)。
3.  **板塊曝險 (Sector limit)**: 單一板塊是否超過總資產 30%。

若觸發熔斷，交易將被拒絕並回傳 `status: failed`。

### 5.2 全域緊急開關 (Kill Switch)
若發生異常，可於 Dashboard 設定頁面點擊 **"🔴 Emergency Stop"**，此變更對所有券商同時生效。

---

## 6. 參考 (References)
*   [Futu API Docs](https://openapi.futunn.com/futu-api-doc/)
*   [IBKR TWS API](https://interactivebrokers.github.io/tws-api/)
*   [核心系統規格](核心系統規格-Core-System-Specs)

