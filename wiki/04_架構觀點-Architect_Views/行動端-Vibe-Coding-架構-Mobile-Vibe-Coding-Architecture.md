# 行動端 Vibe Coding 架構 (Mobile Vibe Coding Architecture)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


### 迭代紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v1.0.0 | **Initial Creation**: Documenting the Hub-and-Spoke architecture and the state-machine logic. | Antigravity |

---

## 🏗️ 系統架構 (Hub-and-Spoke)

系統採用 **GitHub 雲端 (Hub)** 與 **本地 IDE 環境 (Spoke)** 之間的橋接模式。

```mermaid
graph TD
    subgraph "GitHub (Cloud Hub)"
        App[GitHub Mobile App] <-->"Issue[Issue #3: Mobile Hub]"
    end

    subgraph "Local Environment (Spoke)"
        Bridge[scripts/github_bridge.py] <-->|Polls/Posts| Issue
        Agent[Antigravity Agent] <-->|Signal Files| Bridge
        IDE[IDE Codebase] <--> Agent
    end
```

## ⚙️ 運作原理

### 1. 輪詢機制 (Polling Mechanism)
`github_bridge.py` 腳本每 10 秒透過 GitHub REST API (`gh api`) 輪詢 Hub Issue 的新留言。這種方式避開了複雜的 Webhook/ngrok 設定，適合簡單的行動端互動。

### 2. 嚴格身分驗證 (Strict Identity Verification)
為防止未經授權的代碼執行，橋接器會嚴格驗證每個留言的 `login` 欄位。僅處理來自已驗證擁有者帳號（如 `neohsiung`）的留言。

### 3. 狀態機核准迴圈 (State Machine Approval Loop)
橋接器實作了一個狀態機來管理非同步的「計畫-核准-執行」週期：

| 狀態 (State) | 觸發條件 (Transition Trigger) | 動作 (Action) |
| :--- | :--- | :--- |
| **IDLE** | 偵測到 `/task <cmd>` | 擷取任務，狀態轉為 `AWAITING_PLAN` |
| **AWAITING_PLAN** | 本地 Agent 生成計畫 | 將計畫貼至 GitHub，狀態轉為 `AWAITING_APPROVAL` |
| **AWAITING_APPROVAL** | 偵測到 `Approve` | 狀態轉為 `EXECUTING` |
| **EXECUTING** | 任務完成訊號 | 貼上執行結果/Walkthrough，狀態轉回 `IDLE` |

## 🔒 安全與隱私
- **本地憑證**：系統使用本地 `gh` token，憑證絕不離開你的機器。
- **顯式閘控 (Explicit Gating)**：具破壞性的操作或代碼變更需要你從驗證裝置回覆 "Approve"，本地 Agent 才會繼續執行。
- **Git 隔離**：此文件與橋接器實作皆已加入 `.gitignore`，以保持專案核心代碼的純淨。

---

## 🏗️ System Architecture (Hub-and-Spoke)

The system operates as a bridge between the **GitHub Cloud (Hub)** and the **Local IDE Environment (Spoke)**.

## ⚙️ Operational Principles

### 1. Polling Mechanism
The `github_bridge.py` script uses the GitHub REST API (via `gh api`) to poll the Hub Issue for new comments every 10 seconds. This bypasses the need for complex webhook/ngrok setups for simple mobile interaction.

### 2. Strict Identity Verification
To prevent unauthorized code execution, the bridge strictly validates the `login` field of every comment. Only comments from verified owner accounts (e.g., `neohsiung`) are processed.

### 3. State Machine Approval Loop
The bridge implements a state machine to manage the asynchronous "Plan-Approve-Execute" cycle:

| State | Transition Trigger | Action |
| :--- | :--- | :--- |
| **IDLE** | `/task <cmd>` detected | Capture task, status -> `AWAITING_PLAN` |
| **AWAITING_PLAN** | Local Agent generates plan | Post plan to GitHub, status -> `AWAITING_APPROVAL` |
| **AWAITING_APPROVAL** | `Approve` detected | Status -> `EXECUTING` |
| **EXECUTING** | Task completion signal | Post report/walkthrough, status -> `IDLE` |

## 🔒 Security & Privacy
- **Local Credentials**: The system uses the local `gh` token, meaning your credentials never leave your machine.
- **Explicit Gating**: Destructive actions require a literal "Approve" comment from your verified device before the local agent proceeds.
- **Git Alined**: This document and the bridge implementation are ignored by Git (`.gitignore`) to keep the project core clean.
