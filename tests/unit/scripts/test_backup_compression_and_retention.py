"""Compressed DB backups and pre-deploy backup retention (scripts/backup_lib.sh, scripts/backup_db.sh, start.sh).
資料庫備份壓縮與部署前備份保留上限。

Nothing here talks to a real container: the nightly script runs from a temp copy whose PATH puts a fake `docker` first.
這裡不碰真實容器：夜間腳本從暫存複本執行，PATH 最前面是假的 `docker`。
"""
import gzip
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "scripts" / "backup_lib.sh"
TRAILER = "--\n-- PostgreSQL database dump complete\n--\n\n"


def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", f'. "{LIB}"; {script}'], cwd=cwd, capture_output=True, text=True)


def _gz(path: Path, text: str) -> Path:
    path.write_bytes(gzip.compress(text.encode()))
    return path


# ── verify_sql_gz ────────────────────────────────────────────────────────────

def test_complete_gzip_dump_passes(tmp_path):
    f = _gz(tmp_path / "ok.sql.gz", "CREATE TABLE t();\n" * 100 + TRAILER)
    assert _bash(f'verify_sql_gz "{f}"', tmp_path).returncode == 0


def test_truncated_dump_without_trailer_fails(tmp_path):
    f = _gz(tmp_path / "trunc.sql.gz", "CREATE TABLE t();\n" * 100)
    assert _bash(f'verify_sql_gz "{f}"', tmp_path).returncode != 0


def test_gzip_of_empty_input_fails_even_though_file_is_not_empty(tmp_path):
    f = _gz(tmp_path / "empty.sql.gz", "")
    assert f.stat().st_size > 0
    assert _bash(f'verify_sql_gz "{f}"', tmp_path).returncode != 0


def test_corrupt_gzip_fails(tmp_path):
    f = _gz(tmp_path / "bad.sql.gz", "x\n" * 1000 + TRAILER)
    data = f.read_bytes()
    f.write_bytes(data[: len(data) // 2])  # cut mid-stream / 從中間截斷
    assert _bash(f'verify_sql_gz "{f}"', tmp_path).returncode != 0


def test_plain_uncompressed_sql_fails(tmp_path):
    f = tmp_path / "plain.sql"
    f.write_text("x\n" + TRAILER)
    assert _bash(f'verify_sql_gz "{f}"', tmp_path).returncode != 0


# ── prune_deploy_backups ─────────────────────────────────────────────────────

GROUP_TS = ["20261016-085215", "20261017-135413", "20261019-155055", "20261020-204948",
            "20261021-040718", "20261022-081741", "20261023-064528"]
UNTOUCHABLE = ["pre-m1-deploy-20260911-100839.sql", "pre-m6-deploy-20260920-000144.sql",
               "db_backup_20261025_030000.sql", "db_backup_20261026_030000.sql.gz",
               "db-20261022-080507.sql",  # orphan: no manifest / 沒有 manifest 的孤兒檔
               "deploy_audit.log", "backup.log", "crontab.before-20261021.txt",
               "n8n_workflow_1_20260823_204011.json", "alpha_spy_settings_20261016.json"]


def _populate(d: Path):
    for i, ts in enumerate(GROUP_TS):
        # Old groups are plain .sql, the newest two are .sql.gz. / 舊組為 .sql，最新兩組為 .sql.gz。
        (d / (f"db-{ts}.sql.gz" if i >= 5 else f"db-{ts}.sql")).write_text("x")
        (d / f"config-{ts}.tar.gz").write_text("x")
        (d / f"env-{ts}.bak").write_text("x")
        (d / f"manifest-{ts}.json").write_text("{}")
    for name in UNTOUCHABLE:
        (d / name).write_text("x")
    # mtimes inverted against names: ordering must come from the name, not mtime.
    # mtime 與檔名順序相反：排序必須依檔名。
    for i, ts in enumerate(GROUP_TS):
        os.utime(d / f"manifest-{ts}.json", (1_000_000 + (len(GROUP_TS) - i), 1_000_000 + (len(GROUP_TS) - i)))


def _groups(d: Path):
    return sorted(p.name[len("manifest-"):-len(".json")] for p in d.glob("manifest-*.json"))


def test_keeps_newest_n_groups_and_removes_old_groups_whole(tmp_path):
    _populate(tmp_path)
    r = _bash("prune_deploy_backups . 3", tmp_path)
    assert r.returncode == 0, r.stderr
    assert _groups(tmp_path) == GROUP_TS[-3:]
    for ts in GROUP_TS[:-3]:
        assert not list(tmp_path.glob(f"*-{ts}.*")), ts
    for ts in GROUP_TS[-3:]:
        assert (tmp_path / f"config-{ts}.tar.gz").exists() and (tmp_path / f"env-{ts}.bak").exists()
    assert (tmp_path / f"db-{GROUP_TS[-1]}.sql.gz").exists() and (tmp_path / f"db-{GROUP_TS[-3]}.sql").exists()


def test_never_touches_milestone_nightly_orphan_or_other_files(tmp_path):
    _populate(tmp_path)
    assert _bash("prune_deploy_backups . 1", tmp_path).returncode == 0
    for name in UNTOUCHABLE:
        assert (tmp_path / name).exists(), name


def test_fewer_groups_than_keep_deletes_nothing(tmp_path):
    _populate(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    assert _bash("prune_deploy_backups . 99", tmp_path).returncode == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_zero_empty_or_garbage_keep_disables_pruning(tmp_path):
    _populate(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    for keep in ["0", "''", "-1", "abc", "5x"]:
        r = _bash(f"prune_deploy_backups . {keep}", tmp_path)
        assert r.returncode == 0 and "disabled" in r.stdout, (keep, r.stdout)
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_prune_is_safe_under_set_e_with_no_manifests(tmp_path):
    (tmp_path / "pre-m1-deploy-x.sql").write_text("x")
    r = _bash("set -e; prune_deploy_backups . 5; echo after", tmp_path)
    assert r.returncode == 0 and "after" in r.stdout


# ── scripts/backup_db.sh end to end with a fake docker ───────────────────────

def _nightly_sandbox(tmp_path: Path, docker_body: str) -> Path:
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "config").mkdir()
    shutil.copy(LIB, root / "scripts" / "backup_lib.sh")
    src = (REPO / "scripts" / "backup_db.sh").read_text()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text("#!/bin/bash\n" + docker_body)
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    # Put the fake docker in front of the PATH the script sets for cron. / 讓假的 docker 排在腳本設定的 PATH 前面。
    line = 'export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:${PATH}"'
    assert line in src
    (root / "scripts" / "backup_db.sh").write_text(src.replace(line, f'export PATH="{fake_bin}:/usr/bin:/bin"'))
    return root


def _run_nightly(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(root / "scripts" / "backup_db.sh")], capture_output=True, text=True)


def test_nightly_writes_verified_gzip_and_status(tmp_path):
    root = _nightly_sandbox(tmp_path, f"printf 'CREATE TABLE t();\\n{TRAILER.encode('unicode_escape').decode()}'\n")
    r = _run_nightly(root)
    assert r.returncode == 0, r.stdout + r.stderr
    dumps = list((root / "backups").glob("db_backup_*.sql.gz"))
    assert len(dumps) == 1 and not list((root / "backups").glob("*.partial"))
    assert gzip.decompress(dumps[0].read_bytes()).decode().rstrip().endswith("--")
    st = json.loads((root / "config" / ".backup_status.json").read_text())
    assert st["ok"] is True and st["file"] == dumps[0].name and st["bytes"] == dumps[0].stat().st_size
    assert not (root / "backups" / "BACKUP_FAILED").exists()


def test_nightly_fails_when_pg_dump_fails_even_though_gzip_succeeds(tmp_path):
    root = _nightly_sandbox(tmp_path, "printf 'partial\\n'; exit 3\n")
    r = _run_nightly(root)
    assert r.returncode != 0
    assert not list((root / "backups").glob("db_backup_*"))
    assert "pg_dump exited non-zero" in (root / "backups" / "BACKUP_FAILED").read_text()
    assert json.loads((root / "config" / ".backup_status.json").read_text())["ok"] is False


def test_nightly_fails_on_truncated_dump(tmp_path):
    root = _nightly_sandbox(tmp_path, "printf 'CREATE TABLE t();\\n'\n")
    r = _run_nightly(root)
    assert r.returncode != 0
    assert not list((root / "backups").glob("db_backup_*"))
    assert "completion trailer" in (root / "backups" / "BACKUP_FAILED").read_text()


def test_nightly_retention_covers_legacy_sql_and_new_gz(tmp_path):
    root = _nightly_sandbox(tmp_path, f"printf 'x\\n{TRAILER.encode('unicode_escape').decode()}'\n")
    b = root / "backups"
    b.mkdir()
    old = [b / "db_backup_20260101_030000.sql", b / "db_backup_20260102_030000.sql.gz"]
    keep = b / "pre-m1-deploy-20260101-000000.sql"
    for p in old + [keep]:
        p.write_text("x")
        os.utime(p, (1_600_000_000, 1_600_000_000))
    assert _run_nightly(root).returncode == 0
    assert not any(p.exists() for p in old)
    assert keep.exists()


# ── start.sh wiring (static: running it would touch the live stack) ─────────

def test_start_sh_writes_gzip_prunes_after_manifest_and_restores_both_formats():
    s = (REPO / "start.sh").read_text()
    backup = s[s.index("function cmd_backup"):s.index("function cmd_restore")]
    restore = s[s.index("function cmd_restore"):s.index("function cmd_upgrade")]
    assert 'db_file="backups/db-${ts}.sql.gz"' in backup
    assert '"db": "db-${ts}.sql.gz"' in backup
    assert "verify_sql_gz" in backup
    assert backup.index("manifest-${ts}.json") < backup.index("prune_deploy_backups")
    assert 'DEPLOY_BACKUP_KEEP:-5' in backup
    assert 'backups/db-${target}.sql.gz' in restore and 'db_file="backups/db-${target}.sql"' in restore
    assert "gzip -cd" in restore


# ── start.sh cmd_backup, run in isolation (function extracted; fake docker; temp dir) ──

def _run_cmd_backup(tmp_path: Path, docker_body: str, keep: str = "2") -> subprocess.CompletedProcess:
    s = (REPO / "start.sh").read_text()
    fn = s[s.index("function cmd_backup"):s.index("function cmd_restore")]
    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    (proj / "config").mkdir()
    (proj / "config" / "a.yaml").write_text("x: 1\n")
    shutil.copy(LIB, proj / "scripts" / "backup_lib.sh")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    docker = fake_bin / "docker"
    docker.write_text("#!/bin/bash\n" + docker_body)
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    script = f"set -e\nPROD_DB=fake_db\n{fn}\ncmd_backup\necho AFTER_BACKUP\n"
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "DEPLOY_BACKUP_KEEP": keep, "HOME": str(tmp_path)}
    return subprocess.run(["bash", "-c", script], cwd=proj, capture_output=True, text=True, env=env)


def test_cmd_backup_writes_gzip_group_and_prunes_old_groups(tmp_path):
    b = tmp_path / "proj" / "backups"
    b.mkdir(parents=True)
    for ts in ["20200101-000000", "20200102-000000", "20200103-000000"]:
        for name in [f"db-{ts}.sql", f"config-{ts}.tar.gz", f"env-{ts}.bak", f"manifest-{ts}.json"]:
            (b / name).write_text("x")
    (b / "pre-m1-deploy-20200101-000000.sql").write_text("x")
    body = f"printf 'CREATE TABLE t();\\n{TRAILER.encode('unicode_escape').decode()}'\n"
    r = _run_cmd_backup(tmp_path, body, keep="2")
    assert r.returncode == 0 and "AFTER_BACKUP" in r.stdout, r.stdout + r.stderr
    new = [p for p in b.glob("manifest-*.json") if not p.name.startswith("manifest-2020")]
    assert len(new) == 1
    m = json.loads(new[0].read_text())
    assert m["files"]["db"].endswith(".sql.gz") and (b / m["files"]["db"]).exists()
    assert gzip.decompress((b / m["files"]["db"]).read_bytes()).decode().startswith("CREATE TABLE")
    # keep=2 → the new group plus the newest old one. / 保留 2 組：新的一組加上最新的舊組。
    assert sorted(p.name for p in b.glob("manifest-2020*")) == ["manifest-20200103-000000.json"]
    for ts in ["20200101-000000", "20200102-000000"]:
        for name in [f"db-{ts}.sql", f"config-{ts}.tar.gz", f"env-{ts}.bak", f"manifest-{ts}.json"]:
            assert not (b / name).exists(), name
    assert (b / "pre-m1-deploy-20200101-000000.sql").exists()
    assert not list(b.glob("*.partial"))


def test_cmd_backup_failed_dump_returns_error_writes_nothing_and_prunes_nothing(tmp_path):
    b = tmp_path / "proj" / "backups"
    b.mkdir(parents=True)
    for ts in ["20200101-000000", "20200102-000000", "20200103-000000"]:
        (b / f"manifest-{ts}.json").write_text("{}")
        (b / f"db-{ts}.sql").write_text("x")
    r = _run_cmd_backup(tmp_path, "printf 'CREATE TABLE t();\\n'; exit 1\n", keep="1")
    assert r.returncode != 0 and "AFTER_BACKUP" not in r.stdout
    assert "Database dump failed" in r.stdout
    assert not list(b.glob("db-*.sql.gz*")) and not list(b.glob("config-*"))
    assert len(list(b.glob("manifest-*.json"))) == 3
