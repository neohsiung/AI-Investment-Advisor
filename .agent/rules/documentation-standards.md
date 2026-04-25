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
本專案嚴格依循 [文件框架定義](文件框架定義-Document-Frameworks) 與 [文件規範](文件規範-Wiki-Standard) 實施雙語工作流：
- **撰寫順序 (Writing Order)**:
  1. **英文優先 (English First)**: 先以專業、具備產業規格的英文撰寫或更新內容，確保技術精確度與全球化通用性。
  2. **中文翻譯 (Traditional Chinese Translation)**: 完成英文後，完整翻譯為繁體中文。
- **排版佈局 (Layout)**: 必須將繁體中文內容置於對應段落的上方 (Top)，英文放置於下方 (Bottom)。
- **迭代紀錄 (Version History)**: 位於文件頂部，記錄最近 5 次重大變動（Date, Version, Description, Author）。
- ** additive 原則**: 除非結構崩壞，否則更新應視為疊加與增量，嚴禁隨意重寫以保留歷史背景。

### 1.3 視覺化與精簡原則 (Visual & Concise Rule) - **核心規則**
- **Mermaid 優先 (Mermaid First)**: 若有方便說明的架構、狀態轉換、操作流程或組件關聯，**必須優先採用 Mermaid 圖表** (如 `graph TD`, `sequenceDiagram`, `classDiagram`) 進行表達。
- **文字極簡化 (Text Minimalism)**: 文字應僅用於「小結 (Summaries)」與「關注重點 (Key Highlights)」。絕對避免長篇大論的文字堆砌 (Walls of Text)。
- **現代化 Markdown 排版**: 盡可能善用 Markdown 的列表、GitHub-flavored alerts (`> [!NOTE]`, `> [!IMPORTANT]`) 與粗體標示，參考業界 Best Practice 進行排版以提升閱讀體驗。
- **Surgical Additions**: 更新文件時請以局部填補取代全盤覆蓋，確保上下文一致性。

### 1.5 本地專屬文件標準 (Local-Only Document Standard)
- 當使用者要求「產出文檔但不要放到 GitHub 上」或標記為「Local-Only」時：
  1. 檔案依舊產生於對應的 `wiki/` 目錄中。
  2. **嚴禁**將該檔案連結加入到 `wiki/_Sidebar.md` 或 `wiki/Home.md` 之中。
  3. **必須**將該檔案名稱 (或路徑) 加到 `wiki/.gitignore` 中，確保它永遠不會被 commit 回 GitHub 遠端庫。

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

## 3. 智能體產出物標準 (Agentic Artifacts Standards)

本項標準適用於所有由 Agent 產出的階段性文件，包括 `implementation_plan.md` (Plan)、`task.md` (Task) 與 `walkthrough.md` (Walkthrough)。

### 3.1 雙語撰寫與翻譯流程 (Bilingual Workflow)
- **撰寫順序 (Writing Order)**: 
  1. **英文優先 (English First)**: Agent 必須先以專業英文完成上述文件的內容撰寫與更新。
  2. **繁體中文化 (Traditional Chinese Translation)**: 完成英文版後，必須立即將內容完整翻譯為繁體中文。
- **排版要求 (Layout)**: 必須確保繁體中文與英文內容並列或分區清晰，方便使用者核對。

---

## 4. 同步規範 (Sync Rules - Rule #12)
- **原子化同步**: 代碼變更、Commit 文檔、Wiki 更新、README 亮點增補必須在同一週期內完成同步。
