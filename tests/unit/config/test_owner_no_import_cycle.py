"""
`src.config.owner` must be importable with nothing else loaded.

`settings_repository` imports it, and most of `src/` imports
`settings_repository`. A top-level project import inside `owner.py` would
therefore close a cycle that breaks every process at once — API, both workers,
beat and any webhook handler — and the traceback would point at whichever
module happened to be imported first, not at the cause.

This test runs in a *fresh interpreter* on purpose: inside the pytest process
half the package graph is already in `sys.modules`, so a cycle would not
reproduce.

本測試以獨立直譯器執行：pytest 行程內套件圖已載入大半，循環相依不會重現。
"""
import subprocess
import sys
import textwrap


PROBE = textwrap.dedent(
    """
    import sys
    import src.config.owner as owner

    leaked = sorted(
        m for m in sys.modules
        if m.startswith("src.") and m not in ("src", "src.config", "src.config.owner")
    )
    if leaked:
        print("LEAKED:" + ",".join(leaked))
        raise SystemExit(1)

    # The pure-function surface must work with no database and no config.
    assert owner.resolve_user_id("explicit-id") == "explicit-id"
    assert owner._is_unset(None) and owner._is_unset("system")
    print("OK")
    """
)


def test_owner_imports_alone_without_pulling_in_the_package(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "src.config.owner must not import project modules at module scope.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


def test_owner_import_is_first_in_settings_repository_chain():
    """The consumer that makes the cycle dangerous still imports it cleanly."""
    result = subprocess.run(
        [sys.executable, "-c",
         "import src.repositories.settings_repository as m; "
         "assert m.resolve_user_id('x') == 'x'; print('OK')"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout
