# AI 代理人集群 (AI Agent Swarm)

> 返回 [[Home]] | 相關: [[System-Overview]]

## 目標 (Goal)
模擬華爾街專業投資團隊的分工模式，透過多個專精不同領域的 AI Agent 協作，產出全面、客觀且具備深度的投資策略報告。

## 為什麼 (Why)
- **專業分工**: 單一 LLM 難以同時精通技術面、基本面與總體經濟，分工能提升分析深度。
- **減少幻覺**: 透過不同 Agent 的觀點交叉驗證 ("Multi-Agent Debate" 雛形)，降低單一模型產生偏誤的風險。
- **自我進化**: 引入工程師 Agent，讓系統能根據回饋自動優化 Prompt，持續學習。

## 做了什麼 (What)
我們設計了五種角色的 Agent，彼此各司其職：

| Agent 角色 | 職責 (Responsibility) | 關注指標 (Key Metrics) |
| :--- | :--- | :--- |
| **Momentum Agent** | 技術面分析、市場情緒 | RSI, MACD, 均線排列 (MA), 成交量 |
| **Fundamental Agent** | 公司基本面、財報分析 | EPS, P/E, 營收成長率, 利潤率 |
| **Macro Agent** | 全球宏觀經濟環境 | 利率 (Yields), VIX, CPI, 聯準會政策 |
| **CIO Agent** | 總結報告、資產配置決策 | 風險回報比, 投資組合健康度, 最終買賣建議 |
| **Engineer Agent** | 系統自我優化 (Meta-Agent) | Prompt 效能, CIO 回饋, 格式正確性 |

## 如何進行 (How)

### 協作流程 (Collaboration Workflow)

1.  **資訊蒐集 (Observation)**:
    - 系統注入 `yfinance` 的即時報價、技術指標與新聞至各個 Agent 的 Context。
    
2.  **平行分析 (Parallel Analysis)**:
    - **Momentum** 分析價格動能與趨勢。
    - **Fundamental** 檢視財報與估值安全邊際。
    - **Macro** 評估當前市場週期 (Risk-On/Risk-Off)。
    
3.  **決策整合 (Synthesis & Decision)**:
    - **CIO Agent** 接收上述三份分析報告。
    - 進行權重評估 (例如：總經逆風時，降低 Momentum 權重)。
    - 產出最終建議 (Buy/Sell/Hold) 與理由。

4.  **優化迴圈 (Optimization Loop)**:
    - **Engineer Agent** 讀取 CIO 的報告與潛在抱怨 (如 "數據不足")。
    - 自動調整上游 Agent (Momentum/Fundamental) 的 System Prompt。
    - 紀錄 Prompt Diff 至資料庫，實現系統自我迭代。

### Prompt 設計哲學
- **Persona (人設)**: 每個 Agent 都賦予資深專家的人設 (如 "20年經驗的華爾街交易員")。
- **Chain of Thought (CoT)**: 要求 Agent 在給出結論前，先列出推論過程。
- **Data-Driven**: 強制要求引用具體數據 (Quote specific numbers) 佐證觀點。
