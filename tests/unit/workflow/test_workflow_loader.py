"""
Declarative workflow loading.

The graphs used to be built by hand in portfolio_dag.py. The migration was
verified by fingerprinting every node the imperative builders produced against
the YAML-loaded graph (names, classes, input/output key sets, ttls, agent names,
tiers, temperature, max_tokens) plus the derived topological layers — all three
workflows matched exactly. Those builders are now gone, so these tests pin the
properties that matter going forward.

圖原本以手寫程式建構。遷移時已逐欄位比對舊建構器與 YAML 載入的結果（含推導層級），
三個 workflow 完全一致。原建構器已移除，故以下測試固定後續必須成立的性質。
"""
from __future__ import annotations

import pytest
import yaml

from src.infrastructure.workflow.loader import (
    WorkflowError,
    list_workflows,
    load_workflow,
    workflows_dir,
)
from src.infrastructure.workflow.nodes import list_nodes


class TestShippedWorkflows:

    def test_all_shipped_workflows_load(self):
        ids = list_workflows()
        assert ids, "no workflow files found"
        for wf_id in ids:
            load_workflow(wf_id, force=True)

    @pytest.mark.parametrize("wf_id,nodes,layers", [
        ("portfolio_council", 12, 8),
        ("single_ticker_council", 15, 6),
        ("opportunity_detection", 6, 4),
    ])
    def test_expected_shape(self, wf_id, nodes, layers):
        spec = load_workflow(wf_id, force=True)
        assert len(spec.nodes) == nodes
        assert len(spec.layers()) == layers

    def test_scouts_share_a_layer(self):
        """
        Nothing in the YAML says "run these in parallel" — the executor derives
        it from the three scouts having identical inputs. If that stops holding,
        the council silently serialises and gets slower for no visible reason.
        YAML 沒有宣告併行；executor 依相同輸入推導。若此性質失效，
        council 會靜默序列化而無明顯徵兆。
        """
        layers = load_workflow("portfolio_council", force=True).layers()
        scout_layer = next(l for l in layers if "MomentumScout" in l)
        assert {"MomentumScout", "FundamentalScout", "MacroScout"} <= set(scout_layer)

    def test_debate_roster_is_one_parallel_layer(self):
        layers = load_workflow("single_ticker_council", force=True).layers()
        first = layers[0]
        assert len(first) == 10, f"expected the ten-agent roster in one layer, got {first}"

    def test_risk_challenge_precedes_the_final_decision(self):
        """
        The adversarial ordering is the point of the chain: Risk must critique the
        draft BEFORE CIOFinal runs. A reordering here would quietly turn the
        review into a rubber stamp.
        對抗順序是此鏈的重點：Risk 必須在 CIOFinal 之前挑戰草案，
        順序錯了會讓審查退化為橡皮圖章。
        """
        for wf_id in ("portfolio_council", "single_ticker_council"):
            layers = load_workflow(wf_id, force=True).layers()
            flat = [n for layer in layers for n in layer]
            assert flat.index("RiskChallenge") < flat.index("CIOFinal"), wf_id
            assert flat.index("CIODraft") < flat.index("RiskChallenge"), wf_id

    def test_every_code_ref_is_registered(self):
        registered = set(list_nodes())
        for wf_id in list_workflows():
            for node in load_workflow(wf_id, force=True).nodes:
                if node.type == "code":
                    assert node.ref in registered, (
                        f"{wf_id}: node {node.name} references unregistered '{node.ref}'"
                    )

    def test_declared_inputs_are_not_produced_by_any_node(self):
        """
        A workflow's `inputs:` are supplied by the caller. If a node also produced
        one, the caller's value would be silently overwritten mid-run.
        workflow 的 inputs 由呼叫端提供；若某節點也產出同名鍵，
        呼叫端傳入的值會在執行中被靜默覆寫。
        """
        for wf_id in list_workflows():
            spec = load_workflow(wf_id, force=True)
            produced = {o for n in spec.nodes for o in n.outputs}
            overlap = set(spec.inputs) & produced
            assert not overlap, f"{wf_id}: declared inputs also produced by nodes: {overlap}"

    def test_no_dangling_inputs(self):
        """Every node input must be a declared workflow input or another node's output."""
        for wf_id in list_workflows():
            spec = load_workflow(wf_id, force=True)
            available = set(spec.inputs) | {o for n in spec.nodes for o in n.outputs}
            for node in spec.nodes:
                missing = set(node.inputs) - available
                assert not missing, f"{wf_id}: node {node.name} needs unproduced {missing}"


class TestLoaderRejectsBadInput:

    def _write(self, tmp_path, monkeypatch, body: dict, wf_id="probe"):
        monkeypatch.setenv("WORKFLOWS_DIR", str(tmp_path))
        (tmp_path / f"{wf_id}.yaml").write_text(yaml.safe_dump(body))
        return wf_id

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("WORKFLOWS_DIR", str(tmp_path))
        with pytest.raises(WorkflowError, match="not found"):
            load_workflow("nope", force=True)

    def test_empty_nodes(self, tmp_path, monkeypatch):
        wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": []})
        with pytest.raises(WorkflowError, match="non-empty list"):
            load_workflow(wf, force=True)

    def test_duplicate_node_name(self, tmp_path, monkeypatch):
        wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": [
            {"name": "A", "type": "code", "ref": "filter_holdings", "inputs": ["x"], "outputs": ["y"]},
            {"name": "A", "type": "code", "ref": "reduce_holdings", "inputs": ["y"], "outputs": ["z"]},
        ]})
        with pytest.raises(WorkflowError, match="duplicate node name"):
            load_workflow(wf, force=True)

    def test_unknown_field_is_rejected_not_ignored(self, tmp_path, monkeypatch):
        """
        A silently-dropped typo looks like a working edit while changing nothing —
        the operator sets `teir: smart` and the node keeps running on fast.
        靜默忽略打錯的欄位會讓編輯看起來生效，實際上什麼都沒變。
        """
        wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": [
            {"name": "A", "type": "agent", "agent": "CIO", "teir": "smart",
             "inputs": ["x"], "outputs": ["y"]},
        ]})
        with pytest.raises(WorkflowError, match="unknown field"):
            load_workflow(wf, force=True)

    def test_unknown_code_ref(self, tmp_path, monkeypatch):
        wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": [
            {"name": "A", "type": "code", "ref": "os.system", "inputs": ["x"], "outputs": ["y"]},
        ]})
        with pytest.raises(WorkflowError, match="unknown code node"):
            load_workflow(wf, force=True).build()

    def test_yaml_cannot_reference_an_arbitrary_import_path(self, tmp_path, monkeypatch):
        """
        Workflow files are UI-editable. If `ref` were resolved by importing a
        dotted path, that edit box would be a code-execution primitive.
        workflow 檔可從 UI 編輯；若 ref 以 dotted path 匯入，該輸入框即為執行原語。
        """
        for evil in ("os.system", "subprocess.run", "builtins.eval",
                     "src.data.database.init_db"):
            wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": [
                {"name": "A", "type": "code", "ref": evil, "inputs": ["x"], "outputs": ["y"]},
            ]}, wf_id="evil")
            with pytest.raises(WorkflowError):
                load_workflow(wf, force=True).build()

    def test_agent_node_requires_an_agent(self, tmp_path, monkeypatch):
        wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": [
            {"name": "A", "type": "agent", "inputs": ["x"], "outputs": ["y"]},
        ]})
        with pytest.raises(WorkflowError, match="requires `agent:`"):
            load_workflow(wf, force=True).build()

    def test_unknown_node_type(self, tmp_path, monkeypatch):
        wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": [
            {"name": "A", "type": "wizard", "inputs": ["x"], "outputs": ["y"]},
        ]})
        with pytest.raises(WorkflowError, match="unknown type"):
            load_workflow(wf, force=True).build()

    def test_duplicate_output_key_is_caught_by_the_executor(self, tmp_path, monkeypatch):
        """The engine already rejected this; loading must not bypass it."""
        wf = self._write(tmp_path, monkeypatch, {"id": "probe", "nodes": [
            {"name": "A", "type": "code", "ref": "filter_holdings", "inputs": ["portfolio"], "outputs": ["dup"]},
            {"name": "B", "type": "code", "ref": "reduce_holdings", "inputs": ["portfolio"], "outputs": ["dup"]},
        ]})
        with pytest.raises(ValueError, match="Duplicate output key"):
            load_workflow(wf, force=True).layers()


class TestHotReload:

    def test_editing_the_file_changes_the_graph_without_a_restart(self, tmp_path, monkeypatch):
        """
        The reason the graph moved into a file at all. mtime-keyed caching means a
        worker picks up an edit on its next load rather than needing a redeploy.
        這正是把圖移進檔案的目的：以 mtime 快取，worker 下次載入即生效，無須重新部署。
        """
        monkeypatch.setenv("WORKFLOWS_DIR", str(tmp_path))
        path = tmp_path / "probe.yaml"

        path.write_text(yaml.safe_dump({"id": "probe", "inputs": ["portfolio"], "nodes": [
            {"name": "A", "type": "agent", "agent": "CIO", "tier": "fast",
             "inputs": ["portfolio"], "outputs": ["out"]},
        ]}))
        assert load_workflow("probe").nodes[0].tier == "fast"

        import os
        import time
        time.sleep(0.01)
        path.write_text(yaml.safe_dump({"id": "probe", "inputs": ["portfolio"], "nodes": [
            {"name": "A", "type": "agent", "agent": "CIO", "tier": "smart",
             "inputs": ["portfolio"], "outputs": ["out"]},
        ]}))
        os.utime(path, (time.time() + 1, time.time() + 1))

        assert load_workflow("probe").nodes[0].tier == "smart", "edit not picked up"
