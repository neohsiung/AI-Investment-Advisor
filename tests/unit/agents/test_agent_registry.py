"""
Agent registry and manifest-driven construction.

The population of agents was hardcoded three times — the factory's if/elif chain,
BaseAgent's `workspace_map`, and `LLMAgentOverrideService.KNOWN_AGENT_NAMES` — so
adding one meant four coordinated edits and two of the three lists silently
disagreed about who existed.

The tests below also pin a bug this milestone introduced and fixed: the generated
manifests initially carried an explanatory note in their Markdown BODY, and since
the body IS the system prompt, every agent's real workspace identity was shadowed
by that note. A manifest body must be empty unless it is deliberately overriding.

代理清單原本硬編在三處，新增一個要改四個地方，且其中兩份清單對「誰存在」意見不一。
以下也固定本次修掉的一個缺陷：manifest 的 Markdown 本文即系統提示詞，
最初產生的檔案在本文放了說明文字，導致每個代理真正的 workspace 身分被遮蔽。
"""
from __future__ import annotations

import pytest

from src.agents.registry import (
    AgentRegistryError,
    build,
    get_manifest,
    known_agent_names,
    list_impls,
    load_manifests,
)


class TestManifests:

    def test_manifests_load(self):
        manifests = load_manifests(force=True)
        assert manifests, "no agent manifests found in config/agents/"

    def test_every_manifest_names_a_registered_impl(self):
        impls = set(list_impls())
        bad = {m.id: m.impl for m in load_manifests(force=True).values() if m.impl not in impls}
        assert not bad, f"manifests naming unregistered impls: {bad}"

    def test_manifest_bodies_are_empty_unless_overriding(self):
        """
        The body is the system prompt. A non-empty body SHADOWS the agent's
        workspace/<dir>/IDENTITY.md — which is exactly what happened when the
        manifests were generated with an explanatory note in the body, silently
        replacing all 14 agents' real instructions with documentation text.

        A deliberate override is legitimate; this test exists so it can only ever
        be deliberate.

        本文即系統提示詞，非空的本文會遮蔽 workspace 的 IDENTITY.md——
        產生 manifest 時把說明文字放進本文，就把 14 個代理的真正指令換成了文件。
        """
        offenders = {}
        for m in load_manifests(force=True).values():
            body = m.prompt.strip()
            if not body:
                continue
            # A real override should look like instructions, not like guidance
            # about the file format.
            if "intentionally" in body.lower() or "resolution order" in body.lower():
                offenders[m.id] = body[:60]
        assert not offenders, (
            "these manifest bodies look like documentation, not prompts, and will "
            f"be served AS the system prompt: {offenders}"
        )

    def test_lookup_accepts_id_display_name_and_case_variants(self):
        """
        Callers address agents inconsistently: workflow YAML says "Momentum Scout",
        council_service says "CIO", older code says "momentum".
        呼叫端的稱呼並不一致，三種形式都必須可解析。
        """
        assert get_manifest("cio") is not None
        assert get_manifest("CIO") is not None
        assert get_manifest("Momentum Scout") is not None
        assert get_manifest("momentum_scout") is not None

    def test_unknown_agent_returns_none(self):
        assert get_manifest("definitely-not-an-agent") is None


class TestConstruction:

    def test_unknown_agent_raises_and_names_the_alternatives(self):
        """
        The old chain raised a bare "Unknown agent type", leaving the operator to
        guess what was valid.
        舊的 if/elif 只拋出 "Unknown agent type"，使用者無從得知有哪些有效值。
        """
        with pytest.raises(AgentRegistryError) as exc:
            build("nope")
        assert "cio" in str(exc.value)

    def test_disabled_agent_refuses_to_build(self, tmp_path, monkeypatch):
        from src.utils.frontmatter import dump

        monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
        (tmp_path / "off.md").write_text(
            dump({"id": "off", "impl": "cio", "enabled": False}, "")
        )
        load_manifests(force=True)
        with pytest.raises(AgentRegistryError, match="disabled"):
            build("off")
        load_manifests(force=True)

    def test_manifest_cannot_name_an_arbitrary_import_path(self, tmp_path, monkeypatch):
        """
        Manifests are editable from the UI. `impl:` resolves through the registry
        only — never by importing a dotted path.
        manifest 可從 UI 編輯；impl 只能經註冊表解析，不得以 dotted path 匯入。
        """
        from src.utils.frontmatter import dump

        monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
        for evil in ("os.system", "subprocess.run", "src.data.database.init_db"):
            (tmp_path / "evil.md").write_text(dump({"id": "evil", "impl": evil}, ""))
            load_manifests(force=True)
            with pytest.raises(AgentRegistryError, match="unknown impl"):
                build("evil")
        load_manifests(force=True)

    def test_a_broken_manifest_does_not_remove_working_agents(self, tmp_path, monkeypatch):
        from src.utils.frontmatter import dump

        monkeypatch.setenv("AGENTS_DIR", str(tmp_path))
        (tmp_path / "good.md").write_text(dump({"id": "good", "impl": "cio"}, ""))
        (tmp_path / "broken.md").write_text("---\nunclosed: true\n")
        manifests = load_manifests(force=True)
        assert "good" in manifests
        assert "broken" not in manifests
        load_manifests(force=True)


class TestSingleSourceOfTruth:

    def test_known_agent_names_derives_from_manifests(self):
        """
        Was a hardcoded list of eleven strings, so a newly declared agent could not
        be given a per-agent model override until someone remembered to append to
        it — the override was rejected as an unknown agent.
        原為十一個字串的硬編清單：新增代理後無法設定模型覆寫，直到有人記得補清單。
        """
        from src.services.llm_agent_override_service import known_agent_names as svc_names

        declared = {m.id for m in load_manifests(force=True).values() if m.enabled}
        reported = set(svc_names())
        assert declared <= reported, f"declared but not offered: {declared - reported}"
        # skill_router takes overrides but is not an agent manifest.
        assert "skill_router" in reported

    def test_registry_known_names_uses_display_names(self):
        names = known_agent_names()
        assert "CIO" in names
        assert "Momentum Scout" in names

    def test_workspace_comes_from_the_manifest_not_a_hardcoded_map(self):
        """
        The agent -> workspace-directory mapping existed FOUR times: BaseAgent,
        the factory's if/elif chain, KNOWN_AGENT_NAMES, and
        MemoryRepository.get_state_path. Four copies means renaming a directory in
        three of them makes that agent write its STATE.md somewhere nothing reads
        — a silent loss of the agent's own memory.
        該對照表原本存在四份；只改三份會讓某個代理把 STATE.md 寫到沒人讀的位置。
        """
        from pathlib import Path

        for path in ("src/agents/base_agent.py", "src/repositories/memory_repository.py"):
            assert "workspace_map = {" not in Path(path).read_text(), (
                f"a hardcoded workspace map is back in {path}"
            )
        assert get_manifest("CIO").workspace == "captain"

    def test_state_path_and_prompt_path_agree_on_the_directory(self):
        """
        BaseAgent reads prompts from workspace/<dir>/ and MemoryRepository writes
        STATE.md into workspace/<dir>/. If those disagreed, an agent would read its
        identity from one directory and persist its memory into another.
        提示詞讀取與 STATE.md 寫入必須指向同一個目錄，否則代理會從一處讀身分、
        往另一處寫記憶。
        """
        import inspect

        from src.repositories import memory_repository as mr

        cls = next(
            c for _, c in inspect.getmembers(mr, inspect.isclass)
            if hasattr(c, "get_state_path")
        )
        repo = cls()
        manifest = get_manifest("CIO")
        assert repo.get_state_path("CIO") == f"workspace/{manifest.workspace}/STATE.md"
