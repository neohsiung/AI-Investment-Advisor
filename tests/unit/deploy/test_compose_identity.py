"""
Compose files must not hard-code the production identity, and the scheduler must
be a separate profile. Structural facts, asserted by parsing YAML (no docker).

compose 檔不得寫死正式環境的名字，排程必須是獨立 profile。以解析 YAML 驗證，不跑 docker。
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
PROD = REPO / "docker-compose.prod.yml"
DEV = REPO / "docker-compose.yml"


def _services(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}).get("services", {}) or {}


def test_prod_container_names_take_their_prefix_from_env_with_a_non_prod_default():
    for name, svc in _services(PROD).items():
        cn = svc.get("container_name")
        if cn is None:
            continue
        assert cn.startswith("${ADVISOR_CONTAINER_PREFIX:-advisor}_"), f"{name}: container_name {cn!r}"


def test_no_production_hostnames_inside_the_stack_config():
    """Inside the network, services reach each other by service name."""
    for path in (PROD, REPO / "infra" / "nginx" / "nginx.conf"):
        text = re.sub(r"(?m)^\s*#.*$", "", path.read_text())
        assert "advisor_prod_" not in text, f"{path.name} still hard-codes an advisor_prod_* hostname"


def test_scheduler_is_its_own_profile():
    svc = _services(PROD)
    for name in ("worker", "celery_beat"):
        assert svc[name].get("profiles") == ["scheduler"], name
    for name in ("mcp_server", "frontend", "postgres", "redis", "nginx"):
        assert not svc[name].get("profiles"), f"{name} must start by default"


def test_nothing_in_the_default_boot_requires_the_scheduler():
    for name, svc in _services(PROD).items():
        if svc.get("profiles"):
            continue
        deps = svc.get("depends_on") or {}
        if isinstance(deps, dict):
            for dep, cond in deps.items():
                if dep in ("worker", "celery_beat"):
                    assert (cond or {}).get("required") is False, f"{name} depends on scheduler service {dep}"
        else:
            assert not {"worker", "celery_beat"} & set(deps), name


def test_no_named_volume_or_network_pins_a_global_name():
    """An explicit `name:` would make two projects share one database volume."""
    for path in (PROD, DEV):
        doc = yaml.safe_load(path.read_text())
        for section in ("volumes", "networks"):
            for key, val in (doc.get(section) or {}).items():
                assert not (val or {}).get("name"), f"{path.name} {section}.{key} pins a global name"


def test_dev_compose_has_its_own_project_and_no_legacy_schema_mount():
    doc = yaml.safe_load(DEV.read_text())
    assert doc.get("name") == "advisor_dev"
    for name, svc in _services(DEV).items():
        for vol in svc.get("volumes", []) or []:
            assert "init.sql" not in str(vol), f"{name} mounts the legacy init.sql; alembic owns the schema"


def test_dev_db_and_redis_listen_on_loopback_only():
    for name in ("postgres", "redis"):
        for port in _services(DEV)[name].get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name} publishes {port}"


def test_env_example_does_not_carry_the_production_identity():
    text = (REPO / ".env.example").read_text()
    assert re.search(r"(?m)^ADVISOR_PROJECT_NAME=advisor$", text)
    assert re.search(r"(?m)^ADVISOR_CONTAINER_PREFIX=advisor$", text)
    assert not re.search(r"(?m)^COMPOSE_PROJECT_NAME=", text)
