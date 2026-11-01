# DD-2026-1101 session 管理：對齊 Litov 的一卡一 session，改寫成本 repo 的版本

> 一句話：session 一卡一個，名稱 `<組>/advisor/<一句話描述>（#N）`；耐久訊息放 issue；錢與正式環境只有創辦人。組依「誰寫哪些路徑」切，不依職能切。

**狀態**：R0 草稿，2026-11-01，合併由人。本文只提案；唯一會生效的規則寫在 `AGENTS.md`〈session 編排〉（R2）。
**範圍**：只改文件。不碰交易、下單、設定值、門檻、金鑰、排程、程式邏輯。
**範圍收斂**：通用規則已由 dev-standard#42 收編，本文只寫本 repo 的差異與現有 session 盤點。
**來源**：創辦人 2026-11-01 指示：本 repo 與 hermes-investment-agent 照 Litov 的方式管理 session。Litov 的正本是 `litov/docs/dd-session-orchestration-v1.md`、`dd-team-groups-v1.md`、`framework/groups.json`，第一輪實戰發現見 `litov/docs/ops-dispatch-round1-2026-11-01.md`。
**Refs**：[#297](https://github.com/neohsiung/AI-Investment-Advisor/issues/297)

## 0. 一頁結論

| 問題 | 本文建議 |
|---|---|
| 編排單位 | 一卡一 session，屬於一個組，有自己的 worktree 與分支 |
| 命名 | `<組>/advisor/<一句話直觀描述>（#N）`；專案欄在本 repo 固定為 `advisor` |
| 溝通 | 耐久訊息放 issue；`SendMessage` 只當叫醒鈴；確認收到看 `CLAIM` 留言 |
| 組怎麼分 | 8 個 agent 組加 `founder`（§2）；依寫入路徑與風險級切，風險級取自 `.dev-standard/risk.json` |
| 錢與正式環境 | 只有 `founder`；寫進 AGENTS.md 但不改任何既有規則 |
| 組表檔 | 這輪不建，提案見 §6 |
| 現有 session | 本 repo 有 2 個，只建議歸組，不動（§5） |
| 要創辦人決定 | 5 題（§7） |

## 1. 證據：本 repo 現況

快照 2026-11-01。數字會漂移，每列附重算方法。

| # | 觀察 | 重算方法 |
|---|---|---|
| E1 | worktree 累積且散在兩處：repo 內 `.claude/worktrees/` 與 repo 外 `investment-advisor-wt/` | `git worktree list \| wc -l`；`git worktree list \| grep -c investment-advisor-wt` |
| E2 | app 預設開 `claude/…` 分支，與組織前綴規則衝突 | `git branch --format='%(refname:short)' \| grep -c '^claude/'` |
| E3 | 同一個 worktree 被不同 session 重用：「運作檢查與修復」與「Fable 規劃」兩個 session 的 cwd 相同 | `list_sessions` 看 `cwd`（`current-status-bc4ff0`） |
| E4 | 該共用 worktree 有未提交的 `workspace/macro-evaluator/STATE.md`；AGENTS.md〈Do NOT Touch〉列為自動管理 | `git -C .claude/worktrees/current-status-bc4ff0 status --porcelain` |
| E5 | 主 checkout 是正式環境的 bind mount，且有一個未追蹤的 `docs/plans/` | `git -C <主 checkout> status --short` |
| E6 | `install.sh`、`start.sh` 寫死正式環境名稱，在這台機器跑會接管正式環境 | `grep -n advisor_prod install.sh start.sh` |
| E7 | 風險級路徑已有機器可讀的單一來源，R3 清單與 CODEOWNERS 由測試比對 | `cat .dev-standard/risk.json`；`.github/CODEOWNERS`；#293 |
| E8 | `trusted_authors` 是空的：agent 與 owner 共用一個 gh 身分，留言作者證明不了是創辦人 | `grep -n trusted_authors .dev-standard/risk.json` |
| E9 | 本 repo 沒有 growth/product/engineering 之分，也沒有被 git 忽略的共用 outbox | `git check-ignore -q growth/outbox \|\| echo 無`；`ls` 根目錄 |
| E10 | 排程任務 `dev-standard-steward` 會對本 repo 開升版 PR，範圍清單含本 repo，是一個會寫檔的非互動寫入者 | `~/.claude/scheduled-tasks/dev-standard-steward/SKILL.md` 第 12 行 |

E1 到 E4 與 Litov 的 E4、E6、F4 同形；E5、E6、E8 是本 repo 比 Litov 更要小心的地方。

## 2. 團隊與組

### 2.1 分法

Litov 依職能切團隊（growth、product、engineering…），因為它有多個產品與多種職能。本 repo 是單一產品、單一程式庫，職能切不出邊界；真正的邊界是**風險級**：誰能合併。所以組依「寫哪些路徑」切，並讓每組的寫入範圍不跨 R 級邊界，一個組要碰 R3 就不是 agent 組。

本 repo 是單一產品，沒有團隊層，組只用來歸類 session 與看寫入範圍。組名前綴 `advisor` 管產品程式與文件，`ops` 管流程與維運，另外有 `founder`。

### 2.2 組表

路徑樣式沿用 `.dev-standard/risk.json` 的寫法：fnmatch，`*` 跨 `/`。「合併」欄是該組典型 PR 的風險級，由腳本依路徑算，不由本文決定。

| 組 | 做 | 不做 | 主要寫入路徑 | 典型風險級 |
|---|---|---|---|---|
| `advisor.engine` | 分析、評分、工作流程的程式與其單元測試 | 不碰 R3 檔、不寫設定值、不改 schema | `src/agents/`、`src/workflow/`、`src/services/`，不含 R3 檔、`src/api/`、`src/repositories/`、`src/domain/`，不含 `strategy_names.py`、`src/infrastructure/`，不含 `risk_manager.py`、`services/` | R1；列在 `r2_globs` 的檔是 R2 |
| `advisor.config` | prompt、migration、非 R3 的 `config/` | 不改 `mission.yaml`、`parameter_registry.yaml`；登錄鍵的值只有變更引擎能寫（ADR-003） | `prompts/`、`alembic/`、`config/`，不含兩個 R3 檔 | R2 |
| `advisor.web` | 前端儀表板 | 不呼叫券商、不改後端契約 | `frontend/` | R1 |
| `advisor.quality` | 測試與不變量守衛 | 不為了讓綠燈而改弱檢查；改 `tests/invariants/` 要跟人說明 | `tests/` | R1；`tests/invariants/` 是 R2 |
| `advisor.docs` | 使用者文件與設計決策紀錄 | 不寫會漂移的數字；不改使命區塊 | `docs/`、`READMEs/`、`README.md`、`CHANGELOG.md` | R0 |
| `ops.method` | 開發辦法、規則、hook、模板 | 不改 CODEOWNERS 與 `risk.json` 的 R3 清單來讓自己的 PR 過關 | `AGENTS.md`、`.dev-standard/`、`.agent/`、`.github/`，不含 CODEOWNERS、`.githooks/`、`.claude/`、`.pre-commit-config.yaml` | R2 |
| `ops.tooling` | 維運腳本、依賴、lint baseline | 不跑會接管正式環境的腳本；不碰 `start.sh`、`predeploy_gate.sh`、compose | `scripts/`、`deployment/`、`infra/`、`k8s/`、`pyproject.toml`、`uv.lock`、`.ruff-baseline.json` | R1；`scripts/*gate*.sh` 是 R2 |
| `ops.watch` | 唯讀：查 DB、API、CI、排程、相依弱點，結果寫成 issue 留言 | 不寫 repo 檔、不重啟服務、不改設定 | 無，只開卡與留言 | 不適用 |
| `founder` | `r3_globs` 全部；正式環境的實際設定；核可與合併 R3 | 無 | `.github/CODEOWNERS`、`.dev-standard/risk.json` 列的 R3 路徑、`secrets/`、`*.env` | R3 |

規則：

| 規則 | 內容 |
|---|---|
| 一路徑一組 | 一個路徑最多一個組寫。上表已盡量互斥，但沒有測試守，見 §6 |
| 通用角色 | `scout`、`implementer`、`reviewer`、`architect` 在叫起它的組底下做事，寫入範圍跟著那個組 |
| 唯讀組 | `ops.watch` 不落檔；它看見要改的東西就開卡給對應的組 |
| 叫起 | 只有創辦人與調度能 `start_session`；組之間靠卡 |
| R3 | `founder` 以外沒有組可以寫 R3。agent 組的 PR 若算出 R3，照開發辦法：只提案、不合併 |

## 3. 與 Litov 的差異與理由

| 面向 | Litov | 本 repo | 理由 |
|---|---|---|---|
| 團隊層 | growth、product、eng、design、brand、ops | 無團隊層，只有組 | E9：單一產品，沒有職能邊界；風險級才是邊界 |
| 專案欄 | 多產品，每張卡要選 | 固定 `advisor` | 只有一個專案，保留欄位是為了與 Litov、hermes 的命名一致，方便 `ccusage` 與 grep |
| 組表檔 | `framework/groups.json` 加 `tests/test_groups.py` | 這輪不建，§6 提案 | 沒有測試守的組表只是第二份會漂移的文件 |
| 租約檔 | `~/.claude/litov-leases/` 管瀏覽器與 outbox | 不採用 | E9：沒有被忽略的共用 outbox；瀏覽器分頁是否各 session 獨立，Litov 自己也標未證實。本 repo 的共用資源是正式環境，由 R3 規則與創辦人管，不靠租約 |
| 熔斷檔 | `growth/outbox/reply-off`、`.automerge-off` | 不新增 | 本 repo 的熔斷是 `ai_trading_enabled` 與 `tradable_capital_pct`，屬 R3，不屬編排 |
| 對外訊息 | growth 組有核可、送出流程 | 無 | 本 repo 沒有對外發文流程 |
| 錢的路徑 | R3 是 billing、release | R3 是券商、風控、資金政策、mission、金鑰、compose | 後果是真金白銀；`founder` 組的存在就是為了讓這一條在每個 session 開機時被讀到 |
| 設計文件位置 | `docs/dd-*-v1.md` | `docs/design/DD-2026-1101-*.md` | `docs/README.md` 規定 DD 放 `docs/design/` |
| 完成四條、PING、CLAIM、留言前綴 | 有 | 照搬 | 這些與產品無關，是通用做法 |
| 清理腳本 | §5.3 的 worktree 回收腳本 | 這輪不提供 | 本 repo 有 `.agent/workflows/branch-hygiene.md` 處理遠端分支；worktree 回收是刪目錄，由創辦人決定要不要、何時跑，見 §7 第 4 題 |

## 4. 運作方式

通用部分不在此重寫：一卡一 session、命名、`CLAIM`、`PING`、完成四條、留言前綴與核可標記規則，正本是 [neohsiung/dev-standard#42](https://github.com/neohsiung/dev-standard/issues/42)，合併後見 STANDARD 對應節；實戰版本見 Litov 的 `docs/dd-session-orchestration-v1.md`。本 repo 的合併依風險級：R0、R1 由腳本，R2 加創辦人的 `REVIEW: PASS`，R3 只有創辦人。

## 5. 現有 session 盤點與建議歸組

只建議，不動。盤點範圍：`list_sessions` 中 `cwd` 在本 repo 之下的 session，快照 2026-11-01。其他 repo 的 session（litov、hermes）不在本文範圍。

| session | 現況 | 建議歸組與新名稱 | 建議動作 |
|---|---|---|---|
| 運作檢查與修復：排程看守、CI、相依弱點（`local_26b4ec88…`） | 執行中；有 PR #267 已合併；cwd 在 `current-status-bc4ff0`，HEAD 是 detached；該 worktree 有未提交的 `workspace/macro-evaluator/STATE.md`（E4） | `ops.watch/advisor/運作檢查：排程看守、CI、相依弱點`，長駐所以無卡號 | 不打擾、不改名。它同時做排程、CI、相依三件事，建議之後各開一張卡，由 `ops.watch` 查、`ops.tooling` 修。#267 已合併，但它還在跑，完成四條的第 3 條不成立 |
| Fable 規劃：策略名單一真相與凍結閘門第二段（`local_f05f9f3e…`） | 已停；由上一個 session 叫起；與上一列共用同一個 worktree（E3）；規劃對應的 #270、#272 都已合併 | `advisor.engine/advisor/規劃策略名單單一來源與凍結閘門第二段`，歸 `advisor.engine`；改到的 `strategy_names.py`、`charter_state_service.py` 是 R3，那部分屬 `founder` | 若創辦人確認規劃已交付，可在他同意後封存。封存前只做唯讀確認；**不要回收它的 worktree**，因為另一個執行中的 session 正在用 |
| 本 session（`docs/session-management`，#297） | 執行中 | `ops.method/advisor/補上 session 管理的規則與設計文件（#297）` | 做完 PR 後依完成四條封存 |

另有兩個與本 repo 有關、但不是 session 的寫入者，歸組如下，供創辦人知道：

| 寫入者 | 建議歸組 | 說明 |
|---|---|---|
| 排程任務 `dev-standard-steward` | `ops.method` | E10；每次 run 會多一個 session，建議納入 Litov 的「run 成功後封存」規則，由創辦人決定，見 §7 第 5 題 |
| Dependabot | `ops.tooling` | 只動依賴檔，R1 |

## 6. 組表檔：提案，這輪不建

Litov 的 `framework/groups.json` 值得，是因為有 `tests/test_groups.py` 檢查「一個路徑最多一個組」。本 repo 若要建，條件是同一個 PR 附能跑的測試。

| 項目 | 提案 |
|---|---|
| 檔案 | `.dev-standard/groups.json`，與 `risk.json` 同層，repo 差異放這裡是 dev-standard 的慣例；先看 dev-standard 是否要收成通用元件 |
| 測試 | 兩條，皆為純函式、不依賴環境變數：(1) 展開每組的樣式到 `git ls-files`，任一檔被兩個以上的組命中就紅燈，R3 清單內的檔只能被 `founder` 命中；(2) `founder` 的樣式與 `risk.json` 的 `r3_globs` 必須相等，沿用 #293 的作法 |
| 風險級 | `.dev-standard/` 下是 R2 |
| 先決 | 先確認 dev-standard 要不要做成通用元件，再決定放哪；Litov 目前把它放在自己的 `framework/` |
| 不做 | 不用它擋 PR 越界；那是另一件事，先看 §2.2 的分法在兩週內有沒有撐住 |

## 7. 要創辦人決定的點

| # | 決定 | 建議 | 理由 |
|---|---|---|---|
| 1 | 組的分法：依路徑與風險級，即本文的分法，還是仿 Litov 依職能 | 依路徑與風險級 | E9：沒有職能邊界；風險級已有機器可讀的來源（E7） |
| 2 | 現有「運作檢查與修復」session 是否拆成三張卡 | 拆；它跑完目前手上的事之後再拆，不打斷 | 一個 session 兼管排程、CI、相依弱點，違反單一職責 |
| 3 | 「Fable 規劃」session 是否封存 | 你確認規劃已交付就封存；worktree 不動 | #270、#272 已合併；worktree 還有另一個 session 在用 |
| 4 | 是否要做 worktree 一次性回收 | 先盤點再說：本 repo 的 worktree 分在兩處，位置見 E1，數量用該列指令查；清單由調度乾跑產出，由你按 | 刪目錄是不可逆動作，Litov 也由創辦人執行 |
| 5 | 排程 run 的 session 要不要比照 Litov 成功後封存 | 要；但這屬 `~/.claude/scheduled-tasks/` 的設定，由你改 | 不然每次排程多一個沒人收的 session |

其餘 Litov DD §6 的 P 系列，包括 permission、設定畫面、機器帳號，本 repo 這輪不提案，原因是它們動 `.claude/settings.json`，是 R2 且只有人能改；等你決定 Litov 那邊的結果再看要不要跟。

## 8. 驗證

```bash
python3 .dev-standard/sync.py check
python3 .agent/skills/docs-maintainer/scripts/verify_docs_links.py
python3 ~/.claude/skills/zh-tw-docs/scripts/zhtw_scan.py docs/design/DD-2026-1101-session-management.md
git diff --stat origin/main...HEAD
```

最後一條應只出現 `AGENTS.md` 與本文，沒有任何 `src/`、`config/`、`tests/` 的檔。

## 9. 回滾

兩個檔都是文件：還原這個 PR 的 merge commit 即可，不影響任何執行中的服務。

DERIVED: 單一產品的 repo 把 session 分組時，依「寫哪些路徑」與風險級切，不依職能切，讓每組的寫入範圍不跨 R 級邊界；R3 路徑專屬一個只有人的組，並寫在 AGENTS.md〈session 編排〉，讓每個 session 開機時讀到。通用：是。
