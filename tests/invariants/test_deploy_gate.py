"""start.sh must run the pre-deploy gate before building or restarting production containers.
start.sh 在建置或重啟正式容器前必須先跑部署前閘門。"""
import re

from tests.invariants.helpers import REPO


def _body(src: str, func: str) -> str:
    m = re.search(rf"function {func} \{{(.*?)\n\}}\n", src, re.S)
    assert m, f"{func} not found in start.sh"
    return m.group(1)


def test_up_and_upgrade_run_gate_before_build():
    src = (REPO / "start.sh").read_text(encoding="utf-8")
    for func in ("cmd_up", "cmd_upgrade"):
        body = _body(src, func)
        assert "run_predeploy_gate" in body, f"{func} must call run_predeploy_gate"
        assert body.index("run_predeploy_gate") < body.index("$PROD_COMPOSE build"), \
            f"{func}: gate must run before the image build"


def test_gate_script_checks_everything_and_audits_overrides():
    s = (REPO / "scripts" / "predeploy_gate.sh").read_text(encoding="utf-8")
    for needle in ("git diff --quiet", "origin/main", "yaml.safe_load", "alembic", "tests/invariants",
                   "tests/unit/config", "FORCE_DEPLOY", "deploy_audit.log"):
        assert needle in s, f"predeploy_gate.sh missing: {needle}"
