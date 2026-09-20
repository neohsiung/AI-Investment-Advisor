"""
Workflow editing API.

These endpoints let an operator rewrite the graph that decides trades, through a
browser. The tests below concentrate on the three ways that could go wrong:

  1. a YAML `ref` naming an arbitrary import would be remote code execution;
  2. saving a graph that does not load would surface as a missed portfolio review
     at the next scheduled run, not as an error the operator sees;
  3. a failed or partial write must not destroy the working document.

這些端點讓使用者透過瀏覽器改寫決定交易的流程圖，故測試集中在三個風險：
YAML 的 ref 若能指定任意匯入路徑即為遠端執行；存下無法載入的圖會在下次排程
才以「漏掉一次投組審查」的形式出現；寫入失敗不得破壞原本可用的文件。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.v1.router  # noqa: F401  — ensures the endpoint module is initialised
from src.api.v1.endpoints import workflows as ep

VALID = """
id: probe
version: 1
inputs: [portfolio]
nodes:
  - name: Filter
    type: code
    ref: filter_holdings
    inputs: [portfolio]
    outputs: [filtered_portfolio]
    ttl: 0
  - name: Decide
    type: agent
    agent: CIO
    tier: smart
    inputs: [filtered_portfolio]
    outputs: [report]
    ttl: 3600
"""


@pytest.fixture
def workspace(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("WORKFLOWS_DIR", d)
    monkeypatch.setenv("OWNER_ID", "test-owner")
    (Path(d) / "probe.yaml").write_text(VALID)
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def client(workspace):
    app = FastAPI()
    app.include_router(ep.router, prefix="/api/v1/workflows")
    return TestClient(app)


class TestRead:

    def test_list(self, client):
        body = client.get("/api/v1/workflows").json()
        assert [w["id"] for w in body] == ["probe"]
        assert body[0]["valid"] is True
        assert body[0]["node_count"] == 2

    def test_get_returns_yaml_and_derived_layers(self, client):
        body = client.get("/api/v1/workflows/probe").json()
        assert body["valid"] is True
        assert "filter_holdings" in body["yaml"]
        # Layers are derived from the key wiring, not declared.
        assert body["layers"] == [["Filter"], ["Decide"]]

    def test_missing_workflow_is_404(self, client):
        assert client.get("/api/v1/workflows/nope").status_code == 404

    def test_node_palette_lists_only_registered_functions(self, client):
        nodes = client.get("/api/v1/workflows/nodes").json()
        assert "filter_holdings" in nodes
        assert "os.system" not in nodes

    def test_a_broken_file_is_still_listed(self, client, workspace):
        """
        Otherwise it disappears from the UI and becomes unfixable through it.
        否則壞掉的檔案會從 UI 消失，反而無法用 UI 修復。
        """
        (workspace / "broken.yaml").write_text("nodes: []\n")
        body = {w["id"]: w for w in client.get("/api/v1/workflows").json()}
        assert "broken" in body
        assert body["broken"]["valid"] is False
        assert body["broken"]["error"]


class TestValidate:

    def test_accepts_a_good_document(self, client):
        r = client.post("/api/v1/workflows/validate", json={"yaml": VALID}).json()
        assert r["valid"] is True
        assert r["layers"] == [["Filter"], ["Decide"]]

    def test_rejects_malformed_yaml(self, client):
        r = client.post("/api/v1/workflows/validate", json={"yaml": "nodes: [oops"}).json()
        assert r["valid"] is False
        assert "invalid YAML" in r["error"]

    def test_rejects_a_cycle(self, client):
        cyclic = (
            "id: c\nnodes:\n"
            "  - {name: A, type: code, ref: filter_holdings, inputs: [b], outputs: [a]}\n"
            "  - {name: B, type: code, ref: reduce_holdings, inputs: [a], outputs: [b]}\n"
        )
        r = client.post("/api/v1/workflows/validate", json={"yaml": cyclic}).json()
        assert r["valid"] is False
        assert "cyclic" in r["error"].lower()

    @pytest.mark.parametrize("ref", ["os.system", "subprocess.run", "builtins.eval",
                                     "src.data.database.init_db"])
    def test_rejects_arbitrary_import_paths(self, client, ref):
        """
        The editor is a browser text box. If `ref` were an import path, this
        endpoint would be a code-execution primitive.
        編輯器是瀏覽器輸入框；若 ref 可為匯入路徑，此端點即為執行原語。
        """
        doc = (f"id: e\nnodes:\n  - {{name: A, type: code, ref: {ref}, "
               "inputs: [x], outputs: [y]}\n")
        r = client.post("/api/v1/workflows/validate", json={"yaml": doc}).json()
        assert r["valid"] is False
        assert "unknown code node" in r["error"]


class TestSave:

    def test_saves_a_valid_edit(self, client, workspace):
        edited = VALID.replace("tier: smart", "tier: advanced")
        assert client.put("/api/v1/workflows/probe", json={"yaml": edited}).status_code == 200
        assert "tier: advanced" in (workspace / "probe.yaml").read_text()

    def test_snapshots_the_previous_version(self, client, workspace):
        client.put("/api/v1/workflows/probe", json={"yaml": VALID.replace("smart", "advanced")})
        snapshots = client.get("/api/v1/workflows/probe/history").json()
        assert snapshots, "no undo point was written"
        assert (workspace / ".history" / snapshots[0]).exists()

    def test_refuses_an_invalid_document(self, client):
        bad = "id: p\nnodes:\n  - {name: A, type: code, ref: os.system, inputs: [x], outputs: [y]}\n"
        r = client.put("/api/v1/workflows/probe", json={"yaml": bad})
        assert r.status_code == 400

    def test_a_rejected_save_leaves_the_original_intact(self, client, workspace):
        """
        The working document must survive a bad edit — this graph runs scheduled
        portfolio reviews.
        壞掉的編輯不得破壞原本可用的文件；此圖負責排程的投組審查。
        """
        before = (workspace / "probe.yaml").read_text()
        client.put("/api/v1/workflows/probe",
                   json={"yaml": "id: p\nnodes: []\n"})
        assert (workspace / "probe.yaml").read_text() == before

    @pytest.mark.parametrize("bad_id", ["../escape", "a/b", "..", "with space", ""])
    def test_rejects_ids_that_could_escape_the_directory(self, client, bad_id):
        r = client.put(f"/api/v1/workflows/{bad_id}", json={"yaml": VALID})
        assert r.status_code in (400, 404, 405), f"{bad_id!r} was not rejected"

    def test_saved_edit_is_visible_immediately(self, client):
        """mtime-keyed caching must not serve the pre-edit graph back."""
        edited = VALID.replace("tier: smart", "tier: advanced")
        client.put("/api/v1/workflows/probe", json={"yaml": edited})
        assert "tier: advanced" in client.get("/api/v1/workflows/probe").json()["yaml"]
