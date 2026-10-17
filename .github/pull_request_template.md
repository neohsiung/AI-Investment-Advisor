## 變更摘要 / Summary

## 風險等級 / Change-risk tier  (check one)
- [ ] R0 docs  - [ ] R1 non-decision code/UI/tests  - [ ] R2 decisions/config/schema/prompts/migrations/routing  - [ ] R3 money-moving (broker, risk gateway, capital policy, mission.yaml)

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
