"""
Owner-resolution contract.

This file used to assert multi-tenant fan-out: `_resolve_target_users()`
returning every active user, and `settings_repository._resolve_user()` raising
on the 'system' sentinel. The single-box conversion inverts both — scheduling
targets exactly one owner, and the sentinels resolve instead of raising.

What is NOT inverted, and is the point of this file: an explicitly supplied
user id is still passed through untouched. `resolve_user_id()` narrows "no
identity given" to the owner; it does not rewrite identities. That distinction
keeps every `user_id`-filtered query in the repositories meaningful and leaves
a future multi-user mode reachable without unpicking the call sites.

本檔驗證：未指定身分才解析成擁有者，明確傳入的 UUID 一律原樣放行。
"""
import pytest
from unittest.mock import MagicMock, patch

from src.config.owner import (
    OwnerNotResolved,
    active_user_ids,
    get_owner_id,
    reset_owner_cache,
    resolve_user_id,
)
from src.infrastructure.tasks import _resolve_target_users
from src.repositories.user_repository import AlchemyUserRepository

OWNER = "00000000-0000-4000-a000-000000000001"


@pytest.fixture(autouse=True)
def _pin_owner(monkeypatch):
    """Pin the owner via env so no test in this file touches a database."""
    monkeypatch.setenv("OWNER_ID", OWNER)
    reset_owner_cache()
    yield
    reset_owner_cache()


class TestResolverNarrowsOnlyTheUnset:

    @pytest.mark.parametrize("sentinel", [None, "", "   ", "system", "SYSTEM", "None", "default"])
    def test_sentinels_resolve_to_owner(self, sentinel):
        assert resolve_user_id(sentinel) == OWNER

    @pytest.mark.parametrize("explicit", [
        "9f3c1b2a-0000-4000-a000-deadbeefcafe",
        "some-other-user",
        "00000000-0000-4000-a000-000000000002",
    ])
    def test_explicit_ids_pass_through_untouched(self, explicit):
        """The guard rail: resolution must never rewrite a real identity."""
        assert resolve_user_id(explicit) == explicit


class TestOwnerSource:

    def test_env_wins_without_touching_the_database(self):
        with patch.object(AlchemyUserRepository, "get_first_user_id") as spy:
            assert get_owner_id() == OWNER
            spy.assert_not_called()

    def test_falls_back_to_oldest_user_row(self, monkeypatch):
        monkeypatch.delenv("OWNER_ID", raising=False)
        monkeypatch.delenv("PRIMARY_USER_ID", raising=False)
        monkeypatch.delenv("USER_ID", raising=False)
        reset_owner_cache()
        with patch.object(AlchemyUserRepository, "get_first_user_id", return_value="db-user"):
            assert get_owner_id() == "db-user"

    def test_failure_to_resolve_is_loud_not_silent(self, monkeypatch):
        """
        Inventing an id here would scatter settings across two owners, so the
        resolver raises rather than guessing.
        """
        monkeypatch.delenv("OWNER_ID", raising=False)
        monkeypatch.delenv("PRIMARY_USER_ID", raising=False)
        monkeypatch.delenv("USER_ID", raising=False)
        monkeypatch.setenv("OWNER_BOOTSTRAP", "0")
        reset_owner_cache()
        with patch.object(AlchemyUserRepository, "get_first_user_id", return_value=None):
            with pytest.raises(OwnerNotResolved):
                get_owner_id()

    def test_negative_results_are_never_cached(self, monkeypatch):
        """
        A lookup that ran before the database was seeded must not pin failure
        for the lifetime of the process.
        """
        monkeypatch.delenv("OWNER_ID", raising=False)
        monkeypatch.delenv("PRIMARY_USER_ID", raising=False)
        monkeypatch.delenv("USER_ID", raising=False)
        monkeypatch.setenv("OWNER_BOOTSTRAP", "0")
        reset_owner_cache()
        with patch.object(AlchemyUserRepository, "get_first_user_id", return_value=None):
            with pytest.raises(OwnerNotResolved):
                get_owner_id()
        with patch.object(AlchemyUserRepository, "get_first_user_id", return_value="seeded-later"):
            assert get_owner_id() == "seeded-later"


class TestSchedulingFanOut:

    def test_active_user_ids_is_exactly_the_owner(self):
        assert active_user_ids() == [OWNER]

    def test_scheduler_targets_the_owner_by_default(self):
        assert _resolve_target_users() == [OWNER]

    def test_scheduler_honours_an_explicit_target(self):
        assert _resolve_target_users("explicit-user-id") == ["explicit-user-id"]

    def test_extra_user_rows_cannot_multiply_scheduled_work(self):
        """
        The cost regression this guards: `get_all_active_users()` returning a
        stray test account used to double every scheduled LLM job.
        多餘的 users 列不得讓排程工作倍增（LLM 帳單直接翻倍）。
        """
        with patch.object(AlchemyUserRepository, "get_all_active_users",
                          return_value=["user-1", "user-2", "user-3"]):
            assert _resolve_target_users() == [OWNER]


class TestUserRepositoryStillTruthful:
    """`get_all_active_users()` is no longer used for scheduling, but it must
    keep reporting reality for diagnostics."""

    def test_get_first_user_id(self):
        with patch.object(AlchemyUserRepository, "get_all_active_users",
                          return_value=["user-uuid-1", "user-uuid-2"]):
            assert AlchemyUserRepository(engine=MagicMock()).get_first_user_id() == "user-uuid-1"

    def test_get_first_user_id_empty(self):
        with patch.object(AlchemyUserRepository, "get_all_active_users", return_value=[]):
            assert AlchemyUserRepository(engine=MagicMock()).get_first_user_id() is None


class TestSettingsRepositoryResolution:

    def test_system_sentinel_no_longer_raises(self):
        from src.repositories.settings_repository import AlchemySettingsRepository

        repo = AlchemySettingsRepository(engine=MagicMock())
        assert repo._resolve_user("system") == OWNER
        assert repo._resolve_user(None) == OWNER

    def test_explicit_user_still_scopes_the_query(self):
        from src.repositories.settings_repository import AlchemySettingsRepository

        repo = AlchemySettingsRepository(engine=MagicMock())
        assert repo._resolve_user("another-user") == "another-user"
