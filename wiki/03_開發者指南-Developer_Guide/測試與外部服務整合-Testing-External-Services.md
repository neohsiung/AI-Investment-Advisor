# 測試與外部服務整合 (Testing & External Services)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-27 | v3.8 | **Observability Expansion**: Integrated SigNoz OTel tracing for n8n and fixed OTLP gRPC dependencies. | Neo |
| 2026-02-21 | v3.7 | **v1.2.0+ Stability Fix**: Transitioned to native `pytest-asyncio` standards and resolved coroutine warnings. | Neo |
| 2026-02-14 | v3.5 | Added Multi-Broker, LINE, Memory, DSPy external services | Neo |
| 2024-01-04 | v1.0 | Initial Release | Neo |

---

<a id="zh"></a>

## 🇹🇼 測試與外部服務整合指南 (v3.5)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，闡述如何驗證系統正確性以及如何配置關鍵外部數據源。

### 1. 測試策略 (Testing Strategy)

#### 1.0 測試金字塔 (Testing Pyramid - Core Philosophy)
遵循 **Unit > Integration > E2E** 的金字塔原則，確保反饋迴圈效率。
- **Unit Tests (70%)**: 單一函數/類別，**嚴格 Mock** 所有依賴 (DB/Network)。速度 < 0.1s。
- **Integration Tests (20%)**: 模組間交互 (Service + Repository)，使用 SQLite 內存或受控 Mocks。
- **E2E Tests (10%)**: 關鍵路徑 (Smoke Tests)，模擬完整流程。

#### 1.1 測試層級 (Test Tiers)
- **單元測試 (Unit)**: `AnalyticsService` 數學公式 100% 覆蓋 (NLV/Leverage/P&L)。
- **整合測試 (Integration)**: 驗證 [Agent Mesh](底層通信協議-Agent-Mesh-Protocols) 與 SQLite 的交互。
- **端到端測試 (E2E)**: Streamlit Test Runner 模擬使用者行為。
- **Broker 合規測試**: `verify_broker_compliance.py` 驗證各券商 `IBroker` 介面實作。

#### 1.2 模擬最佳實踐 (Mocking Best Practices)
- **Agent Mocking**: `conftest.py` 中全局 Mock Agent 選項 — 節省 LLM Token。
- **Streamlit Mocking**: `unittest.mock.patch` 處理 `st.sidebar`, `st.session_state`。
- **Broker Mocking**: Mock `EtoroService`, `FutuService` 以隔離網路依賴。
- **Memory Mocking**: 測試環境使用 `SqliteMemoryRepository`，無需 Redis。

#### 1.3 測試失敗的思考路徑 (Debugging Mindset)
當測試失敗時，嚴格遵守以下優先順序：
1. **診斷單元化程度**: 先思考「是否程式碼不夠單元 (Unit)？」若測試 Setup 太複雜，應重構源碼而非增加 Mock 難度。
2. **契約驗證**: 檢查 Mock 是否符合最新的介面契約。
3. **隔離性排除**: 檢查是否為全局狀態 (sys.modules, singleton) 污染。

#### 1.3 成功指標 (Success Metrics)
- **覆蓋率狀態**: **72%** ✅ (2026-02-27 達成，641 tests collected)
- **CI 目標**: > 65% (Required) / 70% (Internal target)
- **非同步測試標竿**: 統一使用 `pytest-asyncio` 直播模式，嚴格要求 `await` 所有非同步 Mock 以維護日誌整潔。
- **CI 通過率**: 100% (GitHub Actions)。

### 2. 外部服務清單 (External Services Registry)

| 服務 | 類型 | 性能約束 | 用途 |
| :--- | :--- | :--- | :--- |
| **Polygon** | REST | 5 req/sec (Free) | 即時/歷史行情 |
| **FMP** | REST | 250 req/day (Free) | 財報、估值、公司資料 |
| **FRED** | REST | 120 req/min | 總經指標 (CPI/GDP/利率) |
| **Tavily** | REST | 10s timeout | AI 搜尋引擎 (主要) |
| **DuckDuckGo** | REST | 無限制 | 搜尋 Fallback |
| **OpenRouter** | Gateway | 依模型不同 | LLM 推論 (Gemini/Claude 等) |
| **Etoro Bridge** | REST | Session-based | 帳戶/持倉/下單 |
| **futu-api** | TCP/Protobuf | 需 FutuOpenD | 美港股行情/交易 |
| **ib_insync** | TWS API | 50 req/sec | 多資產交易 (Planned) |
| **LINE Messaging** | REST | 500 msg/min (Free) | 日報/週報推送 |
| **Redis** | TCP | N/A | 生產記憶後端 (AdaptiveCompression) |
| **DSPy** | Library | N/A | Prompt 自動優化 (Engineer Agent) |
| **Google OAuth** | OAuth 2.0 | N/A | 使用者認證 |
| **n8n** | Automation | N/A | RSS/Webhook 橋接 (OTel Enabled) |
| **SigNoz** | Monitoring | N/A | 分散式追蹤與日誌中心 (OTLP gRPC) |

### 3. 非功能性: 可觀測性 (Observability)
- **日誌追蹤**: 每個 Agent 調用附帶 `request_id`。
- **SigNoz (OTel)**: 核心服務透過 OTLP gRPC 匯出追蹤數據至 `otel-collector:4317`。
- **n8n 觀測性**: 已啟用內建 OTel SDK 以實現服務地圖 (Service Map) 平滑對接。
- **效能監控**: `reports/` 目錄生成時間定期稽核。
- **HR 回饋**: Agent 互評分數追蹤於 `agent_reviews` 表。

---

<a id="en"></a>

## 🇺🇸 Testing & External Services (v3.5)

### 0. Core Philosophy: The Testing Pyramid
All development must adhere to the **Testing Pyramid** strategy:
- **Unit Tests (70%)**: Single function/class. **STRICTLY mocked**. Fast (< 0.1s).
- **Integration Tests (20%)**: Module interactions. In-memory DBs ok.
- **E2E Tests (10%)**: Critical user flows. Expensive, use sparingly.

### 1. Verification Tiers
- **Math Reliability**: 100% unit coverage for `AnalyticsService`.
- **Broker Compliance**: Dedicated test suite for `IBroker` implementations.
- **Memory**: SQLite fallback tested in CI, Redis integration tested separately.
- **Coverage Status**: **75%** ✅ (Achieved 2026-02-15, 513+ tests, 6995 stmts)
- **CI Target**: > 70%

### 2. External Services (13 integrations)
Polygon, FMP, FRED, Tavily, DuckDuckGo, OpenRouter, Etoro Bridge, futu-api, ib_insync, LINE Messaging, Redis, DSPy, Google OAuth.

### 3. Mocking Philosophy
Use `unittest.mock` to bypass LLM, broker API, and external service calls during CI/CD.

#### Debugging Mindset (Root Cause Analysis)
When a test fails, your first question should be: **"Is the code modular enough?"**
- If setup is too heavy, the code is likely violating SRP (Single Responsibility Principle).
- Refactor the code into pure units before fixing the test.
- Priority: Unit Fix > Integration Fix > E2E Fix.

## 🔗 Bidirectional Links
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
- **Dev Guide**: [Local Dev Setup](環境設定與本地開發-Environment-Local-Dev)
- **PM Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
- **Broker Guide**: [Broker Integration](券商整合指南-Broker-Integration-Guide)
