# 服務層開發指南 (Service Layer Blueprints)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

### 版本紀錄 (Version History)

| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-03-07 | v4.5 | **Async Interaction Loop**: `InteractionService` 支援雙向委派至 `VerificationService`，實現全通路 "OK" 應答驗證。 | Antigravity |
| 2026-03-05 | v4.4 | **Keyword Discovery Service**: 新增 `RiskKeywordService` 3源探索、DI 注入、MAX_KEYWORDS 動態上限。Repository 新增 3 方法。 | Antigravity |
| 2026-02-28 | v4.3 | **Webhook Updates**: Added Heartbeat API and Market-Alert webhooks for Sentinel. | Antigravity |
| 2026-02-18 | v4.1 | **Async & Multi-Identity**: Refactored Notification/Interaction services to be non-blocking. Unified user identity resolution. | Neo |
| 2026-02-15 | v3.6 | Added Leverage Engine & Bilingual Code Standards | Neo |
| 2026-02-14 | v3.5 | Added RiskKeywordRepository, Sentinel 4D triggers, weighted keywords, Tavily pipeline | Neo |
| 2026-02-21 | v4.2 | **Service Census Update**: 38 services documented. Added Attribution, SupplyChain, UserFocus, Verification, Reporting, NotificationFilters, AutomatedTrading, ExperienceReplay, Webhook. | Antigravity |
| 2026-02-14 | v3.5 | Full rewrite — 27 services documented, Multi-Broker, Sentinel/Council, Memory | Neo |
| 2024-01-04 | v1.0 | Initial Release (3 services) | Neo |

---

<a id="zh"></a>

## 🇹🇼 服務層開發指南 (v4.1)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，詳解 `src/services/` 下核心業務邏輯的實作規範。

### 1. 架構概覽 (Overview)

服務層作為「領域邏輯」的承載者，負責協調 Repository 與外部 API。

- **無狀態設計 (Stateless)**: 不持有用戶狀態，透過參數或 Repository 傳入。
- **故障轉移 (Failover)**: `MarketDataService` 等核心服務具備多層級 Provider 退避策略。
- **依賴注入 (DI)**: Service 接受 Repository 介面注入，Details 見 [DI Pattern](設計模式-依賴注入-DI-Pattern)。

### 2. 服務總覽 (Service Registry — 38 Services)

#### 2.1 數據與市場 (Data & Market)

| 服務 | 檔案 | 核心職責 |
| :--- | :--- | :--- |
| `MarketDataService` | `market_data_service.py` | 聚合 Polygon/FMP/YFinance，含退避策略與 TTL=300s 快取。 |
| `FredService` | `fred_service.py` | FRED 總經指標 (利率/CPI/GDP)。 |
| `SearchService` | `search_service.py` | Tavily (主) + DuckDuckGo (備) 搜尋服務。 |
| `BrowserService` | `browser_service.py` | 網頁內容擷取與解析。 |
| `SupplyChainService` | `supply_chain_service.py` | 硬體瓶頸追蹤 (CoWoS/HBM)、MAG7 CaPex 供應鏈知識圖譜映射與短缺溢價估算。 |

**退避策略 (Failover Strategy)**:

```mermaid
graph TD
    Start[請求報價] --> P1{Polygon API}
    P1 -->|失敗/無金鑰| P2{FMP API}
    P2 -->|失敗| P3{YFinance}
    P3 -->"|最終失敗| Err[返回空值/日誌紀錄]"
    P1 -->"|成功| Success[返回數據]"
    P2 -->|成功| Success
```

#### 2.2 多券商與風控 (Multi-Broker & Risk)

| 服務 | 檔案 | 核心職責 |
| :--- | :--- | :--- |
| `BrokerFactory` | `broker_factory.py` | 依據 `preferred_broker` 設定建立 `IBroker` 實例 (Factory Pattern)。 |
| `EtoroService` | `etoro_service.py` | Etoro Bridge API 整合 — 帳戶/持倉/下單/歷史同步。 |
| `FutuService` | `futu_service.py` | 富途 futu-api 整合 — 美港股交易與行情。 |
| `IbkrService` | `ibkr_service.py` | IBKR ib_insync 骨架 — 多資產交易 (Planned)。 |
| `PortfolioAggregatorService` | `portfolio_aggregator_service.py` | 跨券商統一持倉、NLV 與資產配置。 |
| `AutomatedTradingService` | `automated_trading_service.py` | 自動化交易執行 — 依據 AI 信心分數與使用者閾值觸發下單。 |

#### 2.3 Agent 引擎 (Agent Engine)

| 服務 | 檔案 | 核心職責 |
| :--- | :--- | :--- |
| `WorkflowService` | `workflow_service.py` | 主循環引擎 — Daily/Weekly 報告生成 (Template Method)，並呼叫 `Engineer Agent` 進行繁體中文翻譯。 |
| `TaskPlanningService` | `task_planning_service.py` | DAG 任務分解、複雜度評分、動態模型路由。 |
| `HRService` | `hr_service.py` | 360° 互評、Zombie Agent 偵測、績效追蹤。 |
| `RefinementService` | `refinement_service.py` | DSPy Prompt 自動優化 (Engineer Agent 後端)。 |
| `EvaluationService` | `evaluation_service.py` | Agent 產出品質評估。 |
| `AttributionAnalyzer` | `attribution_analyzer.py` | 自動歸因與動態權重校準引擎 — 掃描歷史推薦、比對市場表現、計算勝率與 Alpha。 |
| `ExperienceReplayService` | `experience_replay_service.py` | 復盤服務 — 分析警報歷史與投資組合表現，動態調整 SNR 閾值與誤報抑制。 |

#### 2.4 監控與仲裁 (Monitoring & Arbitration)

| 服務 | 檔案 | 核心職責 |
| :--- | :--- | :--- |
| `SentinelService` | `sentinel_service.py` | 7×24 市場事件監聽，**4 觸發維度**: VIX/持倉異動/加權新聞 (DB 關鍵字)/宏觀指標。 |
| `CouncilService` | `council_service.py` | 碎形辯論 (Fractal Debate) — 對每檔持倉執行多角度質疑。 |
| `VerificationService` | `verification_service.py` | 多通路連線性測試與身分驗證 (**Challenge-Response 應答流程**)。支援非同步驗證碼與全局回覆匹配。 |

#### 2.5 持久化與記憶 (Persistence & Memory)

| 服務 | 檔案 | 核心職責 |
| :--- | :--- | :--- |
| `MemoryService` | `memory_service.py` | 統一記憶讀寫介面，支援對話/分析上下文。 |
| `MemoryFactory` | `memory_factory.py` | 依環境自動選擇 Redis (生產) 或 SQLite (本地) 後端。 |
| `TransactionService` | `transaction_service.py` | 交易記錄 CRUD、Atomic 匯入。 |
| `IngestionService` | `ingestion_service.py` | CSV 匯入 (交易/股利)、全有或全無。 |
| `UserRepository` | `user_repository.py` | **[NEW v4.1]** 跨通路身分映射與 UUID 解析核心介面。 |
| `RiskKeywordService` | `risk_keyword_service.py` | **[NEW v4.4]** 動態關鍵字探索與精煉。快取存取 + 3 源探索 + 自動精煉 + 修剪。|
| `RiskKeywordRepository` | `risk_keyword_repository.py` | 風險關鍵字 CRUD + 命中追蹤 + 復盤分析 + UPSERT 探索 (160+ 預設種子)。 |

#### 2.6 Dashboard & UI 支援 (UI Support)

| 服務 | 檔案 | 核心職責 |
| :--- | :--- | :--- |
| `AnalyticsService` | `analytics_service.py` | NLV/Leverage/P&L 確定性計算 (0% 幻覺)。**[v3.6 New]** Leverage Engine. |
| `DashboardService` | `dashboard_service.py` | Dashboard 數據聚合與即時指標。 |
| `PerformanceService` | `performance_service.py` | 歷史績效追蹤與趨勢分析。 |
| `SettingsService` | `settings_service.py` | 系統設定 CRUD (Unified DB backed)。 |
| `ThemeService` | `theme_service.py` | 統一主題系統 (22 Design Tokens)，支援 OS 自動偵測與 WCAG AA Dark Mode。 |
| `BacktestService` | `backtest_service.py` | 策略回測引擎。 |

#### 2.7 互動與通知 (Interaction & Notifications)

| 服務 | 檔案 | 核心職責 |
| :--- | :--- | :--- |
| `InteractionService` | `interaction_service.py` | **[Async v4.5]** 雙向互動 (Approvals) — 支援 LINE/Telegram Webhook 路由；具備**未匹配訊息委派**機制 (委派至 VerificationService)。 |
| `SchedulerService` | `scheduler_service.py` | Cron 排程 — 自動日報/週報生成。 |
| `NotificationService` | `notification_service.py` | **[Async v4.1]** 非同步警報推送，具備 UUID 多通路映射能力。 |
| `NotificationFilters` | `notification_filters.py` | 興趣導向通知過濾 — 依據使用者每通道訂閱的類別 (sentinel/report/approval) 決定是否推送。 |
| `ReportingService` | `reporting_service.py` | Agent Markdown 報告轉換為專業機構級 HTML 格式 (Email/Web)。 |
| `WebhookService` | `webhook_service.py` | 外部 Webhook 接收與解析 — 支援心跳檢查 (Heartbeat) 與異常警報 (Market-Alert) 觸發 Sentinel。 |
| `UserFocusService` | `user_focus_service.py` | 使用者投資焦點提取 — 從 eToro 觀察名單分析板塊/產業偏好。 |

### 3. 代理人執行引擎 (Agent Execution Engine)

#### 3.1 ReAct 思考機制 (Think-Act-Observe)

實現於 `BaseAgent.run_tool_loop`：

1. **Regex 解析**: 解析 `CALL: tool_name({"arg": "val"})` 或 `SEARCH: "query"`。
2. **McpServer 調度**: 優先搜尋 Local Skills，無則調用 Remote MCP。
3. **上下文拼接**: 工具輸出封裝為 `System: [Tool Output]` 並重新注入 LLM 歷史。

#### 3.2 A2A 實體化路徑 (Agent Instantiation)

1. **Factory 介入**: `AgentFactory` 根據名稱動態建立 Agent (支援 `tier` 參數)。
2. **依賴注入**: 自動注入 `feedback_repo` 與 `market_tools`。
3. **同步執行**: 目前為同步阻塞調用，適合確定性研究路徑。

#### 3.3 任務規劃引擎 (Task Planning)

*詳見: [任務規劃與執行引擎](任務規劃與執行引擎-Task-Planning-Engine)*

- **核心**: Goal → DAG 分解 → Complexity Scoring → Model Tier Selection。
- **模型路由**: Fast (Flash) / Smart (Pro) / Advanced (Thinking)。

### 4. 槓桿引擎 (Leverage Engine) - v3.6 新增

位於 `AnalyticsService` -> `LeverageCalculator`，負責精確計算帳戶健康度指標：

- **TNV (Total Nominal Value)**: 總名義價值 = $\sum |Position \times Price|$
  - *Note*: 包含多頭與空頭頭寸的絕對值總和 (Gross Exposure)。
- **Portfolio Value**: 投資組合市值 = $\sum (Position \times Price)$
- **Net Invested Capital**: 淨投入資本 = 累計存款 - 累計提款。
- **Cash Balance**: 淨現金餘額 = $Cash Flow Sum + \sum Transaction Cash Impact$
  - *Impact*: BUY (-), SELL (+), DIVIDEND (+).
- **NLV (Net Liquidity Value)**: 淨清算價值 = $Cash Balance + Portfolio Value$
- **Leverage Ratio**: $TNV / NLV$ (若 NLV $\le 0$ 則為 $\infty$)。

### 5. 資產快照流程 (Asset Snapshot Flow)

位於 `AnalyticsService` -> `SnapshotRecorder`，由 `SchedulerService` 或 CLI 觸發：

1. **數據獲取**: 從 `ITransactionRepository` 取得當前持倉與現金流。
2. **行情刷新**: 透過 `MarketDataService` 獲取最新的標的價格。
3. **指標計算**: 執行 `LeverageCalculator` 取得 NLV、TNV 與槓桿比率。
4. **持久化**: 呼叫 `SqliteSnapshotRepository.save_snapshot` 記錄時間序列數據。

### 6. 損益計算算法 (PnL Calculation Algorithm)

位於 `AnalyticsService` -> `PnLCalculator`，採用 **加權平均成本法 (Weighted Average Cost)**：

- **買入 (BUY)**: `new_avg_cost = ((old_qty * old_avg_cost) + (buy_qty * buy_price) + fees) / (old_qty + buy_qty)`
- **賣出 (SELL)**:
  - `realized_pnl = (sell_price - avg_cost) * sell_qty - fees`
  - *Note*: 賣出不改變平均成本，僅減少庫存量。
- **未實現損益 (Unrealized PnL)**: `(current_price - avg_cost) * current_qty`

### 5. NFR

- **響應時間**: P95 本地延遲 < 500ms (不含 LLM)。
- **並發**: `ThreadPoolExecutor` 支援 50+ 標的並行分析。

### 6. 預期效益與成果 (Expected Outcomes)

- **商業價值 (Business Value)**: 將散亂的 API 邏輯收攏至統一的 38 個 Service 節點中，大幅提升了程式碼復用率。開發者可透過這份「功能型錄」在 1 天內即插即用完成新業務功能的組合。
- **性能指標 (Performance Target)**: 確保 `AnalyticsService` 與 `MarketDataService` 等核心路徑 P95 響應延遲小於 500 毫秒，支撐多 Agent 併發讀取。

---

<a id="en"></a>

## 🇺🇸 Service Layer Blueprints (v3.6)

### 1. Architecture

- **Model-Service Decoupling**: Services interact with Pydantic models, never raw SQL.
- **Provider Aggregation**: Multiple data sources under a single `MarketDataService`.
- **Factory Pattern**: `BrokerFactory`, `MemoryFactory`, `AgentFactory` for runtime abstraction.

### 2. Service Categories (38 Services)

- **Data & Market** (5): MarketData, Fred, Search, Browser, SupplyChain
- **Multi-Broker & Trading** (6): BrokerFactory, Etoro, Futu, IBKR, PortfolioAggregator, AutomatedTrading
- **Agent Engine** (8): Workflow, TaskPlanning, HR, Refinement, Evaluation, Attribution, ExperienceReplay, UserFocus
- **Monitoring & Verification** (3): Sentinel (4D Multi-Trigger + Weighted Risk Keywords), Council, Verification
- **Persistence** (6): Memory, MemoryFactory, Transaction, Ingestion, **RiskKeyword**, **RiskKeywordService (v4.4: 3-source discovery)**
- **UI Support** (6): Analytics (**Leverage Engine v3.6**), Dashboard, Performance, Settings, Theme (**v4.3 Unified: 22 tokens, OS auto-detect, WCAG AA**), Backtest
- **Interaction & Notifications** (5): Scheduler, Notification, NotificationFilters, Reporting, Webhook

### 3. Performance

- **Local Latency**: < 500ms (P95).
- **Throughput**: 50+ tickers in parallel.

### 4. Expected Outcomes

- **Business Value**: Centralizes disparate APIs into 38 cohesive service nodes, maximizing code reusability. Developers can leverage this 'feature catalog' to compose new business functions rapidly.
- **Performance Target**: Ensures P95 response latency under 500ms for core paths like `AnalyticsService` and `MarketDataService` to support high-concurrency Agent reads.

## 🔗 Bidirectional Links

- **Architect View**: [System Landscape](系統全景圖-System-Landscape)
- **Dev Guide**: [Local Dev Setup](環境設定與本地開發-Environment-Local-Dev)
- **Patterns**: [Design Patterns Intro](設計模式導讀-Design-Patterns-Intro)
- **Broker Guide**: [Broker Integration](券商整合指南-Broker-Integration-Guide)
