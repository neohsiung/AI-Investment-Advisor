"""
`./start.sh upgrade` must bring the code up to date on both checkouts we run:
a normal branch (fast-forward pull) and the production checkout, which sits on a
detached HEAD (a plain `git pull` fails there with "not currently on a branch").
It must refuse, and leave HEAD untouched, when it cannot move forward safely.

These run `advisor_sync_code` from scripts/lib/deploy_sync.sh against real throwaway
git repositories. No docker, no network.

upgrade 要能同步兩種 checkout：一般分支（快轉 pull）與正式環境的 detached HEAD
（直接 git pull 會失敗）。無法安全前進時必須拒絕且不動 HEAD。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "scripts" / "lib" / "deploy_sync.sh"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": "/nonexistent",
}


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(cwd: Path, name: str, text: str) -> str:
    (cwd / name).write_text(text)
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", f"add {name}")
    return git(cwd, "rev-parse", "HEAD")


class Machine:
    """An origin with two commits on main, and a clone that deploys from it."""

    def __init__(self, root: Path):
        self.origin = root / "origin"
        self.work = root / "work"
        self.origin.mkdir()
        git(self.origin, "init", "-q", "-b", "main")
        self.c1 = commit(self.origin, "a.txt", "one\n")
        git(root, "clone", "-q", str(self.origin), "work")
        self.c2 = commit(self.origin, "b.txt", "two\n")   # origin moves ahead of the clone

    def sync(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f'source "{LIB}"; advisor_sync_code'],
            cwd=self.work, env=GIT_ENV, capture_output=True, text=True, timeout=60,
        )

    def head(self) -> str:
        return git(self.work, "rev-parse", "HEAD")


@pytest.fixture
def machine(tmp_path: Path) -> Machine:
    return Machine(tmp_path)


def test_detached_head_behind_origin_moves_to_origin_main(machine: Machine):
    git(machine.work, "checkout", "-q", "--detach", machine.c1)
    result = machine.sync()
    assert result.returncode == 0, result.stdout + result.stderr
    assert machine.head() == machine.c2


def test_detached_head_already_at_origin_main_is_a_no_op(machine: Machine):
    git(machine.work, "fetch", "-q", "origin")
    git(machine.work, "checkout", "-q", "--detach", "origin/main")
    result = machine.sync()
    assert result.returncode == 0, result.stdout + result.stderr
    assert machine.head() == machine.c2


def test_branch_checkout_fast_forwards(machine: Machine):
    assert git(machine.work, "branch", "--show-current") == "main"
    result = machine.sync()
    assert result.returncode == 0, result.stdout + result.stderr
    assert machine.head() == machine.c2


def test_detached_head_not_in_origin_history_is_refused_and_left_alone(machine: Machine):
    git(machine.work, "checkout", "-q", "--detach", machine.c1)
    local = commit(machine.work, "local.txt", "hotfix\n")   # a commit origin does not have
    result = machine.sync()
    assert result.returncode != 0
    assert machine.head() == local
    assert "origin/main" in result.stdout + result.stderr


def test_detached_head_with_conflicting_local_edit_is_refused_and_left_alone(machine: Machine):
    git(machine.work, "checkout", "-q", "--detach", machine.c1)
    (machine.work / "a.txt").write_text("edited on the box\n")
    # origin's next commit touches the same file, so moving forward would overwrite the edit
    commit(machine.origin, "a.txt", "changed upstream\n")
    result = machine.sync()
    assert result.returncode != 0
    assert machine.head() == machine.c1
    assert (machine.work / "a.txt").read_text() == "edited on the box\n"


def test_unreachable_origin_fails_instead_of_continuing(machine: Machine):
    git(machine.work, "checkout", "-q", "--detach", machine.c1)
    git(machine.work, "remote", "set-url", "origin", str(machine.origin) + "-missing")
    result = machine.sync()
    assert result.returncode != 0
    assert machine.head() == machine.c1
