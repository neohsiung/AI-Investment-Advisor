# AI 代理人集群 (AI Agent Swarm)

> 返回 [[Home]] | 相關: [[System-Overview]]

## 版本紀錄 (Version History)
| 版本 | 日期 | 作者 | 摘要 |
| :--- | :--- | :--- | :--- |
| **v3.0** | 2025-12-12 | AI Architect | 引入雙軌模型 (Flash/Deep) 與 被動/主動 (Active/Passive) 運作模式。 |
| **v2.0** | 2025-11-29 | AI Architect | 定義 Momentum/Fundamental/Macro/CIO 四大角色。 |

---

## 1. 集群設計哲學 (Design Philosophy)
本系統的 Agent 群體並非總是喋喋不休，而是遵循**「沉默是金，精準打擊」**的原則。

### 1.1 雙軌模型 (Tiered Models)
為了最大化成本效益，我們依據任務難度分配模型資源：
*   **Flash Tier (輕量級)**: 
    *   **模型**: Google Gemini 2.0 Flash / GPT-4o-mini
    *   **任務**: 每日市場掃描、新聞過濾 (Light CIO)、簡單摘要。
    *   **特性**: 速度快、成本極低。
*   **Deep Tier (深度級)**: 
    *   **模型**: Google Gemini 1.5 Pro / o1-preview
    *   **任務**: 複雜財報解讀、總體經濟推演、CIO 最終決策 (Deep CIO)。
    *   **特性**: 邏輯強、支援長文本 (Long Context)、成本較高。

### 1.2 被動式分析 (Passive Analysis)
*   **Analyst Agents (Momentum/Fundamental/Macro)** 平時處於**被動模式**。
*   **Daily Routine**: 每日收盤後，使用 **Flash Tier** 掃描市場。若無重大異常 (Signal Strength < Threshold)，僅將數據寫入 Database，**不主動發送報告**給 CIO。
*   **Active Dispatch**: 唯有當 **Deep CIO** 明確發出指令 (例如：「分析 NVDA 昨晚的暴跌原因」) 時，Agent 才切換至 **Deep Tier** 進行深度研究。

---

## 2. 角色定義 (Role Definitions)

### 2.1 投資顧問部 (The Investment Team)

| 角色 | 職責 (Responsibility) | 運作模式 (Mode) |
| :--- | :--- | :--- |
| **Light CIO (Router)** | **守門員**。過濾 Event Bus 上的新聞與數據，決定是否喚醒團隊。 | **Always-On (Flash)** |
| **Deep CIO (Leader)** | **決策者**。制定資產配置，調派分析師，撰寫最終報告。 | **On-Demand (Deep)** |
| **Momentum Agent** | **技術面**。關注價格行為、成交量、RSI/MACD。 | Passive / Active |
| **Fundamental Agent** | **基本面**。關注財報 (10-K/10-Q)、營收成長、估值。 | Passive / Active |
| **Macro Agent** | **總體經濟**。關注聯準會政策、利率、地緣政治。 | Passive / Active |

### 2.2 人力資源部 (The HR Team)

| 角色 | 職責 (Responsibility) |
| :--- | :--- |
| **Engineer Agent** | **Prompt 優化師**。觀察分析結果的準確度，動態調整上述 Agent 的 System Prompt。例如發現 Momentum Agent 過於敏感，則修改 Prompt 提高訊號門檻。 |

---

## 3. 協作流程範例 (Collaboration Example)

**情境**: 聯準會意外宣佈升息 (External Event)。

1.  **Filter**: `Light CIO` (Flash) 收到新聞，判定重要性 `9/10` -> 觸發 `CRITICAL_EVENT`。
2.  **Wake Up**: `Deep CIO` (Deep) 被喚醒。
3.  **Dispatch**: CIO 指派任務：
    *   對 `Macro Agent`: "評估升息對科技股估值的影響 (Deep Model)"。
    *   對 `Momentum Agent`: "檢查那斯達克指數的支撐位 (Flash Model)"。
4.  **Execute**: Agents 執行任務並回傳 Artifacts。
5.  **Synthesize**: CIO 產出緊急策略報告，建議降低槓桿。
6.  **Review**: 一週後，`Engineer Agent` 檢查此建議是否正確。若錯誤，則調整 CIO 的決策參數。
