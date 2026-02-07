# OpenClaw 自動化特性借鏡規格書 (OpenClaw Automation Spec)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**
> **最新版本 (Latest Version)**: 請參閱文件頂部的版本紀錄 (Iteration Record).

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-07 | v1.1 | Renamed file & Added Technical Spec links | Neo |
| 2026-02-07 | v1.0 | Initial Migration | Neo |

---

<a id="zh"></a>

## 🇹🇼 OpenClaw 自動化特性借鏡規格書 Analysis Context

經深度分析 `OpenClaw` 專案，其核心強大之處在於 **「完全自主的生命週期 (Full Autonomous Lifecycle)」** 與 **「本地優先的隱私架構 (Local-First Privacy)」**。

本文作為產品概念文件，技術實作細節請參閱：
*   [哨兵與評議會架構 (v3.4)](../04_架構觀點-Architect_Views/哨兵與評議會架構-Sentinel-Council-Architecture.md)
*   [OpenClaw 執行環境 (v3.5)](../04_架構觀點-Architect_Views/OpenClaw執行環境-OpenClaw-Runtime-Environment.md)

### OpenClaw 關鍵特性 (Key Features) of Power
1.  **無限事件循環 (Infinite Event Loop)**: 非單次執行，而是具備長期記憶的守護進程 (Daemon)，能主動輪詢並對環境變化做出反應。
2.  **多模態介面 (Multi-Modal A2A)**: 不僅是 CLI/Web，更原生整合 Telegram/Slack 等即時通訊，讓 Agent 隨時「在線」。
3.  **技能擴充系統 (Skill Plugins)**: 高度模組化的工具鏈，允許動態加載新能力（如操作瀏覽器、文件系統、外部 API）。
4.  **長期記憶 (Long-term Memory)**: 透過 Vector Store 記住使用者的偏好與歷史交互，而非僅是 Session based。

---

## 2. 借鏡優化規格 (Optimization Spec)

本專案將於 **v3.4 里程碑** 引入以下特性，從「理財工具」進化為「理財管家」。

### 2.1 主動式監控服務 (Proactive Monitoring Service)
*   **現狀**: 依賴使用者觸發或每日定時任務 (Daily Cron)。
*   **優化目標**: 建立 `ProactiveService` (或是 `SentinelAgent`)，實現 24/7 市場監聽。
*   **技術實作**:
    *   **Loop**: 實作基於 `asyncio` 的 `Event Loop`，每分鐘檢查「關鍵市場訊號」(Market Signals)。
    *   **Triggers**: 設定閾值觸發器 (e.g., VIX > 20, BTC Drop > 5%)。
    *   **Autonomy**: 觸發後自動喚醒 `ResearchAgent` 進行快速分析，由 `CIOAgent` 決定是否發送警報。

### 2.2 全通路通知中樞 (Omni-Channel Notification Hub)
*   **現狀**: Email 報告 (被動閱讀)。
*   **優化目標**: 實現即時、雙向的「理財秘書」體驗。
*   **技術實作**:
    *   整合 **Telegram Bot API** 與 **Slack App**。
    *   支援 **雙向交互 (Interactive Action)**: 
        *   系統推播: "台積電 (TSM) 觸發 5% 跌幅，是否執行止損檢查？"
        *   使用者回覆: "Yes" -> 觸發 `AnalysisWorkflow`。

### 2.3 強化型記憶層 (Enhanced Vector Memory)
*   **現狀**: Postgres SQL 結構化數據。
*   **優化目標**: 讓 Agent 記住使用者的投資哲學與風險偏好變化。
*   **技術實作**:
    *   引入 **ChromaDB** 或 **PGVector**。
    *   **Profile Ingestion**: 每次對話自動提取使用者偏好 (e.g., "我不喜歡高波動的加密貨幣") 並存入向量庫。
    *   **Context Injection**: 在生成建議時，自動檢索相關的 User Prompt 歷史。

### 2.4 Agent 技能標準化 (Standardized Skill Protocol)
*   **現狀**: 內部 Tool Functions。
*   **優化目標**: 採用類 OpenClaw/MCP 的標準化接口，方便未來擴充第三方工具。
*   **技術實作**:
    *   全面落地 **Model Context Protocol (MCP)**。
    *   將現有 `Tools` 重構為獨立的 MCP Servers (e.g., `Financial-Data-MCP`, `Browser-MCP`)。

---

## 3. v3.4 里程碑定義 (Milestone Definition)

**版本號**: v3.4
**代號**: "The Sentinel" (哨兵)
**預計時程**: 2026 Q2

### 核心交付物 (Deliverables)
1.  [ ] **Sentinel Engine**: 實作 `ProactiveLoop` 與 `Trigger` 機制。
2.  [ ] **Chat Interface**: 完成 Line Bot 整合。
3.  [ ] **Memory Module**: 整合 Vector Database 於 `ContextService`。
4.  [ ] **MCP Migration**: 完成 100% 工具 MCP 化。

### 成功指標 (Metrics)
*   **主動警報延遲**: 市場事件發生後 < 2 分鐘內推播。
*   **交互回應率**: 使用者透過 Chat App 回覆指令成功率 100%。
*   **記憶準確度**: Agent 能正確引用 3 個月前的使用者偏好。

---

> _"OpenClaw 教會我們：Agent 不應只是被動等待指令的 LLM，而是主動感知世界的軟體生命體。"_

---

<a id="en"></a>

## 🇺🇸 OpenClaw Automation Spec

This document serves as the high-level Product Concept for incorporating "OpenClaw" features into our Advisor. 
The core philosophy is to shift from a "Tool" to an "Autonomous Agent".

### 1. Analysis Context
OpenClaw demonstrates the power of **Infinite Event Loops** and **Local-First Vector Memory**. We aim to adopt these traits to create a proactive, 24/7 financial sentinel.

For technical implementation details, please refer to:
*   [Sentinel & Council Architecture (v3.4)](../04_架構觀點-Architect_Views/哨兵與評議會架構-Sentinel-Council-Architecture.md)
*   [OpenClaw Runtime Environment (v3.5)](../04_架構觀點-Architect_Views/OpenClaw執行環境-OpenClaw-Runtime-Environment.md)

### 2. Key Features to Adopt
1.  **Infinite Loop**: The system should never sleep, constantly monitoring market signals.
2.  **Omni-channel A2A**: Interactive alerts via Line/Slack, not just passive emails.
3.  **Vector Memory**: Remembering user risk tolerance changes over time.
4.  **Standardized Skills**: Adopting MCP for modular tool extension.

### 3. Milestone Definition (v3.4)
*   **Code Name**: "The Sentinel"
*   **Timeline**: 2026 Q2
*   **Metrics**: < 2 min Alert Latency, 100% Chat Response Rate.

> _"OpenClaw teaches us: An Agent is not just an LLM waiting for prompts, but a software organism that actively perceives the world."_
