"""
Celery Configuration Module (Optional Overrides)
Celery 可選配置覆寫模組

This file is loaded by celery_app.py via `app.config_from_object()`.
It provides optional overrides for the Celery configuration.
If this file is empty, Celery uses its defaults plus the settings
defined directly in celery_app.py.

此檔案由 celery_app.py 透過 `app.config_from_object()` 載入。
提供 Celery 配置的可選覆寫。若此檔案為空，
Celery 將使用預設值加上 celery_app.py 中直接定義的設定。
"""

# Task serialization settings
# 任務序列化設定
task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]

# Task execution settings
# 任務執行設定
task_track_started = True
task_time_limit = 30 * 60  # 30 minutes
task_soft_time_limit = 25 * 60  # 25 minutes soft limit
worker_max_tasks_per_child = 1000

# Auto-import tasks so workers know about registered task handlers
# Must be a string path to avoid circular imports
imports = ("src.infrastructure.tasks",)

# Result backend settings
# 結果後端設定
result_expires = 60 * 60 * 24  # 24 hours

# Task routing defaults (if not using explicit queue names)
task_default_queue = "default"
task_default_exchange = "default"
task_default_routing_key = "default"

# Worker prefetch
# 公平排程設定
worker_prefetch_multiplier = 1  # Fair scheduling across workers

# Redis connection budget (added 2026-08-10)
# Redis 連線預算
#
# None of these were set before, so Celery ran on unbounded/default pools.
# The workers were not the cause of the 2026-08-10 maxclients exhaustion —
# the API's leaking /health endpoint was — but they were its victims, and
# with no health_check_interval they had no way to recover a stale pool
# once the server started refusing connections. Bounding the pools and
# enabling periodic health checks makes the workers self-healing.
#
# 這些設定原本全部缺漏，Celery 使用預設無界連線池。2026-08-10 的 maxclients
# 耗盡並非 worker 造成（元兇是 API 的 /health 洩漏），但 worker 是受害者，且
# 沒有 health_check_interval 就無法在伺服器開始拒絕連線後自行恢復。
broker_pool_limit = 10
redis_max_connections = 20
redis_backend_health_check_interval = 30
broker_transport_options = {"health_check_interval": 30}
result_backend_transport_options = {"health_check_interval": 30}
