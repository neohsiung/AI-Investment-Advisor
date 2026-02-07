# 哨兵與評議會架構 (Sentinel & Council Architecture)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**
> **最新版本 (Latest Version)**: 請參閱文件頂部的版本紀錄 (Iteration Record).

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-07 | v3.4 | Standardized naming and structure | Neo |
| 2026-02-03 | v3.3 | Initial Draft (Rev 3) | Antigravity |

---

<a id="zh"></a>

## 🇹🇼 哨兵與評議會架構 (Architecture Overview)

本架構融入 **丹尼爾·康納曼 (Daniel Kahneman)** 的《快思慢想》哲學，將系統劃分為兩個認知層次：

### 1. 系統層級 (Cognitive Layers)

#### System 1: 快思 (The Sentinel)
- **角色**: 直覺、反射、模式識別。
- **實作**: `SentinelService` + `Adaptive Thresholds`。
- **特徵**: **Always-on**，成本極低，反應極快。它不進行深度推理，只負責「發現異常」(Pattern Matching) 並喚醒 System 2。

#### System 2: 慢想 (The Council)
- **角色**: 邏輯、運算、辯論、記憶檢索。
- **實作**: `CouncilService` + `Agent Swarm`。
- **特徵**: **On-Demand**，成本較高。它負責針對 System 1 拋出的議題 (或日報中的每一項子條目) 進行深度審議。
- **碎形辯論 (Fractal Debate)**: 在生成「日報」或「週報」時，並非只進行一次辯論。而是針對報告中的 **每一個子項目 (每檔股票)**，都必須經過完整的 `Memory -> Debate -> Synthesis` 循環，確保每一個決策點都是深思熟慮的結果。

### 2. 組件設計 (Component Design)

#### 2.1 哨兵服務 (Sentinel Service)
位於 `src/services/sentinel_service.py`。
*   **職責**: 環境感知器與直覺反應。負責監控市場數據流，當數值異常 (Adaptive Threshold Trigger) 時喚醒 System 2。
*   **介面**: `async def process_tick(self)`
*   **部署模式 (Dual Mode)**:
    1.  **Local (Docker)**: 由 `SchedulerService` 的 `while True` 迴圈每分鐘呼叫一次。
    2.  **GCP (Cloud Run)**: 透過 `Cloud Scheduler` 每分鐘發送 HTTP Request 觸發 API Endpoint。

#### 2.2 評議會核心 (The Council Core)
位於 `src/services/council_service.py`。
*   **成員 (Council Members)**: 
    *   **FundamentalAgent**: 關注財報、護城河、估值。
    *   **MomentumAgent**: 關注趨勢、均線、動能。
    *   **RiskAgent**: 關注波動率 (VIX)、下檔風險、資產配置。
    *   **MacroAgent**: 關注利率、通膨、經濟數據 (FRED)。
    *   **SentimentAgent**: 關注市場情緒、新聞氣氛。
*   **運作協議 (The Protocol)**:
    1.  **Convener**: 哨兵發起議題 (e.g., "Earnings Miss detected for NVDA").
    2.  **Memory Recall**: 檢索 LTM 與 STM，進行「經驗復盤」。
    3.  **Fractal Debate**: 針對議題的每個子項目進行正反辯論。
    4.  **Consensus**: Chairperson (CIO) 綜合權衡，產出最終決策。

#### 2.3 動態智商路由器 (Dynamic Intelligence Router)
位於 `src/infra/llm_router.py`。
*   **設計目標**: 在「成本」與「品質」間取得動態最佳解。
*   **路由邏輯**:
    *   **Default**: `Fabric.Flash` for general tasks (System 1).
    *   **High Volatility / Debate**: `Fabric.Pro` for reasoning (System 2).

#### 2.4 強化記憶層 (Unified PGVector)
位於 `src/repositories/vector_repository.py`。
*   **完整架構**: 採用標準化 PostgreSQL `pgvector` 擴充套件。
*   **Schema**: `memory_embeddings` (General), `council_minutes` (STM), `strategy_reports` (LTM).

#### 2.5 全通路適配器 (Omni-Channel Adapters)
位於 `src/infra/channels/`。
*   **介面定義**: `IChannelAdapter` (Domain Layer).
*   **LINE Bot實作**: 使用 Flex Message 實現 "Visual Issue Ticket"。

### 3. 資料流 (Data Flow)

1.  **市場事件**: `SentinelService` 偵測到 VIX > 25。
2.  **觸發思考**: `SystemEngineerAgent` 被喚醒，讀取 `memory_service` 發現使用者 "討厭波動"。
3.  **決策生成**: Agent 決定建議 "減倉 20%"。
4.  **主動推播**: 透過 `LineAdapter` 發送 Flex Message 給使用者：「⚠️ **市場波動警報** (VIX=25.1) \n建議依您的保守策略減倉 20%。」
5.  **使用者反饋**: 使用者點擊 Flex Message 上的 [執行] 按鈕 (Postback Action)。
6.  **閉環執行**: 系統呼叫 `TransactionService` 下單，並寫入 `memory`：「使用者在 VIX>25 時同意減倉」。

### 4. 記憶體架構與認知循環 (Memory Architecture & Cognitive Cycle)

本系統採用 **Short-Term (STM)** 與 **Long-Term (LTM)** 雙層記憶架構，模擬人類「睡眠鞏固」機制。

#### 4.1 記憶分層
1.  **Short-Term Memory (STM)**:
    *   **載體**: `Daily Council Minutes` (每日評議會紀錄)。
    *   **特性**: 高頻、詳細、包含情緒與當下市場雜訊。
    *   **用途**: 供 `Sentinel` (System 1) 進行快速比對 (Pattern Matching)。
2.  **Long-Term Memory (LTM)**:
    *   **載體**: `Weekly Strategy Reports` (週報戰略)。
    *   **特性**: 低頻、抽象、去雜訊 (Denoised)、結構化。
    *   **用途**: 供 `Council` (System 2) 進行長期趨勢判斷與修正體制 (Regime Shift)。

#### 4.2 記憶鞏固流程 (Consolidation Process)
1.  **Daily (Fast Thinking)**:
    *   每日產出 `Daily Report`，作為 STM 存入 Vector DB。
    *   決策重點: Tactial Alpha (戰術優勢)。
2.  **Weekly (Slow Thinking)**:
    *   每週末觸發 `Consolidation Job`。
    *   **Recall**: 檢索過去 5 日的 STM。
    *   **Refinement**: 執行 `CIO Agent` 的 **Memory Chain Review** 任務，剔除雜訊 (Noise)，提取訊號 (Signal)。
    *   **Save**: 將「精煉後的戰略」存回 LTM，作為下週的指導原則 (Base Prompt Context)。

### 5. 可行性與風險分析 (Feasibility & Risk)

#### 5.1 費用預估 (Cost Estimation)
以 GCP 為基準：
*   **Serverless Tick 模式**: 
    *   **Cloud Run**: 0 實例待命 (Scale to Zero)。每日 1440 次 invocations (每分鐘 1 次)。
    *   **Cloud Scheduler**: $0.10 / month (每 job)。
    *   **Cost**: 計算運算時間極短，預估 **< $2 USD / Month**。
    *   **Docker Local**: 透過 `scheduler` 容器執行，無額外費用。

#### 5.2 技術風險 (Risks)
1.  **冷啟動延遲 (Cold Start)**: Cloud Run 喚醒可能需 3-5 秒。
    *   *Mitigation*: 哨兵監控非高頻交易 (HFT)，秒級延遲可接受。
2.  **LINE Webhook**: 需要 HTTPS 公網 IP 且必須驗證簽章。
    *   *Local Dev*: 必須使用 `ngrok` (或其他 Tunnel)，URL 需填入 LINE Developer Console。
    *   *Prod*: Cloud Run 原生支援 HTTPS，直接設定即可。

---

<a id="en"></a>

## 🇺🇸 Sentinel & Council Architecture

### 1. Architecture Overview (System 1 & 2)

Inspired by Daniel Kahneman's *Thinking, Fast and Slow*, the system is divided into two cognitive layers:

#### System 1: The Sentinel (Fast)
- **Role**: Intuition, Reflex, Pattern Matching.
- **Implementation**: `SentinelService`.
- **Characteristics**: Always-on, low cost. Matches patterns and wakes up System 2.

#### System 2: The Council (Slow)
- **Role**: Logic, Reasoning, Debate.
- **Implementation**: `CouncilService` + `Agent Swarm`.
- **Characteristics**: On-Demand, high cost. Performs fractal debates on issues raised by Sentinel.

### 2. Component Design
*   **Sentinel Service**: Monitors market data streams using adaptive thresholds.
*   **The Council**: A swarm of specialized agents (Risk, Macro, Fundamental) engaging in debate using the `Fractal Debate` protocol.
*   **Router**: Dynamically routes easy tasks to Flash models and hard tasks to Pro models.
*   **Unified PGVector**: Stores memories in PostgreSQL.

### 3. Data Flow
Sentinel detects anomaly -> Wakes System 2 -> Agent generates decision based on Memory -> Pushes to LINE -> User Approves -> Transaction Executed.

### 4. Memory Architecture
*   **STM (Daily)**: High-frequency, noisy. Used for pattern matching.
*   **LTM (Weekly)**: Consolidated, denoised. Used for regime shift detection.
*   **Consolidation**: A weekly job refines STM into LTM strategies.

### 5. Cost & Risk
*   **Cost**: < $2/month on GCP using Serverless scaling.
*   **Risks**: Cold starts (3-5s) are acceptable for non-HFT use cases.
