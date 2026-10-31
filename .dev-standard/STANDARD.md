# 開發辦法（dev-standard）

適用於 litov、investment-advisor、hermes-investment-agent，以及之後新開的 repo。每個 repo 用 `tools/sync.py` 把下方〈給 agent 的精簡版〉帶進自己的 AGENTS.md 與各家 agent 規則檔，repo 自己的差異寫在 overlay，不改這份。

寫法延續 hermes：**規則是帳單。** 每條附來由，指到哪個 repo 的哪次事件。說不出來由的規則，下一個人會把它當成偏好刪掉。

## 怎麼讀

- 〈給 agent 的精簡版〉是會被同步出去、每個 session 都讀到的那段。只放「會改變下一個動作」的句子。
- 後面各節是全文：規則、為什麼、怎麼檢查。改精簡版之前先改全文。
- 檢查方法寫不出來的規則不收。沒有檢查方法的原則只是口號。

<!-- AGENT-RULES:BEGIN -->
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
<!-- AGENT-RULES:END -->

## 1. 分支、worktree、PR

| 規則 | 為什麼（來由） | 怎麼檢查 |
|---|---|---|
| 不在 main commit、不 push main | hermes：`~/.hermes` 是正式環境的 bind mount，在上面切分支讓 cron 正在跑的腳本消失（2026-10-08）。litov：main 定義為「已審」 | guard hook（`templates/hooks/guard.py`）擋 `git commit` on main 與 `git push … main`；investment 的 pre-push hook 目前只在本機 `.git/hooks`，導入時進版控 |
| 一個任務一個分支；會寫檔的 session 或 agent 各用自己的 worktree，唯讀的不開；兩個 writer 不碰同一檔 | hermes 同上事件：兩個 session 的改動混在同一棵樹。litov 與全域設定：唯讀的開 worktree 是浪費，兩個 writer 同檔會互相覆蓋且沒有訊號 | `.dev-standard/bin/wt.sh new`（wt 元件）；`tools/prune.py` 列出殘留；派工時寫明每個 writer 的檔案範圍 |
| 一個 PR 一個連貫範圍；以「合併後系統自洽」為單位，上限是一次 review 讀得完 | decision-stack 寫入程序：只加工具不改契約等於沒生效；審不完的 diff 等於沒被審 | reviewer 問「拿掉這個 PR 的任一半，另一半還成立嗎」 |
| 疊起來的 PR 每一個都合進 main | litov #2 疊在 #1 上，#1 先合進 main，#2 合進沒人看的 base 分支，main 沒拿到內容 | 合併前看 base 是不是 main |
| 合併依風險級，一律 merge commit、不 squash | hermes：squash 會讓部署端的 `pull --ff-only` 與原子 commit 失效。litov 的私有免費 repo 沒有分支保護，`--auto` 等於立刻合，所以只用 `--match-head-commit` 鎖住檢查時的 head。2026-10-31 使用者決定：自動合併升成通用規則、預設開啟（`docs/design/DD-2026-1031-merge-by-risk.md`） | `tests/test_pr_checks.py`：R3 路徑判 R3 且拒絕合併、`.automerge-off` 拒絕、R2 缺 reviewer 拒絕、合併指令不含 `--squash`／`--auto` |
| main 與共用分支不 force push；自己的 feature 分支整理歷史，例如 rebase、拿掉試做後又刪掉的 commit，用 `--force-with-lease=<分支>:<遠端舊 SHA>`，推完讀回遠端 SHA 確認等於本機 | 某 Rails 專案 2026-10：8 條 PR 送審前整理歷史，不 force 就推不上去。不寫舊 SHA 的 `--force` 會蓋掉別人在同一分支的推送，而且沒有訊號 | guard 擋 push 到 main（`templates/hooks/guard.py`）；`pre-push` 以「遠端 SHA 不是本機 SHA 的祖先」判 non-fast-forward，對 main 與共用分支擋、對 feature 分支要求帶 lease，這一段範本尚未實作；推完 `git ls-remote origin <分支>` 的 SHA 等於 `git rev-parse HEAD` |
| 只做 `git mv` 的 commit 單獨放；有這種 commit 的 PR 合併時不 squash | 某 Rails 專案 2026-10：搬檔與後面加的內容合成一個 commit，內容一多，相似度掉到 50% 以下，git 認不出是搬檔，`git log --follow` 與 `git blame` 追不回搬檔前的歷史。單獨放時 git 判 rename 100%，reviewer 可略過逐行 | `git show -M100% --name-status <commit>` 是 `R100`，且 `--numstat` 0 增 0 刪 |
| PR 合併後不再往同一分支推；要補從 main 開新分支 | litov#25 合併後又推了三個檔，沒進 main，半天後才被另一個 session 發現，另開 #34 補；錶面 repo 發生過同樣的事。每條分支的檢查只看分支，看不到「它已經合併了」 | `templates/hooks/pre-push.sh`：分支已有合併的 PR 就擋；gh 不在時印警告不靜默 |
| PR 第一行風險級、`Refs #N`、`DERIVED:` | hermes PR 模板與 investment 的風險分級；`DERIVED:` 把每個 PR 變成一條記下來的規則 | PR 模板；reviewer 確認三項都在 |

## 2. 風險級 R0–R3

| 級 | 範圍 | 要什麼 |
|---|---|---|
| R0 | 文件、知識、註解 | 綠燈即可 |
| R1 | 一般程式、測試、UI、孤立腳本 | 綠燈（`green.sh`）＋測試 |
| R2 | 設定、門檻、prompt、schema、migration、部署腳本、hook、排程、被很多模組 import 的共用模組 | 綠燈＋驗證指令＋`reviewer` 審查＋CODEOWNERS |
| R3 | 會動錢的路徑（下單、風險閘道、資金政策）、正式環境的 gateway 與帳本 | **不開放給 agent。** 只提案與寫 DD，由人核可或自己執行 |

R3 不是「門檻設很高的 R2」，是關著的車道。門檻會被調，關著的車道不會（hermes lane C）。

對照：hermes 的 lane A＝R0／R1，B＝R2，C＝R3。investment 的 R0–R3 名稱不變。

各 repo 把 R2／R3 路徑樣式寫在 `.dev-standard/risk.json`（元件 pr-checks，缺才從範例建，sync 不覆蓋），並寫進 `.github/CODEOWNERS`。能用程式判定的就用程式判定：risk.json 的 `classifier` 可指定一支命令（例：hermes `scripts/dev/lane.py` 用 import 閉包判斷會不會碰到下單腳本），它的結論與路徑樣式取高，只會抬高、不會壓低路徑樣式判出的 R3。

**R3 由路徑判定，不靠宣告**：私有免費 repo 沒有分支保護，GitHub 也不執行 CODEOWNERS，所以把交易相關改動標成 R1 就能被自動合併（litov 2026-10 盤點）。pr-checks 的 `computed ＝ max(各路徑的級, classifier)`，宣告低於 computed 判紅燈並點名路徑；合併、reviewer 條件、R3 拒絕都看 `max(宣告, computed)`。設定檔一律讀 base 分支的版本，PR 不能在同一個改動裡拿掉自己的 R3 樣式。檢查工具評估 PR 時不能用 PR 自己的程式：改到 `.dev-standard/bin/pr_checks/**`、`risk.json` 或 classifier 腳本的 PR 一律要人合併；本機 checkout 必須是 base 最新；base 不是預設分支或改動檔清單被截斷的 PR 也不自動合併。

合併表、熔斷開關與來由見 `docs/design/DD-2026-1031-merge-by-risk.md`。

## 3. 模型分層

| 規則 | 為什麼 | 怎麼檢查 |
|---|---|---|
| 主 session 用 Sonnet，Opus 當 advisor；查找類 subagent 用 Haiku，實作與審查類用 Sonnet（深度 1、同時 ≤4） | hermes DD-2026-1009：實測 cache 讀取兩個模型同價，長 session 裡 Opus 每回合只貴 1.3–1.9 倍，但整體 Opus 佔比要壓在 40% 以下 | hermes `scripts/dev/claude_cost.py`：Opus 佔比 <40%、subagent 佔比 >15% |
| advisor 三個時點：照計畫動手前、同一件事第二次失敗、宣告完成前；context >150K 改用 reviewer | 同上 | session 紀錄裡有沒有這三次呼叫 |
| 6 回合內判斷是不是難題；換 Opus 開新 session，交接 ≤20K | 在 300K context 中途換模型，光重建快取約 1.5 美元 | 交接檔大小 |
| 角色：`scout`（haiku 查找）、`implementer`（sonnet 實作）、`reviewer`（sonnet 審查）、`architect`（opus，卡關才用） | 難度決定模型，升級兩段式，不預設用強模型 | 定義檔正本在 `templates/agents/`，全域以 symlink 接進 `~/.claude/agents/`，所有專案共用，不在各 repo 複製 |
| 開新 session 或 subagent 一律寫明 model，不繼承主 session。唯讀、照表做的 session（巡檢、量測、驗證）用 Haiku；實作與維運 Sonnet；設計為主才 Opus | 2026-10-25 一次開了 4 個 session 都沒寫 model，全數繼承 Opus 5.5。Haiku 5.5 每百萬 token $0.10／$0.50，是 Sonnet 的 1/20，唯讀 session 用它幾乎不花錢 | 開 session 的呼叫有沒有帶 `model`；`claude_cost.py` 的 Opus 佔比 |
| Fable 5.1 只在使用者點名時用：architect（Opus）也失敗一次，或高風險、難回頭的決策。不做成 agent，不列進自動升級 | $10／$50，是 Opus 的 2.5 倍、Sonnet 的 5 倍；放進自動升級鏈，失敗的成本會一路放大 | session 紀錄裡用到 Fable 的都有使用者點名 |

## 4. 閘門

| 規則 | 為什麼 | 怎麼檢查 |
|---|---|---|
| 先寫 `.claude-task/green.sh`（會失敗的檢查）再寫碼；Stop hook 跑它，紅就回給 agent，連三次紅就停並告訴人「計畫可能錯了」 | hermes DD-2026-1009：「看起來好」「模型說有把握」「沒報錯」都不是檢查。同一單元修三次不好，問題在計畫 | `templates/hooks/green_gate.py`；green.sh 被改過會擋一次，要求說明 |
| 行為說法附可重跑的指令 | investment PR 模板與文件規範：說法不可驗就等於沒說 | PR 模板〈驗證〉節 |
| 改門檻、規則、契約，同一個 commit 附 DD | hermes `dd_gate`：門檻在沒有紀錄的情況下被調過，之後沒人知道為什麼 | hermes 由 git 歷史判定；其他 repo 由 reviewer 檢查 |
| 逾時算失敗，不算跳過 | hermes green_gate：逾時被當成沒事，紅燈就消失了 | green_gate 逾時回 124 |
| 送出去的 PR 描述、留言、訊息也是產出：裡面每個「已補、已改、第 N 行」的宣稱，對著要推的那一版逐項核對才送 | 某 Rails 專案 2026-10：回覆寫「已補」但程式裡沒有，被 reviewer 逐點抓出。當時驗過程式與描述，從來沒驗過回覆 | 宣稱核對腳本在送出前跑；送出動作比對文字內容的雜湊，沒有通過標記就擋 |
| 迭代檢核要有可數的停止條件：本輪新必修為 0 才停，最多兩輪，超過就把剩下的攤給人決定 | 某 Rails 專案 2026-10：檢核迴圈跑了數次，最後一輪仍找出 7 項必修。沒有收斂判準時，次數多不代表收斂 | 每輪報告最後一行寫「新必修數：N」，兩輪後 N 仍大於 0 就轉給人 |
| 跨天的 worktree、草稿、未 commit 的實作，不放在會被系統清掉或被排程掃到的位置 | 某 Rails 專案 2026-10：`/tmp` 底下的暫存一個週末後被清空；放在被每日同步工具掃描的目錄下，凍結中的分支被 rebase，上游的 commit 被重寫 | 閘門拒收 `/tmp` 底下的路徑；同步類工具只處理 `.git` 是目錄的主 checkout，不處理 `.git` 是檔案的 linked worktree |

## 5. 決策紀錄（DD）

模板在 `templates/dd-template.md`。每份 DD 要答出：
1. 舊做法是什麼、錯在哪（附證據）；
2. 新做法與它的正本在哪；
3. 可重跑的證明；
4. 已知殘留與不做的事；
5. `## 驗收條件`（AC1、AC2…，每條附反驗：故意弄壞，檢查要抓得到）。

檔名 `docs/design/DD-YYYY-MMDD-主題.md`。教訓另外記在該 repo 的地雷清單（hermes `knowledge/hermes-landmines.md`），有編號，DD 引用編號。

## 6. 安全

| 規則 | 為什麼 | 怎麼檢查 |
|---|---|---|
| `.gitignore` 用白名單（`/*` 再逐項放行），而且放行的目錄裡也排除 `*.bak*`、`_tmp_*`／`tmp_*`、執行狀態檔 | hermes：頂層 250 項含三個憑證檔，白名單擋下；但白名單放行的目錄裡仍有 95 個 .bak／tmp 檔被追蹤 | `git ls-files \| grep -E '\.bak\|_tmp'` 回 0 |
| `.gitignore` 不寫行尾註解 | hermes 2026-09-13：五條帶行尾註解的排除規則全部失效，git 不報錯 | pre-commit 驗不該進來的目錄 |
| pre-commit 用兩套掃描器（gitleaks＋detect-secrets）加檔名、內容、目錄、單檔 1MB 四層 | investment 2026-07-12：`.env.bak` 帶著金鑰變數名被追蹤數週，單一掃描器沒抓到 | `templates/pre-commit-config.yaml`、`templates/hooks/pre-commit.sh`；CI 跑 secret-scan |
| pre-commit hook 不用 `set -e`，一律 `if` 區塊、最後明確 `exit 0` | hermes 2026-09-13：`set -e` 配 `[ … ] && fail` 讓 hook 無聲擋掉每一次 commit，`git commit` 回 0 卻沒產生 commit | 範本照這個寫 |
| 個人側 repo 不得含公司識別；pre-commit 用同一份 denylist 擋 | 個人側 repo 要能帶到下一家公司 | `hooks/pre-commit`、`tools/personal_audit.py` |
| `.gitleaksignore` 只用指紋，每條寫理由 | investment：五個已輪替的金鑰不重寫歷史，理由寫明 | reviewer |
| 金鑰只驗存在或長度，不印出來；被 hook 擋下不繞路 | hermes guard：讀憑證、`docker inspect`、`printenv` 都會把金鑰帶進 context | guard hook |
| 個人設定（`settings.local.json`）不進版控 | investment：個人權限檔被追蹤，一直顯示為已修改 | `git ls-files \| grep settings.local` 回 0 |
| CI 的 token 最小權限 | investment secret-scan：gitleaks 只需要讀 commit 與 PR | workflow 的 `permissions:` |

## 7. 不靜默失敗

決策路徑上的錯誤不能被吞掉，失敗要讓呼叫端看得到：子行程檢查 return code、`except` 不能只 `pass`、空輸出不能當成功。

來由：investment 憲章第 0 條；hermes 地雷 #94（吞掉的失敗）、DD-2026-1024（子腳本失敗、節點仍 exit 0）。

檢查：用 AST 掃，不用字串比對（investment `tests/unit/test_fail_silent_policy.py`、hermes 的 yaml 守衛測試）。例外清單每條附理由，過期項讓測試失敗。

## 8. 軟體工程原則

每條寫「是什麼、違反長什麼樣、怎麼檢查」。完整審查問句在 `templates/review-checklist.md`。

### SOLID

| 原則 | 是什麼 | 違反長什麼樣 | 怎麼檢查 |
|---|---|---|---|
| 單一職責（SRP） | 一個模組只有一個改它的理由 | 一個 service 同時抓資料、算分數、寫 DB、發通知 | ruff `C901`（複雜度 >10）、`PLR0912`（分支 >12）、`PLR0915`（敘述 >50）；審查問「這個 PR 為什麼要改這個檔」，答出兩個理由就拆 |
| 開放封閉（OCP） | 新增一種資料源、券商、模型時加一個實作，不改既有分支 | 每加一種就在同一串 `if/elif` 多一條 | 審查問「新增一種 X，有沒有改到既有的 if/elif 鏈」 |
| 里氏替換（LSP） | 替代實作不能收緊輸入、放寬輸出、多丟例外 | 某個實作對空清單丟錯，其他回空 | 同一組合約測試跑在每個實作上 |
| 介面隔離（ISP） | 介面只放呼叫端真的用到的方法 | 實作裡有 `raise NotImplementedError` 或空方法 | 審查掃 `NotImplementedError` 與 `pass` 方法 |
| 依賴反轉（DIP） | 核心邏輯依賴抽象，I/O（網路、DB、檔案、時鐘、LLM）從外面注入 | 計分函式裡直接 `requests.get`、`datetime.now()` | import-linter 分層合約（核心不准 import 外部 client）；核心測試不 mock 網路就能跑 |

### 其他

| 原則 | 是什麼 | 怎麼檢查 |
|---|---|---|
| 純核心、外殼做 I/O | 計算與判定寫成純函式，讀寫放在最外層 | 核心模組的測試不需要 fixture 檔或網路 |
| 確定性的事不交給 LLM | 數字、計算、判定、轉錄、格式一律函式加測試；LLM 提案、程式決定 | hermes DD-2026-1007、investment 憲章第 2 條；審查問「這個數字是誰算的」 |
| KISS、YAGNI | 沒有第二個呼叫端就不抽象，不為假想需求加參數 | 審查問「這個參數現在誰在傳」 |
| 三次法則 | 第三次重複才抽出來；前兩次寧可重複，避免抽錯 | 審查 |
| 組合優先於繼承 | 繼承深度 ≤2 | ruff 無對應規則，審查 |
| 不可變資料優先 | 設定、結果物件用 `frozen` dataclass 或 tuple | 審查 |
| 型別與邊界 | 公開函式有型別標註；外部輸入在邊界驗證一次，裡面信任 | `ruff ANN`（新程式碼）；pydantic 或 dataclass 驗證 |
| 命名用領域詞 | 名字是使用者或領域會講的詞，不是 `data2`、`helper` | 審查 |
| 不寫死模型名 | LLM 用別名或等級，不在程式裡寫模型 id | investment 憲章第 1 條；grep 模型 id |

### 測試

- 金字塔：單元多、整合少、端到端最少。
- 測行為不測實作；重構 PR 不改測試，改了就代表行為變了。
- 測試不依賴環境變數與正式資料（hermes 把 `HERMES_HOME` 指到暫存目錄；investment 用 patch `os.environ`）。
- 檢查「不存在」用 AST 或行為，不用字串掃描（hermes 地雷 #147：動態組出來的呼叫字串掃不到）。
- 每個測試在檔頭宣告它守什麼（hermes `QA = {label, why}`＋`COVERS`），說不出守什麼的測試是負債。

### 導入既有程式碼

- 新程式碼直接適用。
- 既有違規存成 baseline（ruff `--add-noqa` 或 per-file ignore 清單；import-linter 先描述現況再收緊），CI 只擋新增的。
- 重構併在碰到那塊的 PR 一起做（童子軍規則），與行為改變分開 commit。
- 新規則生效時，只檢查生效日之後寫的 commit，依 author date 判斷。rebase 不改 author date，所以在途分支不會因為 rebase 失去豁免。豁免的 commit 在輸出裡逐筆列出，不靜默略過。生效日寫成具名常數，規則文件裡的日期與常數由測試比對。來由：某 Rails 專案 2026-10，新規則一上線就擋到十幾條在途的分支。檢查：測試斷言文件日期等於常數。
- 每個 repo 盤點 SOLID 最嚴重的 3 處寫成 issue，排進待辦，不一次大改。

## 9. 文件、commit、待辦

| 規則 | 為什麼 | 怎麼檢查 |
|---|---|---|
| Commit `type(scope): 摘要`，摘要一律繁體中文，type 與 scope 用英文；原子 commit 含它的測試，自己能過測試 | hermes 與 investment 現行做法；litov 2026-10 復盤時創辦人定為「一律」，混用讓 log 難掃；原子 commit 讓 revert 與 bisect 可用 | commit-msg 檢查（選用）；reviewer |
| 給人讀的文件照 zh-tw-docs 技能寫 | litov loop-v2：文件被評「AI 文、英翻中」重寫一輪；整理成技能後跨專案共用 | `templates/skills/zh-tw-docs/scripts/zhtw_scan.py <檔>`：FAIL 為 0 |
| 文件不寫會漂移的數字，改寫查詢方法 | investment 憲章第 6 條；hermes `DEVELOPMENT.md` 寫「92 個測試」，實際 284 個檔 | reviewer；PR 模板勾選 |
| 給人讀的 PR 描述裡的測試數、情境數、行號、結果，由閘門腳本產出，不手抄 | 某 Rails 專案 2026-10：手抄的描述出現 139 與 81 兩個互相矛盾的數字，另有行號因後續修改而位移 | 描述裡的每個數字都能對到閘門腳本的輸出 |
| 待辦只放 GitHub Issues | hermes：CLAUDE.md、DEVELOPMENT.md、OPEN-ITEMS.md 對「待辦在哪」三種說法 | grep 文件裡的待辦清單 |
| 同一套規則只有一份正本，其餘由產生器帶出，CI 跑 `sync.py check` | investment：五份 agent 規則檔各自漂移，`.cursorrules` 留著過時的「615+ 測試」 | `python3 .dev-standard/sync.py check` |

## 10. 回填：各 repo 的好做法回到這裡

- **判準：** 一個做法換到另一個 repo 也成立，就屬於這裡；只在原 repo 成立的（正式環境路徑、特定檔名、產品名）留在 overlay。
- **觸發：** PR 的 `DERIVED:` 行標「通用：是」，同一週對 dev-standard 開回填 PR，連回原 PR。
- **工具：** `tools/sync.py report <repo>…` 列出各 repo overlay 的段落，標出跨 repo 重複的標題（通用候選）與跟正本重名的段落（可能是漂移）。它只列不判，「是不是通用」由人決定。
- **來由的寫法：** 來源不是本 repo 清單內的專案時，寫成「某 Rails 專案 2026-10」這種形狀：只留技術類型與年月，不寫公司、專案或 repo 名、票號、人名、MR 編號。0.4.0 的來源是某 Rails 專案 2026-10 一批 PR 的送審：§1 的 force 與搬檔、§4 的三條、§8 與 §9 各一條。
- **定期回看：** 每月一次，或累積 3 個候選時。
- **升版：** 加或改規則升 minor，只改文字升 patch。CHANGELOG 每版寫出換掉了哪個想法，每條規則記來源 repo。
