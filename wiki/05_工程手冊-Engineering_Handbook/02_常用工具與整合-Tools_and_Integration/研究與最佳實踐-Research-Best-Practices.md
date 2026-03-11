### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-17 | v4.0.0 | **DB Evolution**: Evaluation of PostgreSQL JSONB vs NoSQL & pgvector. | Neo |
| 2026-02-15 | v3.6.1 | **Multi-Tier Agent Architecture**: Role × 3-Tier (Advanced/Smart/Fast) 並行模式 | Neo |
| 2026-02-15 | v3.6 | Added Kimi K2.5 Swarm, OpenClaw Channel Adapters, UI Navigation research | Neo |
| 2026-02-14 | v3.5 | Initial Release | Neo |

---

<a id="zh"></a>

## 🇹🇼 研究與最佳實踐 (Intelligence Research)

本文件匯整 AI 投資領域的行業標準與學術研究，並說明本系統如何將其轉化為具體的代碼實作。

### 1. 代理反思模式 (Reflection Pattern)
**理論**: 代理不僅執行任務，更需具備自我批判與輸出修正的能力，這在容錯率極低的金融領域至關重要。
- **項目實作**: `EngineerAgent` 會針對歷史投資決策執行 Reflection，分析預測與真實走勢的偏差。
- **參考**: Andrew Ng 的 *Agentic Workflow* 模式。

### 2. 金融級 RAG (Financial Retrieval-Augmented Generation)
**理論**: 解決 LLM 知識截止與幻覺問題。金融 RAG 強調數據的時效性（Real-time）與精確性。
- **項目實作**: [MarketDataService](服務層開發指南-Service-Layer-Blueprints) 通過聚合 Polygon、FRED 等多源 API，實現「動態上下文注入」，而非僅依賴靜態向量庫。
- **最佳實踐**: 使用 Metadata-based 聚類以提升檢索準確度。

### 3. DSPy 與程序化 Prompt 優化
**理論**: 捨棄脆弱的手寫 Prompt，改用程序化定義的 Signature 與 Optimizer。
- **項目實作**: 詳見 [提示詞工程規範](提示詞工程規範-Prompt-Engineering-Specs)。系統利用 `dspy.GEPA` 等技術，自動優化專家 Agent 的指令語法。

### 4. 零信任代理安全性 (Zero-Trust Agent Security)
**理論**: 每一個 Agent 與工具的互動都必須經過驗證，防止惡意指令注入。
- **項目實作**: [MCP Server](底層通信協議-Agent-Mesh-Protocols) 實現了權限隔離，Agent 只能透過受控的 API Endpoint 訪問工具。
- **最佳實踐 (Tool Gating)**: 實施工具准入機制。在加載 Skill 前驗證 OS 依賴（如 `docker`, `curl`），若環境不具備則禁止該工具加載以防運行崩潰。
- **最佳實踐 (Regex Guard)**: 建立提示詞層級的正則守衛，即時攔截並封鎖包含 `rm -rf`, `sudo` 等高危代碼的 LLM 輸出。

### 5. 行業工作流模式 (Industry Workflow Patterns)
**參考**: Bloomberg & BlackRock (Aladdin)
- **Planner-Executor 分離**: 模仿 Bloomberg 的架構，由一個規劃代理 (Planner) 拆解複雜任務，多個執行代理 (Executor) 平行運作。
- **Supervisor 模式**: BlackRock 的 Aladdin Copilot 採用此模式，由 Supervisor 協調多個專任 LLM，這與本系統的 CIO Agent 邏輯高度契合。
- **MCP 標準化**: 系統已導入 Model Context Protocol，這與 Bloomberg 推動的開放工具連接標準一致，確保跨平台工具的可組合性。

### 6. 智能體集群與併發優化 (Agent Swarm & Multi-Tier Parallelism)
**理論**: 模仿 Kimi K2.5 的 **Agent Swarm** 框架 + **Role × Multi-Tier Agents** 並行執行架構。
- **項目實作**: 詳見 [產品演進藍圖](產品演進藍圖-Evolutionary-Roadmap)。系統採用 Orchestrator-Multi-Tier 模型：
  - 每個 Role (如 `FundamentalAgent`) 下有 N 個 Sub-Agents (如 `RevenueExtractor`)
  - 每個 Sub-Agent 有 **3 個層級**並行執行：
    - 🚀 **Advanced** (戰略): 深度分析、關鍵決策 (Claude Opus, Gemini Pro)
    - 🧠 **Smart** (智囊): 平衡質量與速度 (GPT-4, Gemini Pro)
    - ⚡ **Fast** (前鋒): 快速初篩、探索性研究 (Gemini Flash, GPT-3.5)
  - 例: `FundamentalAgent` → 3 Sub-Agents × 3 Tiers = **9 並行執行**
- **最佳實踐**: 
  - Progressive Output: Fast tier 30s 輸出初結論 → Smart 60s 補充 → Advanced 120s 深度洞察
  - Voting/Fusion: 三層級投票或加權融合決定最終輸出
  - Cost Optimization: 70% 任務由 Fast tier 承擔，僅 20% 需要 Advanced tier
  - 使用「關鍵路徑」指標優化端對端延遲，優先處理最慢的 Sub-Agent 分支。

### 7. 確定性 UI 導航研究 (Deterministic UI Navigation)
**研究**: 在 Streamlit 等動態 UI 框架中，頁面順序往往受載入速度影響。
- **最佳實踐**: 使用 **數字前綴 (02_..., 03_...)** 強制執行側邊欄順序。這能確保用戶形成穩定的心理模型 (Mental Model)，避免導航項隨機跳動。

### 8. 管道適配器模式 (Channel Adapter Pattern)
**參考**: OpenClaw Architecture
- **項目實作**: `NotificationService` 作為單一入口，調用實作了 `IChannelAdapter` 的多元管道。這確保了當未來需要整合 Telegram 或 Slack 時，無須修改 Sentinel 或 Workflow 原始碼。
- **最佳實踐**: 使用「管道過濾 (Channel Filtering)」機制。日常報告預設走 Email/Web，而 CRITICAL 等級的風險警報則強制觸發 LINE 推送。

### 9. 集中式 UI 模擬策略 (Centralized UI Mocking)
**研究**: 測試 Streamlit 應用的主要挑戰在於模組污染與 `@st.cache_data` 的狀態殘留。
- **最佳實踐**: 在 `tests/conftest.py` 中建立全域 Mock。透過 `sys.modules["streamlit"]` 注入具備 `.clear()` 方法的虛擬裝飾器，確保測試環境的乾淨啟動。

---

<a id="en"></a>

## 🇺🇸 Research & Best Practices

### 1. Reflection Pattern (Andrew Ng)
- **Concept**: Self-correcting workflows to minimize hallucinations.
- **Implementation**: The `EngineerAgent` serves as the primary evaluation engine.

### 4. Agent Swarm & Multi-Tier Parallelism (Kimi K2.5 + v3.7)
- **Critical Path Optimization**: Shifting from total steps to "Critical Steps" metrics to minimize end-to-end latency.
- **Role × Multi-Tier Architecture**: Each role (e.g., `FundamentalAgent`) has N sub-agents, each executing in **3 parallel tiers** (Advanced 🚀 / Smart 🧠 / Fast ⚡):
  - Example: `FundamentalAgent` → 3 Sub-Agents × 3 Tiers = 9 parallel executions
  - Progressive output: Fast tier (30s) → Smart (60s) → Advanced (120s)
  - Fusion via voting or weighted aggregation for final decision
- **Decoupled Orchestration**: Using a stateful orchestrator with frozen, specialized multi-tier sub-agents for stable convergence.

### 5. Frontend & Reliability Research
- **Deterministic Sidebar**: Enforcing page order via numeric prefixes to stabilize the User Mental Model in Streamlit.
- **Centralized UI Mocking**: Global `sys.modules` patching for clean, state-free unit testing of reactive frontend frameworks.

### 6. Channel Abstraction (OpenClaw)
- **Adapter Logic**: Decoupling the reasoning engine from delivery channels (LINE, Web) via standardized command parsing and formatting layers.

### 10. Search & NoSQL Evaluation
**Research**: Assessment of adding ElasticSearch or MongoDB for the v3.9 refactor.
- **Best Practice**: **PostgreSQL JSONB** is sufficient for current semi-structured configs and tag data.
- **Implementation**:
    - ✅ **pgvector** meets 90% of vector search and semantic retrieval needs.
    - ⚠️ **ElasticSearch** is categorized as a Phase 2 option, to be introduced only when event logs exceed 1M/month or advanced synonym search is required.
    - ❌ **MongoDB** is not recommended due to lack of ACID necessity given Postgres's native JSONB flexibility.
- **Reference**: `plans/nosql-elasticsearch-evaluation.md`.

## 🔗 Bidirectional Links
- **Product View**: [Evolutionary Roadmap](產品演進藍圖-Evolutionary-Roadmap)
- **Technical Specs**: [Future Roadmap Specs](未來演進規格-Future-Roadmap-Specs)
- **Engineering Handbook**: [Prompt Engineering Specs](提示詞工程規範-Prompt-Engineering-Specs)
- **Architect View**: [Architectural Philosophies](架構哲學-Architectural-Philosophies)
