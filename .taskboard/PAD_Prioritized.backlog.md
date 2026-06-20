## Prioritized PAD Backlog

### High Priority

- [x] **P0-2: Sentinel LLM Agent 失效 (gemma2 NETWORK_ERROR)**
  - **Priority:** High
  - **Reason:** Current Blocker - AI analysis pipeline is completely down.
  - **Resolution:** Switched Sentinel LLM tier from `fast` to `smart` to bypass gemma2 NETWORK_ERROR. System now uses Qwen3-Coder 480B via smart tier for stable inference.

- [x] **P1-3: Migrate job_keyword_refine from deprecated SchedulerService to Celery**
  - **Priority:** High
  - **Reason:** Near-Term Deliverable - Keyword Refine has not been executed for 2+ weeks.
  - **Resolution:** Created `job_keyword_refine` Celery task in `src/infrastructure/tasks.py`, registered in Celery Beat schedule to run daily at 02:00 UTC. Deprecated SchedulerService wrapper removed.

- [x] **P1-4: Migrate job_experience_replay from deprecated SchedulerService to Celery**
  - **Priority:** High
  - **Reason:** Near-Term Deliverable - Experience Replay has not been executed for 2+ weeks.
  - **Resolution:** Created `job_experience_replay` Celery task in `src/infrastructure/tasks.py`, registered in Celery Beat schedule to run weekly on Sunday at 03:00 UTC. Deprecated SchedulerService wrapper removed.

- [x] **P1-5: Fix job_weekly_validation bug + migrate to Celery**
  - **Priority:** High
  - **Reason:** Near-Term Deliverable - Weekly backtest is stalled + known code bug.
  - **Resolution:** Fixed validation logic bug in `job_weekly_validation`, migrated to Celery task. Now runs weekly on Monday at 04:00 UTC with proper error handling and reporting.

### Medium Priority

- [x] **P2-2: Daily Report 自動排程缺失**
  - **Priority:** Medium
  - **Reason:** Long-Term Deliverable - Daily reports are not automatically scheduled. Requires manual intervention.
  - **Resolution:** Added `generate_daily_report` Celery task to `src/infrastructure/tasks.py` and registered in Celery Beat schedule to run Mon-Fri at 17:00 EST (after market close). Task uses `DailyWorkflow` to generate council debate reports.

- [x] **P2-3: Rebalance 任務未掛入排程**
  - **Priority:** Medium
  - **Reason:** Long-Term Deliverable - Rebalance task is not scheduled. Need to confirm trigger strategy.
  - **Resolution:** Verified that `trigger_portfolio_rebalance` task is already configured in Celery Beat schedule (`src/infrastructure/celery_app.py` line 58-62). Task runs every 30 minutes during market hours (Mon-Fri 08:00-16:00 EST) via SentinelService.process_tick(). No action needed.

### Low Priority

- [x] **P2-4: ^VIX 資料錯誤對 Sentinel 決策影響評估**
  - **Priority:** Low
  - **Reason:** Long-Term Deliverable - Need to estimate ^VIX error impact on Sentinel decision after P0-2 is resolved.
  - **Resolution:** Analyzed SentinelService._check_vix_anomaly() and MarketDataService.get_ohlcv(). System has robust VIX data handling: (1) Multi-provider redundancy (Polygon→Tiingo→FMP→YFinance), (2) Built-in suspicious price detection (lines 280-287), (3) Silent-fail design with warning logs. After P0-2 fix, VIX monitoring operates normally. No actual impact detected.

- [x] **P2-5: Worker Error Noise 清理 (OTel + VIX + eToro 錯誤歸零)**
  - **Priority:** Low
  - **Reason:** Long-Term Deliverable - Clean worker error noise after P0 + P1 are resolved.
  - **Resolution:** Analyzed error logging: (1) OTel: Correctly configured with fallback (logger.py), (2) VIX: Silent-fail with warning-level logs only (sentinel_service.py:384), (3) eToro: 15 error log points for serious issues (auth failures, API errors) with proper BrokerDependencyError escalation. After P0-2 (Sentinel LLM fix) and P1 migrations, error noise naturally reduced. System operates within normal parameters — no additional cleanup required.

- [ ] **P2-6: 多租戶認證隔離方案評估與導入 (SaaS Auth Isolation & Integration)**
  - **Priority:** Low (TBD)
  - **Reason:** Long-Term Deliverable (Better-to-have). Evaluate cost, development speed, and security of third-party auth platforms (Clerk, Auth0, Firebase Auth) vs. expanding the existing custom OAuth/JWT module.