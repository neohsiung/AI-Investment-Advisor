# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- DB schema normalization with updated models and Alembic migration (Phase 1)
- LLM Gateway TTL caching and config chain optimization (Phase 2)
- Sentinel D10 allocation drift detection in `_do_send_alert` (Phase 4)
- TelegramAdapter with comprehensive unit tests and stabilized dependencies (Phase 5)

### Changed
- Consolidated agents: `macro_agent` logic merged into `macro_scout_agent` (Phase 3)
- Rebalanced complexity detector weights in V2 for improved cognitive layer routing (Phase 6)
- Removed `"list"` from `DEESCALATING_KEYWORDS` in V1 complexity detector (Phase 6)

### Fixed
- Broken imports/references in `experience_replay_service.py` and `memory_distillation_service.py` (Phase 3)
- Lowered confidence fallback threshold to 0.4 in `ComplexityDetector` to prevent unintended downgrades (Phase 6)
- Signature mismatch in `StructuralFeatures.complexity_score()` regarding `text_length` (Phase 6)

### Removed
- Redundant prompt files: `prompts/fundamental_scout_agent.txt`, `prompts/macro_agent.txt`, `prompts/momentum_scout_agent.txt` (Phase 3)
- Obsolete Alembic migrations related to cost tracking (Phase 1)
