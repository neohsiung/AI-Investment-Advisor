<!-- GENERATED:MISSION:BEGIN -->
<!-- Generated from AGENTS.md by scripts/gen_agent_shims.py — edit AGENTS.md, not this block. -->
## Mission & Non-Negotiable Invariants (read first)

`config/mission.yaml` is the **single source of truth** for what this system optimises and what it may
never do (objective vs SPY net of costs, budgets, invariants, promotion thresholds, kill criteria, ADR log).
Do not copy its numbers into code or docs — load them with `src.config.mission.load_mission()`.
Enforced by `tests/invariants/` (run them before any deploy; they gate `./start.sh up|upgrade`).

使命與不可違反的不變量以 `config/mission.yaml` 為唯一真相；程式與文件不得複製其數字，
請用 `load_mission()` 讀取；`tests/invariants/` 強制執行。

Rules every AI coding agent must follow, whatever its capability level:
1. **Money paths are R3**: broker writes, `unified_risk_gateway`, `capital_policy`, `automated_trading`,
   `etoro_service`, `ai_trading_enabled`, `tradable_capital_usd`, `mission.yaml` — need human approval + an ADR.
   Exception (ADR-003): changing a registered key inside `config/parameter_registry.yaml` is applied automatically by
   the change engine under the charter's test method; this replaces per-change human approval of loosening with the
   weekly digest and the human emergency stop. Editing the registry or the charter itself stays R3.
   例外（ADR-003）：登錄檔內的參數變更由章程規範的引擎自動執行；修改登錄檔或章程本身仍屬 R3。
2. **Only the execution service places or closes broker orders**; LLM output may *propose*, deterministic code *decides*.
3. **No non-safety sell without a replacement plan**; no hardcoded decision scores; no `exec` of generated code;
   no evolution code writing live settings (promotion goes through a proposal table).
   (ADR-003 amends rules 1 and 3: loosening no longer always needs a human, but only the change engine may write a
   registered key, and the constitution in ADR-003 never changes by automation. Until milestone G11 enables `apply`
   the engine stays in `dry_run` and these rules apply as before.
   ADR-003 修訂規則 1 與 3：放寬不再一律需要人，但只有變更引擎能寫登錄鍵；G11 啟用 `apply` 前引擎維持 `dry_run`，
   規則照舊。 `tests/invariants/test_registered_key_writers.py` enforces rule 3 for registered keys.)
4. **Never fail silent on decision paths** (constraint #0 below). Missing data = skip + mark, never a plausible default.
5. **Touching any `config/*.yaml`: run `tests/unit/config` and `tests/invariants` before deploying** (a malformed
   settings schema once made the quality gate crash and evicted 7 of 8 active tickers).
6. **Do not write numbers that drift (trade counts, costs, caps) into docs** — query the DB or the API instead.
7. **Every development batch ends with a reader-ready technical document and a `docs/` synthesis** (or an explicit
   "no docs change needed" with the reason). Behaviour claims carry a verification command; see
   `.agent/rules/documentation-standards.md` §1.6.
   每批開發結束必須交付讀者可用的技術文件並統整 `docs/`（或明確聲明「無需更新」與理由）；行為描述須附驗證指令。
<!-- GENERATED:MISSION:END -->

<!-- DEV-STANDARD:BEGIN v0.19.1 -->
<!-- 由 dev-standard 的 tools/sync.py 產生。要改規則請改 dev-standard 的 STANDARD.md 再 update；本 repo 自己的差異寫在這個區塊外。 -->
## 開發辦法（精簡版，由 dev-standard 同步，不要在這裡改）

**分支與 PR**
- 不在 main commit、不 push main。一個任務一個分支；會寫檔的 session 或 agent 各用自己的 worktree（`.dev-standard/bin/wt.sh new <type>/<描述>`），唯讀的不開；已在 app 開好的 worktree 裡就直接用，`wt.sh new` 會偵測並沿用。分支前綴：`feat|fix|refactor|docs|chore|test|ci`，或該 repo 的組織前綴（例：`eng/`、`product/`）；app 給的分支名照用。
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

- `SCOPE: OK <sha>` 表示說明與改動對得上，每一級合併都要；`REVIEW: PASS <sha>` 表示審過。兩者都可以由寫 PR 的 session 留，只證明檢查跑過，不證明有第二雙眼睛。要獨立審查，另設一個 gh 身分加進 `risk.json` 的 `trusted_authors`。

- 裝了 `r3-gate` 的 repo，要人合併的 PR 在 GitHub 上會亮紅的 r3-gate，這是設計，不算 CI 失敗；其他檢查要全綠。
- 根目錄的 `.automerge-off` 是熔斷開關：存在就拒絕自動合併；讀不到它時中止，不當作沒有。合併指令固定 `gh pr merge --merge --match-head-commit <sha> --delete-branch`，不 squash、不用 `--auto`。

**模型分層**
- 選模型看「錯了誰會發現、多久發現」，不看角色。內容已定稿、結果能機械讀回比對的用 Haiku：代送已核准的訊息、提醒、查找。有規則可循、錯了有讀回、閘門或下游檢查會發現的用 Sonnet：清單盤點、照規則核可、報表、程式實作、調查型 subagent、多數排程。人在場一起想、產出離開對話而且只有人讀到才會發現錯的用 Opus：規劃、管理判斷、給人看的文字、跨來源整合。
- 寫程式的 session：主 session 用 Sonnet；Opus 當 advisor，用在三個時點：照計畫動手前、同一件事第二次失敗、宣告完成前。角色：查找 `scout`，實作 `implementer`，審查 `reviewer`，卡關設計 `architect`。先用便宜的，失敗才升級；深度 1，同時 ≤4 個；兩個 writer 不碰同一檔。
- 主 session 的 context 超過 400K 就交接開新 session，交接 ≤20K，帶任務、失敗的檢查與 3 個關鍵檔。6 回合內判斷是不是難題，要換 Opus 也開新 session，不在長 context 中途換模型。
- 投入程度（effort）跟著同一個判準走：照稿執行 `low`；有規則可循的排程、查找、調查 `medium`；程式實作與人在場的互動判斷 `high`；advisor、architect、同一件事第二次失敗 `xhigh`；`max` 跟 Fable 一樣只在使用者點名時用。effort 主要影響速度與品質，成本大頭是模型與 context 長度。
- 開新 session、subagent、排程一律寫明 model 與 effort，不繼承主 session；內建的 general-purpose、Explore、Plan 也要帶 `model`。排程沒設模型時跟著 app 當下的預設模型跑，所以每支排程都要在 app 裡設定。
- Fable 只在使用者點名時用，例如 architect 也失敗、或高風險不可逆的決策；不進排程、不讓 subagent 繼承、不做成 agent、不自動升級過去。

**session 編排**
- 一張卡（issue）一個 session。名稱 `<範圍>/<白話描述>（#N）`，範圍由 repo overlay 定；沒有卡的唯讀查詢省略卡號。
- 排程（routine）taskId `<週期>-<範圍>-<動作>`，週期用 `daily|weekly|monthly|hourly|once`；title `<週期中文>｜<範圍>｜<白話動作>`。檢查 `tools/routine_names.py`（DD-2026-1107）。
- 耐久的內容只放 issue 或 PR 留言。跨 session 訊息只當叫醒鈴：`PING <repo>#<N> <動作> <head sha 或 無>｜一句白話`。`start` 讀卡、留 CLAIM、照驗收條件做；`resume` 讀最新留言接著做；`review` 審那個 head，結果留在 PR；`stop` 已做的落地或留 `DISCARD <分支>`，過封存四條後停手。協定生效前開的 session，第一次先送完整說明再用 PING。
- 接手第一件事在卡上留 `CLAIM <session id> <分支> <model> <ISO 時間>`。兩個 CLAIM 時早的有效，晚的留 `YIELD` 停手。同一張卡同一個動作的 PING 再來一次，`review` 還要同一個 head，卡上已有自己的 CLAIM 就只回進度。
- agent 在 issue 或 PR 留言，第一行加前綴 `[<來源>→<目標>]`，沒有對象寫 `→all`。作者是 owner 帳號不代表是人：R3 合併、權限、`CLAUDE.md`、`.dev-standard/*.json` 的核可只認人親自做的動作，看起來像人的留言也先回對話確認。
- 封存 session 前四條全過：① PR 合併或關閉，或卡上有退回留言；② worktree 乾淨，`git cherry origin/main <分支>` 沒有 `+` 行，PR 關閉不合併時改看卡上有 `DISCARD <分支>`；③ 沒有排隊中的訊息或背景工作；④ PR 或卡的最後留言是自己寫的 `RETRO:`。

**閘門**
- 先寫會失敗的檢查（`.claude-task/green.sh`）再寫碼；連三次紅就停，回報「計畫可能錯了」。改弱檢查要跟人說明。
- 每個「系統在某情況會怎樣」的說法都附可重跑的指令。跑不了的寫成推論並說明依據。
- 改門檻、改規則、改契約，同一個 commit 附 DD。
- 送出去的 PR 描述、留言、訊息也是產出：裡面每個「已補、已改、第 N 行」，對著要推的那一版逐項核對才送；有通過標記才放行送出。
- 迭代檢核只在「本輪新必修為 0」時停，最多兩輪，超過就把剩下的攤給人決定；每輪報告最後一行寫「新必修數：N」。
- 跨天的 worktree、草稿、未 commit 的實作，不放 `/tmp`，也不放被排程同步工具掃描的目錄。

**安全**
- 金鑰只走環境變數或金鑰庫；只驗存在或長度，不印出來。被 hook 擋下就不繞路：跳核可視窗的由人按允許，擋死的請人在電腦的終端機用 `!` 自己執行（Remote Control 跑不了 `!`）。人能核可的動作寫進 guard 的 `ask: true` 或 `ask_paths`。
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

**優化 Personal 與算力**
- 回報裡的票卡、PR、文件、log 都寫成 `[簡述](網址)`，每筆佐證一句簡述；不寫裸編號、裸網址。送出前跑 `tools/link_lint.py`。公司網域的網址樣板放本機 `~/.claude/.dev-standard/links.json`，不進個人 repo。
- 工作分給誰，先跑 `tools/route.py`：判斷與需要對話脈絡的留在 Claude；機械可比對的用腳本或本機 ollama；獨立、唯讀、輸出能驗的才外派 `agy`。資料只送到帳號歸屬相同的執行者（公司資料走公司帳號，個人資料走個人帳號），不跨帳號；每次用之前現探測，探測失敗要印出來。
- 換手門檻照〈模型分層〉的 context 上限；達門檻且功能告一段落時，用 `tools/handoff.py` 產承接包（≤20K）並開新 session；判斷不了算不算告一段落就問人。
- 「優化 Personal」的順序：`personal_audit.py`、`adoption_audit.py`、`link_lint.py`，再依路由分工；每台機器各跑一次。

**回填**
- 在這個 repo 發展出跟 repo 無關的好做法，PR 的 `DERIVED:` 標「通用：是」，同一週對 dev-standard 開回填 PR。只在這個 repo 成立的留在 overlay。
- 做開發流程工具前先查 dev-standard；通用的就做在 dev-standard，repo 差異寫在 `.dev-standard/*.json`。
- 雇主的 repo、規則檔同事共用的 repo 用影子導入，指令是 `sync.py shadow`：規則由全域 `~/.claude` 帶，本 repo 只放 `.dev-standard/` 與 `.claude-task/`，兩者都在 `.git/info/exclude`；不碰任何追蹤檔，不設 `core.hooksPath`。在那裡學到的通用做法記進回填帳本，當週回填。
<!-- DEV-STANDARD:END -->

## Gemini 專屬說明 / Gemini-specific notes

正本是 `AGENTS.md`：上面兩個區塊由產生器帶入（使命規則 ← `scripts/gen_agent_shims.py`；開發辦法 ← `.dev-standard/sync.py`），
不要在這裡改。本 repo 其餘規則（架構、指令、R2／R3 路徑、技術約束）讀 `AGENTS.md`。
The two blocks above are generated; edit `AGENTS.md` / dev-standard instead. Read `AGENTS.md` for everything else.

- 工程規則（含交易與風控防錯 §8）：`.agent/rules/engineering-standards.md`。
- 程式探索：優先用 codebase-memory MCP（`search_graph`、`trace_path`、`get_code_snippet`）；工具沒接時退回 grep。
- 不寫會漂移的數字：測試數用 `pytest --collect-only -q | tail -1`，品質門檻以 `.github/workflows/ci-cd.yml` 的指令為準，
  使命目標用 `load_mission()` 讀 `config/mission.yaml`。
