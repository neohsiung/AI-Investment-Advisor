# 智能體大腦演進與 OpenClaw 實踐計畫 (Agentic Brain Evolution & OpenClaw Implementation Plan)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-28 | v1.0 | Initial release based on OpenClaw/Clawdbot architecture analysis | AI Agent |

> **版本 (Version):** v1.0
> **狀態 (Status):** Proposal / Planning Phase

---

## 一、 現況分析與優化痛點 (Current State Analysis)

在我們目前的 AI 投資顧問 (AI Investment Advisor) 架構中，雖然已經導入了 PostgreSQL (`pgvector`) 作為 RAG (檢索增強生成) 記憶層，以及 Redis 作為短期會話 (`ResponseCache`) 緩衝，但我們在「自主學習能力」、「長文脈切斷」以及「維護透明度」上，依然面臨與大多現存 LLM 應用一樣的瓶頸。

### 現況痛點對比 OpenClaw 設計：

1. **記憶的黑盒子 (Opaque Memory DBs)**
   - **現況**: 所有的長期記憶、使用者偏好、金融工具定義都被序列化塞進 PostgreSQL 或 Redis 中，開發者或使用者無法「一目了然」看到 AI 到底知道什麼。
   - **OpenClaw 解法**: **純文字配置即大腦 (Files as Source of Truth)**。將長期記憶 (`MEMORY.md`)、任務心跳 (`HEARTBEAT.md`)、人格 (`IDENTITY.md`) 與技能配置都透過 Markdown 留存在本地，達成絕對的透明度與**最高度的代碼生成友善性 (AI-Support First)**。

2. **RRF 排序導致絕對信號喪失 (Flattened Signal in RRF)**
   - **現況**: 在執行 Hybrid Search 時，傳統常依賴倒數排名融合 (Reciprocal Rank Fusion; RRF) 將向量與全文檢索引擎的分數打平為排名。這會導致語意極度相近 (Cosine Similarity 0.98) 的結果，與一般相近的結果 (0.71) 沒有數學權重上的差異。
   - **OpenClaw 解法**: 採用**加權分數融合 (Weighted Score Fusion)** (e.g., `0.7 * Cosine + 0.3 * BM25`)，確保冰冷的股票代號或關鍵錯碼 (FTS) 與極度相關的語意背景，能得到最高度且真實的召回權重。

3. **被動的排程任務與盲目通知 (Passive Cron & Blind Alerts)**
   - **現況**: 排程任務 (如早晨寄送每日財報) 是盲目的、硬編碼的 cron job，不具備上下文感知能力。只要觸發，就會通知使用者，極易造成「通知疲勞」。
   - **OpenClaw 解法**: **主動心跳機制 (Active Heartbeat)**。系統每 30 分鐘向主 Session 靜默注入 `HEARTBEAT.md` 檢查任務。Agent 使用上下文判斷是否有事；沒事則回傳 `HEARTBEAT_OK` 讓 Gateway 丟棄訊息，達到**「無感守護、有感示警」**的最高標準。

4. **長對話 Token 溢出導致斷片 (Context Overflow Amnesia)**
   - **現況**: 對話一旦到達 LLM Token 上限，常用的作法是直接切除最早的記憶，導致「斷片」，高難度決策任務失敗。
   - **OpenClaw 解法**: **壓縮前記憶沖洗 (Pre-Compaction Memory Flush)**。在逼近 Token 儲備底線 (Reserve Limit) 時，系統會強迫注入一次無感知的 Agent Turn 讓其主動將重要進行中狀態寫回 `MEMORY.md` 或是 PostgreSQL 中，保障分析思路的持久性。

---

## 二、 實踐架構圖 (Architecture Blueprint)

```mermaid
flowchart TD
    %% 用戶輸入層
    User([User / Messaging Channel]) <--> Gateway[Multi-Channel Gateway]
    
    %% 主進程
    subgraph Agentic Orchestrator [Agent System (Temporal Workflow + Gateway)]
        Gateway <--> SessionManager[Session Manager & Lane FIFO]
        Heartbeat[Heartbeat Scheduler \n(Every 30m)] -.->|Injects Silent Turn| SessionManager
    end

    %% 智能體與記憶庫交互
    subgraph AI Engine [LLM Core (Agents)]
        SessionManager <--> ReAct[ReAct / Workflow Loop]
        ReAct <--> Tools((External APIs \n Yahoo / Fred))
    end
    
    %% 混合記憶架構
    subgraph Storage [Three-Tier Agentic Memory]
        ReAct <--> Workspace[<b>Workspace Directory (Markdown)</b>\n- IDENTITY.md\n- HEARTBEAT.md\n- MEMORY.md\n- skills/SKILL.md]
        ReAct <--> DB[(PostgreSQL + pgvector\n<b>Weighted Score Fusion</b>\n 0.7 Vector + 0.3 BM25)]
        ReAct <--> Redis[(Redis Cache)]
    end
    
    %% 安全隔離機制
    DB -.-> |Semantic Knowledge| ReAct
    Workspace -.-> |Private Auth Only| ReAct
```

---

## 三、 四階段實踐演進計畫 (4-Phase Actionable Implementation Plan)

為確保現有服務的穩定，我們將遵循**領域驅動設計 (DDD)**，對服務進行漸進式重構。此計畫高度符合 **GCWAF (卓越營運)** 與我們的 **Rule #15 (AI-Support First)** 哲學。

### Phase 1: 知識庫 Markdown 結構化 (Markdown Workspace Setup)
*   **目標**: 將黑盒子的 Persona (人格設定)、LLM Prompts 與長時間不變的技能規則，抽取至目錄管理的 Markdown 文件。
*   **任務清單**:
    *   [ ] 在專案建立 `~/.agent/workspace/` 與 `skills/` 路徑。
    *   [ ] 將現行 `prompt.py` 中硬編碼的 System Prompts 解耦為 `IDENTITY.md` 與 `SOUL.md`。
    *   [ ] 將使用者偏好存入唯讀在私人通道的 `MEMORY.md` 中。
    *   [ ] **驗收標準**: `AgentLLMProvider` 改由掛載 `workspace/` 底下的文本組裝 `SystemMessage`。修改完畢可輕易在 GitHub PR 單中由人類進行肉眼 code review。

### Phase 2: 混合搜索加權改造 (Hybrid Search Fusion Override)
*   **目標**: 升級我們基於 PostgreSQL/pgvector 的 Hybrid Search，揚棄 RRF，改為「加權分數融合 (Weighted Score Fusion)」。
*   **任務清單**:
    *   [ ] 改寫 `HybridMemory` 或 `search_service.py` 裡的 Postgres SQL 語句。
    *   [ ] 在查詢時引入權重公式 `finalScore = (vectorWeight * cosineSimilarity) + (textWeight * BM25Score)` (預設 `0.7 / 0.3`)。
    *   [ ] **驗收標準**: 在提供錯字或明確指定股票代號 `#AAPL` 時，即便語義不相近，也能因高達 30% 分數的 BM25 強制命中而被喚醒。

### Phase 3: 主動心跳與靜默示警 (Active Heartbeat Implementation)
*   **目標**: 取代依賴 Cron 定時發送「盲目報表」的架構。
*   **任務清單**:
    *   [ ] 在 Temporal 工作流或主 API 中，刻劃一個 `HeartbeatScheduler` (每 30 分鐘自動對主 Agent Trigger 一次)。
    *   [ ] 把檢查清單寫在 `workspace/HEARTBEAT.md` (e.g., 檢查大盤漲跌、持股重大新聞)。
    *   [ ] 實作過濾器 (ACK Filter): 若 LLM 推理回傳 `HEARTBEAT_OK`，則在 `notification_service.py` 直接廢棄不推播；否則才轉發 LINE / Discord。
    *   [ ] **驗收標準**: 使用者不再每天收到例行「無異狀」公報，但當標的暴跌時，能立刻收到 Agent **連同處理對策** 一起整理好的主動通知。

### Phase 4: Token 安全墊與壓縮前沖洗 (Pre-Compaction Memory Flush)
*   **目標**: 終結高長度財報會議分析中，Token Overflow 造成的斷片問題。
*   **任務清單**:
    *   [ ] 於 `MemoryService` 設置 `reserveTokensFloor` (e.g., 4,000 token 預備空間)。
    *   [ ] 當 Session 空間即將過載，自動插入一條不可見 (Silent) 的任務要求 LLM：「將目前重要思路持久化記錄回 PostgreSQL，並回傳 NO_REPLY」。
    *   [ ] 在收到 `NO_REPLY` 後，執行原有的 80% 摘要壓縮清理。
    *   [ ] **驗收標準**: 無論對話延長多少週，過去被「提煉」的知識仍可從持久層被完美拉出，不會中斷。

---
> 註：此演進計畫將在下一個 Sprint 啟動，請工程師與 AI Agent 將精力先集中在 **Phase 1** 與 **Phase 2** 的基底架構改造。
