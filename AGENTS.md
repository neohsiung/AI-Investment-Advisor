# AGENTS.md — AI Coding Assistant Context

# ═══════════════════════════════════════════════════════════════════════
# This file follows the open AGENTS.md standard (https://agentsmd.io).
# It provides a unified first-layer context for ALL AI coding assistants
# (Antigravity, Claude Code, Cursor, GitHub Copilot, etc.).
#
# For deeper governance rules, skills, and workflows, see .agent/ directory.
# ═══════════════════════════════════════════════════════════════════════

## Project Identity

**AI Investment Advisor** — An autonomous quantitative investment platform
that scores trade decisions with a multi-agent ensemble and executes them
against eToro.

<!-- MISSION:BEGIN -->
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
<!-- MISSION:END -->

**Current capability (stated honestly; re-verify from the DB, do not trust this text).** The order path is wired
end to end to a live eToro account and has filled trades; whether it earns a net excess return over SPY is
**not demonstrated** and is not assumed. Use `/api/v1/net-alpha` and the `transactions` /
`llm_real_cost_daily` tables for current facts.

The `TRADING_MODE=paper` brake was lifted on 2026-08-23. Paper mode is not a usable fallback: the eToro token
has no demo permission (deliberate — there is no demo path), so `TRADING_MODE=paper` makes every broker call
return `InsufficientPermissions` (a full stop, not a degraded mode). Live risk is bounded by
`tradable_capital_pct` (share of the real account the system may deploy; **0 disables trading**),
`tradable_capital_usd` (an optional extra USD ceiling; **0 means "no extra USD cap" — the percentage still
binds**) and `ai_trading_enabled` (schema default false on a clean install; production runs it true only by
an explicit operator setting). Do not read the schema defaults as the production state — query it.

訂單路徑已接通實盤並已有成交；是否相對 SPY 賺得淨超額報酬**尚未被證明**。請以資料庫與 API 查證，勿信文字。
實盤風險由三者界定：`tradable_capital_pct`（可動用帳戶比例，**0＝禁止交易**）、`tradable_capital_usd`
（額外的美元上限，**0＝不另設美元上限，百分比仍然生效**）、`ai_trading_enabled`（乾淨安裝預設 false；
正式環境由操作者明確設為 true）。設定檔預設值不等於正式環境狀態，請查詢實際值。

**Agent counts refer to different subsystems — four numbers, all real**
(verified against source 2026-08-23; canonical table in the docs page
代理人戰略協定 §2.1):

- **10** — the Council debate roster, run in parallel as Layer 1 of
  `SingleTickerAnalysisDAG.AGENT_ROSTER`: Macro, Momentum, Fundamental,
  Sentiment, Thematic, Risk, Sentinel plus three buy-side Scouts.
- **7** — that roster minus the three Scouts (the analysis agents).
- **4** — the buy-side weighted **scoring ensemble**: Fundamental 0.35,
  Momentum 0.25, Sentiment 0.20, Risk 0.20
  (`src/services/confidence_compositor_service.py`). Exits are scored
  separately by `ExitCompositorService` on different factors.
- **11** — the functional role table in `docs/`, which includes CIO, Council
  and the `extract_actions` skill; not any single execution path.

An earlier revision of this file called the "10 parallel debate agents" claim
an unimplemented design. That was wrong: the debate roster is real, and it is
the scoring ensemble that is 4. Say which subsystem you mean when quoting a
number.

- **Repo**: `neohsiung/AI-Investment-Advisor`
- **Language**: Python 3.11 (Docker) / 3.10+ (local)
- **Package Manager**: `uv` (lockfile: `uv.lock`, config: `pyproject.toml`)
- **Frontend**: Next.js 15 (TypeScript, in `frontend/`)
- **Backend**: FastAPI + MCP Server (in `services/mcp_server/`)

<!-- DEV-STANDARD:BEGIN v0.6.2 -->
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

## 開發辦法：本 repo 的差異 / Dev-standard overlay

上面區塊是 dev-standard 的通用辦法（`.dev-standard/sync.py` 產生，CI 跑 `python3 .dev-standard/sync.py check`）。
以下是本 repo 在它之外的差異；兩者衝突時以使命區塊與 R3 規則為準。
The block above is the shared dev-standard; below is what differs here.

- **風險級路徑**：R2／R3 路徑以 `.github/CODEOWNERS` 為準（R3＝動錢）。R3 照上方使命規則 1：只提案，人核可加 ADR。
- **DD**：改 `config/mission.yaml` 或 R3 行為的決策記在 `mission.yaml` 的 ADR log；其他門檻、規則、契約的變更照 dev-standard §5。
- **Commit 格式**：一律繁中，第一行 `type(scope): 繁中摘要`，細節照 `.agent/rules/git-commit-format.md`。
- **Worktree**：主 checkout 是正式環境的 bind mount（detached 在 `origin/main`），不在那裡切分支或寫檔；一律開 worktree。
- **pre-push 保護分支 hook**：正本在 `.githooks/pre-push`，用 `scripts/install_git_hooks.sh` 安裝到共用的 `.git/hooks/`。
  不設 `core.hooksPath`：那會讓 pre-commit framework 裝在 `.git/hooks/pre-commit` 的掃描失效。
- **Lint**：ruff 只擋新增違規。舊違規存成計數 baseline（`.ruff-baseline.json`），不在原始碼加 `noqa`（R3 檔不因 lint 被改）。
  檢查：`python3 scripts/ruff_baseline.py check`；修掉舊違規後跑 `python3 scripts/ruff_baseline.py update` 收緊 baseline。


## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  User Interface                  │
│       Next.js 15 Web Dashboard (frontend/)      │
│     (/workflows, /agents, /extensions, /settings)│
└──────────────────────┬──────────────────────────┘
                       │ Loopback Nginx Gateway (:8088)
┌──────────────────────▼──────────────────────────┐
│              FastAPI + MCP Server                │
│         services/mcp_server/ + src/api/          │
├──────────────────────────────────────────────────┤
│   WorkflowDAGEngine → CIO Agent → Sub-Agents     │
│   SentinelService → 10D Radar → Auto-Hedging     │
│   AutomatedTradingService → Broker APIs          │
├──────────────────────────────────────────────────┤
│   4-Tier Cognitive Routing (Nano/Fast/Smart/Adv) │
│   via ResilientLLMPipeline + LLMGatewayFactory   │
├──────────────────────────────────────────────────┤
│  PostgreSQL 16 + pgvector │ Redis │ Celery Beat  │
│  Declarative State: config/ (Workflows, Agents)  │
└──────────────────────────────────────────────────┘
```

## Key Technical Constraints

0. **Never fail silently on a decision path** — On the trading, scoring, risk
   and scheduling paths, an `except` must not do BOTH of these: log below
   `warning`, AND return a value that looks like a real answer. Pick one.
   If you must substitute a default, mark it (`_fallback_reason`,
   `_insufficient_data`) and make the caller able to show that mark to the
   user. Enforced by `tests/unit/test_fail_silent_policy.py`.
   決策路徑（交易/評分/風控/排程）的 except 不得同時「以 warning 以下層級記錄」
   且「回傳看似真實的答案」；若必須代換預設值，要帶可觀察的標記並讓呼叫端顯示。

   Every serious incident in this system has been this pattern, not a crash:
   a three-day outage with every monitor green, confidence scores that were
   hashes of the ticker, three BUY guards that passed because their table was
   empty. A crash gets noticed; a plausible wrong number does not.
   See `docs/05_Quality_Assurance/靜默失敗防治-Fail-Silent-Prevention.md`.

1. **No hardcoded model names or API keys** — All LLM config is DB-managed
   via `llm_tier_bindings` table; resolved by `ResilientLLMPipeline`.
   Note: `model_code` must be a **LiteLLM tier alias** (`nano`/`fast`/`smart`/
   `advanced` + `-fbN`), never a raw vendor name — the proxy serves only
   aliases and rejects raw names with HTTP 400.
2. **Raw SQL for performance paths** — Transactions, market data, pgvector
   queries use SQLAlchemy Core / raw SQL. ORM only for admin entities.
3. **Parameterized queries only** — Zero tolerance for string concatenation
   in SQL (see `.agent/skills/postgres-raw-sql/`).
4. **Bilingual code comments** — English (primary) + Traditional Chinese.
5. **Fernet encryption at rest** — All provider API keys encrypted via
   `LLMCredentialCipher`; key from env `LLM_CREDENTIAL_KEY`.

## Commands

```bash
# Turnkey cold-start installation
./install.sh

# Single-box operations (7-container stack)
./start.sh up              # Build and start stack
./start.sh health          # Health verification gate
./start.sh backup          # Snapshot DB + config/ state + manifest
./start.sh restore [id]    # Restore database and config from backup
./start.sh upgrade         # Auto-backup, git pull, rebuild, migrate, health check
./start.sh wizard          # Interactive onboarding & cost profile setup
./start.sh logs [svc]      # Follow live container logs
./start.sh down            # Stop services

# Local testing
pytest tests/unit/ -q
```

## Directory Semantics

```
.agent/              → Agent governance: rules, skills, workflows (Antigravity-specific)
alembic/             → Database migrations (PostgreSQL)
config/              → Model routing configs, persona definitions, LLM seed data
  config/workflows/*.yaml → multi-agent DAGs (/workflows UI); config/agents/*.md → agent definitions (/agents UI)
  config/data_providers.yaml, channels.yaml, tools.yaml → plugin manifests (/extensions UI)
  config/settings_schema.yaml → single source of truth for user settings
  config/llm_providers.yaml, llm_tiers.yaml → provider catalog and cognitive tier routing
deployment/          → Helm charts, PostgreSQL manifests
frontend/            → Next.js 15 dashboard (TypeScript)
infra/               → Nginx reverse proxy, SigNoz observability
k8s/                 → Kubernetes manifests (future production)
prompts/             → Agent system prompts (CIO, Sentinel, sub-agents)
scripts/             → Ops scripts: DB seed, deployment, health checks
services/            → Microservice entrypoints (MCP server, notification, scheduler, dashboard)
src/                 → Core Python package
  src/agents/        → Agent definitions + skills (eToro trade, research, etc.)
  src/api/           → FastAPI route handlers
  src/config/        → App configuration + data source matrix
  src/domain/        → Domain models
  src/infrastructure/→ Celery, LLM gateway, OTel instrumentation
  src/repositories/  → Database access layer (ORM + raw SQL)
  src/services/      → Business logic services
  src/workflow/      → Daily/weekly workflow orchestrators
tests/               → Unit, integration, e2e tests
workspace/           → Multi-agent workspace (WAL, identity, memory per agent)
```

## Documentation Reference

> **All agent documentation follows the project rules defined in
> `.agent/rules/`**. Before writing any code, review the relevant
> rule files for coding, testing, security, and commit standards.

| Topic | Location |
|---|---|
| Engineering & coding standards | `.agent/rules/engineering-standards.md` |
| Git commit format（一律繁中） | `.agent/rules/git-commit-format.md` |
| Documentation standards | `.agent/rules/documentation-standards.md` |
| Observability standards | `.agent/rules/observability-standards.md` |
| Security policy | `SECURITY.md` |
| Technical docs (7-category taxonomy; old wiki retired) | `docs/` (see `docs/README.md`) |

## Do NOT Touch

- `secrets/` — Runtime secrets, never commit
- `.env` / `env.production` — Local environment, gitignored
- `workspace/*/STATE.md` — Agent WAL state, auto-managed
- `data/*.db` — Runtime SQLite databases

## Code discovery: codebase-memory MCP

Prefer the codebase-memory MCP tools over grep for structure questions; fall back to grep/read for text and configs.
程式結構問題優先用 codebase-memory MCP；文字與設定檔照常用 grep／read。

| Tool | Use when |
|---|---|
| `search_graph` | Find functions, classes, routes by name pattern |
| `trace_path` | Callers / callees / data flow of a function |
| `get_code_snippet` | Exact source of one symbol |
| `query_graph` | Cypher queries for complex patterns |
| `get_architecture` | High-level structure |
| `detect_changes` | Impact of the current diff |

If the project is not indexed yet, run `index_repository` first. 尚未索引時先跑 `index_repository`。
