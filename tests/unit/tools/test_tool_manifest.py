"""
Tool manifest (M7-4) — one declaration, one surface.

What was here before:
  - `McpServer` on each agent: the only surface that worked.
  - `POST /tools/register`: wrote a name into the dict that gates
    `POST /tools/call/{name}`, but dispatch is a fixed if/elif chain. A registered
    name passed the gate, matched nothing, and returned HTTP 200
    {"status": "success", "result": "Tool implementation not found in dispatch
    logic."} — a success envelope carrying an error string.
  - `LlamaIndexTools.register()`: four RAG tools, zero callers, so no agent could
    reach them; `/tools/call` reimplemented the same four inline.
  - `external_mcp_servers`: a JSON blob in the settings table read by
    `conversation_agent` alone, so external tools reached one agent.

These tests hold the manifest as the single declaration, and hold the resolver
narrow — `func:`/`bundle:` name code to import, so they must not become a general
import primitive.

本檔驗證 manifest 是唯一宣告位置，且 dotted path 解析保持狹窄（不得成為任意匯入原語）。
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from src.tools import tool_manifest as tm
from src.tools.mcp_server import McpServer, McpTool

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "config" / "tools.yaml"


@pytest.fixture(autouse=True)
def _reset():
    tm.reset_cache()
    yield
    tm.reset_cache()


class _StubAgent:
    """Enough of an agent for registration: a name, a user, a real McpServer."""

    def __init__(self, name="TestAgent", user_id="u1"):
        self.name = name
        self.user_id = user_id
        self.toold = McpServer(name=f"{name}_Tools")

    def register_tool(self, tool):
        self.toold.register_tool(tool)

    def run_script(self, skill_name: str, args: list = None) -> str:
        return "ran"

    def _private_thing(self):
        return "nope"


def _write(tmp_path, body, monkeypatch):
    path = tmp_path / "tools.yaml"
    path.write_text(body)
    monkeypatch.setenv(tm.MANIFEST_ENV, str(path))
    tm.reset_cache()
    return path


class TestShippedManifest:

    def test_it_parses(self):
        data = yaml.safe_load(MANIFEST.read_text())
        assert data["version"] >= 1
        assert data["builtin"]

    def test_every_entry_declares_exactly_one_kind(self):
        for entry in yaml.safe_load(MANIFEST.read_text())["builtin"]:
            kinds = [k for k in ("method", "func", "bundle") if entry.get(k)]
            assert len(kinds) == 1, entry

    def test_run_script_is_declared_rather_than_hardcoded(self):
        """
        run_script spawns subprocesses. It was registered unconditionally for
        every agent with no way to withhold it; being in the manifest is what
        makes that reviewable and revocable.
        run_script 會啟動子行程，原本無條件註冊且無法收回。
        """
        names = [e["name"] for e in tm.builtin_entries()]
        assert "run_script" in names

    def test_the_orphaned_rag_bundle_is_now_wired_up(self):
        """`LlamaIndexTools.register()` had no callers anywhere in the repo."""
        bundles = [e["bundle"] for e in tm.builtin_entries() if e.get("bundle")]
        assert "src.tools.llama_index_tools.LlamaIndexTools" in bundles

    def test_external_mcp_ships_disabled(self):
        """Outbound tool calls must not start because a manifest shipped a URL."""
        assert tm.enabled_external_servers() == []

    def test_the_external_gate_key_exists_in_the_settings_schema(self):
        """An ungated feature flag that cannot be set is a flag that is never on."""
        schema = yaml.safe_load((REPO / "config" / "settings_schema.yaml").read_text())
        keys = {s["key"] for s in schema["settings"]}
        assert tm.external_mcp_config()["enabled_setting"] in keys


class TestResolverIsNarrow:

    @pytest.mark.parametrize("dotted", [
        "os.system",
        "builtins.eval",
        "builtins.__import__",
        "subprocess.run",
        "shutil.rmtree",
        "importlib.import_module",
    ])
    def test_code_outside_the_project_is_refused(self, dotted):
        with pytest.raises(tm.ToolManifestError):
            tm.resolve_callable(dotted)

    def test_a_class_is_not_accepted_as_a_func(self):
        with pytest.raises(tm.ToolManifestError):
            tm.resolve_callable("src.tools.mcp_server.McpServer")

    def test_a_non_callable_is_refused(self):
        with pytest.raises(tm.ToolManifestError):
            tm.resolve_callable("src.tools.tool_manifest.DEFAULT_MANIFEST")

    def test_private_attributes_are_refused(self):
        with pytest.raises(tm.ToolManifestError):
            tm.resolve_callable("src.tools.tool_manifest._import_attr")

    def test_a_bundle_must_expose_register(self):
        with pytest.raises(tm.ToolManifestError):
            tm.resolve_bundle("src.tools.mcp_server.McpTool")

    def test_a_valid_bundle_resolves(self):
        cls = tm.resolve_bundle("src.tools.llama_index_tools.LlamaIndexTools")
        assert callable(cls.register)

    def test_a_missing_attribute_is_an_error_not_none(self):
        with pytest.raises(tm.ToolManifestError):
            tm.resolve_callable("src.tools.tool_manifest.no_such_function")


class TestRegistration:

    def test_a_method_entry_binds_the_agents_own_method(self, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin:
  - name: run_script
    method: run_script
    category: system
""", monkeypatch)
        agent = _StubAgent()
        assert tm.register_builtin_tools(agent) == ["run_script"]
        tool = agent.toold.tools["run_script"]
        assert tool.category == "system"
        assert agent.toold.call_tool("run_script", {"skill_name": "x"}) == "ran"

    def test_a_private_method_is_refused(self, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin:
  - name: sneaky
    method: _private_thing
""", monkeypatch)
        agent = _StubAgent()
        assert tm.register_builtin_tools(agent) == []
        assert agent.toold.tools == {}

    def test_a_missing_method_is_skipped_not_fatal(self, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin:
  - name: ghost
    method: does_not_exist
  - name: run_script
    method: run_script
""", monkeypatch)
        agent = _StubAgent()
        assert tm.register_builtin_tools(agent) == ["run_script"]

    def test_disabled_entries_are_not_registered(self, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin:
  - name: run_script
    method: run_script
    enabled: false
""", monkeypatch)
        agent = _StubAgent()
        assert tm.register_builtin_tools(agent) == []

    def test_an_entry_can_be_scoped_to_named_agents(self, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin:
  - name: run_script
    method: run_script
    agents: [CIO]
""", monkeypatch)
        assert tm.register_builtin_tools(_StubAgent(name="CIO")) == ["run_script"]
        assert tm.register_builtin_tools(_StubAgent(name="Momentum")) == []

    def test_an_entry_declaring_two_kinds_is_skipped(self, tmp_path, monkeypatch):
        """Ambiguity on a path that imports code resolves to refusal, not a guess."""
        _write(tmp_path, """
version: 1
builtin:
  - name: confused
    method: run_script
    func: src.tools.tool_manifest.manifest_path
""", monkeypatch)
        assert tm.register_builtin_tools(_StubAgent()) == []

    def test_a_bundle_registers_all_of_its_tools(self, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin:
  - name: rag
    bundle: src.tools.llama_index_tools.LlamaIndexTools
""", monkeypatch)
        agent = _StubAgent()
        registered = tm.register_builtin_tools(agent)
        # The four tools that previously reached no agent at all.
        assert set(registered) == {
            "llama_search_reports", "llama_search_news",
            "llama_ingest_pdf", "llama_index_stats",
        }

    def test_a_missing_manifest_registers_nothing_and_says_so(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv(tm.MANIFEST_ENV, str(tmp_path / "absent.yaml"))
        tm.reset_cache()
        agent = _StubAgent()
        with caplog.at_level("ERROR"):
            assert tm.register_builtin_tools(agent) == []
        assert any("manifest missing" in r.message for r in caplog.records)

    def test_manifest_edits_apply_without_a_restart(self, tmp_path, monkeypatch):
        import os

        path = _write(tmp_path, """
version: 1
builtin:
  - name: run_script
    method: run_script
""", monkeypatch)
        assert tm.register_builtin_tools(_StubAgent()) == ["run_script"]

        path.write_text("version: 1\nbuiltin: []\n")
        stat = path.stat()
        os.utime(path, (stat.st_atime, stat.st_mtime + 10))
        assert tm.register_builtin_tools(_StubAgent()) == []


class TestExternalMcpIsDoublyGated:

    @pytest.fixture
    def agent(self):
        from src.agents.base_agent import BaseAgent

        stub = _StubAgent()
        # Borrow the real implementation without constructing a BaseAgent, which
        # needs a database-backed tier binding.
        # 借用真實實作，避免建構 BaseAgent（需要資料庫中的 tier binding）。
        stub.bind_external_mcp_tools = BaseAgent.bind_external_mcp_tools.__get__(stub)
        stub.logger = MagicMock()
        return stub

    @pytest.mark.asyncio
    async def test_no_servers_means_no_work(self, agent, tmp_path, monkeypatch):
        _write(tmp_path, "version: 1\nbuiltin: []\nexternal_mcp:\n  servers: []\n", monkeypatch)
        assert await agent.bind_external_mcp_tools(settings_service=None) == 0

    @pytest.mark.asyncio
    async def test_a_manifest_server_still_needs_the_settings_flag(self, agent, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin: []
external_mcp:
  enabled_setting: external_mcp_enabled
  servers:
    - url: http://127.0.0.1:9/sse
      enabled: true
""", monkeypatch)
        settings = MagicMock()
        settings.get_setting.return_value = False
        assert await agent.bind_external_mcp_tools(settings_service=settings) == 0

    @pytest.mark.asyncio
    async def test_a_server_disabled_in_the_manifest_is_not_reached(self, agent, tmp_path, monkeypatch):
        _write(tmp_path, """
version: 1
builtin: []
external_mcp:
  enabled_setting: external_mcp_enabled
  servers:
    - url: http://127.0.0.1:9/sse
      enabled: false
""", monkeypatch)
        settings = MagicMock()
        settings.get_setting.return_value = True
        assert await agent.bind_external_mcp_tools(settings_service=settings) == 0

    @pytest.mark.asyncio
    async def test_an_unreadable_gate_fails_closed(self, agent, tmp_path, monkeypatch):
        """
        If the flag cannot be read, the choice is between reaching out anyway and
        not reaching out. Sending agent arguments to a remote host on a failed
        read is the worse half.
        讀不到開關時不對外連線：在讀取失敗的情況下把 agent 參數送往遠端是更糟的一半。
        """
        _write(tmp_path, """
version: 1
builtin: []
external_mcp:
  enabled_setting: external_mcp_enabled
  servers:
    - url: http://127.0.0.1:9/sse
      enabled: true
""", monkeypatch)
        settings = MagicMock()
        settings.get_setting.side_effect = RuntimeError("db down")
        assert await agent.bind_external_mcp_tools(settings_service=settings) == 0

    @pytest.mark.asyncio
    async def test_remote_tools_are_namespaced_and_cannot_shadow_local_ones(
        self, agent, tmp_path, monkeypatch
    ):
        _write(tmp_path, """
version: 1
builtin: []
external_mcp:
  enabled_setting: external_mcp_enabled
  namespace_prefix: "ext_"
  servers:
    - url: http://127.0.0.1:9/sse
      enabled: true
""", monkeypatch)
        agent.toold.register_tool(McpTool(
            name="run_script", description="local", func=lambda: "local"
        ))

        remote = MagicMock()
        remote_tool = MagicMock()
        remote_tool.name = "run_script"          # deliberately collides
        remote_tool.description = "remote"
        remote.list_tools.return_value = [remote_tool]

        async def _get_client(url, user_id):
            return remote

        import src.tools.mcp_client_adapter as adapter
        monkeypatch.setattr(adapter, "get_mcp_client", _get_client, raising=False)

        settings = MagicMock()
        settings.get_setting.return_value = True
        assert await agent.bind_external_mcp_tools(settings_service=settings) == 1

        assert agent.toold.tools["run_script"].description == "local"
        assert agent.toold.tools["ext_run_script"].description.startswith("[External]")

    @pytest.mark.asyncio
    async def test_an_unreachable_server_does_not_cost_the_local_tools(
        self, agent, tmp_path, monkeypatch
    ):
        _write(tmp_path, """
version: 1
builtin: []
external_mcp:
  enabled_setting: external_mcp_enabled
  servers:
    - url: http://127.0.0.1:9/sse
      enabled: true
""", monkeypatch)
        agent.toold.register_tool(McpTool(name="local", description="", func=lambda: 1))

        async def _boom(url, user_id):
            raise ConnectionError("refused")

        import src.tools.mcp_client_adapter as adapter
        monkeypatch.setattr(adapter, "get_mcp_client", _boom, raising=False)

        settings = MagicMock()
        settings.get_setting.return_value = True
        assert await agent.bind_external_mcp_tools(settings_service=settings) == 0
        assert "local" in agent.toold.tools


class TestHttpSurfaceNoLongerRegisters:

    def test_the_register_endpoint_is_gone_from_the_app(self):
        source = (REPO / "services" / "mcp_server" / "src" / "app" / "__init__.py").read_text()
        code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
        assert '@app.post("/tools/register")' not in code

    def test_unhandled_dispatch_raises_instead_of_reporting_success(self):
        source = (REPO / "services" / "mcp_server" / "src" / "app" / "__init__.py").read_text()
        code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
        assert "Tool implementation not found in dispatch logic." not in code
        assert "status_code=501" in code
