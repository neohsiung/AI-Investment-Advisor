# 底層通信協議 (Agent Mesh Protocols)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 底層通信協議與 Agent Mesh (Internal Specs)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，詳細定義了 Agent Mesh 的通訊規範、安全性要求與工具調用協議。

### 1. 通訊框架 (Communication Framework)
系統採用基於 MCP (Model Context Protocol) 的異步通信模式。
- **協定類型**: HTTP/1.1 + gRPC (內部)。
- **訊息格式**: JSON。

#### 1.1 請求格式示例 (Request Schema)
每個工具調用必須遵循標準 Header 與 Payload：
```json
{
  "agent_id": "CIO-001",
  "tool": "get_current_price",
  "params": {
    "ticker": "AAPL",
    "use_cache": true
  },
  "context_hash": "sha256_..."
}
```

### 2. 工具集詳細定義 (Toolset Specification)
所有工具均封裝於 [MCP 微服務](系統全景圖-System-Landscape) 中，確保權限隔離。

| 工具名稱 | 輸入參數 | 輸出範例 |
| :--- | :--- | :--- |
| `get_current_price` | `ticker` (str) | `{"price": 180.25, "ts": 169...}` |
| `get_news` | `query` (str), `limit` (int) | `[{"title": "...", "url": "..."}]` |
| `calculate_leverage` | `current_prices` (dict) | `{"ratio": 1.25, "status": "safe"}` |

### 3. 安全與品質要求 (Security & Quality NFR)

- **預防 SQL 注入 (SQLi Prevention)**:
    - **強制規範**: 嚴禁在 Repo 層使用字串格式化拼接 SQL。
    - **範例**: `conn.execute("SELECT * FROM t WHERE id = ?", (id,))`。
- **機密管理 (Secrets Management)**:
    - 所有 API Keys 不得明文出現於日誌或代碼。
    - 採用 `Environment Repository` 模式加載加密變數。
- **HR 回饋協議**:
    - Agent 互相對報告品質評分 (1-5 分)，存儲於 `agent_reviews` 表。
    - 當平均評分 < 3.0 時，觸發 [Engineer Agent](核心系統規格-Core-System-Specs) 的 Prompt 重調。

### 4. 成功指標 (Success Metrics)
- **工具調用成功率**: > 99.5%。
- **注入漏洞發生率**: 0 (由 SAST `bandit` 保證)。

---

<a id="en"></a>

## 🇺🇸 Agent Mesh Protocols

### 1. Framework
Asynchronous MCP-based communication utilizing JSON payloads for inter-agent messages and tool execution.

### 2. Toolset Spec
Standardized interfaces for `get_current_price`, `get_news`, and `calculate_leverage`. Mathematical calculations are isolated in Python modules to prevent hallucinations.

### 3. Security (NFR)
- **SQLi**: Mandatory use of parameterized queries across all repositories.
- **Secrets**: Encrypted storage and environment-only loading.
- **HR Protocols**: 360-degree cross-agent scoring loop for automated prompt tuning.

### 4. Success Metrics
- **Tool Success Rate**: > 99.5%.
- **Zero-Injection Policy**: Verified by monthly SAST scans.

## 🔗 Bidirectional Links
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
- **PM Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **DB Design**: [Database Standards](資料庫設計與代碼規範-Database-Git-Standards)
