# 外部事件整合指南 (External Event Integration Guide)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v1.2 | 重新定位為技術串接規範，將來源註冊移至「數據矩陣」 | Antigravity |
| 2026-02-15 | v1.1 | 增加低依賴本地整合與 Custom Header 保護 | Antigravity |

---

<a id="zh"></a>

## 🇹🇼 外部事件串接規範 (v3.8)

本文件定義本系統 Inbound Webhook 的技術規格、驗證標準與通訊協議。具體數據源的註冊請參閱 [金融數據矩陣](金融數據矩陣與整合成本-Financial-Data-Matrix-Cost)。

### 1. 統一存取規範 (Technical Interface)

本系統提供標準 RESTful 入口，用於接收來自外部正規服務（如 MktRecap, TradingView Official Webhook）的訊號。

- **協定**: `HTTPS` (非私有網域務必使用加密隧道)
- **基礎路徑 (Base URL)**: `${EXTERNAL_BASE_URL}/webhook/{source}`
- **方法 (Method)**: `POST`
- **內容類型 (Content-Type)**: `application/json`

### 2. 驗證與資安 (Security Standards)

為了確保端點安全，實作必須遵循以下層次：

#### 2.1 標頭驗證 (Header Authentication)
所有傳入請求**必須**包含自定義密鑰：
- **Header Key**: `X-API-Key`
- **值**: 需與 `Settings` 標籤頁中生成的 API Key 匹配（或資料庫中的 `webhook_api_key`）。

#### 2.2 IP 白名單 (IP Whitelisting)
在生產環境中，建議在網關層 (Nginx/Cloudflare) 限制僅允許來源伺服器的 IP 範圍（如 TradingView 或 IFTTT 的出口 IP）。

---

### 3. 資料規範 (Schema Specifications)

#### 3.1 核心欄位要求
雖然各來源 Payload 不同，但通用的正規化處理遵循：
- `ticker`: 必須包含標的名 (e.g., "AAPL", "BTCUSDT")。
- `type`: 事件類型 (e.g., "PRICE_ALERT", "NEWS_FLASH")。

#### 3.2 來源別名對照 (Source Aliases)
本系統原生支持以下來源路由：
- `/webhook/mktrecap`: 市場快照。
- `/webhook/tradingview_alerts`: 技術指標警報。
- `/webhook/rss_bridge`: 新聞媒體與 RSS 轉發。

---

### 4. 調試與測試 (Debugging)
- 使用 `POSTMAN` 或 `cURL` 進行測試時，請確保包含正確的 Header。
- **範例**:
  ```bash
  curl -X POST https://your-domain.ngrok-free.dev/webhook/test \
    -H "X-API-Key: YOUR_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"ticker": "AAPL", "msg": "Official Test"}'
  ```

---

<a id="en"></a>

## 🇺🇸 External Event Technical Standards (v3.8)

This document specifies the technical requirements for inbound webhooks, focusing on protocol, security, and schema validation.

### 1. Interface Specs
- **Method**: `POST`
- **Endpoint**: `/webhook/{source}` (Generic: `/api/v1/webhook/{source}`)
- **Auth**: Mandatory `X-API-Key` header.

### 2. Security Compliance
- **No Hardcoding**: All URLs must be managed via environment variables.
- **Payload Validation**: All incoming data undergoes light normalization before being dispatched to the `SentinelService`.

### 3. Usage Patterns
For specific registration and source-level configuration (e.g., Futu, FRED), refer to the [Financial Data Matrix](金融數據矩陣與整合成本-Financial-Data-Matrix-Cost).

## 🔗 Bidirectional Links
- **Data Inventory**: [Financial Data Matrix & Cost Analysis](金融數據矩陣與整合成本-Financial-Data-Matrix-Cost)
- **Architecture**: [Sentinel & Council Architecture](哨兵與評議會架構-Sentinel-Council-Architecture)
