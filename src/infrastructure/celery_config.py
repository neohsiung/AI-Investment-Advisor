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
task_acks_late = True
worker_prefetch_multiplier = 1

# Task time limits (seconds)
# 任務時間限制（秒）
task_soft_time_limit = 300
task_time_limit = 600

# Result backend settings
# 結果後端設定
result_expires = 3600
