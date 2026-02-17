---
description: 當原始碼變更時，強制同步更新並提交 Wiki 文檔 (Force sync and commit Wiki changes when source code changes)
---

# Wiki 同步工作流 (Wiki Sync Workflow)

本工作流旨在確保代碼變更與 Wiki 文檔保持 100% 同步，避免文檔過時。

## 執行步驟

1. **檢查 Wiki 狀態**
   - 執行 `git -C wiki/ status` 確認是否有未提交的文檔變更。

2. **驗證雙語一致性**
   - 確保所有新增或修改的 .md 文件符合 `wiki-standards.md`。

// turbo
3. **執行 Wiki 原子提交**
   - 進入 `wiki/` 目錄，將文檔變更獨立提交。
   - `git -C wiki/ add .`
   - `git -C wiki/ commit -m "docs(wiki): sync documentation with source changes"`

4. **同步更新主專案 Repo**
   - 在主專案中提交 `docs(wiki)` 類型的原子 Commit。
