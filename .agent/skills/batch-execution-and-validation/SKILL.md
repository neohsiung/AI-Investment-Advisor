---
name: batch-execution-and-validation
description: Antigravity 互動優化守則：強制批量操作與靜默自檢。
version: 1.0.0
category: meta-skill
tier: smart
---
# Antigravity 互動優化守則 (Batch Execution & Self-Diagnostic)

本守則旨在降低 Agent 與使用者之間的冗餘來回，提升開發效率與品質。

## 核心準則

1. **批量操作 (Batch Execution)**:
   - 當任務涉及多個相似檔案（如重構所有 Skill 目錄）時，Agent 必須在單次 Thought Block 或連續的工具呼叫鏈中完成所有變更。
   - 禁止修改一個檔案就請求一次使用者確認。

2. **靜默自檢 (Silence on Success / Self-Diagnostic)**:
   - 在宣稱任務完成或 Phase 結束前，Agent **必須** 撰寫並執行一段驗證腳本（如 Python 或 Shell）。
   - 驗證腳本應檢查：檔案結構完整性、關鍵字匹配（如 YAML 標頭）、或執行單元測試。
   - 只有在自檢「全數通過」後，Agent 才能向使用者報備成功。若有錯誤，應自動修復而非將錯誤噴給使用者。

3. **減少確認 (Reduction of Confirmation)**:
   - 對於非破壞性且符合已核准計畫的結構化調整，Agent 應標記為 `SafeToAutoRun: true` 並直接完成。
   - 僅在最終 Milestone 或發現重大架構衝突時，才摘要回報成果。

## 執行範例
- **錯誤範例**: "我改好了 A 檔案，要繼續改 B 檔嗎？"
- **正確範例**: (靜默執行 A, B, C 的修改) -> (執行驗證腳本證明 A, B, C 皆正確) -> "我已批量完成 A, B, C 的重構，並通過了自動化驗證。"
