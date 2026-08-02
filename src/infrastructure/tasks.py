import os
import pandas as pd
import pandas_market_calendars as mcal
from datetime import datetime
from src.infrastructure.celery_app import app
from src.services.intelligence_service import IntelligenceService
from src.services.settings_service import SettingsService
from src.utils.logger import setup_logger

logger = setup_logger("CeleryTasks")

def is_market_open_today():
    """Checks if the NYSE is open today (EST)."""
    nyse = mcal.get_calendar("NYSE")
    today = pd.Timestamp.now(tz="US/Eastern").normalize()
    schedule = nyse.schedule(start_date=today, end_date=today)
    return not schedule.empty

import asyncio

def _run_async_safe(coro):
    """
    Safely runs an async coroutine from a synchronous Celery task.
    Handles nested event loop issues in some environments.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, we need to create a new one in a thread
            # or use a different approach. In Celery workers, it shouldn't be running.
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists, create a new one
        return asyncio.run(coro)

def _resolve_target_users(user_id: str = None) -> list:
    """解析目標租戶：指定則回傳單一；否則從 DB 查詢所有活躍用戶。"""
    if user_id:
        return [user_id]
    from src.repositories.user_repository import AlchemyUserRepository
    users = AlchemyUserRepository().get_all_active_users()
    if not users:
        fallback = os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
        return [fallback] if fallback else []
    return users

@app.task(name="src.infrastructure.tasks.dispatch_market_intelligence")
def dispatch_market_intelligence():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        generate_market_intelligence.delay(user_id=uid)
    return f"Dispatched {len(users)} market_intelligence tasks"

@app.task(name="src.infrastructure.tasks.generate_market_intelligence")
def generate_market_intelligence(user_id: str = None):
    # ... check market open ...
    if not is_market_open_today():
        return "Skipped"

    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("generate_market_intelligence: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        settings_svc = SettingsService(user_id=user_id)
        intel_svc = IntelligenceService(settings_service=settings_svc, user_id=user_id)
        
        # 3. Execution (Async as sync)
        briefing = _run_async_safe(intel_svc.compute_briefing())
        
        # 4. Persistence
        settings_svc.save_setting("cached_intelligence_briefing", briefing, user_id=user_id)
        settings_svc.save_setting("last_intelligence_timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        return "Success"
        
    except Exception as e:
        logger.error(f"Failed to generate intelligence in background: {e}")
        return f"Error: {str(e)}"

# dispatch_portfolio_rebalance removed 2026-08-02 along with the
# "portfolio-rebalance-trigger" beat entry — see the note in celery_app.py.
# Its only caller was that schedule.
# 2026-08-02 隨 beat 排程一併移除，唯一呼叫端就是該排程。


@app.task(name="src.infrastructure.tasks.trigger_portfolio_rebalance")
def trigger_portfolio_rebalance(user_id: str = None):
    """
    Executes a high-priority rebalance check via SentinelService.

    User-initiated path only (dashboard "Rebalance now"). Passes force=True so
    it bypasses the per-minute tick lock — otherwise a user pressing the button
    at :00 would be silently swallowed by the lock the scheduled tick just took.
    The endpoint is rate-limited (1/5minute), so forcing is safe.
    使用者主動觸發的路徑，force=True 略過每分鐘 tick 鎖，否則按鈕會被排程剛取得的鎖吃掉。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("trigger_portfolio_rebalance: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from src.services.sentinel_service import SentinelService
        sentinel = SentinelService(user_id=user_id)
        _run_async_safe(sentinel.process_tick(force=True))
        return "Success"
    except Exception as e:
        logger.error(f"Failed to trigger rebalance in background: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.dispatch_sentinel_tick")
def dispatch_sentinel_tick():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        sentinel_tick.delay(user_id=uid)
    return f"Dispatched {len(users)} sentinel_tick tasks"

@app.task(name="src.infrastructure.tasks.sentinel_tick")
def sentinel_tick(user_id: str = None):
    """
    Periodic heartbeat for Sentinel system (Minutely).
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("sentinel_tick: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from src.services.sentinel_service import SentinelService
        sentinel = SentinelService(user_id=user_id)
        _run_async_safe(sentinel.process_tick())
        return "Success"
    except Exception as e:
        logger.error(f"Sentinel heartbeat failed: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.dispatch_broker_sync")
def dispatch_broker_sync():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        sync_broker_positions.delay(user_id=uid)
    return f"Dispatched {len(users)} broker_sync tasks"

@app.task(name="src.infrastructure.tasks.sync_broker_positions")
def sync_broker_positions(user_id: str = None):
    """
    Syncs portfolio positions from broker (Every 5 mins).
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("sync_broker_positions: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from src.services.transaction_service import TransactionService
        tx_svc = TransactionService(user_id=user_id)
        _run_async_safe(tx_svc.sync_broker_positions())
        return "Success"
    except Exception as e:
        logger.error(f"Broker sync failed: {e}")
        return f"Error: {str(e)}"

@app.task(name="src.infrastructure.tasks.dispatch_memory_distill")
def dispatch_memory_distill():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        distill_memories.delay(user_id=uid)
    return f"Dispatched {len(users)} memory_distill tasks"

@app.task(name="src.infrastructure.tasks.distill_memories")
def distill_memories(user_id: str = None):
    """
    Daily cognitive memory distillation: archives STM (cognitive_memories older
    than 30 days) into LTM (pgvector) via CognitiveMemoryManager.archive_to_long_term().

    2026-07-12 fix: this previously called `memory_mgr.distill_memories()`, a
    method that never existed on CognitiveMemoryManager (only
    `distill_conversation(channel_id)` and `archive_to_long_term(days_old)` do)
    — every daily/weekly run silently AttributeError'd and STM->LTM
    consolidation never actually ran in production. Confirmed via direct
    reproduction before this fix.
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("distill_memories: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from src.services.cognitive_memory_manager import CognitiveMemoryManager
        memory_mgr = CognitiveMemoryManager(user_id=user_id)
        archived_count = memory_mgr.archive_to_long_term(days_old=30)
        result = f"Success: archived {archived_count} memories"
    except Exception as e:
        logger.error(f"Memory distillation failed: {e}")
        result = f"Error: {str(e)}"

    # P1 learning loop (2026-07-11): resolve any decisions whose horizon has
    # elapsed — alpha-anchored reflection. Non-blocking: failure here must not
    # fail the daily distillation task.
    try:
        from src.services.outcome_reflection_service import OutcomeReflectionService
        summary = OutcomeReflectionService(user_id=user_id).resolve_pending()
        logger.info(f"decision_outcomes resolve_pending: {summary}")
    except Exception as e:
        logger.warning(f"resolve_pending failed (non-blocking): {e}")

    # B-P3.1 Rule backtest gate evaluation
    try:
        from src.services.rule_lifecycle_service import RuleLifecycleService
        gate_stats = _run_async_safe(RuleLifecycleService(user_id=user_id).gate_candidate_rules())
        logger.info(f"distill_memories gate_candidate_rules: {gate_stats}")
    except Exception as e:
        logger.warning(f"gate_candidate_rules failed (non-blocking) in distill_memories: {e}")

    return result

@app.task(name="src.infrastructure.tasks.dispatch_experience_replay")
def dispatch_experience_replay():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        experience_replay.delay(user_id=uid)
    return f"Dispatched {len(users)} experience_replay tasks"

@app.task(name="src.infrastructure.tasks.experience_replay")
def experience_replay(user_id: str = None):
    """
    Weekly Experience Replay optimization to tune Sentinel thresholds based on history.
    每週經驗復盤：根據歷史警報頻率與績效動態調整 Sentinel 閾值。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("experience_replay: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from src.services.experience_replay_service import ExperienceReplayService
        # L4 復盤：低頻（每週）高槓桿，用最強模型（2026-07-11）
        svc = ExperienceReplayService(tier="advanced")
        result = svc.optimize_thresholds(user_id)
        logger.info(f"experience_replay completed: {result}")
        return f"OK: {result}"
    except Exception as e:
        logger.error(f"experience_replay failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.dispatch_keyword_refine")
def dispatch_keyword_refine():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        keyword_refine.delay(user_id=uid)
    return f"Dispatched {len(users)} keyword_refine tasks"

@app.task(name="src.infrastructure.tasks.keyword_refine")
def keyword_refine(user_id: str = None):
    """
    Weekly risk keyword discovery and weight refinement.
    每週風險關鍵字探索與權重精煉。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("keyword_refine: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from src.services.risk_keyword_service import RiskKeywordService
        keyword_svc = RiskKeywordService()
        result = keyword_svc.refine()
        logger.info(f"keyword_refine completed: {result}")
        return f"OK: {result}"
    except Exception as e:
        logger.error(f"keyword_refine failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.dispatch_rule_curation")
def dispatch_rule_curation():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        curate_agent_rules.delay(user_id=uid)
    return f"Dispatched {len(users)} rule_curation tasks"

@app.task(name="src.infrastructure.tasks.curate_agent_rules")
def curate_agent_rules(user_id: str = None):
    """
    Weekly agent_rules curation (Loop 1, B-P2.1): backfill missing rule
    embeddings, dedupe/merge near-duplicate active rules per agent
    (advanced-tier judge), then retire under-cited or poorly-scoring
    rules. Pure maintenance — never touches score accumulated via
    resolve_pending's per-decision EWMA backfill.
    每週規則整理：補齊嵌入、去重（進階模型判定）、退役低效規則。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("curate_agent_rules: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from sqlalchemy import text
        from src.data.database import get_db_engine
        from src.services.rule_lifecycle_service import RuleLifecycleService

        # B-P3.1 Rule backtest gate evaluation
        try:
            gate_stats = _run_async_safe(RuleLifecycleService(user_id=user_id).gate_candidate_rules())
            logger.info(f"curate_agent_rules gate_candidate_rules: {gate_stats}")
        except Exception as e:
            logger.warning(f"gate_candidate_rules failed (non-blocking) in curate_agent_rules: {e}")

        engine = get_db_engine()
        with engine.connect() as conn:
            agent_names = [
                row[0] for row in conn.execute(
                    text("SELECT DISTINCT agent_name FROM agent_rules WHERE user_id = :uid AND status = 'active'"),
                    {"uid": user_id},
                ).fetchall()
            ]

        svc = RuleLifecycleService(user_id=user_id)
        embedded = 0
        deduped = 0
        for agent_name in agent_names:
            embedded += _run_async_safe(svc.backfill_embeddings(agent_name, user_id=user_id))
            deduped += _run_async_safe(svc.dedupe_agent_rules(agent_name, user_id=user_id))
        retired = svc.expire_stale_rules(user_id=user_id)

        result = f"OK: {len(agent_names)} agents, {embedded} embedded, {deduped} deduped, {retired} expired"
        logger.info(f"curate_agent_rules: {result}")
        return result
    except Exception as e:
        logger.error(f"curate_agent_rules failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.dispatch_user_preferences")
def dispatch_user_preferences():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        update_user_preferences.delay(user_id=uid)
    return f"Dispatched {len(users)} user_preferences tasks"

@app.task(name="src.infrastructure.tasks.update_user_preferences")
def update_user_preferences(user_id: str = None):
    """
    Weekly user-preference profile update (Loop 3, B-P2.2): aggregates
    interaction_feedback (approve/reject + reason codes) into a risk
    appetite score, sector aversions, and position-size comfort signal,
    plus a fast-tier prose summary injected into CIO's council prompt.
    每週用戶偏好更新：彙整拒絕原因為風險胃納/板塊迴避/部位舒適度。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("update_user_preferences: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        from src.services.user_preference_service import UserPreferenceService
        profile = _run_async_safe(UserPreferenceService(user_id).update_preferences())
        if profile is None:
            logger.info("update_user_preferences: no feedback history yet, skipping")
            return "OK: no feedback history"
        result = f"OK: risk_appetite={profile['risk_appetite_score']}, sectors={list(profile['sector_aversions'].keys())}"
        logger.info(f"update_user_preferences: {result}")
        return result
    except Exception as e:
        logger.error(f"update_user_preferences failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.dispatch_weekly_validation")
def dispatch_weekly_validation():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        weekly_validation.delay(user_id=uid)
    return f"Dispatched {len(users)} weekly_validation tasks"

@app.task(name="src.infrastructure.tasks.weekly_validation")
def weekly_validation(user_id: str = None):
    """
    Weekly Backtest Validation — runs simulation on major stocks to generate
    feedback examples from the past week.
    P1-5: Migrated from deprecated SchedulerService.job_weekly_validation.
    每週回測驗證：對主要標的執行模擬，生成過去一週的回饋樣本。
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("weekly_validation: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    tickers = ["AAPL", "TSLA", "NVDA", "SPY"]
    try:
        from src.services.backtest_service import BacktestService
        svc = BacktestService()
        for ticker in tickers:
            logger.info(f"weekly_validation: validating {ticker}...")
            _run_async_safe(svc.run_simulation(ticker, days_back=7))
        logger.info("weekly_validation completed")
        return f"OK: validated {', '.join(tickers)}"
    except Exception as e:
        logger.error(f"weekly_validation failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.dispatch_event_digest")
def dispatch_event_digest():
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        send_event_digest.delay(user_id=uid)
    return f"Dispatched {len(users)} event_digest tasks"

@app.task(name="src.infrastructure.tasks.send_event_digest")
def send_event_digest(user_id: str = None):
    """
    Hourly event-queue digest: pulls P0-P3 events accumulated in event_queue
    and dispatches them to matching DigestNodes in the registry, handles
    suppression/release/notification, and logs adapter response details.
    """
    from src.data.models import EventQueue
    from src.services.event_aggregator import EventAggregator
    from src.services.notification_service import NotificationService
    from src.services.settings_service import SettingsService
    from src.services.digest_nodes import REGISTRY

    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("send_event_digest: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    try:
        aggregator = EventAggregator()
        all_tiers = [EventQueue.TIER_P0, EventQueue.TIER_P1, EventQueue.TIER_P2, EventQueue.TIER_P3]
        events = aggregator.pull_multi_tier(user_id=user_id, tiers=all_tiers, max_total=200)

        if not events:
            logger.info("send_event_digest: no pending events, skipping notification")
            return "OK: no events"

        # Dispatch events to matching nodes
        node_events = {node.name: [] for node in REGISTRY}
        fallback_events = []
        
        for event in events:
            matched = False
            for node in REGISTRY:
                if node.selector(event):
                    node_events[node.name].append(event)
                    matched = True
                    break
            if not matched:
                fallback_events.append(event)
                
        # Fallback to investment_digest
        node_events["investment_digest"].extend(fallback_events)

        settings_svc = SettingsService(user_id=user_id)
        notification_svc = NotificationService.create_with_settings(
            settings_service=settings_svc, user_id=user_id
        )

        released_ids = []
        processed_ids = []
        dispatched_nodes = []

        for node in REGISTRY:
            node_list = node_events[node.name]
            if not node_list:
                continue

            should_suppress = node.suppress(node_list) if node.suppress else False
            if should_suppress:
                logger.info(f"Digest node '{node.name}' is suppressed. Releasing {len(node_list)} events.")
                released_ids.extend([e["id"] for e in node_list])
            else:
                title, content = node.composer(node_list)
                results = _run_async_safe(notification_svc.notify_all(
                    user_id=user_id,
                    title=title,
                    content=content,
                    category=node.category,
                    channels=node.channels
                ))
                logger.info(f"Digest node '{node.name}' dispatched. Results: {results}")
                processed_ids.extend([e["id"] for e in node_list])
                dispatched_nodes.append(node.name)

        if processed_ids:
            aggregator.mark_processed(processed_ids)
        if released_ids:
            aggregator.repo.release_batch(released_ids)

        summary = f"Processed {len(processed_ids)} events (dispatched: {', '.join(dispatched_nodes)}), released {len(released_ids)} events"
        logger.info(f"send_event_digest: {summary}")
        return f"Success: {summary}"
    except Exception as e:
        logger.error(f"send_event_digest failed: {e}", exc_info=True)
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.self_ops_check")
def self_ops_check():
    """
    Self-ops sentinel (Loop 2): dead-man switches + config-drift detection.
    Pure SQL against task_runs/expected_outcomes — zero LLM cost.
    Syncs expectations from the live beat schedule, then evaluates all of
    them, escalating breaches to event_queue (P1) and critical ones to
    notification channels.
    自我維運哨兵：dead-man 監控 + 組態漂移偵測,純 SQL,零 LLM 成本。
    """
    try:
        from src.services.self_ops_service import SelfOpsService
        svc = SelfOpsService()
        sync_result = svc.sync_beat_expectations()
        check_result = svc.check_all()
        n_breach = len(check_result.get("breaches", []))
        if sync_result.get("drift_disabled"):
            logger.warning(f"self_ops_check: schedule drift, disabled: {sync_result['drift_disabled']}")
        logger.info(f"self_ops_check: {sync_result['synced']} expectations, {n_breach} breach(es)")
        return f"OK: {n_breach} breaches"
    except Exception as e:
        logger.error(f"self_ops_check failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.cost_anomaly_check")
def cost_anomaly_check():
    """
    Daily LLM cost anomaly detection (Loop 2c): weekly-budget projection +
    2.5σ daily-spike detection over llm_usage_logs. Pure SQL, zero LLM cost.
    每日 LLM 成本異常偵測：週預算投影 + 單日 2.5σ 尖峰。
    """
    try:
        from src.services.self_ops_service import SelfOpsService
        result = SelfOpsService().check_cost_anomaly()
        n = len(result.get("breaches", []))
        logger.info(f"cost_anomaly_check: projected ${result['projected_week_usd']}/wk, {n} breach(es)")
        return f"OK: {n} breaches, projected ${result['projected_week_usd']}/wk"
    except Exception as e:
        logger.error(f"cost_anomaly_check failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.housekeep_event_queue")
def housekeep_event_queue():
    """
    Archives event_queue rows older than 72h to keep the queue lean.
    Ported from the never-scheduled `event_housekeeper.py` script (same root
    cause as send_event_digest above — see its docstring).
    將超過 72 小時的 event_queue 紀錄歸檔，避免佇列無限膨脹。
    """
    try:
        from src.services.event_aggregator import EventAggregator
        aggregator = EventAggregator()
        archived = aggregator.repo.archive_old_events(older_than_hours=72)
        logger.info(f"housekeep_event_queue: archived {archived} events")
        return f"Success: archived {archived} events"
    except Exception as e:
        logger.error(f"housekeep_event_queue failed: {e}")
        return f"Error: {str(e)}"


@app.task(name="src.infrastructure.tasks.dispatch_daily_report")
def dispatch_daily_report(force_report: bool = False):
    """Fan-out dispatcher: 查詢所有活躍租戶，為每位分派獨立 Task。"""
    users = _resolve_target_users()
    for uid in users:
        generate_daily_report.delay(user_id=uid, force_report=force_report)
    return f"Dispatched {len(users)} daily_report tasks"

@app.task(name="src.infrastructure.tasks.generate_daily_report", soft_time_limit=600, time_limit=660)
def generate_daily_report(user_id: str = None, force_report: bool = False):
    """
    Daily Report Generation — runs the DailyWorkflow to produce council debate report.
    P2-2: Migrated from deprecated SchedulerService.job_daily_check.
    每日報告生成：執行 DailyWorkflow 產生委員會辯論報告。
    
    Args:
        user_id: Target user ID (defaults to PRIMARY_USER_ID env var)
        force_report: Force report generation even if no significant changes
    """
    user_id = user_id or os.getenv("PRIMARY_USER_ID") or os.getenv("USER_ID")
    if not user_id:
        logger.error("generate_daily_report: user_id is required. Set PRIMARY_USER_ID env var or pass explicitly.")
        return "Error: user_id is required"
    
    # Check if market is open (unless force_report is requested)
    if not is_market_open_today() and not force_report:
        logger.info("Market is closed today, skipping daily report.")
        return "Skipped (Market Closed)"
    
    try:
        from src.services.workflow_service import DailyWorkflow
        
        # Run the daily workflow
        workflow = DailyWorkflow(user_id=user_id)
        result = _run_async_safe(workflow.run(dry_run=False, force_refresh=force_report))
        
        logger.info(f"daily_report completed for user {user_id}")
        return f"Success: Daily report generated for {user_id}"
    except Exception as e:
        logger.error(f"daily_report failed for user {user_id}: {e}")
        return f"Error: {str(e)}"
