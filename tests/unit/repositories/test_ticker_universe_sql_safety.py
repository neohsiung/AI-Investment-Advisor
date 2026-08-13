"""
Dynamic-SQL safety for `ticker_universe_repository` (2026-08-14).

`upsert` and `upsert_target` are the only two places in the repository layer
that interpolate caller-supplied **kwargs *keys* into SQL — values are always
bound, but a column name cannot be. Static allowlists have guarded both since
2026-06-21 (commit 47351d97, a CodeQL fix), and nothing tested them: deleting
the guard broke no test, which is the state that lets a security control get
"cleaned up" during an unrelated refactor.

這兩個方法會把呼叫端的 kwargs key 插進 SQL（值一律綁定，但欄位名無法綁定）。
白名單自 2026-06-21 起就存在，卻沒有任何測試——拿掉它不會有任何測試失敗。
"""
from unittest.mock import MagicMock, patch

import pytest

from src.repositories.ticker_universe_repository import (
    TARGET_UPDATABLE_FIELDS,
    UNIVERSE_UPDATABLE_FIELDS,
    TickerUniverseRepository,
)

USER = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def repo():
    with patch.object(TickerUniverseRepository, "_init_tables"):
        r = TickerUniverseRepository(engine=MagicMock())
    r.get_by_ticker = MagicMock(return_value=None)
    return r


def _executed_sql(repo) -> str:
    conn = repo.engine.begin.return_value.__enter__.return_value
    return str(conn.execute.call_args.args[0])


def _executed_params(repo) -> dict:
    conn = repo.engine.begin.return_value.__enter__.return_value
    return conn.execute.call_args.args[1]


# ─────────────────────────────────────────────────────────────────────────────
# Rejection
# ─────────────────────────────────────────────────────────────────────────────

INJECTION_ATTEMPTS = [
    "status = 'x', company_name",          # extra assignment smuggled in
    "company_name; DROP TABLE ticker_universe; --",
    "(SELECT password FROM users)",
    "status)--",
    "__class__",
]


@pytest.mark.parametrize("field", INJECTION_ATTEMPTS)
def test_upsert_rejects_field_names_outside_the_allowlist(repo, field):
    with pytest.raises(ValueError, match="allowlist"):
        repo.upsert(USER, "NVDA", **{field: "x"})

    repo.engine.begin.assert_not_called()


@pytest.mark.parametrize("field", INJECTION_ATTEMPTS)
def test_upsert_target_rejects_field_names_outside_the_allowlist(repo, field):
    with pytest.raises(ValueError, match="allowlist"):
        repo.upsert_target(USER, "NVDA", **{field: 0.5})

    repo.engine.begin.assert_not_called()


def test_rejection_names_the_offending_field(repo):
    """The message has to be actionable; a bare 'invalid input' sends the next
    reader to the wrong place."""
    with pytest.raises(ValueError) as exc:
        repo.upsert(USER, "NVDA", sector="Tech", not_a_column="x")

    assert "not_a_column" in str(exc.value)
    assert "sector" not in str(exc.value).split("allowed:")[0]


def test_one_bad_field_rejects_the_whole_call(repo):
    """No partial application: a call carrying an unknown field must not have
    its other fields written as if the caller got what it asked for."""
    with pytest.raises(ValueError):
        repo.upsert(USER, "NVDA", sector="Tech", evil="x")

    repo.engine.begin.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Empty kwargs — used to build syntactically invalid SQL
# ─────────────────────────────────────────────────────────────────────────────

def test_upsert_with_no_fields_raises_instead_of_emitting_broken_sql(repo):
    """Both branches join kwargs into a clause; with none they produced
    `SET , last_reviewed_at = ...` and an empty `DO UPDATE SET`, which the
    caller saw only as a generic False."""
    with pytest.raises(ValueError, match="no updatable fields"):
        repo.upsert(USER, "NVDA")

    repo.engine.begin.assert_not_called()


def test_upsert_target_with_no_fields_raises(repo):
    with pytest.raises(ValueError, match="no updatable fields"):
        repo.upsert_target(USER, "NVDA")

    repo.engine.begin.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Acceptance — allowed names reach SQL, values never do
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field", sorted(UNIVERSE_UPDATABLE_FIELDS))
def test_every_allowlisted_universe_field_is_accepted(repo, field):
    assert repo.upsert(USER, "NVDA", **{field: "value"}) is True
    assert field in _executed_sql(repo)


@pytest.mark.parametrize("field", sorted(TARGET_UPDATABLE_FIELDS))
def test_every_allowlisted_target_field_is_accepted(repo, field):
    assert repo.upsert_target(USER, "NVDA", **{field: 0.25}) is True
    assert field in _executed_sql(repo)


def test_values_are_bound_not_interpolated(repo):
    """The values are the untrusted part. They must appear in the parameter
    dict and never in the statement text."""
    hostile = "'); DROP TABLE ticker_universe; --"
    repo.upsert(USER, "NVDA", company_name=hostile, sector="Tech")

    sql = _executed_sql(repo)
    params = _executed_params(repo)

    assert hostile not in sql
    assert "DROP TABLE" not in sql.upper()
    assert hostile in params.values()
    assert ":company_name" in sql


def test_update_branch_is_used_when_the_row_exists(repo):
    repo.get_by_ticker = MagicMock(return_value={"ticker": "NVDA", "status": "active"})
    repo.upsert(USER, "NVDA", status="removed")

    sql = _executed_sql(repo)
    assert sql.strip().upper().startswith("UPDATE")
    assert "status = :status" in sql


# ─────────────────────────────────────────────────────────────────────────────
# The service must not carry its own divergent copy
# ─────────────────────────────────────────────────────────────────────────────

def test_service_filters_on_the_repository_allowlist():
    """`ticker_universe_service.update_ticker` used to restate the field set as
    a literal. Two copies of a security boundary drift, and the failure mode is
    invisible: the service silently drops a field the repository would have
    accepted, and reports success for an update that never happened."""
    import src.services.ticker_universe_service as svc

    assert svc.UNIVERSE_UPDATABLE_FIELDS is UNIVERSE_UPDATABLE_FIELDS

    import ast
    import inspect

    tree = ast.parse(inspect.getsource(svc.TickerUniverseService.update_ticker).strip())
    literal_sets = [n for n in ast.walk(tree)
                    if isinstance(n, ast.Set)
                    and any(isinstance(e, ast.Constant) and e.value in UNIVERSE_UPDATABLE_FIELDS
                            for e in n.elts)]
    assert not literal_sets, (
        "update_ticker is restating the allowlist as a literal instead of importing it"
    )
    assert "UNIVERSE_UPDATABLE_FIELDS" in inspect.getsource(svc.TickerUniverseService.update_ticker)
