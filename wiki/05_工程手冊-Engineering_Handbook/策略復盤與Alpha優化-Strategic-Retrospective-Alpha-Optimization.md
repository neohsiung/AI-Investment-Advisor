# 策略復盤與 Alpha 優化 (Strategic Retrospective & Alpha Optimization)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v1.0 | Initial Specification for Multi-Agent Retrospective Protocol | Neo |

---

## 1. 核心願景 (Vision)
**目標**: 透過「多智能體共同復盤 (Multi-Agent Joint Retrospective)」，建立一個能自主識別決策偏誤、修正策略權重、並最終產生穩定超額收益 (Alpha) 的閉環系統。

## 2. 為什麼需要自動復盤？ (The "Why")
在動態市場中，靜態的 Agent Prompt 或固定的權重會導致「策略漂移 (Strategy Drift)」。
- **決策偏誤**: 某個 Sub-Agent (如 Sentiment) 可能在特定行情下過於樂觀。
- **環境變化**: 低波動體制切換至高波動體制時，舊的因數可能失效。
- **閉環學習**: 系統必須知道「昨天為什麼賠錢」，才能在「明天賺回來」。

## 3. 多智能體共同復盤協議 (The Protocol)

### 3.1 職責對照表 (Retrospective Roles)

| 智能體 (Role) | 復盤任務 (Task) | 數據源 (Data Source) |
| :--- | :--- | :--- |
| **RetrospectiveAgent** | **主編排器**。收集各方分析與真實 P&L，生成歸因報告。 | SQLite Transaction DB, Decision Logs. |
| **AttributionAnalyzer** | **歸因分析**。拆解收益來源（Beta, Sector Alpha, Specific Alpha）。 | Market Data Service, Portfolio Service. |
| **RealityChecker** | **真實性核查**。比對決策時的「預期收益」與「實際結果」的偏差 (Delta)。 | Broker API (Realized P&L). |
| **StrategyRefiner** | **權重修正**。根據 Delta 調整 `CIOAgent` 的信心係數或 Agent 排序。 | Prompt Repository (Weights). |

### 3.2 復盤工作流 (The Workflow)

1.  **數據匯聚 (Fan-in)**: 每週末自動觸發，從 `DecisionLog` 提取該週所有買入/賣出指令及背後的 Agent 理由。
2.  **績效對帳 (Reconciliation)**: `RealityChecker` 比對買入價格與當前價格，計算各持倉的對標 (Benchmark) 表現。
3.  **多維辯論 (Fractal Retrospective)**:
    - **挑戰者**: 如果當時發生虧損，由 `RiskAgent` 挑戰 `CIOAgent` 當時的決策邏輯。
    - **辯解者**: `CIOAgent` 提出當時的數據支撐 (News/Fundamentals)。
    - **裁判**: `RetrospectiveAgent` 判斷是「運氣因素」還是「邏輯缺陷」。
4.  **權重凍結與修正 (Policy Update)**:
    - 若判定為邏輯缺陷，將該錯誤模式存入 `Long-term Memory` (A2A Memory)。
    - 下週決策時，`TaskPlanner` 會優先查詢該 Memory 以避免重複錯誤。

## 5. 決策存修與日誌規範 (Decision Persistence - Mandatory)
為了確保 `RetrospectiveAgent` 能夠準確對帳，系統必須以 **確定性格式** 記錄決策瞬間的快照：
- **Snapshot-at-Decision**: 存儲決策時的「當前價格 (Bid/Ask)」、「預期止盈/止損」、「Agent 理由鏈 (Chain-of-Thought)」。
- **Reasoning IDs**: 每一條指令必須標記生成它的 Sub-Agent ID，以便歸因。
- **Environment Context**: 記錄當時的 VIX、宏觀指標數值。

## 6. Alpha 優化指標 (Success Metrics)
- **歸因準確度 (Attribution Accuracy)**: 系統能否正確識別虧損來源。
- **學習增益 (Learning Gain)**: 復盤後的策略在回測中的表現是否優於原策略。
- **策略存活率 (Strategy Survival)**: 核心因子在不同體制下的穩定性。

## 🔗 Bidirectional Links
- **Product View**: [Evolutionary Roadmap](../02_產品經理-Product_Managers/產品演進藍圖-Evolutionary-Roadmap)
- **Technical Specs**: [Future Roadmap Specs](../02_產品經理-Product_Managers/01_規格書-Specs/未來演進規格-Future-Roadmap-Specs)
- **Engineer Handbook**: [Prompt Engineering Specs](提示詞工程規範-Prompt-Engineering-Specs)
