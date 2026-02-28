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

1. **共享且不透明的黑盒子大腦 (Shared Opaque Memory DBs)**
   - **現況**: 目前的記憶被單一系統共享並序列化存入 PG/Redis。缺乏智能體隔離，開發者也無法一目了然看見各個 Agent 的上下文與學習曲線。如果未來需要擴充第 10 個 Agent，系統架構將難以乾淨切割。
   - **OpenClaw 解法**: **多智能體獨立純文本大腦 (Multi-Agent independent files)**。為專案中的 **9個 Agent** 建立完全獨立的 Workspace (如 `~/.agent/workspace/<agentId>`)。長期記憶、人格設定、專屬技能全部依賴檔案隔離。未來新增 Agent 時完美繼承此標準。

2. **RRF 排序導致絕對信號喪失 (Flattened Signal in RRF)**
   - **現況**: Hybrid Search 常依賴 RRF 將向量與全文檢索引擎的分數打平為排名，使語意極度相近 (0.98) 的結果與次等結果 (0.71) 沒有數學權重上的巨大差異。
   - **OpenClaw 解法**: 採用**加權分數融合 (Weighted Score Fusion)** (e.g., `0.7 * Cosine + 0.3 * BM25`)，並導入 **MMR Re-ranking** (最大邊際相關性以防結果過度重複) 與 **Temporal Decay** (時間衰減給予近期記憶高比重)，這套機制需要更嚴密的成本控制來實現。

3. **被動的排程任務與高昂盲目通知 (Passive Cron & Blind Alerts)**
   - **現況**: 盲目排程會不斷消耗 LLM Token 判斷是否有事，如果讓全部 9 個 Agent 都定期甦醒，會造成龐大的 API 成本。
   - **優化解法**: **部分主動心跳與 Webhook 雙軌並存 (Selective Heartbeat & Webhooks)**。只有需要深度宏觀判斷的特務 Agent (如 Sentinel/Captain) 配備每 30 分鐘的主動 `HEARTBEAT.md` 檢查，其餘負責被動計算的 Agent 保留現有低成本的 Webhook 觸發模式，兼顧敏感度與預算。

4. **長對話 Token 溢出導致斷片 (Context Overflow Amnesia)**
   - **現況**: Token 溢出時，傳統作法直接切除最早記憶，導致高難度決策流產。
   - **OpenClaw 解法**: **WAL Protocol 與壓縮前記憶沖洗 (Pre-Compaction Flush)**。在逼近 Token 底線前，不僅強制靜默沖洗，更寫入 WAL (Write-Ahead Logging) 軌跡，保證重要思維狀態如實存入該 Agent 專屬的資料庫，保證不丟失推理脈絡。

---

## 二、 實踐架構圖 (Architecture Blueprint)

```mermaid
flowchart TD
    %% 用戶輸入層
    User([User / Webhooks]) <--> Gateway[Multi-Channel Gateway]
    
    %% 主進程
    subgraph Agentic Orchestrator [Agent System (Temporal Workflow + Gateway)]
        Gateway <--> SessionManager[Session Manager & Lane FIFO]
        Heartbeat[Selective Heartbeat \n(Critical Agents Only)] -.->|Silent Turn| SessionManager
    end

    %% 智能體與記憶庫交互
    subgraph Multi Agent Swarm [9 Independent Agents]
        SessionManager <--> ReAct[Agent 1: Captain]
        SessionManager <--> ReAct2[Agent 2: Sentinel...]
        SessionManager <--> ReAct9[Agent N]
    end
    
    %% 混合記憶架構 (獨立分離)
    subgraph Storage [Independent Brain architecture (Cost Optimized)]
        ReAct <--> Workspace[<b>Workspace: /agent-1/</b>\n- IDENTITY.md\n- HEARTBEAT.md\n- WAL/STATE.md]
        ReAct <--> DB[(PostgreSQL + pgvector\n<b>QMD Sidecar Logic</b>\n 0.7 Vector + 0.3 BM25\n + Temporal Decay\n + MMR Re-ranking)]
        ReAct <--> Redis[(Redis Cache)]
    end
    
    %% 安全隔離機制
    DB -.-> |Semantic Knowledge| ReAct
    Workspace -.-> |Private Auth Only| ReAct
```

---

## 三、 四階段實踐演進計畫 (4-Phase Actionable Implementation Plan)

為確保現有服務的穩定，我們將遵循**領域驅動設計 (DDD)**，對服務進行漸進式重構。此計畫高度符合 **GCWAF (卓越營運)** 與我們的 **Rule #15 (AI-Support First)** 哲學。

### Phase 1: 九大智能體「獨立大腦」分割 (9-Agent Memory Workspace Setup)
*   **目標**: 將黑盒子的記憶庫拆分為 9 個完全獨立的目錄實體與資料庫結構，未來每增加一個 Agent，均可透過相同的 Template 開箱具備同樣的檢索能力與隔離性。
*   **任務清單**:
    *   [ ] 建立 `~/.agent/workspace/<agent_name>/` 路徑結構 (共 9 組)。
    *   [ ] 為每個 Agent 配置專屬的 `IDENTITY.md`, `SOUL.md` 與獨立的寫入 `MEMORY.md`。
    *   [ ] 確保 RAG 查詢與寫入時，SQL 層面對 `agent_id` 加入強過濾器 (Role-Level Isolation)。
    *   [ ] **驗收標準**: 各自 Agent 學習到的上下文與習慣絕對不會跨界污染。

### Phase 2: QMD 概念導入與進階檢索算分 (Advanced Storage, MMR & Temporal Decay)
*   **目標**: 為求精準召回與成本控制，導入 QMD (Sidecar) 概念來維護向量庫，並升級混合分數演算法。
*   **任務清單**:
    *   [ ] 揚棄 RRF，改寫 Postgres SQL 以 `finalScore = (0.7 * Cosine) + (0.3 * BM25)` 融合搜尋。
    *   [ ] 引入 **MMR (最大邊際相關性)** 來 Re-ranking，過濾完全重複的知識塊。
    *   [ ] 引入 **Temporal Decay (時間衰減)**，確保在相似度相同時，近期的記憶段落獲得加分。
    *   [ ] **驗收標準**: 搜尋結果召回率達 100% 同時具備時間敏感度。

### Phase 3: Webhook 雙軌制與部分主動心跳 (Dual-Track: Heartbeat / Webhooks)
*   **目標**: 大幅降低 API 成本，僅分配算力給需要守望市場變化的特務，剩餘 Agent 從旁待機。
*   **任務清單**:
    *   [ ] 分析 9 個 Agent，僅指定 (例如 Sentinel Agent、Captain Agent) 掛載每 30 分鐘的 `HeartbeatScheduler`，讓它們主動關注市場大盤或重要事件。
    *   [ ] 為另外一批功能單純的 Agent (如 Backtest Agent、Data Prep)，保留現有的低成本 `Webhook` 被動觸發機制，有指令才喚醒。
    *   [ ] 實作過濾器 (ACK Filter): 心跳推論後回傳 `HEARTBEAT_OK` 者直接靜默不推播給外部使用者。
    *   [ ] **驗收標準**: 系統維護了極高的市場敏銳度，但 API 消耗成本精準可控，未產生通知疲勞。

### Phase 4: Token 安全墊與 WAL 狀態寫入 (Pre-Compaction Flush & WAL Protocol)
*   **目標**: 終結高長度財報分析中 Context Token 溢出導致的斷片現象，實作極致的壓縮儲存。
*   **任務清單**:
    *   [ ] 於 `SessionManager` 設置 `reserveTokensFloor` (e.g., 預留 4,000 token 空間)。
    *   [ ] 空間超載前插入 Silent Turn 要求 LLM 輸出 Write-Ahead Logging (WAL) 到 `STATE.md`。
    *   [ ] 在收到 `NO_REPLY` 後，清除緩存，系統根據日誌重建上下文而不丟失核心推導。
    *   [ ] **驗收標準**: 對話無論長度多龐大，都不中斷推論脈絡。

---
> 註：此演進計畫將在下一個 Sprint 啟動，請工程師與 AI Agent 將精力先集中在 **Phase 1** 與 **Phase 2** 的基底架構改造。
