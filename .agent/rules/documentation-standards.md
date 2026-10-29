# 文檔維護標準 (Documentation Standards)

本文件定義 `docs/` 與 README 的維護標準，確保專案文檔始終作為「開發藍圖」與「規格來源」。

---

## 1. docs/ 標準 (Docs Standards)

> 舊 GitHub wiki 已退役，技術文件放在 repo 的 `docs/`，跟程式一起走 PR。分工見 `docs/README.md`。

### 1.1 檔案命名與結構
- **命名規則**: `{繁體中文}-{英文}.md`。禁止在檔名中使用數字前綴。
- **目錄規則**: 資料夾必須以 `XX_名稱` 數字開頭以維持顯示順序。
- **一文一事**: 每份文件應專注於單一主題，避免內容冗長。

### 1.4 相對連結 (Relative Links)
- **核心格式**: 內部連結一律用相對路徑，例如 `[系統全景圖](../01_System_Architecture/系統全景圖-System-Landscape.md)`。
- **不用扁平連結**: 不再使用 wiki 的 `[Label](PageName)` 寫法；連結要指到存在的檔案。
- **檢查**: `python .agent/skills/docs-maintainer/scripts/verify_docs_links.py`（有壞連結回傳 1，CI 會跑）。

### 1.2 雙語並列與撰寫順序 (Bilingual Workflow)
本專案依循 `.agent/rules/wiki-standard.md`（分類與命名）實施雙語工作流：
- **撰寫順序 (Writing Order)**:
  1. **英文優先 (English First)**: 先以專業、具備產業規格的英文撰寫或更新內容，確保技術精確度與全球化通用性。
  2. **中文翻譯 (Traditional Chinese Translation)**: 完成英文後，完整翻譯為繁體中文。
- **排版佈局 (Layout)**: 必須將繁體中文內容置於對應段落的上方 (Top)，英文放置於下方 (Bottom)。
- **迭代紀錄 (Version History)**: 位於文件頂部，記錄最近 5 次重大變動（Date, Version, Description, Author）。
- ** additive 原則**: 除非結構崩壞，否則更新應視為疊加與增量，嚴禁隨意重寫以保留歷史背景。

### 1.2a 語言決議（2026-10-17，取代 1.2 的「英文先寫」要求）
- **新文件以繁體中文全文撰寫，頂部附 3–5 行英文摘要（English summary）**，供外部讀者與 agent 快速定位。
- 不再要求每份文件都有完整英文版（兩份全文會各自漂移）；既有雙語文件不強制重寫（維持 additive 原則）。
- 程式碼註解與 commit 訊息仍維持英文＋繁體中文雙語。

### 1.2b PR 描述語言（2026-10-19）
- **PR 描述以繁體中文為主、英文為輔**：變更摘要、風險、驗證說明、回滾方式都用繁體中文寫；描述頂部附 2–4 行 `English summary`。
- 指令、檔案路徑、識別名稱（函式、資料表、設定鍵）、錯誤訊息原文保持英文，不翻譯。
- 理由：審查者是用繁體中文讀的；只有英文描述會讓審查者得自行翻譯，審查重點容易漏看。commit 訊息仍依 `git-commit-format.md` 維持雙語。

### 1.3 視覺化與精簡原則 (Visual & Concise Rule) - **核心規則**
- **Mermaid 優先 (Mermaid First)**: 若有方便說明的架構、狀態轉換、操作流程或組件關聯，**必須優先採用 Mermaid 圖表** (如 `graph TD`, `sequenceDiagram`, `classDiagram`) 進行表達。
- **文字極簡化 (Text Minimalism)**: 文字應僅用於「小結 (Summaries)」與「關注重點 (Key Highlights)」。絕對避免長篇大論的文字堆砌 (Walls of Text)。
- **現代化 Markdown 排版**: 盡可能善用 Markdown 的列表、GitHub-flavored alerts (`> [!NOTE]`, `> [!IMPORTANT]`) 與粗體標示，參考業界 Best Practice 進行排版以提升閱讀體驗。
- **Surgical Additions**: 更新文件時請以局部填補取代全盤覆蓋，確保上下文一致性。

### 1.6 技術文件交付與可讀性（每批開發必做）
> 來源：decision-stack 的可遷移原則（`behavior-claims-are-run-not-reasoned`、`version-bump-needs-the-idea`、
> `recipient-delta-defines-the-artifact`、`an-explanation-must-change-a-next-action`、`a-review-batch-names-what-to-read-first`）。

**何時要寫**：每一批開發（一個 PR 或一組相關 PR）結束時，必須交付一份技術文件並統整 `docs/`；若確實不需要，PR 內寫「無需更新 docs/」與理由。

**寫之前先回答**：這份文件的讀者是誰（維護者／審查者／未來的 agent）？他還缺什麼？只寫那幾項。

**內容規則**
1. **行為描述必須實際跑過，並附驗證指令。** 寫「在某情況下系統會怎樣」之前先執行一次，把指令放在驗證欄；跑不了就寫成推論並說明依據，不寫成直述句。
2. **改既有文件時，開頭寫「這一版換掉了哪個想法」**，而不只是列改了哪幾節；版本沿革表記錄每一版要解的問題。
3. **只放讀者需要知道且尚不知道的內容。** 查證過程、推論鏈、檔案清單留在對話或 commit，不進文件；自檢問句：「砍掉這段，讀者的下一個動作會不同嗎？」
4. **「為什麼」只在會改變未來動作時才寫**，並落在提交說明、規範或原則庫；成因寫成規則或檢查，而不只是一段文字。
5. **圖優先**：架構／狀態／時序／控制迴圈一律用 Mermaid；每張圖下方用一兩句話講「讀這張圖該注意什麼」。
6. **不寫會漂移的數字**（交易筆數、成本、上限）；需要時寫查詢方式（API 或 SQL）。
7. **一批文件的審查順序要先講**：這批的目的、先看哪一份、每份只列位址。

**文件骨架（建議）**：英文摘要 3–5 行 → 這一版換掉的想法 → 一張總覽圖 → 行為表（情境／結果／驗證指令）→ 失效模式與回滾 → 相關頁面連結。

**docs/ 統整清單（每批結束檢查）**：新增或修改的頁面是否已在 `docs/Home.md` 或 `docs/README.md` 連結？`verify_docs_links.py` 通過？文件與程式在同一個 PR，不需另行 commit。

### 1.5 本地專屬文件標準 (Local-Only Document Standard)
- 當使用者要求「產出文檔但不要放到 GitHub 上」或標記為「Local-Only」時：
  1. 檔案放在 `scratch/` 或 `reports/`（兩者都在 `.gitignore`），不放進 `docs/`（`docs/` 全部進版控且公開）。
  2. **嚴禁**從 `docs/` 或 README 連結到這些檔案。

---

## 2. README 門戶標準 (README Portal Standards)

`README.md` 應被視為專案的「技術名片」，必須展現極高的專業度與視覺吸引力。

### 2.1 撰寫原則 (The Golden Rules)
- **視覺優先 (Aesthetics First)**: 使用精心挑選的徽章 (Badges)、Mermaid 圖表與清晰的分隔線。避免純文字堆砌。
- **內容淬鍊 (Content Distillation)**: 內容應從 `docs/` 深度文件中「淬鍊」精華，而非簡單複製。確保每個章節都能引發讀者對 `docs/` 的進一步探索好奇。
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
6. **深度導航**: 指向 `docs/` 目錄的精確分類連結。

## 3. 智能體產出物標準 (Agentic Artifacts Standards)

本項標準適用於所有由 Agent 產出的階段性文件，包括 `implementation_plan.md` (Plan)、`task.md` (Task) 與 `walkthrough.md` (Walkthrough)。

### 3.1 雙語撰寫與翻譯流程 (Bilingual Workflow)
- **撰寫順序 (Writing Order)**:
  1. **英文優先 (English First)**: Agent 必須先以專業英文完成上述文件的內容撰寫與更新。
  2. **繁體中文化 (Traditional Chinese Translation)**: 完成英文版後，必須立即將內容完整翻譯為繁體中文。
- **排版要求 (Layout)**: 必須確保繁體中文與英文內容並列或分區清晰，方便使用者核對。

---

## 4. 同步規範 (Sync Rules - Rule #12)
- **原子化同步**: 代碼變更、Commit 文檔、`docs/` 更新、README 亮點增補必須在同一週期內完成同步。
