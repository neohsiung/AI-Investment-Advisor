---
name: troubleshooting-isolated-mcp
description: 專核嚴格使用者隔離與 MCP 服務的疑難排解技能 (Troubleshooting skill for strict user isolation and MCP services).
---

# Troubleshooting Isolated MCP Services

## 核心哲學 (Core Philosophy)

在「嚴格使用者隔離」體制下，系統不允許任何無上下文（Anonymous）或廣域（Global System）的設定讀取。所有錯誤必須導航至使用者綁定、資料庫完整性或 API 金鑰配置。

## 排錯流程 (Troubleshooting Flow)

### 1. 容器層級檢查 (Docker Layer)

- **連線失敗**：檢查 `docker ps` 確認 `investment_advisor_db` 是否 Running。
- **健康檢查超時 (Python 服務)**：
  - **現象**：`mcp_server` 狀態為 `(health: starting)` 且最終超時。
  - **分析**：若容器內無 `curl`，必須使用 `python3 -c "import urllib.request; ..."`。
  - **解決方案**：
    1. 增加 `start_period` (建議 60s) 以應對 LLM/DB 初始化耗時。
    2. 將相鄰依賴（如 `dashboard`）的 `condition` 由 `service_healthy` 改為 `service_started`，避免單點阻塞導致全鏈路掛起。
- **SigNoz 組件**：確保 `otel-collector` 依賴於 `signoz` 且移除不相容的健康檢查腳本。

### 2. 使用者上下文驗證 (User Context)

- **關鍵日誌**：`✓ MCP Services binding to primary user: <UUID>`。
- **報錯模式**：`ValueError: Global 'system' user is retired`。
- **修復**：檢查模組實例化時（如 `SettingsService`, `MarketDataService`）是否遺漏了 `user_id` 參數。

### 3. 資料庫設定同步 (DB Settings)

- **API 金鑰缺失**：
  - 行為：日誌顯示 `History fetch failed on PolygonProvider: 'Close'` 或 `FRED client initialized unsuccessfully`.
  - 檢查：
    ```sql
    SELECT key, value FROM settings WHERE user_id = '<UUID>' AND key LIKE 'source_%';
    ```
  - **重要限制**：嚴禁使用 `os.getenv` 作為 API 金鑰的回推。若資料庫無值，服務應直接失敗並報錯。

### 4. Webhook 與效能問題 (Webhook & Latency)

- **503 Service Unavailable**：通常發生在 `mcp_server` 啟動中或 `lifespan` 初始化失敗。
- **延遲 (Latency)**：
  - 檢查背景任務：`PolygonStreamClient` 的 WebSocket 是否因頻寬或鎖定資源阻塞事件循環。
  - 檢查 `SentinelService` 的 `_escalate` 邏輯是否因 LLM 呼叫緩慢而阻塞實時響應。

## 常用命令 (Useful Commands)

- **重啟服務**：`docker compose restart mcp_server`
- **追蹤日誌**：`docker compose logs -f mcp_server`
- **檢查資料庫**：`docker exec investment_advisor_db psql -U postgres -d portfolio`

## 常見問題 (Gotchas)

- **JSON 雙引號問題**：`SettingsService` 在讀取字串時，若資料庫存入帶引號的字串（如 `"sk_..."`），需確保 `_parse_setting_value` 能正確處理。
- **Lifespan 失敗**：FastAPI 的 `lifespan` 異常會導致整個服務無法對外提供 API 回應。
