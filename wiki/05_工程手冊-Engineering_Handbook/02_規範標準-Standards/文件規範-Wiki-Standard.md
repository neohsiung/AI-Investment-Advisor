# 文件規範 (Wiki Standard)

本文件定義專案 Wiki 的建立與維護規範，旨在確保文件的一致性、可讀性與維護性。所有新增或修改的文件皆須遵循此規範。
This document defines the standards for creating and maintaining the project Wiki, ensuring consistency, readability, and maintainability. All new or modified documents must follow these guidelines.

## 1. 檔案命名 (File Naming)

*   **格式 (Format)**: `{繁體中文}-{英文}.md`
    *   `{Traditional Chinese}-{English}.md`
*   **規則 (Rules)**:
    *   **繁體中文 (Traditional Chinese)**: 使用精簡的中文詞彙描述主題。
    *   **英文 (English)**: 使用 PascalCase 或 hyphen-separated (kebab-case) 英文詞彙，需與中文對應。
    *   **連接符號 (Separator)**: 使用半形連字號 `-` 連接中英文與單字。
    *   **數字前綴 (Numeric Prefixes)**: 
        *   **檔案 (Files)**: 禁止使用數字作為開頭 (No numeric prefixes for filenames)。禁止在檔名中包含版本號 (e.g., v3.7)，版本控制應於文件內部的「版本紀錄」表格維護 (No version numbers in filenames; manage versions within the document's Version History)。
        *   **資料夾 (Folders)**: 必須包含數字前綴以符合顯示順序 (Must use numeric prefixes for ordering)，格式為 `XX_名稱`。
    *   **禁止 (Forbidden)**: 禁止使用空格、特殊符號 (底線 `_` 僅限於資料夾命名)。
*   **範例 (Examples)**:
    *   ✅ `系統概觀-System-Overview.md`
    *   ✅ `01_使用手冊` (資料夾)
    *   ❌ `01-系統概觀.md` (檔案不應有數字)
    *   ❌ `SystemOverview.md` (缺少中文)

## 2. 內容結構 (Content Structure)

*   **雙語並列 (Bilingual)**:
    *   所有標題與關鍵段落原則上應採「先繁體中文，後英文」的方式呈現。
    *   **排版佈局 (Layout)**:
        *   **上半部 (Top Half)**: 繁體中文版本 (Traditional Chinese Version).
        *   **下半部 (Bottom Half)**: 英文版本 (English Version).
        *   **分隔線 (Separator)**: 使用 `---` 分隔兩種語言。
    *   **撰寫建議 (Workflow/Mandatory)**: 所有文件必備先完成英文內容（確保技術精確度與全球化通用性），再翻譯為中文置於文件上方。
    *   First Traditional Chinese (Top), then English (Bottom).
*   **行文風格 (Writing Style)**:
    *   **一文一事 (One Topic Per Doc)**: 每份文件應專注於單一主題。
    *   **簡明扼要 (Concise)**: 避免冗長贅述，使用列點 (Bullet points) 輔助說明。
    *   **專有名詞 (Terminology)**: 首次出現的專有名詞或系統組件，應補上 Wiki 內部連結 `[[檔名|顯示名稱]]` 或 `[顯示名稱](相對路徑)`。
*   **目錄結構 (Folder Structure)**:
    *   依照「目標讀者 (Target Audience)」為最上層分類。
    *   資料夾命名同樣建議遵循編號 `{數字}_{中文}_{英文}` (視情況可簡化英文或不含中文，但建議已易讀為準)。
    *   **資料夾分類與定義 (Folder Categories & Definitions)**:
        *   `01_使用手冊` (User Manual):
            *   **Target**: End Users.
            *   **Content**: How to use the application, feature guides, FAQ.
        *   `02_產品經理` (Product Manager):
            *   **Target**: PMs, Stakeholders.
            *   **Content**: PRD, Roadmap, User Stories, Business Logic Specs.
        *   `03_開發者指南` (Developer Guide):
            *   **Target**: New & Existing Developers.
            *   **Content**: **Onboarding**, **Environment Setup**, Local Deployment, Testing Guide, API Usage (How-to).
        *   `04_架構觀點` (Architect View):
            *   **Target**: Architects, Tech Leads.
            *   **Content**: High-level System Design, C4 Diagrams, Security Audits, Infrastructure decisions.
        *   `05_工程手冊` (Engineering Handbook):
            *   **Target**: All Engineers.
            *   **Content**: **Reference Manuals**, Design Patterns, Coding Standards, Best Practices (The "Why" and "What", not just "How-to Setup").

## 3. 連結與導航 (Links & Navigation)

*   **雙向連結 (Bi-directional Links)**: 若兩份文件高度相關 (如「API 規格」與「資料庫 Schema」)，應在文件末尾或相關章節互相參照。
*   **側邊欄 (Sidebar)**: 主要文件應列入 `_Sidebar.md` 以利導航。

---

## 4. 文件迭代與版本控制 (Iteration & Versioning)

*   **整合現有架構 (Integration)**:
    *   新文件應優先融入現有架構 (.md 檔案)，盡量避免新建檔案，除非該主題具有獨立且完整的敘事性。
    *   若需新建檔案，命名須嚴格遵循「一文一事」原則與命名規範。

### 4.1 迴圈式填補迭代 (Iterative Patching Loop)
*   **核心機制**: 更新文件時，嚴禁一次性大範圍重寫。應採用「迴圈 (Loop)」模式，針對文件中的各個相關段落進行局部的「補丁式 (Patching)」更新。
*   **上下文保留**: 這種方式能確保在引入新功能的同時，保留原有的歷史背景與技術細節，達成新舊資訊的無縫接軌。
*   **Mechanism**: Wholesale rewrites are strictly forbidden. Use an iterative "loop" approach to patch specific sections or paragraphs throughout the document, ensuring new features are integrated while preserving valuable context.
*   **版本紀錄 (Version History)**:
    *   **位置**: 文件頂部或尾部 (建議頂部)。
    *   **內容**: 記錄每次重大迭代的原因 (Why) 與內容 (What)。
    *   **保留原則**: 僅保留最近 5 筆迭代紀錄 (Last 5 iterations only)。
    *   **格式**:
        ```markdown
        ### 版本紀錄 (Version History)
        | Date | Version | Description | Author |
        | :--- | :--- | :--- | :--- |
        | 2024-01-20 | v1.2 | Added MCP integration details | Neo |
        | 2024-01-10 | v1.1 | Refactored for v3.0 specs | Neo |
        ```

## 5. 語言工作流 (Language Workflow)

*   **撰寫順序 (Writing Order)**:
    1.  優先撰寫或更新 **英文 (English)** 內容，確保技術精確度。
    2.  將英文內容翻譯為 **繁體中文 (Traditional Chinese)**。
    3.  將繁體中文內容置於文件段落的上方 (Top)，英文在下方 (Bottom)。
*   **維護 (Maintenance)**: 每次更新時，須同步更新雙語內容。

---

## 6. 敏捷文件政策 (Agile Documentation Policy)

*   **去月份化 (No Deadlines)**: 針對未完成的未來特性，嚴禁加上固定月份或季度。使用「迭代 (Iteration)」或「里程碑 (Milestone)」取代。
*   **代碼對齊 (Code Alignment)**: 文件的進度描述必須與 `src` 代碼庫實際狀態同步。定期審計 `src` 已完成功能並更新里程碑標記 `[x]`。
*   **持續精進**: 文件為活動實體，應隨研究發現（如 OpenClaw/Kimi 研究）即時迭代最佳實踐與規格。

## 7. 範例 (Template)

```markdown
# 範例標題 (Example Title)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2024-02-07 | v1.0 | Initial Release | Neo |

---

這裏是繁體中文的內容描述。
Here is the content description in English.

## 章節一 (Section 1)

繁體中文描述...
English description...

*   關鍵點 A (Key Point A)
*   關鍵點 B (Key Point B)

參閱: [首頁](Home)
See also: [Home](Home)
```

## 8. 技術計畫文件規範 (Technical Plan Documentation Standards)

*   **圖表與設計原則 (Diagrams & Design Principles)**:
    *   所有涉及技術實作的計畫 (Plan) 或設計文件，必須根據內容提供相應的圖表以輔助說明，並列出設計原則。
    *   All technical plans or design documents must include relevant diagrams and design principles.
    *   **必要項目 (Required Items)**:
        *   **流程圖 (Flowchart)**: 描述業務邏輯或數據流向 (Describe business logic or data flow).
        *   **循序圖 (Sequence Diagram)**: 描述系統組件間的時間序列互動 (Describe chronological interactions between components).
        *   **架構圖 (Architecture Diagram)**: 描述系統整體結構與邊界 (Describe overall system structure and boundaries).
        *   **設計原則 (Design Principles)**: 明確列出採用的設計模式與原則 (Explicitly list adopted design patterns and principles, e.g., SOLID, DDD).
