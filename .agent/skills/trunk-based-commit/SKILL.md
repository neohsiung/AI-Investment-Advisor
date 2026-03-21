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

### 1. 嚴格的主幹開發 (Strict Trunk-Based Development)
- **直接推進主幹**：除非使用者特別要求開啟 Feature Branch 或提出 PR，否則所有變更應**直接 commit 到開發主幹**。
- **避免長時間未提交 (No Long-Lived Uncommitted State)**：Agent 在執行任務時，**絕對不要**等到整個跨越多個檔案的巨大功能做完才做一次巨大的 commit。

### 2. 高頻次、原子化的提交 (High-Frequency Atomic Commits)
- **單點突破，立即提交**：每當成功寫好一個 Function、修正好一個 Bug、或是建立好一個模組且確認語法無誤後，就要執行 `git commit`。
- **確保主幹不被破壞 (Don't Break the Trunk)**：每次 Commit 的段落至少不能引發 Syntax Error 或導致專案無法編譯/啟動測試。就算新功能尚未上線，也可先以 Dead Code 形式推入主幹。

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

---

## Agent 執行範例

1. 修改了 `registry.py` -> **遵循 `git-commit-format.md` 撰寫中英雙語詳細變更日誌並獨立 Commit**
2. 更新了 `wiki/` 裡面的技術文件 -> **單獨對 `wiki` repository 進行對應的 docs(wiki) 中英雙語 Commit**
