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
2. **Only the execution service places or closes broker orders**; LLM output may *propose*, deterministic code *decides*.
3. **No non-safety sell without a replacement plan**; no hardcoded decision scores; no `exec` of generated code;
   no evolution code writing live settings (promotion goes through a proposal table).
4. **Never fail silent on decision paths** (constraint #0 below). Missing data = skip + mark, never a plausible default.
5. **Touching any `config/*.yaml`: run `tests/unit/config` and `tests/invariants` before deploying** (a malformed
   settings schema once made the quality gate crash and evicted 7 of 8 active tickers).
6. **Do not write numbers that drift (trade counts, costs, caps) into docs** — query the DB or the API instead.

**Current capability (stated honestly; re-verify from the DB, do not trust this text).** The order path is wired
end to end to a live eToro account and has filled trades; whether it earns a net excess return over SPY is
**not demonstrated** and is not assumed. Use `/api/v1/net-alpha` and the `transactions` /
`llm_real_cost_daily` tables for current facts.

The `TRADING_MODE=paper` brake was lifted on 2026-08-23. Paper mode is not a usable fallback: the eToro token
has no demo permission (deliberate — there is no demo path), so `TRADING_MODE=paper` makes every broker call
return `InsufficientPermissions` (a full stop, not a degraded mode). The `tradable_capital_usd` cap and
`ai_trading_enabled` bound live risk; **a cap of 0 currently means "uncapped" in code — treat that as a bug
(see governance plan P-1) until changed.**

訂單路徑已接通實盤並已有成交；是否相對 SPY 賺得淨超額報酬**尚未被證明**。請以資料庫與 API 查證，勿信文字。
`tradable_capital_usd=0` 目前在程式中代表「不設上限」，視為待修缺陷。

**Agent counts refer to different subsystems — four numbers, all real**
(verified against source 2026-08-23; canonical table in the wiki page
代理人戰略協定 §2.1):

- **10** — the Council debate roster, run in parallel as Layer 1 of
  `SingleTickerAnalysisDAG.AGENT_ROSTER`: Macro, Momentum, Fundamental,
  Sentiment, Thematic, Risk, Sentinel plus three buy-side Scouts.
- **7** — that roster minus the three Scouts (the analysis agents).
- **4** — the buy-side weighted **scoring ensemble**: Fundamental 0.35,
  Momentum 0.25, Sentiment 0.20, Risk 0.20
  (`src/services/confidence_compositor_service.py`). Exits are scored
  separately by `ExitCompositorService` on different factors.
- **11** — the functional role table in the wiki, which includes CIO, Council
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
   See `wiki/05_Quality_Assurance/靜默失敗防治-Fail-Silent-Prevention.md`.

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
| Git commit format (bilingual) | `.agent/rules/git-commit-format.md` |
| Documentation standards | `.agent/rules/documentation-standards.md` |
| Observability standards | `.agent/rules/observability-standards.md` |
| Security policy | `SECURITY.md` |
| Full Wiki (8-pillar taxonomy) | `wiki/` (separate git repo) |

## Do NOT Touch

- `secrets/` — Runtime secrets, never commit
- `.env` / `env.production` — Local environment, gitignored
- `workspace/*/STATE.md` — Agent WAL state, auto-managed
- `data/*.db` — Runtime SQLite databases

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
