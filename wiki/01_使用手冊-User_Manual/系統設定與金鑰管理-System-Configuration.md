# 系統設定與金鑰管理 (System Configuration & Key Management)

## 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-14 | v1.0 | Initial Release: Settings UI & Broker Config | Neo |

---

## 1. 概觀 (Overview)

自 v3.5 版本起，**AI Investment Advisor** 支援透過網頁介面 (Settings UI) 管理所有關鍵設定，包括券商連線 (Broker Connections) 與 AI 模型金鑰 (API Keys)。這不僅提高了安全性，也讓使用者無需重新啟動容器即可動態調整設定。

Starting from v3.5, **AI Investment Advisor** supports managing all key configurations via the Web UI (Settings UI), including Broker Connections and AI Model API Keys. This enhances security and allows dynamic adjustments without restarting containers.

## 2. 交易設定 (Trading Settings)

前往 **Settings > 交易與風控 (Trading & Risk)** 分頁進行以下設定：

Go to the **Settings > Trading & Risk** tab to configure:

### 券商連結 (Broker Connections)
*   **啟用開關 (Enable Toggles)**:
    *   **Enable eToro**: 啟動 eToro 服務 (需填寫 API Key)。
    *   **Enable Futu**: 啟動富途牛牛連線 (需填寫 Host/Port)。
    *   **Enable IBKR**: 啟動 Interactive Brokers 連線 (需填寫 Host/Port)。
*   **金鑰管理 (Key Management)**:
    *   在此介面輸入的 API Key 會被加密儲存於資料庫中 (SQLite `settings` table)。
    *   **優先權 (Priority)**: 資料庫設定 > `.env` 環境變數。

### 風控參數 (Dist Control)
*   **Max Daily Trades**: 每日最大交易次數限制。
*   **Circuit Breaker**: 連續虧損熔斷機制。

## 3. AI 模型設定 (AI Configuration)

前往 **Settings > AI 模型設定 (AI Configuration)** 分頁：

Go to the **Settings > AI Configuration** tab:

*   **API Key**: 輸入 OpenRouter 或 Google Gemini 的 API Key。
*   **Model Tiering**: 設定不同等級 (Advanced/Smart/Fast) 使用的模型。
*   **Base URL**: (選填) 自定義 LLM 端點。

> **注意 (Note)**: 若未設定 API Key，系統將進入 **模擬模式 (Simulation Mode)**，Agent 僅會回傳模擬分析結果。
> If no API Key is set, the system enters **Simulation Mode**, where Agents return simulated analysis only.

## 4. Google 身份驗證 (Google Authentication)

系統支援 Google OAuth 登入，憑證檔案讀取邏輯如下：

*   **預設路徑**: `secrets/client_secret.json` (建議存放處) 或根目錄 `client_secret.json`。
*   **環境變數**: 可透過 `GOOGLE_CLIENT_SECRET_PATH` 自定義路徑。
*   **Google Console 設定**:
    - **Authorized Javascript Origins**: `http://localhost:8501`, `http://localhost:8000`
    - **Authorized Redirect URIs**:
      - `http://localhost:8000/api/auth/callback`
      - `http://127.0.0.1:8000/api/auth/callback`
*   **注意**: 即使檔案不存在，系統也會嘗試讀取環境變數進行驗證，若兩者皆無則進入受限模式。

## 5. 可觀測性設定 (Observability - SigNoz)

要將日誌與追蹤數據發送至 **SigNoz**，必須在 `.env` 中設定以下變數：

```bash
# SigNoz OTLP Endpoint (gRPC 預設埠號 4317)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
# 服務名稱標記
OTEL_SERVICE_NAME=investment-advisor
```

> **注意**: 若未設定 `OTEL_EXPORTER_OTLP_ENDPOINT`，系統將僅輸出 JSON 格式日誌至標準輸出 (stdout)，而不會發送至 SigNoz。
