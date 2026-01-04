# 底層通信協議 (Agent Mesh Protocols)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 底層通信協議與 Agent Mesh

本文件深入說明代理人之間的通訊模式、工具調用協議以及系統安全性保障。

### 1. 模型分級執行 (Tiered Model Execution)
為了平衡成本與智能，系統將運算資源分為兩層：
- **Flash Tier (基礎)**: 使用 Gemini 1.5 Flash。用於初步數據清洗、新聞抓取與簡單過濾。
- **Deep Tier (進階)**: 使用 Gemini 1.5 Pro。用於複雜財報分析、宏觀推論與最終選股。

### 2. MCP 微服務協議 (Model Context Protocol)
MCP Server 提供一個統一的微服務介面，讓所有 Agent 透過 HTTP 調用標準化工具：
- **註冊中心**: 提供 `get_current_price` (股價)、`get_news` (新聞) 等工具。
- **訊息匯流排**: 支持 Agent 間發送需求訊息 (Request) 與狀態同步。

### 3. 搜尋服務架構 (Search Architecture)
採用**雙層檢索策略**以確保持續可用性：
1. **主要來源 (Tavily)**: 結構化、AI 優化的搜尋结果。
2. **備援來源 (DuckDuckGo)**: 當 API 額度用罄或超時時自動降級。

### 4. 資安審計與防護 (Security & Protection)
系統採取的安全性強化措施：
- **預防 SQL 注入**: 核心層全面停用字串拼接，改用參數化查詢 (Parameterized Queries)。
- **代碼執行保護**: 嚴格過濾 `subprocess` 呼叫，避免指令注入。
- **API 金鑰管理**: 敏感資料全面由環境變數或加密資料庫儲存，嚴禁寫死在代碼中。

---

<a id="en"></a>

## 🇺🇸 Agent Mesh Protocols

### 1. Tiered Execution
- **Flash Tier**: Low-cost models (Flash) for preprocessing and data fetching.
- **Deep Tier**: High-reasoning models (Pro) for complex final decision making.

### 2. MCP Microservice
- **Tool Registry**: Centralized service for data tools (Price, News, Financials).
- **Communication**: Standardized HTTP endpoints for agent interaction.

### 3. Search Strategy
- **Primary (Tavily)**: Structured JSON output, AI-focused.
- **Fallback (DuckDuckGo)**: High-latency, no-key backup.

### 4. Security Audit
- **SQLi Prevention**: Mandatory parameterized queries across the codebase.
- **Secret Management**: DB-First or Env-based configuration; no hardcoded secrets.

## 🔗 See Also
- [System Landscape](wiki/04_架構觀點-Architect_Views/系統全景圖-System-Landscape.md)
- [Database & Git Standards](wiki/03_開發者指南-Developer_Guide/資料庫設計與代碼規範-Database-Git-Standards.md)
