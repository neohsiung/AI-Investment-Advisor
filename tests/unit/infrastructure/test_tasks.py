"""
Celery task body tests — `src/infrastructure/tasks.py`.

Why this file exists (2026-08-13): before it, `tasks.py` sat at 22.17%
statement coverage and **not one of the 2336 tests executed the body of any
`@app.task`**. The covered fraction was module-level imports. That is the
structural reason the 2026-08-10 outage could hide for three days: the failing
state (dispatcher enqueues, child never runs) cannot occur in a test suite that
never runs a task body, so only production could ever see it.

本檔補上排程層的測試：每個 dispatcher 的 fan-out、每個 child task 的三種情境
（缺 user_id / 服務拋例外 / 正常路徑），以及 `soft_fail` 契約。

The `soft_fail` contract is the load-bearing assertion here. `task_telemetry`
classifies a task run by matching the *return value* against `^Error`
(`_SOFT_FAIL_RE`); a task that raises is `failure`, one that returns "Error: x"
is `soft_fail`, anything else is `success`. If someone "cleans up" these
handlers into bare `raise` or into returning `None`, every scheduled failure
starts recording as a success and the dead-man switches go blind. These tests
assert the convention against the real regex, not a copy of it.
"""
import contextlib
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.infrastructure import tasks
from src.infrastructure.task_telemetry import _SOFT_FAIL_RE

USER = "u-test"


@pytest.fixture(autouse=True)
def no_user_env(monkeypatch):
    """Tasks fall back to PRIMARY_USER_ID/USER_ID. Clear both so every test
    states its own user_id, and the "missing user_id" cases are real."""
    monkeypatch.delenv("PRIMARY_USER_ID", raising=False)
    monkeypatch.delenv("USER_ID", raising=False)


@pytest.fixture
def run_async_identity():
    """`_run_async_safe(x)` -> x. Lets a MagicMock service's return value flow
    through the task body without needing a real coroutine or event loop."""
    with patch.object(tasks, "_run_async_safe", side_effect=lambda coro: coro) as m:
        yield m


@pytest.fixture
def market_open():
    with patch.object(tasks, "is_market_open_today", return_value=True) as m:
        yield m


# Every service a task body can construct, all raising. Used by the tests that
# care about what happens *around* the service call (env resolution, the
# soft_fail contract) rather than about the call itself — patching them all
# keeps those tests from building real services against a real DB.
_ALL_SERVICE_TARGETS = [
    "src.services.sentinel_service.SentinelService",
    "src.services.transaction_service.TransactionService",
    "src.services.cognitive_memory_manager.CognitiveMemoryManager",
    "src.services.outcome_reflection_service.OutcomeReflectionService",
    "src.services.rule_lifecycle_service.RuleLifecycleService",
    "src.services.experience_replay_service.ExperienceReplayService",
    "src.services.risk_keyword_service.RiskKeywordService",
    "src.services.user_preference_service.UserPreferenceService",
    "src.services.backtest_service.BacktestService",
    "src.services.event_aggregator.EventAggregator",
    "src.services.workflow_service.DailyWorkflow",
    "src.data.database.get_db_engine",
]

SERVICE_ERROR = "service exploded"


@contextlib.contextmanager
def all_services_failing():
    err = RuntimeError(SERVICE_ERROR)
    with contextlib.ExitStack() as stack:
        for target in _ALL_SERVICE_TARGETS:
            stack.enter_context(patch(target, side_effect=err))
        # SettingsService / IntelligenceService are module-level imports in tasks.py
        stack.enter_context(patch.object(tasks, "SettingsService", side_effect=err))
        stack.enter_context(patch.object(tasks, "IntelligenceService", side_effect=err))
        stack.enter_context(patch.object(tasks, "_run_async_safe", side_effect=err))
        yield


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

class TestIsMarketOpenToday:
    def _calendar(self, empty: bool):
        cal = MagicMock()
        cal.schedule.return_value = pd.DataFrame() if empty else pd.DataFrame({"market_open": [1]})
        return cal

    def test_open_when_schedule_non_empty(self):
        with patch.object(tasks.mcal, "get_calendar", return_value=self._calendar(empty=False)) as gc:
            assert tasks.is_market_open_today() is True
            gc.assert_called_once_with("NYSE")

    def test_closed_when_schedule_empty(self):
        with patch.object(tasks.mcal, "get_calendar", return_value=self._calendar(empty=True)):
            assert tasks.is_market_open_today() is False


class TestRunAsyncSafe:
    def test_runs_coroutine_and_returns_value(self):
        async def coro():
            return 42

        assert tasks._run_async_safe(coro()) == 42

    def test_runs_on_a_fresh_loop_when_none_is_available(self):
        """`get_event_loop()` raises RuntimeError when no loop is set; the
        coroutine must still run.

        Regression (2026-08-13): this used to call `asyncio.run`, which
        `nest_asyncio.apply()` replaces process-wide with a version that calls
        `asyncio.get_event_loop()` itself — the very call that just raised. A
        worker that had ever hit the nested-loop branch would thereafter return
        "Error: ..." from every task without executing anything. Hence the
        permanently-raising mock here: the fallback must not depend on
        get_event_loop at all."""
        async def coro():
            return "ok"

        with patch.object(tasks.asyncio, "get_event_loop", side_effect=RuntimeError("no loop")):
            assert tasks._run_async_safe(coro()) == "ok"

    def test_fallback_survives_nest_asyncio_having_been_applied(self):
        """The production shape of the regression above: nest_asyncio already
        applied in this process, then a task hits the no-loop branch."""
        import nest_asyncio

        async def coro():
            return "still ok"

        nest_asyncio.apply()
        with patch.object(tasks.asyncio, "get_event_loop", side_effect=RuntimeError("no loop")):
            assert tasks._run_async_safe(coro()) == "still ok"

    def test_applies_nest_asyncio_when_loop_already_running(self):
        async def coro():
            return "nested"

        loop = MagicMock()
        loop.is_running.return_value = True
        loop.run_until_complete.return_value = "nested"

        c = coro()
        try:
            with patch.object(tasks.asyncio, "get_event_loop", return_value=loop), \
                 patch("nest_asyncio.apply") as apply_mock:
                assert tasks._run_async_safe(c) == "nested"
                apply_mock.assert_called_once()
                loop.run_until_complete.assert_called_once_with(c)
        finally:
            c.close()  # the loop is a mock, so nothing ever awaits it


class TestResolveTargetUsers:
    def test_explicit_user_id_skips_db(self):
        with patch("src.repositories.user_repository.AlchemyUserRepository") as repo:
            assert tasks._resolve_target_users("u1") == ["u1"]
            repo.assert_not_called()

    def test_queries_active_users_from_db(self):
        with patch("src.repositories.user_repository.AlchemyUserRepository") as repo:
            repo.return_value.get_all_active_users.return_value = ["u1", "u2", "u3"]
            assert tasks._resolve_target_users() == ["u1", "u2", "u3"]

    def test_falls_back_to_env_when_db_empty(self, monkeypatch):
        monkeypatch.setenv("PRIMARY_USER_ID", "env-user")
        with patch("src.repositories.user_repository.AlchemyUserRepository") as repo:
            repo.return_value.get_all_active_users.return_value = []
            assert tasks._resolve_target_users() == ["env-user"]

    def test_falls_back_to_secondary_env_var(self, monkeypatch):
        monkeypatch.setenv("USER_ID", "legacy-user")
        with patch("src.repositories.user_repository.AlchemyUserRepository") as repo:
            repo.return_value.get_all_active_users.return_value = []
            assert tasks._resolve_target_users() == ["legacy-user"]

    def test_returns_empty_when_no_users_and_no_env(self):
        """No users anywhere -> empty list, so dispatchers fan out to nobody
        rather than enqueueing a task with user_id=None."""
        with patch("src.repositories.user_repository.AlchemyUserRepository") as repo:
            repo.return_value.get_all_active_users.return_value = []
            assert tasks._resolve_target_users() == []


# ─────────────────────────────────────────────────────────────────────────────
# Dispatchers — fan-out
# ─────────────────────────────────────────────────────────────────────────────

DISPATCHERS = [
    ("dispatch_market_intelligence", "generate_market_intelligence"),
    ("dispatch_sentinel_tick", "sentinel_tick"),
    ("dispatch_broker_sync", "sync_broker_positions"),
    ("dispatch_memory_distill", "distill_memories"),
    ("dispatch_experience_replay", "experience_replay"),
    ("dispatch_keyword_refine", "keyword_refine"),
    ("dispatch_rule_curation", "curate_agent_rules"),
    ("dispatch_user_preferences", "update_user_preferences"),
    ("dispatch_weekly_validation", "weekly_validation"),
    ("dispatch_event_digest", "send_event_digest"),
    ("dispatch_daily_report", "generate_daily_report"),
]


@pytest.mark.parametrize("dispatcher_name,child_name", DISPATCHERS)
def test_dispatcher_fans_out_once_per_user(dispatcher_name, child_name):
    """N active users -> exactly N `.delay()` calls, each carrying its own
    user_id. A dispatcher that enqueues fewer is the 2026-08-10 outage shape:
    the dispatcher reports success while most tenants are never processed."""
    dispatcher = getattr(tasks, dispatcher_name)
    child = getattr(tasks, child_name)
    users = ["u1", "u2", "u3"]

    with patch.object(tasks, "_resolve_target_users", return_value=users), \
         patch.object(child, "delay") as delay:
        result = dispatcher()

    assert delay.call_count == len(users)
    assert [c.kwargs["user_id"] for c in delay.call_args_list] == users
    assert "3" in result


@pytest.mark.parametrize("dispatcher_name,child_name", DISPATCHERS)
def test_dispatcher_enqueues_nothing_when_no_users(dispatcher_name, child_name):
    dispatcher = getattr(tasks, dispatcher_name)
    child = getattr(tasks, child_name)

    with patch.object(tasks, "_resolve_target_users", return_value=[]), \
         patch.object(child, "delay") as delay:
        result = dispatcher()

    delay.assert_not_called()
    assert "0" in result


def test_dispatch_daily_report_propagates_force_flag():
    with patch.object(tasks, "_resolve_target_users", return_value=["u1"]), \
         patch.object(tasks.generate_daily_report, "delay") as delay:
        tasks.dispatch_daily_report(force_report=True)

    delay.assert_called_once_with(user_id="u1", force_report=True)


# ─────────────────────────────────────────────────────────────────────────────
# Missing user_id — every user-scoped task must refuse, not guess
# ─────────────────────────────────────────────────────────────────────────────

USER_SCOPED_TASKS = [
    "generate_market_intelligence",
    "trigger_portfolio_rebalance",
    "sentinel_tick",
    "sync_broker_positions",
    "distill_memories",
    "experience_replay",
    "keyword_refine",
    "curate_agent_rules",
    "update_user_preferences",
    "weekly_validation",
    "send_event_digest",
    "generate_daily_report",
]


@pytest.mark.parametrize("task_name", USER_SCOPED_TASKS)
def test_task_refuses_without_user_id(task_name, market_open):
    task = getattr(tasks, task_name)
    result = task()

    assert result == "Error: user_id is required"
    assert _SOFT_FAIL_RE.match(result), "must be recorded as soft_fail by task_telemetry"


@pytest.mark.parametrize("task_name", USER_SCOPED_TASKS)
def test_task_uses_env_user_id_when_not_passed(task_name, monkeypatch, market_open):
    """The env fallback is what production actually uses for the single-tenant
    deployment; if it stops working every scheduled task silently no-ops."""
    monkeypatch.setenv("PRIMARY_USER_ID", "env-user")
    task = getattr(tasks, task_name)

    with all_services_failing():
        result = task()

    assert result == f"Error: {SERVICE_ERROR}", (
        f"{task_name} did not get past the user_id check using the env fallback"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Child task bodies
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateMarketIntelligence:
    def test_skips_when_market_closed(self):
        with patch.object(tasks, "is_market_open_today", return_value=False):
            assert tasks.generate_market_intelligence(user_id=USER) == "Skipped"

    def test_success_persists_briefing_and_timestamp(self, market_open, run_async_identity):
        with patch.object(tasks, "SettingsService") as settings_cls, \
             patch.object(tasks, "IntelligenceService") as intel_cls:
            intel_cls.return_value.compute_briefing.return_value = "BRIEFING"
            result = tasks.generate_market_intelligence(user_id=USER)

        settings = settings_cls.return_value
        assert result == "Success"
        settings.save_setting.assert_any_call(
            "cached_intelligence_briefing", "BRIEFING", user_id=USER
        )
        saved_keys = [c.args[0] for c in settings.save_setting.call_args_list]
        assert "last_intelligence_timestamp" in saved_keys

    def test_service_failure_returns_soft_fail_string(self, market_open):
        with patch.object(tasks, "SettingsService", side_effect=RuntimeError("db down")):
            result = tasks.generate_market_intelligence(user_id=USER)

        assert result == "Error: db down"
        assert _SOFT_FAIL_RE.match(result)


class TestSentinelTasks:
    def test_sentinel_tick_success(self, run_async_identity):
        with patch("src.services.sentinel_service.SentinelService") as cls:
            assert tasks.sentinel_tick(user_id=USER) == "Success"

        cls.assert_called_once_with(user_id=USER)
        cls.return_value.process_tick.assert_called_once_with()

    def test_sentinel_tick_failure_returns_error_string_not_raise(self, run_async_identity):
        with patch("src.services.sentinel_service.SentinelService", side_effect=ValueError("boom")):
            result = tasks.sentinel_tick(user_id=USER)

        assert result == "Error: boom"
        assert _SOFT_FAIL_RE.match(result)

    def test_trigger_rebalance_forces_past_the_tick_lock(self, run_async_identity):
        """force=True is the whole point of this task: the dashboard button
        must not be swallowed by the lock the minutely tick just took."""
        with patch("src.services.sentinel_service.SentinelService") as cls:
            assert tasks.trigger_portfolio_rebalance(user_id=USER) == "Success"

        cls.return_value.process_tick.assert_called_once_with(force=True)

    def test_trigger_rebalance_failure(self, run_async_identity):
        with patch("src.services.sentinel_service.SentinelService", side_effect=RuntimeError("x")):
            assert tasks.trigger_portfolio_rebalance(user_id=USER) == "Error: x"


class TestSyncBrokerPositions:
    def test_success(self, run_async_identity):
        with patch("src.services.transaction_service.TransactionService") as cls:
            assert tasks.sync_broker_positions(user_id=USER) == "Success"

        cls.assert_called_once_with(user_id=USER)
        cls.return_value.sync_broker_positions.assert_called_once_with()

    def test_failure(self, run_async_identity):
        with patch(
            "src.services.transaction_service.TransactionService",
            side_effect=RuntimeError("InsufficientPermissions"),
        ):
            result = tasks.sync_broker_positions(user_id=USER)

        assert result == "Error: InsufficientPermissions"
        assert _SOFT_FAIL_RE.match(result)


class TestDistillMemories:
    def _patches(self):
        return (
            patch("src.services.cognitive_memory_manager.CognitiveMemoryManager"),
            patch("src.services.outcome_reflection_service.OutcomeReflectionService"),
            patch("src.services.rule_lifecycle_service.RuleLifecycleService"),
        )

    def test_success_reports_archived_count(self, run_async_identity):
        mem_p, refl_p, rule_p = self._patches()
        with mem_p as mem, refl_p, rule_p:
            mem.return_value.archive_to_long_term.return_value = 7
            result = tasks.distill_memories(user_id=USER)

        assert result == "Success: archived 7 memories"
        mem.return_value.archive_to_long_term.assert_called_once_with(days_old=30)

    def test_archive_failure_returns_error_string(self, run_async_identity):
        mem_p, refl_p, rule_p = self._patches()
        with mem_p as mem, refl_p, rule_p:
            mem.return_value.archive_to_long_term.side_effect = RuntimeError("pgvector down")
            result = tasks.distill_memories(user_id=USER)

        assert result == "Error: pgvector down"
        assert _SOFT_FAIL_RE.match(result)

    def test_reflection_failure_is_non_blocking(self, run_async_identity):
        """resolve_pending and the rule gate are explicitly non-blocking — a
        failure there must not lose the distillation result."""
        mem_p, refl_p, rule_p = self._patches()
        with mem_p as mem, refl_p as refl, rule_p as rule:
            mem.return_value.archive_to_long_term.return_value = 2
            refl.side_effect = RuntimeError("reflection exploded")
            rule.side_effect = RuntimeError("gate exploded")
            result = tasks.distill_memories(user_id=USER)

        assert result == "Success: archived 2 memories"


class TestWeeklyLearningTasks:
    def test_experience_replay_uses_advanced_tier(self):
        with patch("src.services.experience_replay_service.ExperienceReplayService") as cls:
            cls.return_value.optimize_thresholds.return_value = {"drift_threshold": 0.05}
            result = tasks.experience_replay(user_id=USER)

        cls.assert_called_once_with(tier="advanced")
        cls.return_value.optimize_thresholds.assert_called_once_with(USER)
        assert result.startswith("OK:")

    def test_experience_replay_failure(self):
        with patch(
            "src.services.experience_replay_service.ExperienceReplayService",
            side_effect=RuntimeError("llm down"),
        ):
            result = tasks.experience_replay(user_id=USER)

        assert result == "Error: llm down"
        assert _SOFT_FAIL_RE.match(result)

    def test_keyword_refine_success(self):
        with patch("src.services.risk_keyword_service.RiskKeywordService") as cls:
            cls.return_value.refine.return_value = {"added": 3}
            result = tasks.keyword_refine(user_id=USER)

        assert result.startswith("OK:")
        cls.return_value.refine.assert_called_once_with()

    def test_keyword_refine_failure(self):
        with patch("src.services.risk_keyword_service.RiskKeywordService", side_effect=RuntimeError("nope")):
            result = tasks.keyword_refine(user_id=USER)

        assert result == "Error: nope"
        assert _SOFT_FAIL_RE.match(result)

    def test_weekly_validation_runs_every_ticker(self, run_async_identity):
        with patch("src.services.backtest_service.BacktestService") as cls:
            result = tasks.weekly_validation(user_id=USER)

        calls = cls.return_value.run_simulation.call_args_list
        assert [c.args[0] for c in calls] == ["AAPL", "TSLA", "NVDA", "SPY"]
        assert all(c.kwargs["days_back"] == 7 for c in calls)
        assert result == "OK: validated AAPL, TSLA, NVDA, SPY"

    def test_weekly_validation_failure(self, run_async_identity):
        with patch("src.services.backtest_service.BacktestService", side_effect=RuntimeError("no data")):
            result = tasks.weekly_validation(user_id=USER)

        assert result == "Error: no data"
        assert _SOFT_FAIL_RE.match(result)


class TestCurateAgentRules:
    def _engine_with_agents(self, agent_names):
        engine = MagicMock()
        conn = engine.connect.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [(n,) for n in agent_names]
        return engine

    def test_success_aggregates_per_agent_counts(self, run_async_identity):
        engine = self._engine_with_agents(["Fundamental", "Momentum"])
        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch("src.services.rule_lifecycle_service.RuleLifecycleService") as cls:
            cls.return_value.backfill_embeddings.return_value = 3
            cls.return_value.dedupe_agent_rules.return_value = 1
            cls.return_value.expire_stale_rules.return_value = 5
            result = tasks.curate_agent_rules(user_id=USER)

        assert result == "OK: 2 agents, 6 embedded, 2 deduped, 5 expired"

    def test_gate_failure_is_non_blocking(self, run_async_identity):
        """The backtest gate is wrapped separately on purpose — its failure
        must not skip embedding backfill and rule retirement."""
        engine = self._engine_with_agents(["Fundamental"])
        with patch("src.data.database.get_db_engine", return_value=engine), \
             patch("src.services.rule_lifecycle_service.RuleLifecycleService") as cls:
            cls.return_value.gate_candidate_rules.side_effect = RuntimeError("gate down")
            cls.return_value.backfill_embeddings.return_value = 0
            cls.return_value.dedupe_agent_rules.return_value = 0
            cls.return_value.expire_stale_rules.return_value = 0
            result = tasks.curate_agent_rules(user_id=USER)

        assert result.startswith("OK:")

    def test_db_failure_returns_error_string(self, run_async_identity):
        with patch("src.data.database.get_db_engine", side_effect=RuntimeError("conn refused")), \
             patch("src.services.rule_lifecycle_service.RuleLifecycleService"):
            result = tasks.curate_agent_rules(user_id=USER)

        assert result == "Error: conn refused"
        assert _SOFT_FAIL_RE.match(result)


class TestUpdateUserPreferences:
    def test_no_feedback_history_is_not_an_error(self, run_async_identity):
        with patch("src.services.user_preference_service.UserPreferenceService") as cls:
            cls.return_value.update_preferences.return_value = None
            result = tasks.update_user_preferences(user_id=USER)

        assert result == "OK: no feedback history"
        assert not _SOFT_FAIL_RE.match(result)

    def test_success_summarizes_profile(self, run_async_identity):
        with patch("src.services.user_preference_service.UserPreferenceService") as cls:
            cls.return_value.update_preferences.return_value = {
                "risk_appetite_score": 0.42,
                "sector_aversions": {"energy": 0.8},
            }
            result = tasks.update_user_preferences(user_id=USER)

        assert "risk_appetite=0.42" in result
        assert "energy" in result

    def test_failure(self, run_async_identity):
        with patch(
            "src.services.user_preference_service.UserPreferenceService",
            side_effect=RuntimeError("no feedback table"),
        ):
            result = tasks.update_user_preferences(user_id=USER)

        assert result == "Error: no feedback table"
        assert _SOFT_FAIL_RE.match(result)


class TestSendEventDigest:
    def _registry(self, suppress_ops=False):
        from src.services.digest_nodes import DigestNode

        return [
            DigestNode(
                name="ops_health",
                selector=lambda e: e.get("category") == "ops",
                composer=lambda evs: ("Ops", f"{len(evs)} ops events"),
                category="ops",
                suppress=(lambda evs: suppress_ops),
            ),
            DigestNode(
                name="investment_digest",
                selector=lambda e: e.get("category") == "investment",
                composer=lambda evs: ("Investment", f"{len(evs)} investment events"),
                category="daily_digest",
            ),
        ]

    def _patch_deps(self, events, registry):
        aggregator_p = patch("src.services.event_aggregator.EventAggregator")
        notif_p = patch("src.services.notification_service.NotificationService")
        settings_p = patch("src.services.settings_service.SettingsService")
        registry_p = patch("src.services.digest_nodes.REGISTRY", registry)
        return aggregator_p, notif_p, settings_p, registry_p

    def test_no_events_skips_notification(self):
        agg_p, notif_p, settings_p, reg_p = self._patch_deps([], self._registry())
        with agg_p as agg, notif_p as notif, settings_p, reg_p:
            agg.return_value.pull_multi_tier.return_value = []
            result = tasks.send_event_digest(user_id=USER)

        assert result == "OK: no events"
        notif.create_with_settings.assert_not_called()

    def test_pulls_all_four_tiers(self):
        agg_p, notif_p, settings_p, reg_p = self._patch_deps([], self._registry())
        with agg_p as agg, notif_p, settings_p, reg_p:
            agg.return_value.pull_multi_tier.return_value = []
            tasks.send_event_digest(user_id=USER)

        kwargs = agg.return_value.pull_multi_tier.call_args.kwargs
        assert kwargs["tiers"] == ["P0", "P1", "P2", "P3"]
        assert kwargs["user_id"] == USER

    def test_dispatches_matched_events_and_marks_processed(self, run_async_identity):
        events = [
            {"id": 1, "category": "ops"},
            {"id": 2, "category": "investment"},
        ]
        agg_p, notif_p, settings_p, reg_p = self._patch_deps(events, self._registry())
        with agg_p as agg, notif_p as notif, settings_p, reg_p:
            agg.return_value.pull_multi_tier.return_value = events
            result = tasks.send_event_digest(user_id=USER)

        assert notif.create_with_settings.return_value.notify_all.call_count == 2
        assert sorted(agg.return_value.mark_processed.call_args.args[0]) == [1, 2]
        assert result.startswith("Success:")

    def test_unmatched_events_fall_back_to_investment_digest(self, run_async_identity):
        """An event no node claims must still reach the user. Dropping it is
        exactly the silent-loss shape the digest exists to prevent."""
        events = [{"id": 9, "category": "something-new"}]
        agg_p, notif_p, settings_p, reg_p = self._patch_deps(events, self._registry())
        with agg_p as agg, notif_p as notif, settings_p, reg_p:
            agg.return_value.pull_multi_tier.return_value = events
            result = tasks.send_event_digest(user_id=USER)

        notify = notif.create_with_settings.return_value.notify_all
        assert notify.call_count == 1
        assert notify.call_args.kwargs["category"] == "daily_digest"
        assert agg.return_value.mark_processed.call_args.args[0] == [9]
        assert "investment_digest" in result

    def test_suppressed_node_releases_events_instead_of_consuming(self, run_async_identity):
        events = [{"id": 5, "category": "ops"}]
        agg_p, notif_p, settings_p, reg_p = self._patch_deps(events, self._registry(suppress_ops=True))
        with agg_p as agg, notif_p as notif, settings_p, reg_p:
            agg.return_value.pull_multi_tier.return_value = events
            result = tasks.send_event_digest(user_id=USER)

        notif.create_with_settings.return_value.notify_all.assert_not_called()
        agg.return_value.repo.release_batch.assert_called_once_with([5])
        agg.return_value.mark_processed.assert_not_called()
        assert "released 1 events" in result

    def test_failure_returns_error_string(self):
        agg_p, notif_p, settings_p, reg_p = self._patch_deps([], self._registry())
        with agg_p as agg, notif_p, settings_p, reg_p:
            agg.return_value.pull_multi_tier.side_effect = RuntimeError("queue down")
            result = tasks.send_event_digest(user_id=USER)

        assert result == "Error: queue down"
        assert _SOFT_FAIL_RE.match(result)


class TestGenerateDailyReport:
    def test_skips_when_market_closed(self):
        with patch.object(tasks, "is_market_open_today", return_value=False):
            result = tasks.generate_daily_report(user_id=USER)

        assert result == "Skipped (Market Closed)"
        assert not _SOFT_FAIL_RE.match(result)

    def test_force_report_overrides_closed_market(self, run_async_identity):
        with patch.object(tasks, "is_market_open_today", return_value=False), \
             patch("src.services.workflow_service.DailyWorkflow") as cls:
            result = tasks.generate_daily_report(user_id=USER, force_report=True)

        assert result.startswith("Success:")
        cls.return_value.run.assert_called_once_with(dry_run=False, force_refresh=True)

    def test_success(self, market_open, run_async_identity):
        with patch("src.services.workflow_service.DailyWorkflow") as cls:
            result = tasks.generate_daily_report(user_id=USER)

        cls.assert_called_once_with(user_id=USER)
        cls.return_value.run.assert_called_once_with(dry_run=False, force_refresh=False)
        assert result == f"Success: Daily report generated for {USER}"

    def test_failure(self, market_open, run_async_identity):
        with patch("src.services.workflow_service.DailyWorkflow", side_effect=RuntimeError("council timeout")):
            result = tasks.generate_daily_report(user_id=USER)

        assert result == "Error: council timeout"
        assert _SOFT_FAIL_RE.match(result)


# ─────────────────────────────────────────────────────────────────────────────
# Tenant-independent ops tasks
# ─────────────────────────────────────────────────────────────────────────────

class TestSelfOpsTasks:
    def test_self_ops_check_reports_breaches(self):
        with patch("src.services.self_ops_service.SelfOpsService") as cls:
            svc = cls.return_value
            svc.sync_beat_expectations.return_value = {"synced": 12, "drift_disabled": []}
            svc.check_all.return_value = {"breaches": [{"name": "sentinel_tick"}]}
            result = tasks.self_ops_check()

        assert result == "OK: 1 breaches"
        svc.sync_beat_expectations.assert_called_once()
        svc.check_all.assert_called_once()

    def test_self_ops_check_logs_schedule_drift(self):
        with patch("src.services.self_ops_service.SelfOpsService") as cls, \
             patch.object(tasks.logger, "warning") as warn:
            svc = cls.return_value
            svc.sync_beat_expectations.return_value = {"synced": 3, "drift_disabled": ["ghost-task"]}
            svc.check_all.return_value = {"breaches": []}
            tasks.self_ops_check()

        assert any("drift" in str(c) for c in warn.call_args_list)

    def test_self_ops_check_failure(self):
        with patch("src.services.self_ops_service.SelfOpsService", side_effect=RuntimeError("sql error")):
            result = tasks.self_ops_check()

        assert result == "Error: sql error"
        assert _SOFT_FAIL_RE.match(result)

    def test_cost_anomaly_check_success(self):
        with patch("src.services.self_ops_service.SelfOpsService") as cls:
            cls.return_value.check_cost_anomaly.return_value = {
                "projected_week_usd": 4.21,
                "breaches": [],
            }
            result = tasks.cost_anomaly_check()

        assert result == "OK: 0 breaches, projected $4.21/wk"

    def test_cost_anomaly_check_failure(self):
        with patch("src.services.self_ops_service.SelfOpsService", side_effect=RuntimeError("no usage table")):
            result = tasks.cost_anomaly_check()

        assert result == "Error: no usage table"
        assert _SOFT_FAIL_RE.match(result)


class TestHousekeepEventQueue:
    def test_archives_events_older_than_72h(self):
        with patch("src.services.event_aggregator.EventAggregator") as cls:
            cls.return_value.repo.archive_old_events.return_value = 41
            result = tasks.housekeep_event_queue()

        cls.return_value.repo.archive_old_events.assert_called_once_with(older_than_hours=72)
        assert result == "Success: archived 41 events"

    def test_failure(self):
        with patch("src.services.event_aggregator.EventAggregator", side_effect=RuntimeError("db gone")):
            result = tasks.housekeep_event_queue()

        assert result == "Error: db gone"
        assert _SOFT_FAIL_RE.match(result)


# ─────────────────────────────────────────────────────────────────────────────
# soft_fail contract — the reason the handlers above return instead of raising
# ─────────────────────────────────────────────────────────────────────────────

class TestSoftFailContract:
    """`task_telemetry` classifies a run by matching the return value against
    `^Error`. These assertions pin that coupling: a task that raised, or that
    returned None, would be recorded as `failure`/`success` respectively — and
    a `success` for a task that did nothing is precisely how the three-day
    outage stayed invisible."""

    @pytest.mark.parametrize("task_name", USER_SCOPED_TASKS)
    def test_service_exception_never_escapes_the_task(self, task_name, market_open):
        task = getattr(tasks, task_name)
        with all_services_failing():
            result = task(user_id=USER)

        assert isinstance(result, str), f"{task_name} must return a string, not {type(result)}"
        assert _SOFT_FAIL_RE.match(result), (
            f"{task_name} returned {result!r}; task_telemetry would record this as "
            "success even though the task did nothing"
        )

    def test_success_returns_are_not_matched_as_soft_fail(self):
        for retval in ["Success", "OK: 3 breaches", "Skipped", "Skipped (Market Closed)",
                       "Dispatched 3 sentinel_tick tasks", "Success: archived 7 memories"]:
            assert not _SOFT_FAIL_RE.match(retval), retval
