---
name: Feature Implementation Preflight Check
description: 強制 Agent 在撰寫程式前，進行全局架構掃描與 UI/UX 確認，避免盲目開發與無效來回溝通。
---

# Feature Implementation Preflight Check

## 📖 Skill 核心理念 (Core Philosophy)
本 Skill 旨在規範 Agent 行為，解決「未充分了解系統」、「自生造輪子」、「忽略設定用介面 (UI)」等常見開發浪費。

當使用者提出一個「新增功能」、「串接 API」或「修改資料管線」的要求時，Agent 絕不能只著眼於單點類別的修改，必須啟動此 Preflight (起飛前) 確認流程。

## 🎯 執行指導手冊 (Execution Guidelines)

### Step 1: 架構先決 (Architecture First)
1. 操作: 必須閱讀 `wiki/04_架構觀點-Architect_Views` 下相關的文件。
2. 目標: 定義本次開發功能是屬於系統的哪個模組 (Data Layer, Swarm Layer, API Gateway...)？

### Step 2: 模式沿用 (Pattern Matching)
1. 操作: 針對需求核心，全局 Search codebase。
2. 目標:
   - 若是串接外部資料源，必須繼承 `src/data/providers/base.py` 內的 `MarketDataProvider`。
   - 若是設定變數，必須整合至 `src/services/settings_service.py`。
   - 若有設定檔矩陣 (如 `data_source_matrix_config.py`)，必須更新該矩陣。

### Step 3: 體驗共感設計 (UX Empathy Design)
**(最重要環節)** 
1. 操作: 檢視 `services/dashboard/src/pages/` 下的頁面佈局。
2. 目標: 評估這項功能在 Dashboard 會長什麼樣子。你需要主動建立一個 Toggle (開關)，或是增加 API Key 輸入框，絕對不能只修改後端邏輯而把 UI 留給使用者自己頭痛。

### Step 4: 規劃對齊 (Alignment & Approval)
1. 操作: 產出 `implementation_plan.md`，使用 Markdown 將預定要更改的前後端模組與檔案清楚表列。
2. 目標: 透過 `notify_user`，請使用者說 "Go" 或確認你的 Blueprint 之後，再寫下第一行 Python 程式碼。

---
🛡️ **防雷提醒**: 勿預設立場跳過上述任何一步驟，一次「慢工出細活」的對齊勝過十次「搞砸重做的程式碼修改」。
