# EXECUTION LOG: Issue #4 & #5 Fixes - Investment Advisor v6.3.1

## Execution Timeline
- **Start Time**: 2026-04-13 20:05:00 UTC
- **Project**: Investment Advisor v6.3.1
- **Location**: ~/Work/Projects/AI/investment-advisor

---

## PHASE 1: Fix Scheduler (Issue #5)

### Target Files:
- `src/services/scheduler_service.py` - Fix async/await handling in job methods
- `src/infrastructure/celery_app.py` - Verify restoration (already done - 56 lines)
- `tests/unit/services/test_scheduler_service.py` - Run tests

### Issue Root Cause:
- Issue #5: Scheduler Job Methods call async functions (broker.sync_history) without proper asyncio.run() wrapping
- The job_etoro_sync() method at line 197 calls broker.sync_history() which could be async (for IBKR) but is called synchronously

### Step 1.1: Current State of scheduler_service.py

**File**: src/services/scheduler_service.py
**Current Line Count**: 382 lines (as expected)
**Status**: Partial async handling already applied for job_keyword_refine() and job_minutely_tick()

**Issue Found**:
- Line 197: `result = broker.sync_history(self.user_id)` - needs async handling
- If broker is IBKR (has async sync_history), this will fail
- If broker is eToro (has sync sync_history), this works

**Fix Required**: Wrap broker.sync_history() call with asyncio.run() to handle both cases

### Step 1.2: Verify celery_app.py Restoration

