# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Versioning note.** The active version line is `0.x`. The repository also
> carries older tags (`v9.0.0`, `v6.0.0`, `v1.6.0`, `v1.0.0`) from a prior
> numbering scheme; they are historical and do not supersede this line.

## [Unreleased]

## [0.3.0] - 2026-08-26

First release since `v0.2.1` (2026-05-10), covering 83 commits. Headline theme:
the eToro credential incident and the class of silent failures it exposed —
paths that logged an error, returned something plausible, and were never
noticed. See PRs #45, #47, #50, #53, #54.

### Added
- `021_backfill_integrity_checks` migration, idempotently installing the ten
  CHECK constraints on `transactions` and `position_lots` that prod never
  received (#54)
- SELL-side churn protection in `TradingProtectionsService`, kept fail-open so a
  query failure cannot lock a user into a position (#50)
- Redis `SETNX` lock on the Sentinel tick, removing ~18 duplicate paid LLM calls
  per trading day (#50)
- `weekly-report-trigger` now dispatches `WeeklyWorkflow.run_weekly_cycle()`;
  it previously pointed at `dispatch_market_intelligence`, so no weekly report
  had ever been generated (#53)
- Webhook duplicate detection via URL / `signal_id` in `WebhookService` (#47)
- DB schema normalization with updated models and Alembic migration (Phase 1)
- LLM Gateway TTL caching and config chain optimization (Phase 2)
- Sentinel D10 allocation drift detection in `_do_send_alert` (Phase 4)
- TelegramAdapter with comprehensive unit tests and stabilized dependencies (Phase 5)

### Changed
- `BrokerFactory` cache fingerprint no longer hashes credentials; it derives
  from non-sensitive values plus the credential row's `settings.updated_at`,
  clearing two HIGH CodeQL `py/weak-sensitive-data-hashing` alerts at the
  source rather than suppressing them (#50)
- `InteractionService` state moved from in-process dictionaries to shared Redis,
  fixing approval-action desync between the API and worker containers (#47)
- Settings writes changed from fire-and-forget to synchronous so callers see the
  real result (#50)
- Each repository now owns its session; the shared global registry is gone (#50)
- Notification category mapping normalized (`rebalance` → `trading`,
  `daily_digest` → `report`) to match the UI settings (#47)
- Consolidated agents: `macro_agent` logic merged into `macro_scout_agent` (Phase 3)
- Rebalanced complexity detector weights in V2 for improved cognitive layer routing (Phase 6)
- Removed `"list"` from `DEESCALATING_KEYWORDS` in V1 complexity detector (Phase 6)

### Fixed
- `UserFocusService.get_user_focus()` was synchronous while
  `EtoroService.get_watchlists()` is `async`, so the coroutine was never
  awaited; the resulting `'coroutine' object has no attribute 'get'` was
  swallowed by a blanket `except Exception`, leaving user focus permanently
  empty. Now `async` and awaited at both `CouncilService` call sites
- OpenRouter transport failures logged as a bare `OpenRouter API error:` with an
  empty message, because `str(e)` is empty for `ConnectError` / `ReadTimeout`.
  Both the request and stream paths now log the exception type and model
- `save_positions()` wrote to `positions`, a table dropped by `f9861a2caa12`
  during the v8 normalization. Every 5-minute `sync_broker_positions` raised
  `UndefinedTable` and, sharing one `try`, silently skipped the two steps after
  it — `position_lots` seeding and `update_daily_snapshot`. The dead method is
  removed and the Celery task now reports the service's error status instead of
  discarding it and returning `"Success"` (#54)
- `chk_tx_qty_positive` asserted an unconditional `quantity > 0`, which
  DEPOSIT / WITHDRAWAL legitimately violate (cash movements have no instrument);
  the constraint is now scoped (#54)
- `SentinelService.close()` called `settings_service.repo`, which has never
  existed — a guaranteed `AttributeError` that, sharing a `try` with the keyword
  close, leaked two sessions per call. Each close is now caught independently
  and named in the log (#53)
- eToro credentials were misclassified as mock data by a hardcoded prefix check
  and wiped; the check is removed and the portfolio cache isolated (#50)
- `RiskManager` now coerces `ai_trading_enabled` with `str()` before reading it,
  so a JSON boolean no longer breaks `.lower()` on every `execute_order` (#50)
- BUY-side protection queries changed to fail-closed (#50)
- Broker cache now reflects credential and mode changes immediately;
  a missing `etoro_mode` defaults to `demo` (#50)
- Telegram conversation agent async crash from invalid `to_thread` calls (#45)
- MCP WebSocket broadcast loop crash from undefined `summary` / `positions` (#47)
- Broken imports/references in `experience_replay_service.py` and `memory_distillation_service.py` (Phase 3)
- Lowered confidence fallback threshold to 0.4 in `ComplexityDetector` to prevent unintended downgrades (Phase 6)
- Signature mismatch in `StructuralFeatures.complexity_score()` regarding `text_length` (Phase 6)

### Removed
- `src/utils/crypto_utils.py`, dead code carrying a hardcoded Fernet key used as
  the "insecure default" when `MASTER_CRYPTO_KEY` is absent — and that variable
  appears in no compose file, k8s manifest or `.env.example`, so the hardcoded
  key was the only reachable path. Added to `DELETED_MODULES` so importing it
  fails rather than reviving the key. Encryption at rest goes through
  `APP_SECRET_KEY` / `LLM_CREDENTIAL_KEY` (#53)
- Duplicate Sentinel beat schedule overlapping the minutely tick (#50)
- Redundant prompt files: `prompts/fundamental_scout_agent.txt`, `prompts/macro_agent.txt`, `prompts/momentum_scout_agent.txt` (Phase 3)
- Obsolete Alembic migrations related to cost tracking (Phase 1)

### Security
- All 5 CodeQL alerts and 2 bandit medium findings fixed at the source, with no
  suppressions or dismissals (#50)
- `secret-scan.yml` only scanned the PR commit range, so a secret older than
  every current branch was invisible to CI (#53)

### Dependencies
- uv group bumps (#46, #48, #52), npm/yarn group bump (#51), axios (#49)

[0.3.0]: https://github.com/neohsiung/AI-Investment-Advisor/compare/v0.2.1...v0.3.0
