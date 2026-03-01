# Agent 開發起飛準則 (Agent Preflight Standards)

本文件提煉自過往開發的反思 (Postmortem)，旨在解決「不必要的來回溝通浪費」、「文件未充分閱讀」、「未釐清現有架構即進行開發」以及「忽略 UI/UX 體驗」等核心問題。

所有 Agent 在接收到使用者任何「新增功能、串接資料或是修改架構」的需求時，**必須無條件遵守**以下四步起飛檢核 (Preflight Check)：

## 1. 架構閱讀優先 (Read First, Code Later)
- **禁止盲目開發**: Agent 在著手撰寫任何程式碼之前，必須先尋找並閱讀相應的架構文件 (位於 `wiki/04_架構觀點-Architect_Views` 或 `wiki/05_工程手冊-Engineering_Handbook`)。
- **全局觀念**: 在處理單點功能 (e.g. 串接一個 API) 時，必須理解它在全局中的位置 (例如它是 Polling 還是 Webhook？它是由哪一個 Controller 負責調用的？)。

## 2. 介面與體驗共識 (UI/UX Empathy)
- **全端思維**: 任何後端的資料源新增或配置改變，都**必須**具備對應的前端管理介面 (UI) 或終端機互動設計。
- **主動提議體驗**: 若使用者要求加入新的 API 或功能，Agent 必須主動思考：「使用者未來該如何在儀表板 (Dashboard) 上開關此功能？」、「需不需要在 Settings 建立輸入框供使用者填寫 API Key？」並主動實作，而非等待使用者追問。

## 3. 現存模式沿用原則 (Pattern Reuse)
- **尋找既有解法**: 在發明新的類別或方法前，先使用 `grep_search` 掃描相似的模組。例如新增數據源時，應發現系統內已有 `MarketDataProvider` 介面，並嚴格繼承，而非自己發明一套獨立的方法。
- **一致性 (Consistency)**: 若現有架構存在統一的配置管理器 (如 `SettingsService` 或 `data_source_matrix_config.py`)，新功能的屬性必須被整合進該管理器。

## 4. 提出計畫並獲取確認 (Plan and Confirm)
- 當對齊文件與架構後，Agent 應在 `.gemini` 腦區產生一份 `implementation_plan.md`，清楚說明將修改哪些前端介面、哪些後端服務，以及符合什麼架構模式。
- **利用 `notify_user` 請求審核**: 在動手寫程式前，簡潔地向使用者確認該計畫的 UI 藍圖與架構。

---
**違反此準則將會導致架構混亂與使用者對 Agent 的信任流失，這在 Vibe Coding 的過程中是絕對零容忍的。**
