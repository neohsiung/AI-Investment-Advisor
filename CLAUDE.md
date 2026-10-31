@AGENTS.md

# CLAUDE.md — Claude Code 專屬說明

<!-- DEV-STANDARD:BEGIN v0.6.1 -->
<!-- 由 dev-standard 的 tools/sync.py 產生。要改規則請改 dev-standard 的 STANDARD.md 再 update；本 repo 自己的差異寫在這個區塊外。 -->
## 開發辦法（精簡版，由 dev-standard 同步，不要在這裡改）

**分支與 PR**
- 不在 main commit、不 push main。一個任務一個分支；會寫檔的 session 或 agent 各用自己的 worktree（`.dev-standard/bin/wt.sh new <type>/<描述>`），唯讀的不開。分支前綴：`feat|fix|refactor|docs|chore|test|ci`，或該 repo 的組織前綴（例：`eng/`、`product/`）。
- 一個 PR 一個連貫範圍：合併後系統自洽。重構與行為改變分開 commit。
- PR 第一行寫風險級 `R0`–`R3`；有 issue 就寫 `Refs #N`（完全做完才用 `Closes #N`）；結尾寫 `DERIVED:` 一行，加上「通用？是／否」。
- 合併依風險級（見下方〈風險級〉合併表），一律 merge commit、不 squash。疊起來的 PR 每一個都合進 main。
- main 與共用分支不 force push。自己的 feature 分支整理歷史後，用 `--force-with-lease=<分支>:<遠端舊 SHA>` 推，推完讀回遠端 SHA 確認等於本機。
- 只做 `git mv` 的 commit 單獨放；有這種 commit 的 PR 不 squash，否則 `git log --follow` 追不回搬檔前的歷史。
- PR 合併後不再往同一分支推；要補就從 main 開新分支、新 PR（pre-push hook 會擋）。

**風險級（看錯了要付多少，不看信心）**
- R0 文件；R1 一般程式、測試、UI；R2 設定、門檻、prompt、schema、migration、部署、hook；R3 會動錢或動正式環境的路徑。
- R3 不開放給 agent：只提案、寫 DD，由人核可或自己執行。R2 要附驗證指令與 reviewer 審查。各 repo 的 R2／R3 路徑樣式寫在 `.dev-standard/risk.json`（也寫進 CODEOWNERS）。
- 級數由腳本依改動路徑算出，不信任 PR 宣告：算出的級高於第一行宣告就紅燈；算出 R3 就不自動合併。
- 合併表（本機 `python3 .dev-standard/bin/pr_checks/run.py <PR> [--merge]`，不需要 GitHub Actions）：

| 級（宣告與路徑取高） | 誰合併 |
|---|---|
| R0、R1 | 七項檢查與 CI 全過，腳本合併 |
| R2 | 同上，另加受信任作者在當前 head 留 `REVIEW: PASS <sha>` |
| R3 | 人。腳本印「R3：要人合併」並拒絕 |

- 根目錄的 `.automerge-off` 是熔斷開關：存在就拒絕自動合併；讀不到它時中止，不當作沒有。合併指令固定 `gh pr merge --merge --match-head-commit <sha> --delete-branch`，不 squash、不用 `--auto`。

**模型分層**
- 主 session 用 Sonnet；Opus 當 advisor，用在三個時點：照計畫動手前、同一件事第二次失敗、宣告完成前。查找類 subagent 用 Haiku，實作與審查類用 Sonnet；深度 1，同時 ≤4 個。
- 6 回合內判斷是不是難題。要換 Opus 就開新 session，交接 ≤20K（任務、失敗的檢查、3 個關鍵檔），不在長 context 中途換模型。
- 角色：查找 `scout`，實作 `implementer`，審查 `reviewer`，卡關設計 `architect`。先用便宜的，失敗才升級。兩個 writer 不碰同一檔。
- 開新 session 或 subagent 一律寫明 model，不繼承主 session：唯讀、照表做的（巡檢、量測、驗證）用 Haiku，實作與維運用 Sonnet，設計為主的才用 Opus。
- Fable 只在使用者點名時用（architect 也失敗、或高風險不可逆的決策）；不做成 agent，不自動升級過去。

**閘門**
- 先寫會失敗的檢查（`.claude-task/green.sh`）再寫碼；連三次紅就停，回報「計畫可能錯了」。改弱檢查要跟人說明。
- 每個「系統在某情況會怎樣」的說法都附可重跑的指令。跑不了的寫成推論並說明依據。
- 改門檻、改規則、改契約，同一個 commit 附 DD。
- 送出去的 PR 描述、留言、訊息也是產出：裡面每個「已補、已改、第 N 行」，對著要推的那一版逐項核對才送；有通過標記才放行送出。
- 迭代檢核只在「本輪新必修為 0」時停，最多兩輪，超過就把剩下的攤給人決定；每輪報告最後一行寫「新必修數：N」。
- 跨天的 worktree、草稿、未 commit 的實作，不放 `/tmp`，也不放被排程同步工具掃描的目錄。

**安全**
- 金鑰只走環境變數或金鑰庫；只驗存在或長度，不印出來。被 hook 擋下就不繞路，請人用 `!` 自己執行。
- `.gitignore` 用白名單；pre-commit 掃金鑰（兩套掃描器）與單檔大小。不用 `--no-verify`。
- 不靜默失敗：決策路徑不吞錯；失敗要讓呼叫端看得到。

**程式設計**
- 依 SOLID、純核心加外殼 I/O、組合優先、三次法則才抽象。完整清單與檢查方法見 dev-standard `templates/review-checklist.md`。
- 新程式碼直接適用；舊程式碼碰到那塊時順手改（童子軍規則），lint 用 baseline 只擋新增違規。
- 新規則生效只檢查生效日之後寫的 commit，依 author date 判斷；豁免的逐筆列在輸出裡；生效日寫成具名常數，文件日期與常數由測試比對。
- 測試測行為不測實作，不依賴環境變數；重構 PR 不改測試。

**文件與 commit**
- Commit：`type(scope): 摘要`，摘要一律繁體中文，type 與 scope 用英文；一個 commit 一個邏輯變更，含它的測試，自己能過測試。
- 給人讀的文件照 zh-tw-docs 技能寫：繁中台灣用語、言簡意賅、能用表格與 mermaid 就用；送出前跑它的掃描腳本。
- 文件不寫會漂移的數字（測試數、筆數、成本），改寫查詢方法。給人讀的 PR 描述裡的數字由閘門腳本產出，不手抄。
- 待辦只放 GitHub Issues，不散在 markdown 清單。

**回填**
- 在這個 repo 發展出跟 repo 無關的好做法，PR 的 `DERIVED:` 標「通用：是」，同一週對 dev-standard 開回填 PR。只在這個 repo 成立的留在 overlay。
- 做開發流程工具前先查 dev-standard；通用的就做在 dev-standard，repo 差異寫在 `.dev-standard/*.json`。
<!-- DEV-STANDARD:END -->

## Claude Code 專屬 / Claude Code specifics

`AGENTS.md`（上面已 import）是本 repo 規則的正本：使命與不變量、R2／R3、指令、架構都在那裡，這裡不重述。
`AGENTS.md` (imported above) is the source of truth; this file only holds what is specific to Claude Code.

- 程式探索：codebase-memory MCP（見 `AGENTS.md`〈Code discovery〉）。
- 本機測試用 repo 的 venv：`.venv/bin/python -m pytest tests/unit/ -q`（worktree 裡沒有 `.venv` 時用主 checkout 的）。
- 正式環境狀態（例如 `ai_trading_enabled`）不寫在這裡：設定檔預設值不等於正式值，照 `AGENTS.md` 查 DB 或 API。
- subagent 分工與 advisor 時點照上方開發辦法區塊；`scout`／`implementer`／`reviewer`／`architect` 定義目前在個人全域設定。
