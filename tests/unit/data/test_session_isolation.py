"""
Session isolation regression tests.
測試 SQLAlchemy session 隔離。

Context (2026-08-02): BaseRepository shared ONE `scoped_session` registry per
Engine, and `get_db_engine` caches engines by URL — so the whole process shared
one registry. `scoped_session` with no scopefunc scopes to `threading.local()`,
but FastAPI runs every coroutine on a single event-loop thread, so
"thread-local" meant "shared by every concurrent request".

Consequences, all real:
  - one coroutine's `finally: close_session()` (21 sites) tore down a session
    another coroutine was mid-use of;
  - 23 direct `session.close()` calls in the llm_* repos did the same;
  - 16 `commit()` calls with `expire_on_commit=True` expired EVERY in-flight
    object process-wide.

`llm_tier_binding_repository.get_by_tier` returns ORM objects from a session it
already closed, and `llm_config_chain` reads their attributes — on the path of
every LLM call in the system.
"""
import pytest

from src.data import database
from src.data.database import BaseRepository, get_db_engine


@pytest.fixture
def engine():
    return get_db_engine()


class TestSessionIsolation:

    def test_repository_instances_do_not_share_a_session(self, engine):
        """
        The structural invariant. Before the fix these were the SAME object,
        which is the root of every symptom in this file.
        """
        a = BaseRepository(engine)
        b = BaseRepository(engine)

        assert a.session is not b.session

    def test_session_property_is_stable_within_an_instance(self, engine):
        """
        Guards a silent-data-loss trap: several methods read `self.session`
        more than once in one body — e.g. usage_repository does
        `self.session.add(...)` then `self.session.commit()`. If the property
        returned a fresh session per access, the add would land on one session
        and the commit on another, losing the write with no error.
        `session` 必須 memoize：多處在同一方法內兩次讀取，否則會加到 A、commit B。
        """
        repo = BaseRepository(engine)

        assert repo.session is repo.session

    def test_close_session_on_one_repo_leaves_another_usable(self, engine):
        """One coroutine's teardown must not affect another's session."""
        a = BaseRepository(engine)
        b = BaseRepository(engine)

        a_session = a.session
        b_session = b.session
        b.close_session()

        assert a.session is a_session
        assert a_session.is_active

    def test_no_global_session_registry(self):
        """Prevents reintroduction of the shared registry."""
        assert not hasattr(database, "_session_registries")

    def test_expire_on_commit_is_disabled(self, engine):
        """
        With per-call sessions, repositories legitimately return ORM objects
        that outlive their session. expire_on_commit=False is what makes that
        safe rather than a landmine.
        """
        repo = BaseRepository(engine)

        assert repo.session.expire_on_commit is False


class TestInjectedSession:
    """A caller may supply its own session (per-request unit of work)."""

    def test_injected_session_is_returned(self, engine):
        outer = BaseRepository(engine)
        inner = BaseRepository(engine, session=outer.session)

        assert inner.session is outer.session

    def test_repository_does_not_close_an_injected_session(self, engine):
        outer = BaseRepository(engine)
        shared = outer.session
        inner = BaseRepository(engine, session=shared)

        inner.close_session()

        assert shared.is_active, "repository closed a session it does not own"


class TestSessionScope:

    def test_commits_on_clean_exit(self, engine):
        repo = BaseRepository(engine)

        with repo.session_scope() as s:
            assert s is not None

    def test_rolls_back_and_reraises_on_error(self, engine):
        repo = BaseRepository(engine)

        with pytest.raises(ValueError):
            with repo.session_scope():
                raise ValueError("boom")

    def test_injected_session_is_not_committed_or_closed(self, engine):
        outer = BaseRepository(engine)
        shared = outer.session
        inner = BaseRepository(engine, session=shared)

        with inner.session_scope() as s:
            assert s is shared

        assert shared.is_active


class TestGetDbDependency:
    """
    The opt-in per-request unit of work (src/api/v1/dependencies.get_db).
    Used only where a handler writes through more than one repository and
    those writes must land together.
    """

    def test_yields_a_session_and_closes_it(self):
        from src.api.v1.dependencies import get_db

        gen = get_db()
        session = next(gen)
        assert session is not None

        with pytest.raises(StopIteration):
            next(gen)
        assert not session.is_active or session.get_bind() is not None

    def test_rolls_back_and_propagates_on_error(self):
        from src.api.v1.dependencies import get_db

        gen = get_db()
        next(gen)
        with pytest.raises(ValueError):
            gen.throw(ValueError("boom"))

    def test_session_can_be_injected_into_a_repository(self, engine):
        """The whole point: several repos sharing one transaction."""
        from src.api.v1.dependencies import get_db

        gen = get_db()
        db = next(gen)

        a = BaseRepository(engine, session=db)
        b = BaseRepository(engine, session=db)
        assert a.session is b.session is db

        a.close_session()
        assert db.is_active, "repository closed the request-owned session"

        with pytest.raises(StopIteration):
            next(gen)

    def test_expire_on_commit_disabled(self):
        from src.api.v1.dependencies import get_db

        gen = get_db()
        db = next(gen)
        assert db.expire_on_commit is False
        with pytest.raises(StopIteration):
            next(gen)
