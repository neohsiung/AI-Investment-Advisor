"""The daily charter task is importable, registered with Celery and scheduled by beat (G6).
每日章程任務可匯入、已向 Celery 註冊並在 beat 排程。"""
from celery.schedules import crontab


def test_task_registered_and_beat_entry():
    from src.infrastructure.celery_app import app
    app.loader.import_default_modules()
    name = "src.workflow.charter_tasks.run_parameter_engine"
    assert name in app.tasks
    entry = app.conf.beat_schedule["charter-parameter-engine"]
    assert entry["task"] == name
    sched = entry["schedule"]
    assert isinstance(sched, crontab) and sched.hour == {7} and sched.minute == {5}


def test_weekly_digest_task_registered_and_saturday_beat_entry():
    from src.infrastructure.celery_app import app
    app.loader.import_default_modules()
    name = "src.workflow.charter_tasks.run_charter_weekly_digest"
    assert name in app.tasks
    entry = app.conf.beat_schedule["charter-weekly-digest"]
    assert entry["task"] == name
    sched = entry["schedule"]
    assert isinstance(sched, crontab) and sched.hour == {10} and sched.minute == {35} and sched.day_of_week == {6}


def test_charter_halt_task_registered_and_0610_beat_entry():
    from src.infrastructure.celery_app import app
    app.loader.import_default_modules()
    name = "src.workflow.charter_tasks.apply_charter_halt"
    assert name in app.tasks
    entry = app.conf.beat_schedule["charter-halt"]
    assert entry["task"] == name
    sched = entry["schedule"]
    assert isinstance(sched, crontab) and sched.hour == {6} and sched.minute == {10}


def test_enablement_task_registered_and_0720_beat_entry():
    from src.infrastructure.celery_app import app
    app.loader.import_default_modules()
    name = "src.workflow.charter_tasks.run_enablement_check"
    assert name in app.tasks
    entry = app.conf.beat_schedule["charter-enablement"]
    assert entry["task"] == name
    sched = entry["schedule"]
    assert isinstance(sched, crontab) and sched.hour == {7} and sched.minute == {20}
