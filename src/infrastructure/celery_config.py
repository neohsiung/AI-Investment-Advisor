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
