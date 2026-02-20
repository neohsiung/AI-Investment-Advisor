# 文檔維護標準 (Documentation Standards)

本文件定義 Wiki 與 README 的維護標準，確保專案文檔始終作為「開發藍圖」與「規格來源」。

---

## 1. Wiki 標準 (Wiki Standards)

### 1.1 檔案命名與結構
- **命名規則**: `{繁體中文}-{英文}.md`。禁止在檔名中使用數字前綴。
- **目錄規則**: 資料夾必須以 `XX_名稱` 數字開頭以維持顯示順序。
- **一文一事**: 每份文件應專注於單一主題，避免內容冗長。

### 1.4 扁平化連結 (Flat-Linking Standard)
- **核心格式**: 所有內部連結必須使用 `[Label](PageName)` 格式。
- **路徑規範**: 嚴禁使用資料夾路徑（如 `../` 或 `01_Manual/`）及 `.md` 副檔名。
- **雙向一致性**: 指向文件的名稱必須與該文件的 `basename`（不含副檔名）完全一致，確保在 GitHub Wiki 中具備正確的雙向導航功能。

### 1.2 雙語並列與撰寫順序 (Bilingual Workflow)
本專案嚴格依循 [文件框架定義](wiki/00_規則規範-Rules/文件框架定義-Document-Frameworks.md) 與 [文件規範](wiki/00_規則規範-Rules/文件規範-Wiki-Standard.md) 實施雙語工作流：
- **撰寫順序 (Writing Order)**:
  1. **英文優先 (English First)**: 先以專業、具備產業規格的英文撰寫或更新內容，確保技術精確度與全球化通用性。
  2. **中文翻譯 (Traditional Chinese Translation)**: 完成英文後，完整翻譯為繁體中文。
- **排版佈局 (Layout)**: 必須將繁體中文內容置於對應段落的上方 (Top)，英文放置於下方 (Bottom)。
- **迭代紀錄 (Version History)**: 位於文件頂部，記錄最近 5 次重大變動（Date, Version, Description, Author）。
- ** additive 原則**: 除非結構崩壞，否則更新應視為疊加與增量，嚴禁隨意重寫以保留歷史背景。

### 1.3 迴圈式填補迭代 (Iterative Patching Loop) - **核心規則**
- **視覺化指導原則 (Visual Documentation Rule)**: 新增技術設計或操作說明時，必須 **加上流程圖 (Flowcharts)、循序圖 (Sequence Diagrams)、架構圖 (Architecture Diagrams)** 等 Mermaid 圖表來展示邏輯。在將圖表加入 Wiki 之前，Agent 必須驗證語法與雙向結構正確無誤，確保圖表能被 UI 渲染。
- **微調而非重寫**: 更新單一文件時，應以「迴圈 (Loop)」形式針對每一個段落進行填補與調整，而非一次性大範圍覆蓋。
- **段落校對**: 每次技術迭代後，需對應 Wiki 中所有相關文件的段落進行掃描，確保新舊資訊邏輯自洽，達成精確的「手術式增補」。
- **Surgical Additions**: When updating documents, use a loop-based approach to patch individual sections or paragraphs specifically, rather than performing wholesale rewrites. Scan all affected sections after each technical iteration to ensure contextual consistency.

---

## 2. README 門戶標準 (README Portal Standards)

`README.md` 應被視為專案的「技術名片」，必須展現極高的專業度與視覺吸引力。

### 2.1 撰寫原則 (The Golden Rules)
- **視覺優先 (Aesthetics First)**: 使用精心挑選的徽章 (Badges)、Mermaid 圖表與清晰的分隔線。避免純文字堆砌。
- **內容淬鍊 (Content Distillation)**: 內容應從 Wiki 深度文件中「淬鍊」精華，而非簡單複製。確保每個章節都能引發讀者對 Wiki 的進一步探索好奇。
- **循環增量 (Loop Enrichment)**: **(Premium Approach)** 每次功能更新後，應以「回圈式」檢視 README，思考如何將新功能的亮點融入現有結構，使內容日益豐富。
- **雙語工作流 (Bilingual Loop)**:
    1. **英文優先**: 先以專業、具備產業規格的英文撰寫。
    2. **中文翻譯**: 完整翻譯為繁體中文，並將中文內容置於對應章節的頂部。

### 2.2 必要元素結構
1. **傳送門連結**: 置於頂部的繁體中文/English 快速導航。
2. **視覺徽章區**: CI 狀態、關鍵技術棧徽標。
3. **專案概覽**: 核心價值主張與 3-5 個高亮亮點。
4. **一鍵啟動**: 讓開發者在 30 秒內看到結果的指令。
5. **架構圖**: 具備 Mermaid 渲染的高級架構概覽。
6. **深度導航**: 指向 `wiki/` 目錄的精確分類連結。

---

## 3. 同步規範 (Sync Rules - Rule #12)
- **原子化同步**: 代碼變更、Commit 文檔、Wiki 更新、README 亮點增補必須在同一週期內完成同步。
