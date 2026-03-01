# 前端架構與 UX 層 (Frontend & UX Layer)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-26 | v4.3 | **Unified Theme System**: OS auto-detection (`prefers-color-scheme`), 22 design tokens (semantic colors, shadows, gradients), WCAG AA dark mode. | Antigravity |
| 2026-02-21 | v4.2 | **Page & Tab Census Update**: Updated page numbering (02_~07_), added channel_tab & data_sources_tab (11 tabs total). | Antigravity |
| 2026-02-14 | v3.5 | Full rewrite — 6 pages, 9 settings tabs, BasePage pattern | Neo |
| 2024-01-04 | v1.0 | Initial Release | Neo |

---

<a id="zh"></a>

### 1. 視圖與服務分層架構 (View-Service Layered Architecture)

為了提高可維護性與職責分離，本系統採用 **View-Service 分層設計**。

```mermaid
graph TD
    Page[""UI View Layer (Streamlit Pages")"] -->"|Calls| Service["""Service Layer (Orchestration")"]
    Service -->"|Uses| Repo["""Repository Layer (Data Access")"]
    Service -->"|Calls| Ext[""External APIs / Agents"]
    Service -->"|Uses| Calc["""Domain Logic (Calculators")"]
```

#### 1.1 職責定義 (Roles & Responsibilities)

| 層級 | 位置 | 職責 |
| :--- | :--- | :--- |
| **View Layer** | `src/pages/`, `src/dashboard.py` | UI 渲染、佈局、使用者輸入、Session State。 |
| **Service Layer** | `src/services/` | 數據編排、業務邏輯、快取策略、錯誤處理。 |
| **Repo / Infra** | `src/data/`, `src/utils/` | 數據 CRUD、外部 API 封裝、技術工具集。 |
| **MCP Layer** | `src/mcp_service/` | 跨 Agent 工具共享、A2A 通訊 (FastAPI)。 |

---

### 2. 頁面管理與基類 (Page Architecture)

#### 2.1 BasePage 樣板方法 (Template Method)
所有頁面繼承 `BasePage` (`src/utils/page_base.py`)，強制執行一致的生命週期：

```mermaid
graph LR
    Init[""__init__(")"] -->"Config["""set_page_config(")"]
    Config -->"Auth["""check_auth(")"]
    Auth -->"Run["""run(")"]
    Run -->"Render["""render(") — 子類覆寫"]
```

- **`__init__`**: 各頁面自行實例化所需 Service (Composition Root 模式)。
- **`run()`**: 基類統一的進入點，處理錯誤邊界與頁面標題。
- **`render()`**: 子類覆寫，實作業務 UI 邏輯。

#### 2.2 頁面清單 (Page Registry)

| 頁面 | 檔案 | 功能 |
| :--- | :--- | :--- |
| 總覽 (Dashboard) | `app.py` | NLV、Cash、Leverage、ROI、持倉、資產配置、券商分佈。 |
| 績效追蹤 | `pages/02_Portfolio_Performance.py` | 歷史淨值走勢、績效分析。 |
| 分析報告 | `pages/03_Analysis_Reports.py` | 日報/週報瀏覽與下載。 |
| 顧問對話 | `pages/04_Advisor_Chat.py` | 與 CIO Agent Swarm 互動。 |
| 資料管理 | `pages/05_Data_Management.py` | 手動輸入、CSV 匯入 (Atomic)、交易紀錄管理。 |
| 系統設定 | `pages/06_Settings.py` | 11 Tab 設定中心 (見下節)。 |
| UI 風格指南 | `pages/07_UI_Styleguide.py` | 設計系統元件展示與風格規範。 |

#### 2.3 設定頁 Tab 架構 (Settings Tabs — 11 Tabs)

| Tab | 檔案 | 功能 |
| :--- | :--- | :--- |
| 交易與風控 | `trading_tab.py` | Broker 選擇、Kill Switch、板塊曝險、每日交易上限。 |
| AI 設定 | `ai_config_tab.py` | LLM 模型選擇、溫度、Token 上限。 |
| 排程 | `scheduler_tab.py` | Cron 排程設定、日報/週報自動化。 |
| 報告試跑 | `report_dry_run_tab.py` | 單次報告生成測試 (不寄送)。 |
| Agent 沙盒 | `agent_playground_tab.py` | 單一 Agent 互動測試。 |
| Prompt 管理 | `optimization_tab.py` | 查看/編輯 Agent Prompt、觸發 DSPy 優化。 |
| HR 協議 | `hr_protocol_tab.py` | 360° 互評記錄查看。 |
| 外觀 | `appearance_tab.py` | Dark/Light 主題切換（含 OS 自動偵測 `prefers-color-scheme`）。 |
| 儲存 | `storage_tab.py` | 資料庫路徑、備份狀態。 |
| 通道管理 | `channel_tab.py` | 多通路 (LINE/Slack/Email/Telegram 等) 連線設定與驗證。 |
| 資料來源 | `data_sources_tab.py` | 外部資料源 (Polygon/FMP/FRED 等) API 金鑰與啟用管理。 |
| 風險關鍵字 | `risk_keywords_tab.py` | Sentinel 風險關鍵字 CRUD、權重設定與命中追蹤。 |

### 3. UX 流程 (UX Flows)

#### 3.1 儀表板全景 (Dashboard Flow)
```mermaid
graph TD
    Load[進入頁面] -->"Sync[更新 Daily Snapshot]"
    Sync -->"FetchTx[拉取交易紀錄]"
    FetchTx -->"Mkt[獲取即時價格 — 具 TTL=300s 快取]"
    Mkt -->"Calc[執行 Analytics 計算 — 0% 幻覺]"
    Calc -->"Render[渲染指標、持倉表與配置圖]"
```

#### 3.2 顧問對話流 (Advisor Chat Flow)
```mermaid
graph TD
    Input[用戶輸入] -->"CIO[CIO Agent]"
    CIO -->"Dispatch[Dispatch to Research Swarm]"
    Dispatch -->"Agents[Fund/Mom/Macro/Sent 並行]"
    Agents -->"Merge[CIO 交叉驗證]"
    Merge -->"Report[返回 Markdown 報告]"
```

### 4. 技術重點 (Technical Highlights)
- **智慧快取 (`@st.cache_data`)**: TTL=300s 降低 API 成本。
- **狀態管理**: `st.session_state` 管理 `user_id`，跨頁面安全隔離。
- **風險提示**: Leverage > 1.5x 黃色警告、> 2.0x 紅色危險。
- **ThemeService**: 統一主題系統 — 22 個 CSS Design Tokens（語意色彩、陰影、漸層）動態注入，支援 OS 自動偵測（`prefers-color-scheme`）與手動切換優先機制。Dark Mode 採用 WCAG AA 對比度優化色彩。

### 5. 預期效益與成果 (Expected Outcomes)
- **商業價值 (Business Value)**: 透過高度解耦的視圖與服務層設計，讓前端儀表板能在極低成本的 Streamlit 環境下，提供近乎原生 App 的專業級對沖基金監控體驗。
- **性能指標 (Performance Target)**: 結合 JIT (即時) 渲染與 300s 智慧快取，確保在切換各個監控 Tab 時的 P99 響應時間小於 2 秒。

---

<a id="en"></a>

## 🇺🇸 Frontend Architecture & UX (v3.5)

### 1. View-Service Layered Architecture
Strict separation of concerns to enhance maintainability and testability.
- **View Layer**: `src/pages/`, `src/dashboard.py` (Streamlit UI).
- **Service Layer**: `src/services/` (Orchestration & Logic).
- **Repo/Infra**: `src/data/`, `src/utils/` (Data Access & Utils).

### 2. Page Architecture
- **BasePage Template Method**: Unified lifecycle (`__init__` → `run()` → `render()`).
- **7 Pages**: Dashboard, Portfolio Performance, Analysis Reports, Advisor Chat, Data Management, Settings, UI Styleguide.
- **11 Settings Tabs**: Trading & Risk, AI Config, Scheduler, Report Dry-Run, Agent Playground, Prompt Management, HR Protocol, Appearance, Storage, Channel Management, Data Sources, Risk Keywords.

### 3. UX Patterns
- **Just-In-Time Calculation**: Metrics computed on-the-fly with current market prices.
- **Risk Highlighting**: Color-coded leverage warnings (1.5x yellow, 2.0x red).
- **Transparent AI**: Agent reasoning displayed alongside raw data.

### 4. Expected Outcomes
- **Business Value**: Delivers an institutional-grade monitoring experience in a cost-effective environment via strict View-Service decoupling.
- **Performance Target**: P99 response time under 2 seconds during tab switching, powered by 300s intelligent JIT caching.

## 🔗 Bidirectional Links
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
- **Data Layer**: [Data & Domain Models](資料與領域模型-Data-Domain-Models)
- **Service Layer**: [Service Layer Blueprints](服務層開發指南-Service-Layer-Blueprints)
- **BasePage Pattern**: [Template Method](設計模式-樣板方法-Template-Method)
