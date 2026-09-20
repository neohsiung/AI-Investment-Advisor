"""
Portfolio workflow definitions — now declarative.

This module was 620 lines: six node functions plus three classes whose
`_build_nodes()` methods constructed ~40 `CodeNode`/`AgentNode` objects by hand.
Both halves moved:

  * the node functions      -> src/infrastructure/workflow/nodes/portfolio.py
                               (each published via @register_node)
  * the graph wiring        -> config/workflows/*.yaml
                               (loaded by src/infrastructure/workflow/loader.py)

What remains here are three thin shims. They keep the class names and the
`.nodes` / `._build_nodes()` surface that council_service.py and
tests/unit/workflow/test_dag_nodes.py already use, so nothing downstream changed.

The migration was verified by fingerprinting every node produced by the old
imperative builders against the YAML-loaded graph — node names, classes, input
and output key sets, ttls, agent names, tiers, temperature and max_tokens all
matched exactly for all three workflows, as did the resulting topological layers.

本模組原有 620 行：六個節點函式與三個手動建出 ~40 個節點物件的類別。
函式移至 nodes/portfolio.py（以 @register_node 發布），接線移至 config/workflows/*.yaml。
此處僅保留三個薄殼，維持既有的類別名稱與 .nodes/_build_nodes() 介面。
遷移已逐欄位比對（名稱、類別、輸入輸出鍵、ttl、agent、tier、溫度、max_tokens）
與推導出的拓撲層級，三個 workflow 全部完全一致。
"""
from __future__ import annotations

import logging
from typing import Any, List

from src.infrastructure.workflow.base import BaseNode
from src.infrastructure.workflow.loader import build_nodes

# Re-exported for backwards compatibility: these used to be defined here, and
# tests/unit/workflow/test_dag_nodes.py imports reduce_debate_stances from this
# module. The implementations live in nodes/portfolio.py.
# 為相容而重新匯出：既有測試從本模組 import reduce_debate_stances。
from src.infrastructure.workflow.nodes.portfolio import (  # noqa: F401
    fetch_market_data,
    filter_holdings,
    reduce_debate_stances,
    reduce_holdings,
    reduce_scouts,
    run_ticker_map_analysis,
)

logger = logging.getLogger(__name__)


class _YamlDAG:
    """Common shim: load a workflow file and expose it as `.nodes`."""

    WORKFLOW_ID: str = ""

    def __init__(self, cache: Any = None):
        self.cache = cache
        self.nodes = self._build_nodes()

    def _build_nodes(self) -> List[BaseNode]:
        return build_nodes(self.WORKFLOW_ID)


class PortfolioAnalysisDAG(_YamlDAG):
    """
    Full portfolio review: scouts, per-ticker map/reduce, CIO draft, risk
    challenge, final decision, verifier.

    Defined in config/workflows/portfolio_council.yaml.

    Initial inputs expected::

        portfolio          — list[dict] of {symbol, quantity}
        topic              — analysis topic string
    """

    WORKFLOW_ID = "portfolio_council"


class SingleTickerAnalysisDAG(_YamlDAG):
    """
    Single-topic council debate: ten agents in parallel, then the adversarial
    CIO Draft -> Risk Challenge -> CIO Final -> Verifier chain.

    Defined in config/workflows/single_ticker_council.yaml. The ten-agent roster
    that was `AGENT_ROSTER` here is now the first layer of that file.

    Initial inputs expected::

        topic              — debate topic string
        debate_context     — enriched context dict (market_data, past_wisdom, …)
        market_data        — raw market data dict for verifier grounding
    """

    WORKFLOW_ID = "single_ticker_council"

    # Kept because tests and callers read it to know who debates. Derived from
    # the workflow file rather than duplicated, so the two cannot disagree.
    # 保留此屬性供測試與呼叫端使用，但改由 workflow 檔推導，避免兩處不一致。
    @property
    def AGENT_ROSTER(self) -> List[tuple]:  # noqa: N802 (existing public name)
        return [
            (n.agent_name, n.output_keys[0])
            for n in self.nodes
            if hasattr(n, "agent_name") and n.name.startswith("Debate_")
        ]


class OpportunityDetectionDAG(_YamlDAG):
    """
    Scout-only pipeline for surfacing new buy-side candidates without paying for
    the full CIO debate. Its `scout_summary` output feeds the notification path.

    Defined in config/workflows/opportunity_detection.yaml.

    Initial inputs expected::

        portfolio          — list[dict] of {symbol, quantity}
    """

    WORKFLOW_ID = "opportunity_detection"
