# AGENTS.md — AI Coding Assistant Context
# ═══════════════════════════════════════════════════════════════════════
# This file follows the open AGENTS.md standard (https://agentsmd.io).
# It provides a unified first-layer context for ALL AI coding assistants
# (Antigravity, Claude Code, Cursor, GitHub Copilot, etc.).
#
# For deeper governance rules, skills, and workflows, see .agent/ directory.
# ═══════════════════════════════════════════════════════════════════════

## Project Identity

**AI Investment Advisor** — A production-grade, autonomous quantitative
investment platform that orchestrates a 7-agent swarm with fractal debate
to manage real portfolios on eToro.

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

1. **No hardcoded model names or API keys** — All LLM config is DB-managed
   via `llm_tier_bindings` table; resolved by `ResilientLLMPipeline`.
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
