"""
Build DAG node lists from declarative workflow files.

The executor already did the hard part. `DAGExecutor._build_dependency_layers`
resolves the graph purely from each node's `input_keys`/`output_keys` using
Kahn's algorithm, and already rejects duplicate output keys and cycles. What was
missing was never an engine — only a way to express the node list as data instead
of as Python.

So this module is deliberately thin: parse YAML, validate, construct the same
`AgentNode`/`CodeNode` objects the imperative builders constructed. Every field
maps 1:1 onto their existing constructors, so no engine behaviour changes.

Safety: `type: code` resolves `ref` through the node registry
(src/infrastructure/workflow/nodes), never by importing a dotted path. Workflow
files are UI-editable, and an arbitrary import would make that a code-execution
surface.

執行引擎本來就會從 input_keys/output_keys 解出相依（Kahn 演算法），也已會拒絕
重複輸出鍵與環。缺的從來不是引擎，而是「把節點清單寫成資料」的方式。
本模組因此刻意很薄：解析 YAML、驗證、建出與原本命令式程式碼相同的節點物件。
`type: code` 只能透過註冊表解析，不允許任意 import 路徑。
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.infrastructure.workflow.base import AgentNode, BaseNode, CodeNode
from src.infrastructure.workflow.nodes import get_node

logger = logging.getLogger(__name__)

_DIR_ENV = "WORKFLOWS_DIR"
_DEFAULT_DIR = "config/workflows"

_lock = threading.Lock()
_cache: Dict[str, tuple] = {}   # id -> (mtime, WorkflowSpec)


class WorkflowError(ValueError):
    """A workflow file is malformed or references something unknown."""


@dataclass
class NodeSpec:
    name: str
    type: str                       # "agent" | "code"
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    ttl: int = 3600
    # agent
    agent: Optional[str] = None
    tier: str = "fast"
    temperature: float = 0.7
    max_tokens: int = 2000
    # code
    ref: Optional[str] = None

    def build(self) -> BaseNode:
        if self.type == "agent":
            if not self.agent:
                raise WorkflowError(f"node '{self.name}': type 'agent' requires `agent:`")
            return AgentNode(
                name=self.name,
                agent_name=self.agent,
                input_keys=list(self.inputs),
                output_keys=list(self.outputs),
                tier=self.tier,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                ttl=self.ttl,
            )

        if self.type == "code":
            if not self.ref:
                raise WorkflowError(f"node '{self.name}': type 'code' requires `ref:`")
            try:
                func = get_node(self.ref)
            except KeyError as exc:
                raise WorkflowError(f"node '{self.name}': {exc}") from exc
            return CodeNode(
                name=self.name,
                func=func,
                input_keys=list(self.inputs),
                output_keys=list(self.outputs),
                ttl=self.ttl,
            )

        raise WorkflowError(
            f"node '{self.name}': unknown type {self.type!r} (expected 'agent' or 'code')"
        )


@dataclass
class WorkflowSpec:
    id: str
    version: int = 1
    description: str = ""
    inputs: List[str] = field(default_factory=list)
    nodes: List[NodeSpec] = field(default_factory=list)

    def build(self) -> List[BaseNode]:
        return [n.build() for n in self.nodes]

    def layers(self) -> List[List[str]]:
        """
        Topological layers, as node names. Uses the real executor so what the UI
        shows is what will actually run — a second implementation here would be
        free to disagree with the engine.
        用真正的 executor 計算層級，避免 UI 顯示與實際執行不一致。
        """
        from src.infrastructure.workflow.executor import DAGExecutor

        executor = DAGExecutor(self.build())
        return [[n.name for n in layer] for layer in executor.layers]


def workflows_dir() -> Path:
    explicit = os.getenv(_DIR_ENV)
    if explicit:
        return Path(explicit)
    return Path(__file__).resolve().parents[3] / _DEFAULT_DIR


def _parse(raw: Dict[str, Any], wf_id: str) -> WorkflowSpec:
    if not isinstance(raw, dict):
        raise WorkflowError(f"{wf_id}: file must contain a mapping")

    nodes_raw = raw.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise WorkflowError(f"{wf_id}: `nodes:` must be a non-empty list")

    seen: set = set()
    nodes: List[NodeSpec] = []
    for entry in nodes_raw:
        if not isinstance(entry, dict):
            raise WorkflowError(f"{wf_id}: each node must be a mapping, got {type(entry).__name__}")
        name = entry.get("name")
        if not name:
            raise WorkflowError(f"{wf_id}: every node needs a `name:`")
        if name in seen:
            raise WorkflowError(f"{wf_id}: duplicate node name {name!r}")
        seen.add(name)

        unknown = set(entry) - {
            "name", "type", "inputs", "outputs", "ttl",
            "agent", "tier", "temperature", "max_tokens", "ref",
        }
        if unknown:
            # Rejected rather than ignored: a typo'd key that is silently dropped
            # looks like a working edit while changing nothing.
            # 未知欄位一律拒絕：靜默忽略會讓打錯的編輯看起來生效。
            raise WorkflowError(f"{wf_id}: node {name!r} has unknown field(s): {sorted(unknown)}")

        nodes.append(NodeSpec(
            name=name,
            type=entry.get("type", "agent"),
            inputs=list(entry.get("inputs") or []),
            outputs=list(entry.get("outputs") or []),
            ttl=int(entry.get("ttl", 3600)),
            agent=entry.get("agent"),
            tier=entry.get("tier", "fast"),
            temperature=float(entry.get("temperature", 0.7)),
            max_tokens=int(entry.get("max_tokens", 2000)),
            ref=entry.get("ref"),
        ))

    return WorkflowSpec(
        id=raw.get("id", wf_id),
        version=int(raw.get("version", 1)),
        description=raw.get("description", ""),
        inputs=list(raw.get("inputs") or []),
        nodes=nodes,
    )


def load_workflow(wf_id: str, force: bool = False) -> WorkflowSpec:
    """
    Parse one workflow, cached on the file's mtime.

    mtime-keyed so editing a workflow takes effect without restarting the
    workers — the point of moving the graph into a file.
    以 mtime 快取：編輯後無須重啟 worker 即生效。
    """
    safe_name = os.path.basename(wf_id.strip())
    if not safe_name or safe_name != wf_id or not re.match(r"^[a-zA-Z0-9_-]+$", safe_name):
        raise WorkflowError(f"invalid workflow id: {wf_id!r}")

    base_dir = workflows_dir().resolve()
    path = (base_dir / f"{safe_name}.yaml").resolve()
    if not path.is_relative_to(base_dir) or not path.exists():
        raise WorkflowError(f"workflow {wf_id!r} not found at {path}")

    mtime = path.stat().st_mtime
    with _lock:
        cached = _cache.get(wf_id)
        if cached and not force and cached[0] == mtime:
            return cached[1]

        import yaml

        with path.open() as fh:
            raw = yaml.safe_load(fh) or {}
        spec = _parse(raw, wf_id)
        _cache[wf_id] = (mtime, spec)
        logger.info("workflow %s loaded: %d nodes (v%d)", wf_id, len(spec.nodes), spec.version)
        return spec


def list_workflows() -> List[str]:
    d = workflows_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def build_nodes(wf_id: str) -> List[BaseNode]:
    """The one call the DAG classes need."""
    return load_workflow(wf_id).build()
