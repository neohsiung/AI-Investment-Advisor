---
name: Plan Governance
description: Plan Governance — 單一 Session 內計劃變更控制規則
---

# Plan Governance (計劃治理規則)

## 核心原則

在同一個 Session（Conversation）中，Agent **不得任意改變已經核准的 Implementation Plan**。

## 允許的行為

1. **優化 (Optimization)**：在不改變計劃範圍與架構的前提下，改善實作細節（例如：更好的演算法、更精簡的代碼）。
2. **迭代 (Iteration)**：在核准範圍內，根據實作過程中的發現，補充或細化原計劃中未提及的技術細節。
3. **Bug 修復 (Bug Fix)**：修復在實作過程中發現的程式碼缺陷，但修復範圍不得超出原計劃的檔案影響範圍。
4. **分支合規性 (Branch Compliance)**：計畫核准後，實作者必須先檢查並確認切換至獨立的 Feature Branch 執行，確保主幹不被破壞。

## 禁止的行為（需使用者核准）

以下行為**必須先說明改變原因並取得使用者同意**才可執行：

1. **範圍變更 (Scope Change)**：增加或移除原計劃中的功能模組。
2. **架構變更 (Architecture Change)**：改變資料流、新增/刪除資料表、替換核心元件。
3. **推翻決策 (Decision Reversal)**：推翻已在計劃中明確做出的技術決策（例如：從 File 改為 DB 儲存）。
4. **Phase 跳轉 (Phase Skip)**：跳過或合併原計劃中的 Phase。

## 執行流程

```markdown
發現需要變更 → 停止實作 → 產出變更說明（含原因、影響、替代方案）→ 等待使用者審閱 → 核准後繼續
```
