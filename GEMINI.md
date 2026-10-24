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
7. **Every development batch ends with a reader-ready technical document and a wiki synthesis** (or an explicit
   "no wiki change needed" with the reason). Behaviour claims carry a verification command; see
   `.agent/rules/documentation-standards.md` §1.6.
   每批開發結束必須交付讀者可用的技術文件並統整 wiki（或明確聲明「無需更新」與理由）；行為描述須附驗證指令。
<!-- GENERATED:MISSION:END -->

<!-- DEV-STANDARD:BEGIN v0.1.0 -->
<!-- 由 dev-standard 的 tools/sync.py 產生。要改規則請改 dev-standard 的 STANDARD.md 再 update；本 repo 自己的差異寫在這個區塊外。 -->
## 開發辦法（精簡版，由 dev-standard 同步，不要在這裡改）

**分支與 PR**
- 不在 main commit、不 push main。一個任務一個分支；會寫檔的 session 或 agent 各用自己的 worktree（`tools/wt.sh new <type>/<描述>`），唯讀的不開。分支前綴：`feat|fix|refactor|docs|chore|test|ci`，或該 repo 的組織前綴（例：`eng/`、`product/`）。
- 一個 PR 一個連貫範圍：合併後系統自洽。重構與行為改變分開 commit。
- PR 第一行寫風險級 `R0`–`R3`；有 issue 就寫 `Refs #N`（完全做完才用 `Closes #N`）；結尾寫 `DERIVED:` 一行，加上「通用？是／否」。
- 合併由人做，不 squash，不 force push。疊起來的 PR 每一個都合進 main。

**風險級（看錯了要付多少，不看信心）**
- R0 文件；R1 一般程式、測試、UI；R2 設定、門檻、prompt、schema、migration、部署、hook；R3 會動錢或動正式環境的路徑。
- R3 不開放給 agent：只提案、寫 DD，由人核可或自己執行。R2 要附驗證指令與 reviewer 審查。各 repo 的 R2／R3 路徑在 CODEOWNERS。

**模型分層**
- 主 session 用 Sonnet；Opus 當 advisor，用在三個時點：照計畫動手前、同一件事第二次失敗、宣告完成前。查找類 subagent 用 Haiku，實作與審查類用 Sonnet；深度 1，同時 ≤4 個。
- 6 回合內判斷是不是難題。要換 Opus 就開新 session，交接 ≤20K（任務、失敗的檢查、3 個關鍵檔），不在長 context 中途換模型。
- 角色：查找 `scout`，實作 `implementer`，審查 `reviewer`，卡關設計 `architect`。先用便宜的，失敗才升級。兩個 writer 不碰同一檔。

**閘門**
- 先寫會失敗的檢查（`.claude-task/green.sh`）再寫碼；連三次紅就停，回報「計畫可能錯了」。改弱檢查要跟人說明。
- 每個「系統在某情況會怎樣」的說法都附可重跑的指令。跑不了的寫成推論並說明依據。
- 改門檻、改規則、改契約，同一個 commit 附 DD。

**安全**
- 金鑰只走環境變數或金鑰庫；只驗存在或長度，不印出來。被 hook 擋下就不繞路，請人用 `!` 自己執行。
- `.gitignore` 用白名單；pre-commit 掃金鑰（兩套掃描器）與單檔大小。不用 `--no-verify`。
- 不靜默失敗：決策路徑不吞錯；失敗要讓呼叫端看得到。

**程式設計**
- 依 SOLID、純核心加外殼 I/O、組合優先、三次法則才抽象。完整清單與檢查方法見 dev-standard `templates/review-checklist.md`。
- 新程式碼直接適用；舊程式碼碰到那塊時順手改（童子軍規則），lint 用 baseline 只擋新增違規。
- 測試測行為不測實作，不依賴環境變數；重構 PR 不改測試。

**文件與 commit**
- Commit：`type(scope): 摘要`，繁體中文為主；一個 commit 一個邏輯變更，含它的測試，自己能過測試。
- 文件不寫會漂移的數字（測試數、筆數、成本），改寫查詢方法。
- 待辦只放 GitHub Issues，不散在 markdown 清單。

**回填**
- 在這個 repo 發展出跟 repo 無關的好做法，PR 的 `DERIVED:` 標「通用：是」，同一週對 dev-standard 開回填 PR。只在這個 repo 成立的留在 overlay。
<!-- DEV-STANDARD:END -->

## Gemini 專屬說明 / Gemini-specific notes

正本是 `AGENTS.md`：上面兩個區塊由產生器帶入（使命規則 ← `scripts/gen_agent_shims.py`；開發辦法 ← `.dev-standard/sync.py`），
不要在這裡改。本 repo 其餘規則（架構、指令、R2／R3 路徑、技術約束）讀 `AGENTS.md`。
The two blocks above are generated; edit `AGENTS.md` / dev-standard instead. Read `AGENTS.md` for everything else.

- 工程規則（含交易與風控防錯 §7）：`.agent/rules/engineering-standards.md`。
- 程式探索：優先用 codebase-memory MCP（`search_graph`、`trace_path`、`get_code_snippet`）；工具沒接時退回 grep。
- 不寫會漂移的數字：測試數用 `pytest --collect-only -q | tail -1`，品質門檻以 `.github/workflows/ci-cd.yml` 的指令為準，
  使命目標用 `load_mission()` 讀 `config/mission.yaml`。

