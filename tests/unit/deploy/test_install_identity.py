"""
Fresh-install identity checks: a clean machine must get its own compose project
and container names, and a machine that already runs a stack must be refused.

These run `install.sh` / `start.sh` from a throwaway copy with a fake `docker`
and `curl` first on PATH. The fake only answers an allowlist of read-only
queries from scenario files and logs every call, so nothing here can start,
stop or touch a real container, volume or database.

乾淨安裝要拿到自己的 compose 專案名與容器名；同機已有 stack 時必須拒絕。
用假的 docker 與 curl 在暫存複本裡跑腳本，只回答白名單內的唯讀查詢並記錄每次呼叫。
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LEGACY_PROJECT = "investment_advisor"
LEGACY_PREFIX = "advisor_prod"

FAKE_DOCKER = r"""#!/usr/bin/env bash
# Fake docker: log argv, answer read-only queries from $FAKE_DIR, refuse the rest.
echo "$*" >> "$FAKE_DIR/calls.log"
case "$1" in
  info) exit 0 ;;
  compose)
    case "$2" in
      version) echo "Docker Compose version v2.0.0"; exit 0 ;;
      *) exit 0 ;;   # build / up / exec / restart: recorded, no effect
    esac ;;
  ps)
    if [[ "$*" == *"{{.Label"* ]]; then cat "$FAKE_DIR/ps.tsv"; else cut -f1 "$FAKE_DIR/ps.tsv"; fi
    exit 0 ;;
  volume)
    case "$2" in
      inspect) grep -qx "$3" "$FAKE_DIR/volumes.txt" && exit 0 || exit 1 ;;
      ls) cat "$FAKE_DIR/volumes.txt"; exit 0 ;;
    esac ;;
  exec) exit 0 ;;
esac
echo "fake docker: refusing unexpected call: $*" >&2
exit 99
"""

FAKE_CURL = "#!/usr/bin/env bash\nexit 0\n"


class Box:
    """One throwaway checkout plus a fake docker whose view of the machine we control."""

    def __init__(self, root: Path):
        self.dir = root / "checkout"
        self.fake = root / "fake"
        self.bin = root / "bin"
        for d in (self.dir, self.fake, self.bin):
            d.mkdir()
        (self.dir / "scripts" / "lib").mkdir(parents=True)
        for name in ("install.sh", "start.sh", ".env.example"):
            shutil.copy(REPO / name, self.dir / name)
        for f in (REPO / "scripts" / "lib").glob("*.sh"):
            shutil.copy(f, self.dir / "scripts" / "lib" / f.name)
        gate = self.dir / "scripts" / "predeploy_gate.sh"   # the real gate runs tests; not under test here
        gate.write_text("#!/usr/bin/env bash\nexit 0\n")
        gate.chmod(gate.stat().st_mode | stat.S_IEXEC)
        for name in ("docker", "curl"):
            p = self.bin / name
            p.write_text(FAKE_DOCKER if name == "docker" else FAKE_CURL)
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
        (self.fake / "ps.tsv").write_text("")
        (self.fake / "volumes.txt").write_text("")
        (self.fake / "calls.log").write_text("")
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(root),
            "FAKE_DIR": str(self.fake),
        }
        assert shutil.which("docker", path=self.env["PATH"]) == str(self.bin / "docker")

    def containers(self, *rows: tuple[str, str, str]) -> None:
        """rows: (container name, compose project, working dir)."""
        (self.fake / "ps.tsv").write_text("".join("\t".join(r) + "\n" for r in rows))

    def volumes(self, *names: str) -> None:
        (self.fake / "volumes.txt").write_text("".join(n + "\n" for n in names))

    def write_env(self, **pairs: str) -> None:
        lines = [ln for ln in (REPO / ".env.example").read_text().splitlines()
                 if not any(ln.startswith(f"{k}=") for k in pairs)]
        lines += [f"{k}={v}" for k, v in pairs.items()]
        (self.dir / ".env").write_text("\n".join(lines) + "\n")

    def run(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", script, *args],
            cwd=self.dir, env=self.env, capture_output=True, text=True, timeout=60,
            stdin=subprocess.DEVNULL,
        )

    def calls(self) -> list[str]:
        return (self.fake / "calls.log").read_text().splitlines()

    def changed_stack(self) -> list[str]:
        return [c for c in self.calls() if c.startswith("compose") and (" build" in c or " up " in c or c.endswith(" up"))]

    def project_names(self) -> set[str]:
        out = set()
        for c in self.calls():
            if c.startswith("compose") and "--project-name" in c:
                out.add(c.split("--project-name")[1].split()[0])
        return out


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


def _refused(r: subprocess.CompletedProcess, box: Box) -> None:
    assert r.returncode != 0, r.stdout + r.stderr
    assert box.changed_stack() == [], f"stack was changed despite refusal: {box.changed_stack()}"


INSTALL = ("install.sh", "--non-interactive", "--skip-build")


class TestCleanMachine:
    def test_install_uses_non_production_names(self, box):
        r = box.run(*INSTALL)
        assert r.returncode == 0, r.stdout + r.stderr
        assert box.project_names(), "install never ran compose"
        assert LEGACY_PROJECT not in box.project_names()
        assert not any(LEGACY_PREFIX + "_" in c for c in box.calls()), "install touched a production-style container name"

    def test_scheduler_starts_only_after_safe_defaults_are_seeded(self, box):
        r = box.run(*INSTALL)
        assert r.returncode == 0, r.stdout + r.stderr
        calls = box.calls()
        first_scheduler = next((i for i, c in enumerate(calls) if "scheduler" in c and " up" in c), None)
        seed = next((i for i, c in enumerate(calls) if "ai_trading_enabled" in c), None)
        assert first_scheduler is not None, "scheduler was never started"
        assert seed is not None, "safe-default seed never ran"
        assert seed < first_scheduler, "scheduler started before the seed"
        early = [c for c in calls[:seed] if " up" in c]
        assert early and not any("scheduler" in c for c in early)

    def test_rerun_in_same_checkout_is_allowed(self, box):
        box.containers(("advisor_api", "advisor", str(box.dir.resolve())))
        r = box.run(*INSTALL)
        assert r.returncode == 0, r.stdout + r.stderr


class TestRefusals:
    def test_refuses_when_legacy_production_runs_in_another_checkout(self, box):
        box.containers(("advisor_prod_api", LEGACY_PROJECT, "/somewhere/else"))
        r = box.run(*INSTALL)
        _refused(r, box)
        assert "advisor_prod_api" in r.stdout + r.stderr

    def test_refuses_on_legacy_production_volume_alone(self, box):
        box.volumes("investment_advisor_advisor_db_data")
        r = box.run(*INSTALL)
        _refused(r, box)

    def test_refuses_when_project_name_is_taken_elsewhere(self, box):
        box.write_env(ADVISOR_PROJECT_NAME="mine", ADVISOR_CONTAINER_PREFIX="mine")
        box.containers(("other_thing", "mine", "/somewhere/else"))
        r = box.run(*INSTALL)
        _refused(r, box)

    def test_refuses_when_a_container_name_is_taken_elsewhere(self, box):
        box.containers(("advisor_api", "unrelated", "/somewhere/else"))
        r = box.run(*INSTALL)
        _refused(r, box)

    def test_start_refuses_unpinned_production_checkout(self, box):
        """The founder's own checkout, .env not yet pinned: fail closed and say what to add."""
        here = str(box.dir.resolve())
        box.containers(("advisor_prod_api", LEGACY_PROJECT, here), ("advisor_prod_db", LEGACY_PROJECT, here))
        box.volumes("investment_advisor_advisor_db_data")
        box.write_env()
        for cmd in ("up", "upgrade"):
            r = box.run("start.sh", cmd)
            _refused(r, box)
            out = r.stdout + r.stderr
            assert f"ADVISOR_PROJECT_NAME={LEGACY_PROJECT}" in out
            assert f"ADVISOR_CONTAINER_PREFIX={LEGACY_PREFIX}" in out


class TestPinnedProduction:
    def test_start_up_proceeds_with_pinned_legacy_names(self, box):
        here = str(box.dir.resolve())
        box.containers(("advisor_prod_api", LEGACY_PROJECT, here))
        box.volumes("investment_advisor_advisor_db_data")
        box.write_env(ADVISOR_PROJECT_NAME=LEGACY_PROJECT, ADVISOR_CONTAINER_PREFIX=LEGACY_PREFIX,
                      APP_SECRET_KEY="x" * 40, LLM_CREDENTIAL_KEY="y" * 40)
        r = box.run("start.sh", "up")
        assert LEGACY_PROJECT in box.project_names(), r.stdout + r.stderr
        assert "Refusing" not in r.stdout + r.stderr


class TestReportCommand:
    def test_report_queues_the_daily_task_in_this_stack_only(self, box):
        here = str(box.dir.resolve())
        box.containers(("advisor_worker", "advisor", here))
        box.write_env()
        r = box.run("start.sh", "report")
        assert r.returncode == 0, r.stdout + r.stderr
        call = next(c for c in box.calls() if " exec " in c)
        assert "--project-name advisor" in call
        assert "dispatch_daily_report" in call

    def test_report_says_so_when_the_scheduler_is_down(self, box):
        box.write_env()
        r = box.run("start.sh", "report")
        assert r.returncode != 0
        assert not any(" exec " in c for c in box.calls())


class TestReviewFindings:
    def test_tunnel_is_guarded_in_unpinned_production_checkout(self, box):
        here = str(box.dir.resolve())
        box.containers(("advisor_prod_api", LEGACY_PROJECT, here))
        box.write_env()
        r = box.run("start.sh", "tunnel")
        assert r.returncode != 0
        assert not any("tunnel" in c for c in box.calls())

    def test_dev_stack_in_same_checkout_does_not_block_install(self, box):
        box.containers(("advisor_dev_db", "advisor_dev", str(box.dir.resolve())))
        r = box.run(*INSTALL)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_container_without_workdir_label_is_not_treated_as_ours(self, box):
        box.containers(("advisor_prod_api", "", ""))
        r = box.run(*INSTALL)
        _refused(r, box)

    def test_restore_without_scheduler_does_not_restart_it(self, box):
        here = str(box.dir.resolve())
        box.containers(("advisor_api", "advisor", here))
        box.write_env()
        box.env["ADVISOR_SCHEDULER"] = "0"
        box.run("start.sh", "restore")
        assert not any("restart" in c and "celery_beat" in c for c in box.calls())
