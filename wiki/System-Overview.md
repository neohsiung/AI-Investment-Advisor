# 系統總覽 (System Overview)

> 返回 [[Home]]

## 簡介 (Introduction)
AI 投資顧問平台是一個基於 AI Agent 架構的自動化投資分析系統。它整合了量化分析引擎與最新的 LLM 技術，為投資者提供深度且即時的市場洞察。

## 核心功能 (Core Features)

### 1. 數據層 (Data Layer)
- **多券商支援**: 支援 Robinhood, Interactive Brokers (IBKR) 與自定義 CSV 匯入。
- **資料標準化**: 自動清洗並正規化不同來源的交易與股息紀錄。
- **本地資料庫**: 使用 SQLite 儲存完整交易歷史 (`transactions`), 持倉 (`positions`) 與現金流 (`cash_flows`)。詳見 [[Cloud-Database-Migration]]。

### 2. 量化引擎 (Quantitative Engine)
- **槓桿監控**: 即時計算總名義價值 (TNV) 與淨清算價值 (NLV)，追蹤槓桿比率 (Leverage Ratio)。
- **績效歸因**: 使用資金加權收益率 (Money-Weighted Return) 計算真實 ROI。
- **快照記錄**: 每日自動記錄資產淨值，繪製權益曲線 (Equity Curve)。

### 3. AI 代理人集群 (AI Agent Swarm)
系統由四大專家 Agent 組成，協同產出投資報告。詳見 [[AI-Agent-Swarm]]。

### 4. 視覺化儀表板 (Dashboard)
提供基於 Web 的互動介面，檢視資產配置、績效圖表與歷史報告。詳見 [[User-Guide]]。

## 系統架構 (System Architecture)
```mermaid
graph TD
    User((User)) -->|Browser| Dashboard[Streamlit Dashboard]
    Dashboard -->|Read/Write| DB[(SQLite DB)]
    
    Scheduler[Task Scheduler] -->|Trigger| Workflow[Analysis Workflow]
    Workflow -->|Fetch Data| MarketData[Market Data Service]
    Workflow -->|Coordinate| CIO[CIO Agent]
    
    CIO -->|Consult| Momentum[Momentum Agent]
    CIO -->|Consult| Fundamental[Fundamental Agent]
    CIO -->|Consult| Macro[Macro Agent]
    
    Momentum & Fundamental & Macro -->|Use| LLM[LLM Provider (Gemini/OpenAI)]
    
    Workflow -->|Save Report| DB
    Workflow -->|Send Email| Notifier[Email Service]
```
