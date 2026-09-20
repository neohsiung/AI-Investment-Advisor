@AGENTS.md

# CLAUDE.md — AI Investment Advisor Assistant Guide

## Project Architecture & Status

**AI Investment Advisor** is an autonomous quantitative investment and market intelligence platform designed for single-operator, self-hosted deployment with zero SaaS dependencies.

The platform has completed its transformation across **Milestones 1 through 8 (M1–M8)** (see full roadmap in [`docs/plans/transformation_roadmap_m1_to_m8.md`](docs/plans/transformation_roadmap_m1_to_m8.md)):
- **Single-operator convergence**: Single `OWNER_ID`, local loopback authentication, no multi-tenant overhead.
- **7 Core Containers Stack**: `advisor_prod_ui` (Next.js 15), `advisor_prod_api` (FastAPI MCP Server), `advisor_prod_beat` (Celery Beat), `advisor_prod_worker` (Celery Worker), `advisor_prod_cache` (Redis 7), `advisor_prod_db` (PostgreSQL 16 + pgvector), `advisor_prod_gateway` (Nginx on `127.0.0.1:8088`).
- **Declarative Low-Code Configuration**:
  - `config/workflows/*.yaml` — Multi-agent Directed Acyclic Graphs (DAGs), managed via `/workflows` UI.
  - `config/agents/*.md` — Markdown agent definitions with YAML frontmatter, managed via `/agents` UI.
  - `src/agents/skills/*/SKILL.md` — Standardized skill manifests with dynamic `intents: [...]` routing.
  - `config/data_providers.yaml`, `config/channels.yaml`, `config/tools.yaml` — Plugin manifests managed via `/extensions` UI.
  - `config/settings_schema.yaml` — Single source of truth for user settings.
  - `config/llm_providers.yaml` & `config/llm_tiers.yaml` — Multi-provider catalog & cognitive tier routing.
- **Cost Profiles**: Three pre-tuned operational cadences (**Frugal**, **Balanced**, **Aggressive**) managing sentinel tick frequency and LLM spend.

---

## Primary Commands

```bash
# One-command installation & bootstrap
./install.sh

# Single-box operations
./start.sh up              # Start stack (and build if needed)
./start.sh health          # Health check gate (exits non-zero on failure)
./start.sh backup          # Create database dump + config archive + manifest
./start.sh restore [id]    # Restore database and config from backup
./start.sh upgrade         # Auto-backup, git pull, rebuild, migrate, health gate
./start.sh wizard          # Interactive onboarding & cost profile setup CLI
./start.sh logs [service]  # Tail container logs
./start.sh down            # Gracefully stop containers

# Local development & testing
.venv/bin/python -m pytest tests/unit/ -q      # Run unit test suite
cd frontend && npm run dev                     # Run Next.js dev server
```

---

## Key Invariants & Safety Principles

1. **Zero Data Loss & Key Guard**: Never overwrite or regenerate `APP_SECRET_KEY` or `LLM_CREDENTIAL_KEY` when an existing Postgres volume exists.
2. **Safe Defaults**: Auto-trading (`ai_trading_enabled`) is strictly pinned to `false` on clean install.
3. **No Hardcoded Models**: Model tiers are resolved dynamically via `llm_tier_bindings` and `config/llm_tiers.yaml`.
4. **Never Fail Silently on Decision Paths**: Decision paths must never swallow exceptions or return plausible-looking fake data without clear fallback markers.

---

<!-- code-review-graph MCP tools -->
## MCP Tools: codebase-memory / code-review-graph

**IMPORTANT: ALWAYS prefer MCP graph tools over Grep/Glob/Read for code discovery.**

### Priority Order:
1. `search_graph` — find functions, classes, routes, variables by pattern
2. `trace_path` — trace callers or callees of a function
3. `get_code_snippet` — read specific function/class source code
4. `query_graph` — run Cypher queries for complex patterns
5. `get_architecture` — high-level project summary
