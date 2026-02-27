---
description: 當 Walkthrough 包含架構變更時，自動回填更新 Wiki 文檔 (Auto-refine Wiki docs when walkthrough contains architectural changes)
---

# Walkthrough → Wiki 文檔回填工作流

本工作流確保在完成架構性的工作（如新增模組、修改服務架構、重構核心組件）後，相關的 Wiki 文件也同步更新，落實 Rule #12「原子化同步」。

## 觸發條件 (Trigger Conditions)

當 Walkthrough 文件中包含以下關鍵字或變更時，必須執行此工作流：
- 新增或移除模組 / 服務
- 架構圖（Mermaid）更新
- 資料流或 API 路徑變更
- 新增 Design Pattern（如 Adapter、Factory）
- 領域模型 (Domain Model) 變更

## 執行步驟 (Steps)

### 1. 辨識影響範圍 (Impact Analysis)
// turbo
1. 讀取當前 walkthrough.md 的「Changes made」區塊
2. 列出所有被修改的核心模組與服務名稱
3. 使用 `grep_search` 搜尋 `wiki/` 目錄中提及這些模組的文件，產出影響清單

### 2. 逐文件迴圈式填補 (Iterative Patching Loop)
// turbo
依照 `.agent/rules/documentation-standards.md` 的 §1.3「迴圈式填補迭代」規則：

1. 逐一開啟受影響的 Wiki 文件
2. 以「段落校對」方式，針對有變更的章節做精確修訂（手術式增補，嚴禁整頁重寫）
3. 若新增了架構設計，必須加入 Mermaid 圖表（流程圖 / 循序圖 / 架構圖）
4. 驗證 Mermaid 語法正確且可渲染
5. 確認雙語格式：英文優先撰寫，繁體中文置於對應段落上方
6. 確認迭代紀錄 (Version History) 已更新於文件頂部

### 3. 扁平化連結驗證 (Flat-Link Verification)
// turbo
1. 確認所有新增或修改的內部連結遵循 `[Label](PageName)` 格式
2. 嚴禁使用 `../`、資料夾路徑或 `.md` 副檔名
3. 確認 `wiki/_Sidebar.md` 中有新文件的導航連結（若為新增文件）

### 4. README 增量檢視 (README Loop Enrichment)
// turbo
依照 `.agent/rules/documentation-standards.md` 的 §2.1「循環增量」規則：

1. 檢視 `README.md`，判斷本次架構變更是否值得更新
2. 若是，以迴圈式增量方式將亮點融入現有結構
3. 確保架構圖（Mermaid）與功能列表保持最新

### 5. 同步驗證 (Sync Validation)
// turbo
1. 執行 `git status` 確認所有 Wiki 變更已暫存
2. 確認變更的 Wiki 文件數量合理（通常 1-5 個）
3. 提示使用者：「Wiki 文檔已更新，是否一起 commit？」
