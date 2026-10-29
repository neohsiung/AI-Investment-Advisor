"""CI must install the versions pinned in uv.lock, not whatever pyproject.toml resolves to that day.
CI 必須安裝 uv.lock 鎖定的版本，不能每天依 pyproject.toml 重新解析。

Why: pyproject.toml has open-ended bounds (e.g. pytest>=9.0.3). On 2026-10-28 CI resolved pytest 9.2.0, which
breaks pytest-asyncio==0.21.1, while uv.lock still pinned the working 9.0.3.
"""
import re

from tests.invariants.helpers import REPO

WORKFLOW = REPO / ".github" / "workflows" / "ci-cd.yml"


def _install_step(src: str) -> str:
    m = re.search(r"- name: Install dependencies\n(.*?)(?=\n      - name:)", src, re.S)
    assert m, "ci-cd.yml has no 'Install dependencies' step"
    return m.group(1)


def test_ci_install_reads_the_lockfile():
    step = _install_step(WORKFLOW.read_text(encoding="utf-8"))
    # --locked (as in the prod Dockerfile) also fails when uv.lock is stale vs pyproject.toml; --frozen would not.
    # --locked（與正式 Dockerfile 一致）在 lock 過期時會失敗，--frozen 不會。
    assert "uv export --locked" in step, "CI must export requirements from uv.lock (uv export --locked)"


def test_every_ci_install_reads_the_exported_requirements():
    step = _install_step(WORKFLOW.read_text(encoding="utf-8"))
    installs = [line for line in step.splitlines() if re.search(r"\buv pip install\b", line)]
    assert installs, "no 'uv pip install' line found in the install step"
    for line in installs:
        assert "-r ci-requirements.txt" in line, f"install must read the exported lock requirements: {line.strip()}"
