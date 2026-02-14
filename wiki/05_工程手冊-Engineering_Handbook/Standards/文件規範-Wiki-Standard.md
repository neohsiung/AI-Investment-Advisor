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
    *   **禁止 (Forbidden)**: 禁止使用空格、特殊符號 (底線 `_` 僅限於資料夾排序前綴，如 `01_`).
*   **範例 (Examples)**:
    *   ✅ `系統概觀-System-Overview.md`
    *   ✅ `資料庫架構-Database-Schema.md`
    *   ❌ `SystemOverview.md` (缺少中文)
    *   ❌ `系統概觀.md` (缺少英文)
    *   ❌ `系統概觀_System_Overview.md` (連接符錯誤)

## 2. 內容結構 (Content Structure)

*   **雙語並列 (Bilingual)**:
    *   所有標題與關鍵段落原則上應採「先繁體中文，後英文」的方式呈現。
    *   **排版佈局 (Layout)**:
        *   **上半部 (Top Half)**: 繁體中文版本 (Traditional Chinese Version).
        *   **下半部 (Bottom Half)**: 英文版本 (English Version).
        *   **分隔線 (Separator)**: 使用 `---` 分隔兩種語言。
    *   **撰寫建議 (Workflow)**: 建議先撰寫英文內容以確保技術精確度，再翻譯為中文置於文件上方。
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

## 6. 範例 (Template)

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

參閱: [首頁](首頁-首頁-Home.md)
See also: [Home](首頁-首頁-Home.md)
```
