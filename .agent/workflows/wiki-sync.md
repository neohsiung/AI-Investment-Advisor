# Wiki 同步工作流 (Wiki Sync Workflow)

本工作流旨在確保代碼變更與 Wiki 文檔保持 100% 同步，避免文檔過時。

## 執行步驟

1. **檢查變更狀態 (Check Status)**
   - 執行 `git status` 檢查暫存待提交代碼。
   - 識別受影響的業務邏輯或架構變更。

2. **Wiki 文檔對齊 (Document Alignment)**
   - 進入 `wiki/` 目錄，更新或新增對應文檔。
   - 確保遵循 `documentation-standards.md` 的 ZH/EN 排版與版本紀錄規範。
   - 堅持 **Additive (疊加)** 原則，保留核心開發脈絡。

3. **雙向連結與索引驗證**
   - 確保新文件已鏈結至 `_Sidebar.md` 或 `Home.md`。
   - 驗證所有內部引用路徑是否正確。

4. ** README 淬鍊 (README Distillation)**
   - 若變更涉及核心架構，須同步更新 `README.md`。
   - `README.md`應作為 Wiki 的精簡索引。

// turbo
5. **執行原子提交 (Execute Atomic Commits)**
   - **Step A**: 執行 Wiki Repository 提交。
   - **Step B**: 執行主專案代碼與子模組指標更新之提交。

## 檢查清單 (Checklist)
- [ ] 提交是否為「原子化」？
- [ ] 是否在使用者下達 `commit` 指令後才執行？
- [ ] 文檔是否符合 `documentation-standards.md`？
