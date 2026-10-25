<!-- 描述以繁體中文為主、英文為輔：頂部附 2–4 行 English summary；指令、路徑、識別名稱、錯誤訊息保持英文。見 .agent/rules/documentation-standards.md §1.2b -->

風險級 / Risk tier：<R0|R1|R2|R3>
<!-- R0 docs ｜ R1 non-decision code/UI/tests ｜ R2 decisions/config/schema/prompts/migrations/routing ｜ R3 money-moving (broker, risk gateway, capital policy, mission.yaml)。R3 agent 不動手，只提案；路徑見 .github/CODEOWNERS，規則見 dev-standard §2 -->

Refs #<issue>   <!-- 完整做完才用 Closes #N -->

## 變更摘要 / Summary

## 對 `config/mission.yaml` 哪個指標有何預期影響？如何量測？ / Mission impact & how it is measured
<!-- Required for R2/R3. "No measurable impact" is a valid answer only for R0/R1. -->

## 驗證指令 / Verification
<!-- 每個「系統在某情況下會怎樣」的描述都要有可重跑的指令。跑不了的寫成推論並說明依據。 -->

## Wiki 統整 / Wiki synthesis
<!-- 列出新增或更新的 wiki 頁面；若無需更新，寫「無需更新」與理由。 -->

## 回滾方式 / Rollback

## 檢查清單 / Checklist
- [ ] `pytest tests/invariants tests/unit/config tests/unit/deploy` 通過
- [ ] `scripts/ci_local.sh` 通過（Alembic upgrade+check、Bandit、wiki 連結；新增資料表時必跑）
- [ ] 未新增寫死分數、未新增繞過 executor 的下單呼叫、未新增 `exec`
- [ ] 若修改 mission.yaml：已新增 ADR 條目
- [ ] 文件未寫入會漂移的數字（交易筆數、成本、上限）
- [ ] `python3 .dev-standard/sync.py check` 與 `python3 scripts/ruff_baseline.py check` 通過（沒有新增 lint 違規）
- [ ] 重構與行為改變在不同 commit；重構的 commit 沒有改測試
- [ ] 依 [審查清單](https://github.com/neohsiung/dev-standard/blob/main/templates/review-checklist.md) 自查過設計原則

DERIVED: <這次學到、以後每個任務都該遵守的約束，以及它落在哪裡（規則檔／守衛測試／ADR）>　通用：<是｜否>
<!-- 通用：是 → 同一週對 dev-standard 開回填 PR，連回這個 PR -->
