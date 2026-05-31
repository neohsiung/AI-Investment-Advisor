## Prioritized PAD Backlog

### High Priority

- **P0-2: Sentinel LLM Agent 失效 (gemma2 NETWORK_ERROR)**
  - **Priority:** High
  - **Reason:** Current Blocker - AI analysis pipeline is completely down.

- **P1-3: Migrate job_keyword_refine from deprecated SchedulerService to Celery**
  - **Priority:** High
  - **Reason:** Near-Term Deliverable - Keyword Refine has not been executed for 2+ weeks.

- **P1-4: Migrate job_experience_replay from deprecated SchedulerService to Celery**
  - **Priority:** High
  - **Reason:** Near-Term Deliverable - Experience Replay has not been executed for 2+ weeks.

- **P1-5: Fix job_weekly_validation bug + migrate to Celery**
  - **Priority:** High
  - **Reason:** Near-Term Deliverable - Weekly backtest is stalled + known code bug.

### Medium Priority

- **P2-2: Daily Report 自動排程缺失**
  - **Priority:** Medium
  - **Reason:** Long-Term Deliverable - Daily reports are not automatically scheduled. Requires manual intervention.

- **P2-3: Rebalance 任務未掛入排程**
  - **Priority:** Medium
  - **Reason:** Long-Term Deliverable - Rebalance task is not scheduled. Need to confirm trigger strategy.

### Low Priority

- **P2-4: ^VIX 資料錯誤對 Sentinel 決策影響評估**
  - **Priority:** Low
  - **Reason:** Long-Term Deliverable - Need to estimate ^VIX error impact on Sentinel decision after P0-2 is resolved.

- **P2-5: Worker Error Noise 清理 (OTel + VIX + eToro 錯誤歸零)**
  - **Priority:** Low
  - **Reason:** Long-Term Deliverable - Clean worker error noise after P0 + P1 are resolved.