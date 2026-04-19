# 工程實作標準 (Engineering Standards)

本文件統合了本專案在開發、測試與資安上的最高指導原則，確保代碼具備高質量、高安全性與高可維護性。

---

## 1. 開發環境要求 (Environment Requirements)

- **Python 版本**: 強制要求使用 **Python 3.10+**。所有新增代碼與依賴項必須與 3.10+ 兼容。
- **依賴管理**: 建議使用 `uv` 或 `pip` 搭配 `requirements.txt` 並鎖定版本。

## 2. 代碼品質規範 (Coding Standards)

本專案遵循 **Google Python Style Guide**，並針對 AI Agent 與混合儲存場景進行擴充。

### 2.1 基本格式 (Basics)

- **縮進**: 統一使用 **4 個空格**。
- **行寬**: Soft limit 100, Hard limit 120。
- **雙語註解 (Bilingual Comments & Docs)**: 遵循多人協作與開源標準 (Best Practice for Collaborative Development)，所有註解、函數說明 (Docstrings) 必須包含 **英文 (上)** 與 **繁體中文 (下)**。英文作為國際共通語境，中文輔助快速理解業務邏輯。

### 2.2 混合儲存策略 (Hybrid Strategy - Rule #9)

### 1.4 LLM 配置誠信 (LLM Configuration Integrity)
- **禁止硬編碼**：嚴禁在代碼、Prompt 或 Skill 指令中寫死任何特定的模型名稱（如 `gemini-2.0-pro`）或 `BASE_URL`。
- **動態解析**：所有 LLM 調用必須通過 `ResilientLLMPipeline` 或 `LLMGateway`，並由 `TierSpec`（DB 綁定）動態解析模型。
- **Fallback 邏輯**：系統應優先從 `llm_tier_bindings` (DB) 選取，若無則降級至 `settings` table (Legacy)；若皆無則必須拋出明確錯誤，而非嘗試猜測預設模型。

[詳細配置範例與優缺點比較，請參閱《混合儲存架構指南》](混合儲存架構-Hybrid-Storage-Architecture)

- **ORM Admin Layer**: 針對 `User`, `Settings`, `Logs` 等管理類實體，強制使用 **SQLAlchemy ORM** 以提升開發效率。
- **Raw SQL Performance Layer**: 針對 `Transactions`, `MarketData`, `pgvector` 等大數據或高效能場景，強制使用 **Raw SQL (SQLAlchemy Core)** 以利精確優化。

### 2.3 Agent 初始化設計 (Kwargs Handling)

- **避免參數重疊 (Avoid Keyword Collisions)**: 在 Agent Swarm 的繼承體系中，若要擷取參數傳遞給明確定義的 `super().__init__` 欄位，強制使用 `kwargs.pop("key", default)` 而非 `.get()`，以防 `**kwargs` 展開時引發 Python 關鍵字多重賦值錯誤 (`multiple values for keyword argument`)。

### 2.4 上下文傳遞與 Agent 委派原則 (Context Propagation & Delegation)

- **避免隱式丟失上下文 (Avoid Silent Context Drops)**: 當不同組件間傳遞 Prompt 變數（如 `msg_prefix`, `directive`）時，必須確保從進入點 (Entry Service) 確實傳遞至最終的系統提示渲染字典 (`final_context` -> `Jinja2 Template`) 中。進行多層呼叫時，需建立測試或明確走查機制，防止指令被中途丟棄。
- **智能邏輯下放 (Push-down Intelligence)**: 當系統需要對事件進行複雜判斷或分類時，如果體系中已有專職此務的分類 Agent (如 `SentinelAgent`)，**嚴禁**在 Service 層中倒退使用脆弱的字串比對 (`string matching`) 或寫死規則 (Hard-coded heuristics)。必須修改 Agent 的 Prompt，強制其以標準化 JSON (如 `{"trigger_type": "news"}`) 輸出邏輯分支結果交給 Service 判斷。
- **後續行動技能化 (Skillification of Post-Actions)**: 針對跨模組通用的後續行動（例如背景深度研究、萃取重點寫入記憶庫），嚴禁並寫在發起端方法內當成 Private Methods。必須將其封裝為獨立的 **Skills** (位於 `agents/skills/` 下的 `skill.yaml` 與 `impl.py`)，並透過 `SkillLoader` 統一調度，落實 DRY (Don't Repeat Yourself) 原則。

---

## 2. 測試規範 (Testing Standards)

### 2.1 測試金字塔 (Testing Pyramid)

- **單元測試 (Unit Tests)**: 佔比 70%。嚴禁出現網路、資料庫或文件 I/O，必須完全 Mock。
- **整合測試 (Integration Tests)**: 佔比 20%。驗證 Service 與 Repository 間的契約（可用 In-memory SQLite）。
- **端到端測試 (E2E Tests)**: 佔比 10%。僅針對核心 CLI/Workflow，模擬真實用戶行為。

### 2.3 環境確定性 (Environment Determinism)

- **環境隔離**: 單元測試嚴禁依賴主機或 CI 環境變數（如 `AI_PROVIDER`, `API_KEY`）。
- **強制 Patch**: 所有涉及環境變數的邏輯必須在測試中使用 `unittest.mock.patch.dict(os.environ, ...)` 進行明確模擬，確保測試在任何機器上執行的結果完全一致。

### 2.4 初始化與微服務測試 (Initialization & Lifespan)

- **資料庫依賴初始化 (DB Table Creation)**: 執行直接使用 Raw SQL 的 SQLite In-Memory 測試前，必須先手動實例化對應的 DB Repository (例如 `AlchemyAgentRepository()`)，確保 `table` 正確建立。
- **FastAPI 啟動隔離 (Lifespan Mocking)**: 測試具備 `lifespan` 事件的 FastAPI App 之前，必須在 Fixture 中完整使用 `patch` 蓋掉所有具備狀態的服務 (例如 `SettingsService`, `InteractionService`)，防止啟動崩潰導致組件 (如 MCP Tools) 載入不完全。

### 2.2 覆蓋率指標 (Coverage Targets)

- **總覆蓋率**: 強制 > 70%，目標 **> 75%**。
- **核心邏輯 (Services)**: 必須 > 80%。
- **錯誤處理**: 必須達到 100% 覆蓋。

### 2.3 語義測試與 Prompt 版本控管法 (Semantic Testing & Versioning - Phase 6)

隨著 Agent 生成內容不可預測性增加，傳統的字串精確比對會導致測試極度脆弱。

- **語義測試標準 (Semantic Evaluation)**: 針對 Agent 生成的自然語言或投資策略，必須優先使用 `tests/utils/semantic_judge.py` 中的 `assert_semantic_match` 方法。該方法透過 Fast Model 判斷生成內容是否符合預期意圖，而非字面匹配。
- **提示詞版本控管 (Prompt Versioning)**: 所有用於 `ConversationAgent` 的核心 Prompt Template 必須存放於 `src/prompts/` 目錄下，嚴禁硬編碼 (Hard-coded) 於類別方法中。每個 Prompt 應具備版本標籤 (如 `v1.0`) 並記錄於 `WISDOM_VAULT` 的 `meta` 欄位中，以便追蹤對應 LLM 表現的演進。

### 2.5 偵錯與日誌原則 (Debugging & Logging Principle)

- **Log First, Code Second**: 當遇到無法確定根源的問題 (Undefined Behavior, Auth Loops, Unexpected Crashes) 時，**嚴禁盲目猜測或直接改動業務邏輯進行檢核**。
- **動態插點 (Dynamic Instrumentation)**: 必須優先使用 `logger.debug()` 甚至 `logger.error()` 在關鍵執行路徑 (Critical Paths) 注入上下文變數與狀態日誌，並從日誌輸出 (Logs Output) 中尋找線索，確立真正的 Problem Statement 後才允許動寫程式碼。

---

## 3. 資安規範 (Security Standards - Rule #11)

### 3.1 基礎設施安全

- **基礎映像檔**: 必須使用 `python:3.11-slim-bookworm` (Docker)，本地開發強制使用 **Python 3.10+**。
- **非 Root 執行**: 所有容器內程序必須以 `appuser` 執行。
- **依賴鎖定**: 嚴禁在 `requirements.txt` 使用無版本號或 `latest` 標籤。
- **二進制相容性**: 核心數據庫 (`numpy`, `pandas`) 必須鎖定主版本號 (Major Version Pinning) 以防止 ABI 不相容 (如 `numpy<2.0.0`)。

### 3.2 數據與 SQL 安全

- **Safe-SQL-Only (Rule #10)**: 所有 Raw SQL 必須使用參數化查詢，嚴禁字串拼接。
- **憑證與參數命名規範 (Naming Standards for Keys & Settings)**:
  - **數據源金鑰 (Data Source Keys)**: 統一使用 `source_{provider_id}_{field_name}` 格式 (Lowercase Snake Case)。例如：`source_polygon_api_key`, `source_fmp_api_key`。
  - **一般應用設定 (General App Settings)**: 統一使用 `{feature_name}_{parameter_name}` 格式 (Lowercase Snake Case)。例如：`notification_line_token`, `ai_trade_threshold`。
  - **嚴禁混用**: 嚴禁在資料庫設定區使用 `UPPERCASE_KEYS` 或 `camelCaseKeys`。
- **憑證讀取原則 (Rule #13)**: 嚴禁硬編碼憑證。生產環境代碼必須優先透過 `SettingsService` 讀取上述標準化金鑰，並支援資料庫加密。

### 3.3 布林值優先標準 (Boolean-First Standard)

- **自動型別校驗 (Type-Safe Toggles)**: 針對所有「啟用類 (Enabled)」或「布林開關 (Toggles)」設定，資料庫 JSON 欄位必須儲存原生 **布林值 (`bool`)**，嚴禁使用 `str("true")` 或 `str("false")` 進行存儲。
- **邊界防禦 (Boundary Defense)**: 在 `MarketDataService`、`SchedulerService` 與 `data_sources_tab.py` 等消費者端，必須使用 `is_enabled = str(val).lower() == "true" if not isinstance(val, bool) else val` 的相容判讀邏輯，以應對舊數據遷移，但寫回資料庫時必須強制轉為 `bool`。
- **API Key 連動校驗**: 指導原則規定，若「資料源啟用 (Source Enabled)」為 `True` 但對應之「API Key」缺失，則消費端應主動將其視為 `False` 並跳過，而非崩潰，以確保系統穩定性。

### 3.4 加密規範 (Cryptographic Standards)

- 嚴禁使用 `MD5` 或 `SHA1` 進行任何具備安全性意涵的雜湊 (Hashing)。
- 所有信號 ID (Signal ID) 或 實體識別碼 (Entity IDs) 生成必須使用 **SHA256**。
- **使用者認證架構 (FastAPI Auth Hub)**:
  - **原則**: 嚴禁在 Streamlit 異步渲染週期內直接進行 OAuth 回調處理或設置 Cookie (極度不穩定)。
  - **流程**: Streamlit (`<a>` tag) → `FastAPI /api/auth/login` → Google OAuth → `FastAPI /api/auth/callback` → `HTTP 302 Redirect` → Streamlit。
  - **前端驗證**: 使用 `st.context.cookies.get(cookie_name)` 同步讀取，透過 `auth_guard` 進行頁面阻斷。Cookie 屬性需設定 `samesite="lax"`。

### 3.5 第三方工具與 Skill 審計 (Third-party Audit)

- **強制審計**：在安裝任何第三方 AI 工具、Plugin、Skill 或 CLI 之前，必須執行 `.agent/skills/audit-plugin` 描述的資安審計流程。
- **審計重點**：嚴禁安裝具備隱藏遙測 (Telemetry)、未授權 Outbound 呼叫、硬編碼外部金鑰或試圖寫入系統敏感目錄的工具。
- **記錄留存**：審計結果必須記錄於當次開發對話或對應之 `implementation_plan.md` 中備查。

---

## 4. 專案組織與腳本管理 (Project Organization & Script Management)

為了保持工作區整潔並確保通性工具的可用性，必須遵循以下組織規範：

### 4.1 指令碼存放規範 (Script Locations)

- **`scripts/`**: 僅存放核心工具。包含部署 (Deployment)、維運/CI (Ops/CI) 及開發者設定 (Dev Setup)。
- **`Archive/scripts/`**: 存放一次性遷移 (Migration)、歷史修復 (Fixes) 及臨時診斷腳本。
- **`Archive/verifications/`**: 存放過往開發階段使用的 Ad-hoc 整合驗證腳本。

### 4.2 個人用腳本規範 (Personal Scripts & Gitignore)

- **命名約定**: 所有個人臨時用或開發中尚未成熟的腳本必須遵循以下命名模式以自動被 Git 排除：
  - `scripts/personal_*` (例如：`scripts/personal_test_api.py`)
  - `scripts/tmp_*`
  - `*_local.py`
- **通性工具**: 具備通用性且需於團隊/CI 間共享的工具（如 `run_full_verification.sh`, `seed_data.py`）嚴禁使用上述個人命名模式，且必須由 Git 追蹤。

---

## 5. 數據源實作準則 (Data Source Guidelines)

為了維護數據源矩陣 (Data Source Matrix) 的透明度與一致性，所有新數據源的開發必須遵循以下原則：

### 5.1 配置透明化 (Configuration Transparency)

- **強制連結**: 必須在 `src/config/data_source_matrix_config.py` 中註冊 `url` 欄位，指向官方 API 取 Key 頁面或文檔。
- **中文描述**: `desc` 欄位必須以繁體中文說明該來源在系統中的具體「業務價值」(例如：用於內線交易異動監控)。

### 5.2 實作封裝與隔離

- **基底繼承**: 所有 Provider 必須繼承 `BaseDataProvider` 介面。
- **敏感資訊處理**: 嚴禁使用 `os.getenv`。必須透過 `SettingsService` 讀取 API Key，確保在 Dashboard 中可動態配置且具備遮蔽能力。

### 5.3 驗證要求

- **關鍵路徑測試**: 必須包含網路異常、API 限流 (Rate Limit) 及無數據回傳等反向情境測試。
- **文件同步**: 完成實作後，必須更新 Wiki 數據源矩陣文檔。

---

## 6. DB 集中管理與 UI 操作原則 (DB-Managed Settings)

- **DB 優先**: 所有可啟用的功能、系統閾值、API 金鑰或管道配置，應優先存放於資料庫（`settings` 表）中，而非寫死在代碼或全域環境變數中。
- **UI 管理**: 所有存放於 DB 的設定，必須在 Dashboard 中提供對應的介面進行操作（如 `SettingsService` 整合），確保非開發人員亦可安全調整系統行為。
- **動態載入**: 系統在啟動或執行期應透過 `SettingsService` 動態獲取配置，確保變更能即時生效（或僅需服務重啟）。
