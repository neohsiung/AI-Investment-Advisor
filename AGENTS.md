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

**Current capability, stated honestly (2026-08-12).** The order path is wired
end to end and connected to a live eToro account, but it has never filled a
trade: `transactions` holds **0 rows** with `entry_category='trade'`. It runs
under a `tradable_capital_usd` cap (currently $100) with a
`TRADING_MODE=paper` brake in `.env`. Treat "autonomous trading" as built and
under test, not as demonstrated. Earlier revisions of this file described the
intent as though it were the capability.
訂單路徑已接通實盤帳戶但至今從未成交（`entry_category='trade'` 為 0 筆），
目前受 $100 資本上限與 paper 煞車限制。請視為「已建置、驗證中」而非已驗證。

**Scoring ensemble: 4 agents**, weighted — Fundamental 0.35, Momentum 0.25,
Sentiment 0.20, Risk 0.20 (`src/services/confidence_compositor_service.py`).
Exits are scored separately by `ExitCompositorService` on different factors.
Older docs claiming a "7-agent swarm" or "10 parallel debate agents" are
describing designs that the running code does not implement.

- **Repo**: `neohsiung/AI-Investment-Advisor`
- **Language**: Python 3.11 (Docker) / 3.10+ (local)
- **Package Manager**: `uv` (lockfile: `uv.lock`, config: `pyproject.toml`)
- **Frontend**: Next.js 15 (TypeScript, in `frontend/`)
- **Backend**: FastAPI + MCP Server (in `services/mcp_server/`)

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  User Interface                  │
│          Next.js Dashboard (frontend/)           │
│             Streamlit (legacy, src/dashboard/)   │
└──────────────────────┬──────────────────────────┘
                       │ REST / WebSocket
┌──────────────────────▼──────────────────────────┐
│              FastAPI + MCP Server                 │
│         services/mcp_server/ + src/api/           │
├──────────────────────────────────────────────────┤
│   WorkflowService → CIO Agent → 7 Sub-Agents     │
│   SentinelService → 10D Radar → Auto-Hedging     │
│   AutomatedTradingService → eToro API             │
├──────────────────────────────────────────────────┤
│   3-Tier LLM Routing (Advanced/Smart/Fast)        │
│   via ResilientLLMPipeline + LLMGateway            │
├──────────────────────────────────────────────────┤
│  PostgreSQL 16 + pgvector │ Redis │ Celery Beat   │
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
# Dev server (backend)
uvicorn services.mcp_server.main:app --reload --port 8000

# Dev server (frontend)
cd frontend && npm run dev

# Full stack via Docker
./start.sh

# Run tests
pytest tests/ -x --tb=short

# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Lint (security)
bandit -r src/ -c pyproject.toml
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
