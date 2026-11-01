<!-- 由 dev-standard v0.7.2 產生，請勿手改；要改請改 dev-standard 的 components/pr-template，再跑 sync.py update -->
風險級：<R0|R1|R2|R3>   <!-- R0 docs ｜ R1 非決策的程式／UI／測試 ｜ R2 決策、設定、schema、prompt、migration、路由 ｜ R3 動錢（券商、風控閘道、資金政策、mission.yaml），agent 不動手只提案；路徑見 .github/CODEOWNERS -->

Refs #<issue>   <!-- 完整做完才用 Closes #N；只做一部分用 Refs #N 並在 issue 留言剩什麼 -->

## 做了什麼

## 驗證
<!-- 每個「系統在某情況會怎樣」的說法都附可重跑的指令。跑不了的寫成推論並說明依據。 -->

## 對 `config/mission.yaml` 哪個指標有何預期影響？如何量測？ / Mission impact
<!-- R2／R3 必填；「無可量測影響」只適用 R0／R1 -->

## 文件統整 / Docs synthesis
<!-- 列出新增或更新的 docs/ 頁面；若無需更新，寫「無需更新」與理由 -->

## 回滾方式
<!-- R2／R3 必填 -->

## 檢查清單
- [ ] 綠燈（`.claude-task/green.sh` 或本 repo 的測試指令）
- [ ] `python3 .dev-standard/sync.py check` 通過
- [ ] 沒有新增 lint 違規（baseline 以外）
- [ ] 重構與行為改變在不同 commit；重構的 commit 沒有改測試
- [ ] 改了門檻、規則或契約 → 同一個 commit 附 DD
- [ ] 文件沒有寫會漂移的數字
- [ ] 依 [審查清單](https://github.com/neohsiung/dev-standard/blob/main/templates/review-checklist.md) 自查過設計原則
- [ ] 描述以繁體中文為主，頂部附 2–4 行 English summary；指令、路徑、識別名稱、錯誤訊息保持英文
- [ ] `pytest tests/invariants tests/unit/config tests/unit/deploy` 通過
- [ ] `scripts/ci_local.sh` 通過（Alembic upgrade+check、Bandit、文件連結；新增資料表時必跑）
- [ ] 未新增寫死分數、未新增繞過 executor 的下單呼叫、未新增 `exec`
- [ ] 若修改 mission.yaml：已新增 ADR 條目

DERIVED: <這次學到、以後每個任務都該遵守的約束，以及它落在哪裡（規則檔／守衛測試／地雷編號）>　通用：<是｜否>
<!-- 通用：是 → 同一週對 dev-standard 開回填 PR，連回這個 PR -->
