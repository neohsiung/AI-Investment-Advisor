# System Migration Plan

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 System Migration Plan

### Version History
| Version | Date | Description |
| :--- | :--- | :--- |
| **v1.0** | 2025-12-12 | Initial plan for v1->v3 migration. |

### 1. Why Migrate?
Current v1 system is linear and cannot handle "Real-time News" or "Cost Control" (v3 dual-unit requirements). A clean migration path is needed to ensure zero downtime.

### 2. Goals
1.  **Zero Downtime**: Daily report service must not stop.
2.  **Risk Mitigation**: Side-by-side validation.
3.  **Data Integrity**: Keep historical data.

### 3. Side-by-Side Strategy (Incremental)

#### Phase 1: Data Layer Expansion (Planning)
- **Action**: Modify `src/database.py`.
- **Details**: Add `event_logs`, `manual_inputs` tables.

#### Phase 2: Agent Dual-Mode (Pending)
- **Action**: Refactor Agent classes.
- **Details**: Add `run_flash()` / `run_deep()` methods.

#### Phase 3: New Core (Pending)
- **Action**: Create `src/workflow_v3.py`.
- **Details**: New Event-Driven entry point.

#### Phase 4: Traffic Switching (Pending)
- **Action**: Switch entry point.
- **Transition**: v1 handles Daily Reports, v3 handles breaking news.
- **Final**: Stop v1 Cron Job.

### 4. Rollback Plan
Since v1 code (`workflow.py`) remains, simply stop v3 process and ensure v1 cron is running to rollback.

---

<a id="traditional-chinese"></a>

## 🇹🇼 系統遷移計畫 (System Migration Plan)

### 版本紀錄
| 版本 | 日期 | 摘要 |
| :--- | :--- | :--- |
| **v1.0** | 2025-12-12 | 初始遷移計畫：Side-by-Side 策略，確保 v1 服務不中斷。 |

### 1. 為什麼需要遷移？ (Why)
目前的系統（v1）採用線性工作流，無法滿足「即時新聞回應」與「成本控管」的需求。
因應 **雙部門架構 (v3)** 的導入，我們需要一個明確的遷移路徑，**在不停止現有每日投資報告服務的前提下**，平滑過渡到新架構。

### 2. 遷移目標 (Goals)
1.  **Zero Downtime**: 現有的每日/每週報告排程不可中斷。
2.  **Risk Mitigation**: 新舊架構並行驗證，確保 ROI 計算與信號一致。
3.  **Data Integrity**: 歷史數據完全保留。

### 3. 遷移策略：並行運作 (Side-by-Side Strategy)
我們採取 **增量式遷移 (Incremental Migration)**，分為四個階段：

#### Phase 1: 數據層擴容 (Data Layer Expansion)
*   **Status**: Planning
*   **Action**: 修改 `src/database.py`。
*   **Details**: 新增此階段所需的 `event_logs`, `manual_inputs` 表格。現有的 `transactions` 表格保持不變。

#### Phase 2: Agent 雙模化 (Agent Dual-Mode)
*   **Status**: Pending
*   **Action**: 重構 Agent 類別。
*   **Details**: 引入 Factory Pattern 或增加 `run_flash()` / `run_deep()` 方法，讓 Agent 能同時支援 v1 的同步呼叫與 v3 的異步調派。

#### Phase 3: 新核心搭建 (New Core Implementation)
*   **Status**: Pending
*   **Action**: 建立 `src/workflow_v3.py` 與 `src/core/event_bus.py`。
*   **Details**: 這是 v3 的全都新入口。它將獨立運行，監聽 Webhook，而不干擾 v1 的 Cron Job。

#### Phase 4: 流量切換 (Traffic Switching)
*   **Status**: Pending
*   **Action**: 切換入口點。
*   **Details**:
    *   **過渡期 (1週)**: v1 負責每日報告，v3 負責處理突發新聞 (Flash Reports)。
    *   **切換日**: 停止 v1 Cron Job，將 v3 設定為每日報告的主要生成者。

### 4. 回滾計畫 (Rollback Plan)
由於 v1 代碼 (`workflow.py`) 完整的保留在 codebase 中，若 v3 出現嚴重 Bug，只需：
1.  關閉 v3 Process。
2.  確保 v1 Cron Job 仍在執行。
3.  系統即可瞬間恢復至舊版穩態。
