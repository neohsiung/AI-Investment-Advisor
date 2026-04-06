---
name: trunk-based-commit
description: 開發指導準則：指導 Agent 遵循 Trunk-based Development 原則，進行高頻次、小單位的原子化 Commit。
---

# Trunk-Based Commit (主幹開發與原子化提交準則)

> 本技能為 **Agent Dev Skill**，用於指導 Agent (Antigravity/Engineer) 在專案中執行程式碼變更時，如何正確進行 `git commit`。本專案採用 **Trunk-based Development（主幹開發）** 模型。

## 適用時機 (When to Use)

- 當 Agent 完成了一個微小但完整的邏輯變更 (Atomic Change) 時。
- 當 Agent 在進行 Refactoring、新增 Feature 或修復 Bug 過程中。
- **任何時候** Agent 被授權修改專案庫並進行版本控制時。

---

## 核心行為規範 (Core Behaviors)

### 1. 擴展型主幹開發 (Scaled Trunk-Based Development)

- **嚴禁直接推送主幹 (No Direct Commits to Main)**：除非是極微小的熱修復 (Hotfix) 或使用者明確授權，否則**禁止直接 commit 到 `main` 或 `master` 分支**。
- **短期特性分支 (Short-Lived Feature Branches)**：所有變更應在從主幹切出的短期分支中執行（分支壽命不應超過 1-2 天）。
- **分支命名規範**：
  - `feat/<task-description>`：新功能開發。
  - `fix/<task-description>`：錯誤修復。
  - `docs/<task-description>`：文件更新。
  - `refactor/<task-description>`：代碼重構。

### 2. 高頻次提交與自動化 Pull Request (PR Workflow)

- **自動化分支流程**：在任務核准後，Agent **必須自動執行** `git checkout -b <branch_name>`。
- **原子化提交 (Atomic Commits)**：在 Feature Branch 上保持高頻次提交，每完成一個邏輯單元即 commit 一次（遵循 `.agent/rules/git-commit-format.md`）。
- **強制自動建立 PR (Automated PR Creation)**：Task 內容開發與測試完成後，Agent **必須主動推送分支並建立 PR**：
    - 使用 **GitHub MCP** (`create_pull_request`) 或 **GitKraken MCP** (`pull_request_create`)。
    - **PR 標題**：與 Commit Message 第一行保持一致。
    - **PR 內容**：從 `walkthrough.md` 提取摘要，並列出核心變更。
- **嚴禁直接 Merge**：PR 建立後， Agent 不得自行合入 `main`，必須等待使用者審核或 CI 通過。
- **確保主幹不被破壞 (Don't Break the Trunk)**：在推 PR 前，Agent 必須至少執行過一次 `py_compile` 或相關的核心單元測試，確保語法與基本邏輯正確。
- **資料庫向下相容性 (Backward Compatibility)**：若涉及 DB Schema 異動，PR 必須清楚說明相容性處理。系統已有多個租戶，新增欄位應有 default 值。

### 3. Commit Message 命名規範 (Conventional Commits & Bilingual Detailed Format)

每一次 Commit 都必須遵循常規約定格式，且**強制遵守專案的雙語詳細格式規範 (`.agent/rules/git-commit-format.md`)**：

- **第一行限制**: `<type>(<scope>): <short-summary-english>`
- **第二行限制**: `<short-summary-traditional-chinese>`
- **內容詳述**: 必須包含 `**核心變更 (Core Changes)**:` 等分類標題，並使用雙語 (`- <zh> / <en>`) 撰寫清單。
- 專案與 Wiki 若同時變更，必須分別獨立 commit，不可混合。

> **Rule of Thumb**: 若你無法用一個簡短的 `feat` 或 `fix` 來描述這個 Commit，代表你的變更包裝得太大了，請拆分成多個更小的原子級 Commits。詳細格式請務必參考 `.agent/rules/git-commit-format.md`。

### 4. 嚴禁混合型提交 (No Mixed Concerns)

- 絕對不要把「修復 A 模組的 Bug」和「新增 B 模組的功能」混在同一個 commit 裡。
- 每個 commit 解決一個單位的問題，落實真正的隔離與原子化提交。

### 5. 雙 Repo 規範與 Wiki 提交 (Dual-Repo & Wiki Commits)

本專案的 `wiki/` 目錄為獨立或視為 Submodule 管理的 Repository。因此：

- **主專案提交**：在專案根目錄執行常規的 `git commit` 時，將不會（也不應）包含 `wiki/` 目錄的變更。
- **Wiki 提交**：任何針對 `wiki/` 內實體文件的修改，**必須強制定向至 Wiki Repo**，使用 `git -C wiki add` 與 `git -C wiki commit` 獨立提交。
- 若一項任務同時包辦了程式碼修改與 Wiki 文件更新，這必須被切分為**兩個完全獨立的原子化提交**（分別在主 Repo 執行 `feat` 等變更，在 Wiki Repo 執行 `docs(wiki)` 變更）。

---

## Agent 執行範例

1. 修改了 `registry.py` -> **遵循 `git-commit-format.md` 撰寫中英雙語詳細變更日誌並獨立 Commit**
2. 更新了 `wiki/` 裡面的技術文件 -> **單獨對 `wiki` repository 進行對應的 docs(wiki) 中英雙語 Commit**

---

---

## 6. Wiki Sync & Commit Workflow (Post-Task)

當 Agent 完成含架構變更（如新增模組/API、變更領域模型）的 task 時，必須執行以下 `walkthrough-wiki-sync` 流程，最後以 `docs(wiki)` 獨立提交 Wiki Repo：

### 1. 辨識影響範圍 (Impact Analysis)

- 讀取當前 walkthrough 的變更模組與影響清單。
- 使用 `grep_search` 搜尋 `wiki/` 中提及這些模組的文件。

### 2. Wiki 迴圈式填補 (Iterative Wiki Patching)

- 開啟受影響文件，進行**段落精確修訂** (嚴禁整頁重寫)。
- 新增架構設計必須加入 Mermaid 圖表並驗證可用性。
- 遵循繁中與英文**雙語並列**格式。

### 3. 扁平化連結驗證 (Flat-Link Verification)

- 確保所有 Wiki 內部連結為 `[Label](PageName)`（嚴禁 `../` 與 `.md`）。

### 4. README 增量檢視 (README Loop Enrichment)

- 以迴圈增量將變更亮點與 Mermaid 架構圖同步更新至專案根目錄的 `README.md`。

### 5. 同步驗證與提交 (Dual-Repo Sync Validation)

- `git -C wiki status` 確認變更範圍。
- 分離提交：主專案 Repo 提交 Code，Wiki Repo 執行 `git -C wiki commit` 提交文件。
