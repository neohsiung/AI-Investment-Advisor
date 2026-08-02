"""
Tests for SingleTickerAnalysisDAG, OpportunityDetectionDAG, and reduce_debate_stances.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.infrastructure.workflow.base import AgentNode, CodeNode
from src.infrastructure.workflow.executor import DAGExecutor
from src.infrastructure.workflow.portfolio_dag import (
    SingleTickerAnalysisDAG,
    OpportunityDetectionDAG,
    reduce_debate_stances,
)


# ──────────────────────────────────────────────────────────────────────
# reduce_debate_stances (CodeNode helper)
# ──────────────────────────────────────────────────────────────────────

class TestReduceDebateStances:
    def test_basic_aggregation(self):
        result = reduce_debate_stances(
            macro_stance="Bearish on rates",
            momentum_stance="Bullish breakout",
            fundamental_stance="Fair value",
        )
        transcript = result["council_transcript"]
        assert "[Fundamental]: Fair value" in transcript
        assert "[Macro]: Bearish on rates" in transcript
        assert "[Momentum]: Bullish breakout" in transcript

    def test_sorted_order(self):
        result = reduce_debate_stances(
            z_stance="Last",
            a_stance="First",
        )
        lines = result["council_transcript"].strip().split("\n")
        assert lines[0].startswith("[A]:")
        assert lines[1].startswith("[Z]:")

    def test_ignores_non_stance_keys(self):
        result = reduce_debate_stances(
            macro_stance="View",
            random_data="should be ignored",
        )
        assert "random_data" not in result["council_transcript"]
        assert "[Macro]: View" in result["council_transcript"]

    def test_empty_input(self):
        result = reduce_debate_stances()
        assert result["council_transcript"] == ""


# ──────────────────────────────────────────────────────────────────────
# SingleTickerAnalysisDAG Topology Tests
# ──────────────────────────────────────────────────────────────────────

class TestSingleTickerAnalysisDAG:
    def test_node_count(self):
        dag = SingleTickerAnalysisDAG()
        # 10 debate agents + ReduceDebateStances + CIODraft + RiskChallenge + CIOFinal + VerifierCheck = 15
        assert len(dag.nodes) == 15

    def test_all_nodes_have_single_output_key(self):
        dag = SingleTickerAnalysisDAG()
        for node in dag.nodes:
            assert len(node.output_keys) == 1, f"Node {node.name} has {len(node.output_keys)} output keys"

    def test_topological_sort_layers(self):
        dag = SingleTickerAnalysisDAG()
        executor = DAGExecutor(dag.nodes)
        # Layer 0: 10 debate agents (all depend on debate_context which is initial input)
        # Layer 1: ReduceDebateStances (depends on 10 stance outputs)
        # Layer 2: CIODraft (depends on council_transcript + topic + market_data)
        # Layer 3: RiskChallenge (depends on draft_report)
        # Layer 4: CIOFinal (depends on risk_challenge + draft_report)
        # Layer 5: VerifierCheck (depends on final_report)
        assert len(executor.layers) == 6
        assert len(executor.layers[0]) == 10  # All debate agents parallel

    def test_layer_0_all_agent_nodes(self):
        dag = SingleTickerAnalysisDAG()
        executor = DAGExecutor(dag.nodes)
        for node in executor.layers[0]:
            assert isinstance(node, AgentNode)
            assert node.tier == "fast"

    def test_cio_nodes_use_smart_tier(self):
        dag = SingleTickerAnalysisDAG()
        cio_nodes = [n for n in dag.nodes if n.name in ("CIODraft", "CIOFinal")]
        assert len(cio_nodes) == 2
        for n in cio_nodes:
            assert n.tier == "smart"

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute", new_callable=AsyncMock)
    @patch("src.infrastructure.llm.llm_config_chain.build_config_chain")
    @patch("src.utils.prompt_utils.load_agent_prompt")
    async def test_full_dag_execution(self, mock_load_prompt, mock_build_chain, mock_pipeline_execute):
        """Integration test: all mocked agents -> full DAG completes."""
        mock_load_prompt.return_value = "System prompt"
        mock_build_chain.return_value = [MagicMock()]
        mock_pipeline_execute.return_value = ("Agent response", {"cost": 0.001})

        dag = SingleTickerAnalysisDAG()
        executor = DAGExecutor(dag.nodes)

        initial_inputs = {
            "topic": "Analysis of TSLA",
            "debate_context": {"market_data": {}, "topic": "TSLA"},
            "market_data": {"TSLA": {"price": 250}},
        }
        context = {"user_id": "test_user", "telemetry": []}

        result = await executor.execute(initial_inputs, context)

        assert "final_report" in result
        assert "verifier_note" in result
        assert "council_transcript" in result
        # 10 debate agents + CIODraft + RiskChallenge + CIOFinal + Verifier = 14 agent calls
        assert mock_pipeline_execute.call_count == 14


# ──────────────────────────────────────────────────────────────────────
# OpportunityDetectionDAG Topology Tests
# ──────────────────────────────────────────────────────────────────────

class TestOpportunityDetectionDAG:
    def test_node_count(self):
        dag = OpportunityDetectionDAG()
        # FilterHoldings + FetchMarketData + 3 Scouts + ReduceScouts = 6
        assert len(dag.nodes) == 6

    def test_all_nodes_have_single_output_key(self):
        dag = OpportunityDetectionDAG()
        for node in dag.nodes:
            assert len(node.output_keys) == 1, f"Node {node.name} has {len(node.output_keys)} output keys"

    def test_topological_sort_layers(self):
        dag = OpportunityDetectionDAG()
        executor = DAGExecutor(dag.nodes)
        # Layer 0: FilterHoldings
        # Layer 1: FetchMarketData
        # Layer 2: 3 Scouts (parallel)
        # Layer 3: ReduceScouts
        assert len(executor.layers) == 4
        assert len(executor.layers[2]) == 3  # 3 scouts parallel

    def test_scouts_use_fast_tier(self):
        dag = OpportunityDetectionDAG()
        scout_nodes = [n for n in dag.nodes if isinstance(n, AgentNode)]
        assert len(scout_nodes) == 3
        for n in scout_nodes:
            assert n.tier == "fast"

    def test_reuses_shared_functions(self):
        """Verify node functions are the same shared functions from portfolio_dag."""
        from src.infrastructure.workflow.portfolio_dag import filter_holdings, fetch_market_data, reduce_scouts
        dag = OpportunityDetectionDAG()
        code_nodes = {n.name: n for n in dag.nodes if isinstance(n, CodeNode)}
        assert code_nodes["FilterHoldings"].func is filter_holdings
        assert code_nodes["FetchMarketData"].func is fetch_market_data
        assert code_nodes["ReduceScouts"].func is reduce_scouts


# ──────────────────────────────────────────────────────────────────────
# CodeNode **kwargs support test
# ──────────────────────────────────────────────────────────────────────

class TestCodeNodeKwargsSupport:
    @pytest.mark.asyncio
    async def test_var_keyword_params_passed(self):
        """Verify CodeNode correctly passes all inputs to **kwargs functions."""
        def kwargs_func(**kwargs):
            return {"keys": sorted(kwargs.keys())}

        node = CodeNode("KwargsNode", kwargs_func, ["a", "b", "c"], ["keys"])
        result = await node.execute({"a": 1, "b": 2, "c": 3}, {})
        assert result == {"keys": ["a", "b", "c"]}

    @pytest.mark.asyncio
    async def test_reduce_debate_stances_via_code_node(self):
        """End-to-end test: CodeNode wrapping reduce_debate_stances."""
        input_keys = ["macro_stance", "momentum_stance"]
        node = CodeNode(
            "ReduceDebateStances",
            reduce_debate_stances,
            input_keys,
            ["council_transcript"],
        )
        result = await node.execute(
            {"macro_stance": "Bearish", "momentum_stance": "Bullish"}, {}
        )
        assert "[Macro]: Bearish" in result["council_transcript"]
        assert "[Momentum]: Bullish" in result["council_transcript"]
