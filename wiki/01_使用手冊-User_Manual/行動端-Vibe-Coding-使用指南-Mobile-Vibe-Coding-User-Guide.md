# 行動端 Vibe Coding 使用指南 (Mobile Vibe Coding User Guide)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


### 迭代紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v1.0.0 | **Initial Creation**: Comprehensive guide for mobile interaction and approval flows. | Antigravity |

---

本指南將協助你快速上手透過 GitHub Mobile App 遠端操控本地 Antigravity Agent 的流程。

## 🛠️ 啟動與準備

1. **認證 GitHub CLI**：確保本地機器已登入 `gh` 且擁有倉庫存取權限。
2. **啟動監聽器**：在本地終端機執行：
   ```bash
   python3 scripts/github_bridge.py
   ```
3. **開啟 Hub Issue**：在手機端 GitHub App 開啟專用的 [Mobile Session Hub #3](https://github.com/neohsiung/AI-Investment-Advisor/issues/3)。

---

## 💬 互動指令說明 (Commands)

在 Issue 留言中輸入以下指令：

### 1. 任務下達 (`/task`)
- **格式**: `/task [你的指令內容]`
- **範例**: `/task 幫我重構 src/agents/factory.py 並增加單元測試`
- **效果**: 觸發本地 Agent 開始分析任務並生成實作計畫。

### 2. 審核流程 (Approval Loop)
當 Agent 回傳計畫後，你必須回覆以下關鍵字：
- **`Approve`**: 授權 Agent 開始修改本地代碼。
- **`Disapprove`**: 取消任務，Agent 將返回 IDLE 狀態。

---

## 📋 最佳實踐 (Best Practices)

- **具體化指令**：提供檔案路徑或明確的功能描述（如：「檢查 ... 中的資安漏洞」）。
- **審閱計畫**：在手機上仔細閱讀 Agent 回傳的 `Proposed Plan`。
- **身分限制**：僅有你的帳號 (`neohsiung`) 的指令會被處理。

---

## 🛡️ 資安提示 (Security)

- **隔離性**：所有的代碼變更僅發生在你的本地環境，GitHub 僅作為指令緩衝區。
- **手動閘控**：除非你回覆 `Approve`，否則 Agent 絕對不會更動代碼。

---

## 🏗️ Commands & Workflow (English)

### 1. Initiating Tasks
- **Format**: `/task [instruction]`
- **Example**: `/task refactor src/agents/factory.py and add tests`

### 2. The Approval Cycle
- **`Approve`**: Grants permission to execute changes.
- **`Disapprove`**: Rejects the plan and resets to standby.

### 🔒 Security Note
This system relies on your local `gh` authentication and restricts execution to authorized comments only.
