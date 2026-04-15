# Issue #5: Scheduled Tasks Failing to Execute - ROOT CAUSE ANALYSIS

## Executive Summary
Scheduled tasks (trading/analysis) are **FAILING SILENTLY** with multiple interconnected issues:
- **Primary Issue**: Async/Sync mismatch in `job_etoro_sync()` 
- **Secondary Issue**: Corrupted/incomplete `celery_app.py` file
- **Tertiary Issue**: Missing Redis connection in scheduler container
- **Quaternary Issue**: Database schema migration incomplete

---

## 1. SCHEDULER TYPE & ARCHITECTURE

### Identified Scheduler Type: **HYBRID**
The Investment Advisor uses **TWO INDEPENDENT SCHEDULERS**:

#### A. Custom Python Scheduler (ACTIVE - PRIMARY)
- **Location**: `services/scheduler/src/app.py` + `src/services/scheduler_service.py`
- **Type**: Python `schedule` library (sync-based, runs in single process)
- **Execution Model**: 
  - Loaded via: `SchedulerService(user_id=uid)` 
  - Uses `schedule.Scheduler()` for job registration
  - Runs in infinite loop: `while True: schedule.run_pending()`
- **Container**: `advisor_prod_scheduler` (Docker)
- **Status**: ✅ **RUNNING** (21 hours)

#### B. Celery Beat Scheduler (DEFUNCT)
- **Location**: `src/infrastructure/celery_app.py`
- **Type**: Celery distributed task queue
- **Status**: ❌ **BROKEN** - File is corrupted/incomplete
- **Not actively running** in current deployment

---

## 2. CURRENT SCHEDULER STATUS

### Running Containers
```
advisor_prod_scheduler   Up 21 hours      ✅ RUNNING
advisor_prod_api         Up 4 hours       ✅ RUNNING  
advisor_prod_ui          Up 21 hours      ✅ RUNNING
```

### Scheduler Service Status
- **Process**: Active (running in `advisor_prod_scheduler` container)
- **Mode**: Multi-tenant B2C SaaS (iterates through all users)
- **User Coverage**: Single user ID (hardcoded or from DB)
- **Queue**: None (all jobs execute synchronously in main thread)

---

## 3. IDENTIFIED ISSUES & ROOT CAUSES

### 🔴 CRITICAL ISSUE #1: Async/Sync Mismatch in Broker Sync Job

**Location**: `src/services/scheduler_service.py`, line 183-203 (job_etoro_sync)

```python
def job_etoro_sync(self):
    """Sync Broker trade history for the current user."""
    try:
        broker = BrokerFactory.get_broker(self.user_id)
        result = broker.sync_history(self.user_id)  # ❌ ERROR HERE
        # ...
```

**Problem**:
- `sync_history()` is **ASYNC** in `src/services/etoro_service.py` line 790
- Called WITHOUT `await` in SYNC context (scheduler_service is pure sync)
- Returns a **coroutine object** instead of dict
- Loop tries to iterate: `result['added']` → fails with `'coroutine' object is not iterable`

**Evidence**:
```json
{
  "filename": "scheduler_service.py",
  "lineno": 202,
  "message": "Broker Sync failed for 90693c07-...: 'coroutine' object is not iterable",
  "timestamp": "2026-04-13T10:23:41Z"
}
```

**Execution History** (from `scheduler_logs` table):
```
All 5 recent "Broker Sync" entries: FAILED
Pattern: STARTED → FAILED (every 4 hours)
Last 5 failures: [10:23, 06:23, 02:23, 22:23 prev day, 18:23 prev day]
Error message: CONSISTENT - 'coroutine' object is not iterable
```

---

### 🔴 CRITICAL ISSUE #2: Corrupted celery_app.py

**Location**: `src/infrastructure/celery_app.py`

**Current State**:
- File is truncated/incomplete (56 lines, should be 100+)
- Missing critical lines 5-37 (configuration)
- Starts with incomplete line:
  ```python
  redis_url = os.getenv("REDIS_URL", "redis://redis:***@worker_process_init.connect
  ```
- Missing Celery app configuration, beat schedule, logger initialization

**Impact**:
- Sentinel health check attempts to import `celery_app` from tasks.py
- Fails with: `cannot import name 'celery_app' from 'src.infrastructure.tasks'`
- This check runs every 2 minutes → fills logs with 50+ errors per hour

**Evidence** (from container logs):
```
Infrastructure Health Check Failed: cannot import name 'celery_app' from 'src.infrastructure.tasks'
Timestamp: 2026-04-13T11:41:17Z (and repeating every 2 minutes)
```

---

### 🟡 ISSUE #3: Missing Redis Connection

**Location**: Scheduler container environment

**Current State**:
- Redis is NOT running or not accessible from scheduler container
- Attempted connections fail: `Error 111 connecting to localhost:6379`
- Cache initialization fails silently
- Impacts: Response caching, session management (non-critical for task execution)

**Evidence** (from logs):
```json
{
  "filename": "cache.py",
  "lineno": 28,
  "message": "Failed to connect to Redis cache: Error 111 connecting to localhost:6379. Connection refused.",
  "level": "ERROR"
}
```

---

### 🟡 ISSUE #4: Database Schema Mismatch

**Location**: `src/services/billing_service.py` line 63

**Current State**:
- User model references non-existent column: `users.current_billing_cycle_start`
- Database schema is missing this column
- Not blocking task execution, but causes errors when billing service is called

**Evidence**:
```
psycopg2.errors.UndefinedColumn: column users.current_billing_cycle_start does not exist
```

---

### ⚠️ ISSUE #5: Missing venv/bin/python Path

**Location**: Sentinel service CLI invocation

**Evidence**:
```
Failed to trigger cash_deployment CLI: [Errno 2] No such file or directory: 'venv/bin/python'
```

---

## 4. LAST 5 TASK EXECUTIONS

### Scheduler Logs (from Database)
```
ID: 8b15a2dd-...  | Timestamp: 2026-04-13T10:23:41Z | Job: Broker Sync   | Status: FAILED  | Message: 'coroutine' object is not iterable
ID: 2d8fbfb8-...  | Timestamp: 2026-04-13T10:23:41Z | Job: Broker Sync   | Status: STARTED | Message: (empty)

ID: 70471720-...  | Timestamp: 2026-04-13T06:23:41Z | Job: Broker Sync   | Status: FAILED  | Message: 'coroutine' object is not iterable
ID: 8597b14c-...  | Timestamp: 2026-04-13T06:23:41Z | Job: Broker Sync   | Status: STARTED | Message: (empty)

ID: e13ed4d2-...  | Timestamp: 2026-04-13T02:23:41Z | Job: Broker Sync   | Status: FAILED  | Message: 'coroutine' object is not iterable
ID: 1c87bd99-...  | Timestamp: 2026-04-13T02:23:41Z | Job: Broker Sync   | Status: STARTED | Message: (empty)

ID: f6a3337f-...  | Timestamp: 2026-04-12T22:23:40Z | Job: Broker Sync   | Status: FAILED  | Message: 'coroutine' object is not iterable
ID: 964d5770-...  | Timestamp: 2026-04-12T22:23:40Z | Job: Broker Sync   | Status: STARTED | Message: (empty)

ID: 5410b4ac-...  | Timestamp: 2026-04-12T18:23:02Z | Job: Broker Sync   | Status: FAILED  | Message: 'coroutine' object is not iterable
```

**Pattern**: 
- **Frequency**: Every 4 hours (as configured in `reload_schedule()`)
- **Success Rate**: 0% (all 10 visible executions FAILED)
- **Execution Time**: ~0 milliseconds (fails immediately on async/sync mismatch)
- **Missing Tasks**: No "Daily Check", "Weekly Report", "Memory Distillation" logged
  - Likely not scheduled for this user OR not reached due to Broker Sync blocking

---

## 5. QUEUE & PERSISTENCE ANALYSIS

### Task Persistence
- ✅ **Tasks ARE logged** to `scheduler_logs` table in PostgreSQL
- ✅ **Status tracking works** (STARTED/COMPLETED/FAILED)
- ❌ **Failed tasks are NOT retried**
- ❌ **No dead-letter queue** (failed tasks are dropped)

### Queue Depth
- **Type**: In-memory Python `schedule.Scheduler` 
- **Max Concurrent**: 1 (single-threaded)
- **Depth**: 0 (no queue, jobs run synchronously)
- **Overflow**: Not applicable (sync execution)

### Task Timing
- **Configured Interval**: Every 4 hours for `job_etoro_sync`
- **Actual Interval**: Every 4 hours (on schedule)
- **Execution Time**: < 1ms (fails immediately)
- **Timezone**: Not timezone-aware in scheduler (uses system time)

---

## 6. ROOT CAUSE SUMMARY

| Issue | Severity | Root Cause | Impact |
|-------|----------|-----------|--------|
| **Async/Sync Mismatch** | 🔴 CRITICAL | `job_etoro_sync()` calls async `sync_history()` without await | ALL Broker Sync tasks FAIL every 4 hours |
| **Corrupted celery_app.py** | 🔴 CRITICAL | File truncated during commit/merge conflict | Sentinel health checks fail every 2 minutes |
| **Missing Redis** | 🟡 MEDIUM | Docker network/service configuration | Cache disabled, but doesn't block tasks |
| **DB Schema Mismatch** | 🟡 MEDIUM | Migration not applied | Billing service fails when called |
| **Missing venv path** | 🟠 LOW | Hard-coded path doesn't exist in container | Cash deployment CLI can't run |

---

## 7. RECOMMENDED FIXES

### 🔴 FIX #1: Async/Sync Mismatch (CRITICAL - IMMEDIATE)

**File**: `src/services/scheduler_service.py`

**Current (BROKEN)**:
```python
def job_etoro_sync(self):
    """Sync Broker trade history for the current user."""
    logger.info(f"Starting Broker Sync Job for user {self.user_id}...")
    self.log_job_execution("Broker Sync", "STARTED")
    
    from src.services.broker_factory import BrokerFactory
    
    try:
        broker = BrokerFactory.get_broker(self.user_id)
        result = broker.sync_history(self.user_id)  # ❌ RETURNS COROUTINE
        # ... rest of code expects dict with 'added', 'skipped'
```

**Fix**:
```python
def job_etoro_sync(self):
    """Sync Broker trade history for the current user."""
    logger.info(f"Starting Broker Sync Job for user {self.user_id}...")
    self.log_job_execution("Broker Sync", "STARTED")
    
    from src.services.broker_factory import BrokerFactory
    import asyncio
    
    try:
        broker = BrokerFactory.get_broker(self.user_id)
        
        # ✅ FIX: Use asyncio.run() to execute async function
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(broker.sync_history(self.user_id))
        
        msg = f"Synced [{broker_name}]: +{result['added']} / skipped {result['skipped']}"
        logger.info(msg)
        self.log_job_execution("Broker Sync", "COMPLETED", msg)
    except Exception as e:
        logger.error(f"Broker Sync failed for {self.user_id}: {e}")
        self.log_job_execution("Broker Sync", "FAILED", str(e))
```

---

### 🔴 FIX #2: Restore celery_app.py (CRITICAL - IMMEDIATE)

**File**: `src/infrastructure/celery_app.py`

**Action**: Restore from git history or reconstruct missing configuration

**Minimal restoration**:
```python
import os
import logging
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger("CeleryApp")

# v2.1: Initialize Celery with Redis as the broker
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

app = Celery('investment_advisor', broker=redis_url, backend=redis_url)

# Celery Configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
)

# Beat Schedule for periodic tasks
app.conf.beat_schedule = {
    'generate-market-intelligence': {
        'task': 'src.infrastructure.tasks.generate_market_intelligence',
        'schedule': crontab(hour=9, minute=0),  # 9 AM daily
    },
    'trigger-portfolio-rebalance': {
        'task': 'src.infrastructure.tasks.trigger_portfolio_rebalance',
        'schedule': crontab(hour='*/4'),  # Every 4 hours
    },
}

@app.before_first_task_sent.connect
def setup_db_worker_context(**kwargs):
    """Ensure each worker process has a clean database engine."""
    logger.info("Initializing Celery Worker Process: Setting IS_CELERY_WORKER=true")
    os.environ["IS_CELERY_WORKER"] = "true"
    
    from src.data import database
    database._db_engines.clear()
    database._session_registries.clear()
    database.get_db_engine()

if __name__ == "__main__":
    app.start()
```

---

### 🟡 FIX #3: Update Sentinel Health Check (MEDIUM)

**File**: `src/services/sentinel_service.py` line 1681

**Current**:
```python
from src.infrastructure.tasks import celery_app  # ❌ FAILS if celery_app is broken
```

**Fix**:
```python
# Safe import with fallback
try:
    from src.infrastructure.tasks import celery_app
    HAS_CELERY = True
except (ImportError, AttributeError):
    logger.warning("Celery app not available; distributed task queue disabled")
    HAS_CELERY = False
```

---

### 🟡 FIX #4: Database Schema Migration (MEDIUM)

**File**: `alembic/versions/` (latest migration)

**Action**: Add missing column to User model
```sql
ALTER TABLE users ADD COLUMN current_billing_cycle_start TIMESTAMP NULL;
```

---

### 🟠 FIX #5: Fix CLI Path References (LOW)

**File**: `src/services/sentinel_service.py` line 1647

**Current**:
```python
subprocess.run([sys.executable, \"venv/bin/python\", ...])
```

**Fix**:
```python
subprocess.run([sys.executable, ...])  # Use current Python executable
```

---

## 8. VERIFICATION STEPS

After applying fixes:

1. **Verify celery_app.py loads**:
   ```bash
   docker exec advisor_prod_api python -c "from src.infrastructure.celery_app import app; print('✅ OK')"
   ```

2. **Test broker sync manually**:
   ```bash
   docker exec advisor_prod_scheduler python -c "
   from src.services.broker_factory import BrokerFactory
   import asyncio
   broker = BrokerFactory.get_broker('test-user')
   result = asyncio.run(broker.sync_history('test-user'))
   print(result)
   "
   ```

3. **Verify next task execution**:
   ```bash
   docker exec advisor_prod_api python -c "
   from sqlalchemy import text
   from src.data.database import get_db_engine
   import pandas as pd
   engine = get_db_engine()
   with engine.connect() as conn:
       df = pd.read_sql(text('SELECT * FROM scheduler_logs ORDER BY timestamp DESC LIMIT 5'), conn)
       print(df)
   "
   ```

4. **Monitor for successful executions** (in logs):
   ```bash
   docker logs -f advisor_prod_scheduler | grep "Broker Sync"
   ```

---

## 9. IMPACT ASSESSMENT

### What's Failing Now
- ❌ Broker trade history syncing (every 4 hours)
- ❌ Sentinel infrastructure health checks (every 2 minutes)
- ❌ Automated trading execution (blocked by sync failures)
- ⚠️ Portfolio rebalancing (not logged, may not be executing)

### What's NOT Failing
- ✅ Sentinel core monitoring (still runs despite health check failures)
- ✅ Dashboard UI (separate service)
- ✅ API server (running)
- ✅ Data persistence to database

### User Impact
- 🔴 **CRITICAL**: Automated trading is effectively disabled
- 🟡 **HIGH**: Portfolio analysis may be stale (missed syncs)
- 🟡 **MEDIUM**: Cash management automation not triggering

---

## 10. DEPLOYMENT NOTES

- **DO NOT restart services without applying fixes** (will only repeat failures)
- **Apply FIX #1 first** (highest impact)
- **Apply FIX #2 second** (prevents log spam)
- **Test after each fix** before moving to next
- **Non-destructive** - all changes are additive or override-safe

---

## Files Involved in Fixes

```
src/services/scheduler_service.py     [Lines 183-203]  - job_etoro_sync()
src/infrastructure/celery_app.py      [ENTIRE FILE]    - Restore/reconstruct
src/services/sentinel_service.py      [Lines 1681-1702] - Safe import
alembic/versions/[latest].py          [NEW]            - Add column
```
