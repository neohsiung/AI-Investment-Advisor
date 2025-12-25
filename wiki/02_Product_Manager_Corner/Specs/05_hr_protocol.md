# Spec: HR Protocol (Zombie Agent Detection)

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Spec: HR Protocol (Zombie Agent Detection)

### Overview
The HR Protocol is a system health monitoring mechanism designed to detect "Zombie Agents"—agents that have not successfully completed a task (updated their state cache) within a specified timeframe.

### Logic

- **Monitoring Target**: `agent_states` table in the database.
- **Metric**: `last_run_time` timestamp.
- **Threshold**: 7 Days (Configurable).
- **Status Definitions**:
    - **Active**: `last_run_time` within threshold.
    - **Zombie**: `last_run_time` older than threshold.
    - **Missing**: Agent defined in system but no record in DB.

### UI Implementation
- **Location**: Settings Page > HR 協議 (Tab 6).
- **Visualization**: Color-coded dataframe (Green=Active, Red=Zombie).
- **Action**: "Refresh Status" button to re-scan.

### Roadmap
- **Auto-Restart**: Future versions should attempt to auto-restart or "heal" zombie agents by triggering a test run.
- **Alerting**: Send Admin email when Zombie count > 0.

---

<a id="traditional-chinese"></a>

## 🇹🇼 規格書: HR 協議 (殭屍 Agent 偵測)

### 概觀 (Overview)
HR 協議 (HR Protocol) 是一套系統健康監控機制，旨在偵測「殭屍 Agent (Zombie Agents)」—即那些在指定時間內未能成功完成任務（未更新狀態快取）的 Agent。

### 邏輯 (Logic)

- **監控目標**: 資料庫中的 `agent_states` 表。
- **指標**: `last_run_time` 時間戳記。
- **閾值**: 7 天 (可設定)。
- **狀態定義**:
    - **活躍 (Active)**: `last_run_time` 在閾值時間內。
    - **殭屍 (Zombie)**: `last_run_time` 早於閾值時間 (太久沒活動)。
    - **遺失 (Missing)**: 系統定義中有該 Agent，但資料庫無紀錄。

### UI 實作 (UI Implementation)
- **位置**: 設定頁面 (Settings Page) > HR 協議 (Tab 6)。
- **視覺化**: 顏色標記的表格 (綠色=活躍, 紅色=殭屍)。
- **操作**: 「刷新狀態 (Refresh Status)」按鈕以重新掃描。

### 未來路線圖 (Roadmap)
- **自動重啟 (Auto-Restart)**: 未來版本應嘗試透過觸發測試執行來自動重啟或「治療」殭屍 Agent。
- **警報 (Alerting)**: 當殭屍數量 > 0 時發送管理員郵件。
