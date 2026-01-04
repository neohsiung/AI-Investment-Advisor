# 測試與外部服務整合 (Testing & External Services)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 測試與外部服務整合指南 (v3.1)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，闡述如何驗證系統正確性以及如何配置關鍵外部數據源。

### 1. 測試策略 (Testing Strategy)

#### 1.1 測試層級 (Test Tiers)
- **單元測試 (Unit)**: 針對 `AnalyticsService` 的數學公式進行 100% 覆蓋。
- **整合測試 (Integration)**: 驗證 [Agent Mesh](底層通信協議-Agent-Mesh-Protocols) 與 SQLite 的交互。
- **端到端測試 (E2E)**: 使用 Streamlit Test Runner 模擬使用者行為。

#### 1.2 模擬最佳實踐 (Mocking Best Practices)
為了節省 Token 成本，所有非聯動測試必須使用 Mock：
- **Agent Mocking**: 在 `conftest.py` 中建立全局 Agent Mock 選項。
- **Streamlit Mocking**: 針對 `st.sidebar` 等 UI 元件執行 `patch`。

#### 1.3 成功指標 (Success Metrics)
- **覆蓋率目標**: 系統核心功能覆蓋率需 > 75%。
- **CI 通過率**: 100% 同步於 GitHub Actions。

### 2. 外部服務配置與約束 (3rd-Party Specs)

| 服務 | 類型 | 性能約束 | 備註 |
| :--- | :--- | :--- | :--- |
| **Polygon/FMP** | REST | 限流 5 req/sec (Free)。 | 用於 [資料管理](核心系統規格-Core-System-Specs)。 |
| **Tavily** | Search | 逾時設為 10s。 | AI 時代的最佳實踐搜尋服務。 |
| **OpenRouter** | Gateway | 支援熱切換模型。 | 關鍵秘密存儲於 [環境變數](環境設定與本地開發-Environment-Local-Dev)。 |

### 3. 非功能性需求: 可觀測性 (Observability)
- **日誌追蹤**: 每個 Agent 調用必須附帶 `request_id`。
- **效能監控**: 定期稽核 `reports` 生成時間。

---

<a id="en"></a>

## 🇺🇸 Testing & External Services

### 1. Verification Tiers
- **Math Reliability**: 100% unit test coverage for `PnLCalculator` and `LeverageEngine`.
- **Consistency**: Integration tests for [Agent Mesh Protocols](底層通信協議-Agent-Mesh-Protocols) to prevent schema regression.

### 2. Mocking Philosophy
Use `unittest.mock` to bypass expensive LLM calls during CI/CD. Target coverage: **75%+**.

### 3. 3rd-Party Constraints
Maintain strict Rate-Limiters for Polygon and FMP. Fallback logic for Search is mandatory for system reliability.

## 🔗 Bidirectional Links
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
- **Dev Guide**: [Local Dev Setup](環境設定與本地開發-Environment-Local-Dev)
- **PM Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
