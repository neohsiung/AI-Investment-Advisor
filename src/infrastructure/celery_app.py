import os
import logging
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

logger = logging.getLogger(__name__)

# v2.1: Initialize Celery with Redis as the broker
# 使用 Redis 作為 Broker
redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = Celery("investment_advisor", broker=redis_url, backend=redis_url)

app.config_from_object("src.infrastructure.celery_config", silent=True)

# Define Periodic Tasks (Celery Beat)
# 定義週期性任務（Celery Beat）

app.conf.beat_schedule = {
    "pre-market-intelligence": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=8, minute=30),  # 08:30 AM EST
    },
    "mid-day-intelligence": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=12, minute=0),   # 12:00 PM EST
    },
    "post-market-intelligence": {
        "task": "src.infrastructure.tasks.dispatch_market_intelligence",
        "schedule": crontab(hour=16, minute=30),  # 04:30 PM EST
    },
    # The sentinel tick is the single largest driver of this deployment's LLM
    # bill: at `crontab(minute="*")` it ran 1,440 times a day, and each tick can
    # fan out into a multi-agent council debate. A self-hosted single-box
    # install should not default to that. */15 cuts it to 96/day; set
    # SENTINEL_TICK_CRON_MINUTE="*" to restore the old behaviour.
    #
    # The tick's three expensive dimensions (breaking news / macro / global
    # macro) no longer depend on this rate — they hold their own elapsed-time
    # windows in sentinel_service._interval_seconds().
    #
    # sentinel tick 是 LLM 帳單的主要來源；單機自架預設改為每 15 分鐘，
    # 需要恢復每分鐘可設 SENTINEL_TICK_CRON_MINUTE="*"。
    "sentinel-tick": {
        "task": "src.infrastructure.tasks.dispatch_sentinel_tick",
        "schedule": crontab(minute=os.getenv("SENTINEL_TICK_CRON_MINUTE", "*/15")),
    },
    "broker-position-sync": {
        "task": "src.infrastructure.tasks.dispatch_broker_sync",
        "schedule": crontab(minute=os.getenv("BROKER_SYNC_CRON_MINUTE", "*/15")),
    },
    "order-reconciliation": {
        "task": "src.infrastructure.tasks.dispatch_order_reconciliation",
        "schedule": crontab(minute=os.getenv("ORDER_RECONCILIATION_CRON_MINUTE", "*/5")),
    },

    # ── Ingestion previously scheduled by n8n ────────────────────────────────
    # Same cadences the n8n workflow used, minus the container and the two HTTP
    # hops per feed. n8n is now an optional compose profile for third-party
    # connectors only; nothing in the product depends on it.
    # 與原 n8n workflow 相同的頻率，但少了一個容器與每個 feed 兩趟 HTTP。
    "rss-ingest": {
        "task": "src.infrastructure.tasks.dispatch_rss_ingest",
        "schedule": crontab(minute=os.getenv("RSS_INGEST_CRON_MINUTE", "*/15")),
    },
    "daily-skill-learning": {
        "task": "src.infrastructure.tasks.dispatch_skill_learning",
        "schedule": crontab(hour=7, minute=0),      # 07:00 daily (was n8n cron 0 7 * * *)
    },
    "podcast-ingest": {
        "task": "src.infrastructure.tasks.dispatch_podcast_ingest",
        "schedule": crontab(minute=0, hour="*/4"),  # every 4h (was n8n cron 0 */4 * * *)
    },
    "daily-memory-distillation": {
        "task": "src.infrastructure.tasks.dispatch_memory_distill",
        "schedule": crontab(hour=2, minute=0),     # 02:00 AM daily
    },
    # 2026-07-12: event_queue digest/housekeeping — previously lived only as
    # standalone scripts (report_digest_worker.py / event_housekeeper.py)
    # whose docstrings claimed a Hermes cron trigger that was never actually
    # registered, so non-P0 events (e.g. n8n RSS news) never reached the user.
    # Cadence is hourly per user decision (2026-07-12) — daily was this
    # session's initial assumption, not a documented product spec.
    "hourly-event-digest": {
        "task": "src.infrastructure.tasks.dispatch_event_digest",
        "schedule": crontab(minute=0),              # every hour on the hour
    },
    "daily-event-queue-housekeeping": {
        "task": "src.infrastructure.tasks.housekeep_event_queue",
        "schedule": crontab(hour=2, minute=15),    # 02:15 AM daily (offset from memory distillation)
    },
    # Self-ops Loop 2 (2026-07-12): dead-man switches over task_runs +
    # config-drift detection. Pure SQL, zero LLM.
    "self-ops-deadman-check": {
        "task": "src.infrastructure.tasks.self_ops_check",
        "schedule": crontab(minute="*/15"),        # every 15 minutes
    },
    "daily-cost-anomaly-check": {
        "task": "src.infrastructure.tasks.cost_anomaly_check",
        "schedule": crontab(hour=6, minute=30),    # 06:30 daily, after full prior day exists
    },
    # P2-2: daily_report — 每個交易日 17:00 執行 (盤後報告)
    "daily-report": {
        "task": "src.infrastructure.tasks.dispatch_daily_report",
        "schedule": crontab(hour=17, minute=0, day_of_week="1-5"),  # Mon-Fri 17:00 EST (after market close)
    },
    # "portfolio-rebalance-trigger" — REMOVED 2026-08-02.
    # It ran `crontab(minute="*/30", hour="8-16", day_of_week="1-5")` against
    # dispatch_portfolio_rebalance, whose body was byte-for-byte identical to
    # sentinel_tick's: `SentinelService(user_id).process_tick()`. But
    # process_tick() already runs Dimension 10 `_check_allocation_drift` and
    # 10.1 `_handle_rebalance_logic` unconditionally on EVERY minutely tick
    # (sentinel_service.py), so this entry added no coverage — it only made
    # process_tick run twice at :00 and :30. Both of those minutes satisfy the
    # `minute % 10 == 0` gate guarding the paid Tavily breaking-news search,
    # and :00 also hits the FRED macro branch, so it was doubling paid API and
    # LLM spend ~18×/trading day. `_handle_rebalance_logic`'s 30-minute
    # debounce could not stop it either: it keys off `self.last_fire_time` on
    # an instance that each Celery task constructs fresh.
    # Manual "rebalance now" still works — see tasks.trigger_portfolio_rebalance.
    # 2026-08-02 移除：與 sentinel_tick 呼叫同一個 process_tick()，而再平衡檢查本來
    # 每分鐘就會跑，此排程只造成 :00/:30 重複，且正好打在付費的 Tavily/FRED 分支上。
    # 2026-08-23: this pointed at dispatch_market_intelligence, so the weekly
    # report had never once been generated on schedule — the entry fired the
    # market-intelligence fan-out a second time instead.
    # Resolved 2026-10-11: weekly-report-trigger points to dispatch_weekly_report
    # and monthly-report points to dispatch_monthly_report.
    # 原本指向市場情報任務，現已統一修正指向各自的報表分派任務。
    "weekly-report-trigger": {
        "task": "src.infrastructure.tasks.dispatch_weekly_report",
        "schedule": crontab(hour=10, minute=0, day_of_week="6"),  # Sat 10:00
    },
    # Ticker Universe Lifecycle Evolution — runs weekly on Monday pre-market (08:00 EST)
    # 標的池生命週期演化：每週一開盤前評估宏觀環境、淘汰劣化標的、補充優質新標的。
    "universe-lifecycle-evolution": {
        "task": "src.infrastructure.tasks.dispatch_universe_lifecycle",
        "schedule": crontab(hour=8, minute=0, day_of_week="1"),  # Mon 08:00 EST
    },
    # Mission watchdog — daily 06:00 EST, 0-LLM; alerts on kill-criteria breaches (never halts trading by itself)
    # 使命看門狗：每日 06:00 EST，0-LLM；kill criteria 觸發即通知（不會自行停止交易）。
    "mission-watchdog": {
        "task": "src.infrastructure.tasks.run_mission_watchdog",
        "schedule": crontab(hour=6, minute=0),
    },
    # Real LLM cost collector — every 15 minutes (LiteLLM /key/info delta -> llm_real_cost_daily)
    # 真實 LLM 成本收集：每 15 分鐘輪詢 LiteLLM /key/info 並記帳。
    "litellm-spend-collect": {
        "task": "src.infrastructure.tasks.run_litellm_spend_collect",
        "schedule": crontab(minute="*/15"),
    },
    # Universe research refresh — weekdays 07:30 EST (before the 09:35 deployment/rebalance tasks)
    # 標的池研究分數刷新：交易日 07:30 EST（早於 09:35 建倉/再平衡），0-LLM。
    "universe-research-refresh": {
        "task": "src.infrastructure.tasks.dispatch_universe_research_refresh",
        "schedule": crontab(hour=7, minute=30, day_of_week="1-5"),
    },
    # Strategy Lifecycle & Discovery Evolution — runs weekly on Sunday night (21:00 EST)
    # 策略生命週期與自主探索演進：每週自動滾動執行歷史回測掃描、檢驗既有策略績效、探索新體制候選策略並更新註冊中心。
    "strategy-lifecycle-evolution": {
        "task": "src.infrastructure.tasks.dispatch_strategy_evolution",
        "schedule": crontab(hour=21, minute=0, day_of_week="0"),  # Sun 21:00 EST
    },
    # Factor Rotation Replay & Annealing Hyperparameter Evolution — runs weekly on Sunday night (22:30 EST)
    # 多因子歷史回放重播與退火調參演進：每週日夜間回放驗證輪動參數並自動動態最佳化各週期因子權重矩陣。
    "factor-rotation-replay-evolution": {
        "task": "src.infrastructure.tasks.dispatch_factor_rotation_evolution",
        "schedule": crontab(hour=22, minute=30, day_of_week="0"),  # Sun 22:30 EST
    },
    # Factor Genetic Hyper-Evolution — runs weekly on Sunday night (23:00 EST)
    # 全歷史多因子權重遺傳演算法超參數演化：每週日夜間執行族群雜交變異演化、Walk-Forward 前向走查與自動晉級。
    "factor-genetic-hyper-evolution": {
        "task": "src.infrastructure.tasks.dispatch_factor_genetic_evolution",
        "schedule": crontab(hour=23, minute=0, day_of_week="0"),  # Sun 23:00 EST
    },
    # Autonomous Factor Exploration & Canary Evolution — runs daily at 01:30 AM EST (off-market hours)
    # 自主量化因子探索與金絲雀灰度演化：每日凌晨離線探索未覆蓋體制策略並自動滾動 14 天金絲雀影子追蹤。
    "daily-autonomous-factor-evolution": {
        "task": "src.infrastructure.tasks.dispatch_autonomous_evolution",
        "schedule": crontab(hour=1, minute=30),  # 01:30 AM EST daily
    },
    # Autonomous Weekly Confidence Rebalance — runs Monday post-market open (09:35 EST)
    # 自主每週置信度再平衡：每週一美股開盤後（09:35 EST）自動計算目標權重並執行賣出與買入下單。
    "weekly-confidence-rebalance": {
        "task": "src.infrastructure.tasks.dispatch_weekly_rebalance",
        "schedule": crontab(hour=9, minute=35, day_of_week="1"),  # Mon 09:35 EST
    },
    # Market-Open Quote Warmup — runs Monday-Friday 15 minutes before market open (09:20 EST)
    # 開盤前標的報價預熱：每個交易日開盤前 15 分鐘（09:20 EST）預載建倉標的之行情、買賣價差與快取。
    "market-open-quote-warmup": {
        "task": "src.infrastructure.tasks.dispatch_market_open_warmup",
        "schedule": crontab(hour=9, minute=20, day_of_week="1-5"),  # Mon-Fri 09:20 EST
    },
    # Market-Open Cash Deployment & Anti-Slippage Guard — runs Monday-Friday post-market open (09:36 EST)
    # 美股開盤分批建倉與防滑點守衛：每個交易日開盤後（09:36 EST）避開開盤前 5 分鐘極端價差後，評估並執行閒置現金分批建倉與防滑點守衛。
    "market-open-cash-deployment": {
        "task": "src.infrastructure.tasks.dispatch_market_open_cash_deployment",
        "schedule": crontab(hour=9, minute=36, day_of_week="1-5"),  # Mon-Fri 09:36 EST
    },
    # Smart Staggered Dip Buying — runs Monday-Friday post-market open (09:35 EST)
    # 主力支撐階梯限價吸籌：每個交易日開盤後（09:35 EST）錨定主力籌碼成本線下發 3-Tier 限價吸籌單。
    "staggered-dip-deployment": {
        "task": "src.infrastructure.tasks.dispatch_staggered_dip_deployment",
        "schedule": crontab(hour=9, minute=35, day_of_week="1-5"),  # Mon-Fri 09:35 EST
    },
    # Market-Close Staggered Orders Cleanup — runs Monday-Friday pre-market close (15:55 EST)
    # 收盤前階梯限價掛單自動安全撤除：每個交易日收盤前（15:55 EST）自動撤除未成交掛單並釋放資金，杜絕隔夜風險。
    "staggered-orders-cleanup": {
        "task": "src.infrastructure.tasks.dispatch_staggered_orders_cleanup",
        "schedule": crontab(hour=15, minute=55, day_of_week="1-5"),  # Mon-Fri 15:55 EST
    },
    # Intraday Staggered Fills Reconciliation — runs every 15 minutes during US market hours (09:45-15:45 EST)
    # 盤中階梯限價掛單撮合對帳與持倉接管：美股交易時段內每 15 分鐘定時檢測限價單撮合成交狀態並自動掛載 ATR 停損保護。
    "staggered-fills-reconciliation": {
        "task": "src.infrastructure.tasks.dispatch_staggered_fills_reconciliation",
        "schedule": crontab(minute="*/15", hour="9-15", day_of_week="1-5"),
    },
    # Intraday Staggered Orders Stalking — runs Monday-Friday at 14:00 EST
    # 盤中動態追單改價：每日 14:00 EST 針對多頭強勢標的將 Tier 1/2 限價向日內 VWAP 微調，提高撮合率消滅現金拖累。
    "staggered-orders-stalking": {
        "task": "src.infrastructure.tasks.dispatch_staggered_orders_stalking",
        "schedule": crontab(hour=14, minute=0, day_of_week="1-5"),  # Mon-Fri 14:00 EST
    },
    # Market-Close Staggered Dip MOC Conversion — runs Monday-Friday at 15:50 EST
    # 尾盤動能接管強制建倉：每日 15:50 EST 撤單前將強勢標的 Tier 1 轉為市價/MOC 成交，強制配置閒置現金。
    "staggered-orders-moc-conversion": {
        "task": "src.infrastructure.tasks.dispatch_staggered_orders_moc_conversion",
        "schedule": crontab(hour=15, minute=50, day_of_week="1-5"),  # Mon-Fri 15:50 EST
    },
    # Real-time Net Alpha & Cash Drag Attribution — runs post-market close daily at 16:15 EST
    # 實時淨 Alpha 歸因與現金拖累量化分析：每個交易日美股盤後（16:15 EST）自動精算扣費淨 Alpha 與現金機會成本並推播。
    "daily-net-alpha-attribution": {
        "task": "src.infrastructure.tasks.dispatch_net_alpha_attribution",
        "schedule": crontab(hour=16, minute=15, day_of_week="1-5"),  # Mon-Fri 16:15 EST
    },
    # Shadow Ledger Evaluation (P2) — runs daily at 16:45 EST (after US market close)
    # 影子交易每日 MTM 損益計算與畢業考核：每個交易日盤後（16:45 EST）自動評估影子部位與提拔晉升。
    "daily-shadow-ledger-eval": {
        "task": "src.infrastructure.tasks.dispatch_shadow_ledger_eval",
        "schedule": crontab(hour=16, minute=45, day_of_week="1-5"),
    },
    # LLM Model Lifecycle & Blue-Green Canary Evolution — runs daily at 02:30 AM EST (off-market hours)
    # LLM 模型生命週期動態掃描與藍綠金絲雀演進：每日定期探測下架模型、探索高性價比新模型並執行藍綠安全驗證與升級。
    "daily-llm-model-lifecycle-evolution": {
        "task": "src.infrastructure.tasks.dispatch_model_lifecycle",
        "schedule": crontab(hour=2, minute=30),  # 02:30 AM EST daily
    },
    "weekly-cost-review": {
        "task": "src.infrastructure.tasks.dispatch_memory_distill",
        "schedule": crontab(hour=22, minute=0, day_of_week="0"),
    },
    "monthly-report": {
        "task": "src.infrastructure.tasks.dispatch_monthly_report",
        "schedule": crontab(hour=9, minute=0, day_of_month="1"),
    },
    # P1-3: keyword_refine — 每週一 07:00 執行
    "weekly-keyword-refine": {
        "task": "src.infrastructure.tasks.dispatch_keyword_refine",
        "schedule": crontab(hour=7, minute=0, day_of_week="1"),  # Mon 07:00
    },
    # B-P2.1 (2026-07-14): weekly agent_rules curation — dedup + expiry.
    "weekly-rule-curation": {
        "task": "src.infrastructure.tasks.dispatch_rule_curation",
        "schedule": crontab(hour=6, minute=30, day_of_week="1"),  # Mon 06:30 (before keyword_refine)
    },
    # B-P2.2 (2026-07-14): weekly user-preference profile update.
    "weekly-user-preferences": {
        "task": "src.infrastructure.tasks.dispatch_user_preferences",
        "schedule": crontab(hour=6, minute=45, day_of_week="1"),  # Mon 06:45
    },
    # P1-4: experience_replay — 每週日 08:00 執行 (週日盤前復盤)
    "weekly-experience-replay": {
        "task": "src.infrastructure.tasks.dispatch_experience_replay",
        "schedule": crontab(hour=8, minute=0, day_of_week="0"),  # Sun 08:00
    },
    # P1-5: weekly_validation — 每週日 09:00 執行 (週日盤前回測驗證)
    "weekly-validation": {
        "task": "src.infrastructure.tasks.dispatch_weekly_validation",
        "schedule": crontab(hour=9, minute=0, day_of_week="0"),  # Sun 09:00
    },
}

app.conf.timezone = "America/New_York"


@worker_process_init.connect
def setup_db_worker_context(**kwargs):
    """
    Ensure each worker process has a clean database engine and is flagged
    to use NullPool to avoid connection sharing across forks.
    確保每個 worker process 有乾淨的資料庫引擎。
    """
    logger.info("Initializing Celery Worker Process: Setting IS_CELERY_WORKER=true")
    os.environ["IS_CELERY_WORKER"] = "true"

    # Force reload of engine if it was already initialized in the parent process.
    # Engines must still be cleared — inherited connections are fork-unsafe.
    # The companion `_session_registries.clear()` is gone with the registry
    # itself (2026-08-02); sessions are now per repository instance.
    # engine 仍須清除（fork 後連線不可共用）；session registry 已於 2026-08-02 移除。
    from src.data import database
    database._db_engines.clear()

    # Pre-warm the engine with NullPool
    database.get_db_engine()


# Explicit import to ensure Celery tasks are registered at worker startup
# The `imports` config in celery_config.py is set but Celery doesn't always
# auto-process it during the worker lifecycle. Direct import guarantees it.
import src.infrastructure.tasks  # noqa: F401

# Self-ops Loop 2 (2026-07-12): persist every task execution to task_runs —
# surfaces the "return 'Error: ...' into the void" legacy failure pattern.
from src.infrastructure.task_telemetry import register_task_telemetry
register_task_telemetry()

if __name__ == "__main__":
    app.start()
