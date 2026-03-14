---
description: 在開始開發新功能或串接服務前，強制執行的架構與體驗檢核流程 (Feature Implementation Preflight Check)
---

# Feature Implementation Preflight Workflow

## 目的 (Purpose)

避免 Agent 陷入「盲目開發」的困境。在每次開發具體功能前，強制檢查系統架構、文件定義與使用者體驗 (UI/UX)，確保每次的 Vibe Coding 都是建立在全局視角上進行的。這能大幅減少反覆溝通與重工的浪費。

## 觸發時機 (When to Run)

- ✅ 使用者要求串接新的 API 或資料源時 (e.g. "幫我把 Readwise 接進來")
- ✅ 使用者要求新增 Agent 功能時
- ✅ 任何涉及系統架構變動的開發前

## 執行步驟 (Steps)

### 1. 閱讀架構文件 (Architecture Scan)

Agent 必須先閱讀以下目錄中的相關文件：
- `wiki/04_架構觀點-Architect_Views/`
- `wiki/05_工程手冊-Engineering_Handbook/`

> **Check**: 該功能屬於現有哪一個模組的管轄範圍？是 Polling 還是 Webhook 觸發？是否涉及使用者認證？(若涉及，必須遵循 FastAPI Auth Hub 模式)。

### 2. 檢視現有實作 (Pattern Matching)

尋找系統內是否已經有類似的介面或類別。

- 例如：資料源應繼承 `MarketDataProvider`。
- 例如：新功能若需要設定，應整合到 `SettingsService`。

### 3. 設計 UI/UX 體驗 (UX Empathy)

**(最重要)** 永遠不要只寫後端邏輯！如果新功能需要設定，**必須**包含前端介面。
- 尋找 `services/dashboard/src/pages/settings_tabs/` 中的對應檔案。
- 確認是否需要新增 Toggle (開關) 或 API Key 輸入框。

### 4. 提出實作計畫 (Implementation Plan)

在 `.gemini/` 目錄建立 `implementation_plan.md`，並透過 `notify_user` 向使用者確認計畫，計畫內必須包含前端 UI 變更與後端架構變更的對應關係。

---
只有在使用者的確認後，才允許正式修改專案程式碼。
