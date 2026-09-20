"""
uv.lock must stay in sync with pyproject.toml.

The lock drifted silently for two milestones: the Dockerfile installed with
`uv pip install -r pyproject.toml`, which ignores the lockfile entirely, so
nothing ever read it and nothing noticed it was missing `pydantic-settings`.
The cost showed up as a 40-minute image build that re-resolved ~50 direct
dependencies against PyPI on every run and was eventually killed by its own
timeout.

The Dockerfile now installs from an `uv export --locked` and therefore FAILS on a
stale lock. This test gives the same signal without waiting for a build.

uv.lock 曾靜默漂移兩個里程碑：Dockerfile 用 -r pyproject.toml 安裝，完全不讀 lock，
因此沒人發現它缺少 pydantic-settings。代價是每次建置都向 PyPI 重新解析約 50 個
直接相依，最後被自己的 timeout 殺掉。現在 Dockerfile 從 --locked 匯出安裝，
lock 一旦過期就會讓建置失敗；本測試提供同樣的訊號，但不必等一次建置。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

UV = shutil.which("uv")
pytestmark = pytest.mark.skipif(UV is None, reason="uv is not installed")


def test_lock_is_in_sync_with_pyproject():
    """
    `uv lock --check` fails when the lock would change. This is the check the
    build performs, run here so it is caught in seconds rather than in a
    multi-minute image build.
    這是建置會做的檢查，提前在幾秒內執行而不必等數分鐘的映像建置。
    """
    result = subprocess.run(
        [UV, "lock", "--check"], capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        "uv.lock is out of sync with pyproject.toml — run `uv lock`.\n"
        f"{result.stderr.strip()}"
    )


def test_dockerfile_installs_from_the_lock():
    """
    Guard the mechanism itself. Reverting to `-r pyproject.toml` would restore
    non-reproducible builds AND make the sync test above meaningless, because
    nothing would read the lock again.
    守住機制本身：改回 -r pyproject.toml 會同時恢復不可重現的建置，
    並讓上面那個同步測試失去意義（因為又沒人讀 lock 了）。
    """
    raw = Path("services/mcp_server/Dockerfile").read_text()
    assert "uv export --locked" in raw, (
        "the image no longer installs from uv.lock; builds are non-reproducible"
    )

    # Strip comments before matching: the Dockerfile DOCUMENTS the old
    # lock-ignoring command in a comment explaining why it was replaced, and a
    # naive search finds that prose instead of a real instruction.
    # 先去掉註解再比對：Dockerfile 的註解中引用了舊指令以說明替換原因，
    # 直接搜尋會命中說明文字而非真正的指令。
    instructions = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("#")
    )
    assert not re.search(r"uv pip install[^\n]*-r pyproject\.toml", instructions), (
        "found `uv pip install -r pyproject.toml`, which ignores uv.lock"
    )


def test_every_declared_extra_is_resolvable():
    """
    Each optional group must export cleanly. An extra that cannot resolve would
    only be discovered by someone trying to install it — likely in a build.
    每個 extra 都必須能順利匯出；無法解析的 extra 只會在有人嘗試安裝時才發現。
    """
    # tomllib is 3.11+; requires-python allows 3.10, so parse the section by hand
    # rather than making this test silently skip on the lower bound.
    # tomllib 需 3.11+，而本專案支援 3.10，故手動解析以免測試在下界靜默跳過。
    text = Path("pyproject.toml").read_text()
    block = text.split("[project.optional-dependencies]", 1)[1]
    block = block.split("\n[", 1)[0]
    extras = re.findall(r"^([a-z][a-z0-9-]*)\s*=", block, flags=re.M)
    assert extras, "no optional-dependency groups found"

    for extra in extras:
        result = subprocess.run(
            [UV, "export", "--locked", "--no-emit-project", "--no-hashes",
             "--extra", extra],
            capture_output=True, text=True, timeout=300, cwd=".",
        )
        assert result.returncode == 0, f"extra '{extra}' does not resolve:\n{result.stderr.strip()}"


def test_removed_dependencies_are_not_declared_directly():
    """
    Packages deleted in the M3 audit (each verified to have zero importers) must
    not return as DIRECT dependencies.

    Deliberately not asserting absence from uv.lock: `litellm` is still in there
    as a transitive dependency of `dspy`, which is correct and not something this
    project controls. Asserting on the whole graph would fail for a reason that
    has nothing to do with the decision being guarded.

    刻意不斷言「不在 uv.lock 中」：litellm 仍以 dspy 的間接相依存在，
    這是正確的、也非本專案可控。對整個相依圖斷言會因無關原因而失敗。
    """
    pyproject = Path("pyproject.toml").read_text()
    for gone in ("stripe", "gradio", "pygithub", "tornado", "ib-insync", "litellm",
                 "authlib", "itsdangerous"):
        assert not re.search(rf'^\s*"{re.escape(gone)}[=<>~\[]', pyproject, flags=re.M), (
            f"{gone} is declared as a direct dependency again"
        )
