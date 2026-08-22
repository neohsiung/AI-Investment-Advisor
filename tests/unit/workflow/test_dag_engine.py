import os
import json
import asyncio
import pytest
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch
from src.infrastructure.workflow.cache import WorkflowCache
from src.infrastructure.workflow.base import BaseNode, AgentNode, CodeNode
from src.infrastructure.workflow.executor import DAGExecutor

# Simple mock nodes for topology testing
class DummyNode(BaseNode):
    async def _run(self, inputs, context):
        return {"out": inputs["val"] + 1}

@pytest.mark.asyncio
async def test_dag_topological_layers():
    """Verify that nodes are grouped into the correct layers based on dependency topological sort."""
    node_a = DummyNode(name="NodeA", input_keys=["val"], output_keys=["out_a"])
    node_b = DummyNode(name="NodeB", input_keys=["out_a"], output_keys=["out_b"])
    node_c = DummyNode(name="NodeC", input_keys=["val"], output_keys=["out_c"])
    node_d = DummyNode(name="NodeD", input_keys=["out_b", "out_c"], output_keys=["out_d"])

    executor = DAGExecutor([node_a, node_b, node_c, node_d])
    
    # NodeA and NodeC have no DAG dependencies (val is initial input). They should be in layer 0.
    # NodeB depends on out_a (NodeA). It should be in layer 1.
    # NodeD depends on out_b (NodeB) and out_c (NodeC). It should be in layer 2.
    assert len(executor.layers) == 3
    
    layer_0_names = {n.name for n in executor.layers[0]}
    assert "NodeA" in layer_0_names
    assert "NodeC" in layer_0_names
    
    layer_1_names = {n.name for n in executor.layers[1]}
    assert layer_1_names == {"NodeB"}
    
    layer_2_names = {n.name for n in executor.layers[2]}
    assert layer_2_names == {"NodeD"}


@pytest.mark.asyncio
async def test_dag_cyclic_dependency():
    """Verify that a circular dependency raises ValueError."""
    node_a = DummyNode(name="NodeA", input_keys=["out_b"], output_keys=["out_a"])
    node_b = DummyNode(name="NodeB", input_keys=["out_a"], output_keys=["out_b"])
    
    with pytest.raises(ValueError, match="Cyclic dependency or unresolved input key detected"):
        DAGExecutor([node_a, node_b])


@pytest.mark.asyncio
async def test_workflow_cache_sqlite(tmp_path):
    """Test SQLite caching set, get, TTL, and fallback mechanisms."""
    db_file = str(tmp_path / "test_cache.db")
    cache = WorkflowCache(db_path=db_file, disable_cache=False)
    
    node_name = "TestNode"
    inputs = {"symbol": "AAPL", "threshold": 150}
    outputs = {"signal": "BUY", "confidence": 0.95}
    
    # Initial get should miss
    res = await cache.get(node_name, inputs)
    assert res is None
    
    # Store in cache
    await cache.set(node_name, inputs, outputs, ttl_seconds=5)
    
    # Get again, should hit
    res_hit = await cache.get(node_name, inputs)
    assert res_hit == outputs
    
    # Check that SQLite holds the correct value
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT outputs_json FROM workflow_cache")
    row = cursor.fetchone()
    assert row is not None
    assert json.loads(row[0]) == outputs
    conn.close()


@pytest.mark.asyncio
async def test_workflow_cache_ttl_expiry(tmp_path):
    """Verify that expired cache entries are cleaned up and return None."""
    db_file = str(tmp_path / "test_cache_ttl.db")
    cache = WorkflowCache(db_path=db_file, disable_cache=False)
    
    node_name = "ExpireNode"
    inputs = {"key": "value"}
    outputs = {"data": "cached"}
    
    # Store with 0 or negative TTL to simulate instant expiry
    await cache.set(node_name, inputs, outputs, ttl_seconds=-1)
    
    # Memory and SQLite should return None
    res = await cache.get(node_name, inputs)
    assert res is None
    
    # Store with 1 second TTL, sleep 1.1 seconds, verify expired
    await cache.set(node_name, inputs, outputs, ttl_seconds=1)
    await asyncio.sleep(1.1)
    res_expired = await cache.get(node_name, inputs)
    assert res_expired is None


@pytest.mark.asyncio
async def test_code_node_execution():
    """Test CodeNode executes deterministic functions and maps outputs correctly."""
    def sample_sync_func(a, b):
        return {"result": a * b}
        
    async def sample_async_func(a, b):
        return {"result": a + b}

    node_sync = CodeNode("SyncNode", sample_sync_func, ["a", "b"], ["result"])
    node_async = CodeNode("AsyncNode", sample_async_func, ["a", "b"], ["result"])
    
    res_sync = await node_sync.execute({"a": 3, "b": 4}, {})
    assert res_sync == {"result": 12}
    
    res_async = await node_async.execute({"a": 3, "b": 4}, {})
    assert res_async == {"result": 7}


@pytest.mark.asyncio
async def test_node_cache_hit_and_miss_telemetry(tmp_path):
    """Verify that node execution correctly increments cache hit/miss and workflow runs metrics."""
    db_file = str(tmp_path / "telemetry_test.db")
    cache = WorkflowCache(db_path=db_file, disable_cache=False)
    
    # Simple deterministic Node with cache enabled (TTL > 0)
    called_count = 0
    def sample_func(x):
        nonlocal called_count
        called_count += 1
        return {"y": x * 2}
        
    node = CodeNode("CountNode", sample_func, ["x"], ["y"], ttl=60)
    executor = DAGExecutor([node], cache=cache)
    
    # First execution -> Cache Miss
    context = {"telemetry": []}
    res1 = await executor.execute({"x": 10}, context)
    assert res1["y"] == 20
    assert called_count == 1
    assert context["telemetry"][0]["cache_hit"] is False
    
    # Second execution with same parameters -> Cache Hit
    context2 = {"telemetry": []}
    res2 = await executor.execute({"x": 10}, context2)
    assert res2["y"] == 20
    assert called_count == 1 # Function not called again
    assert context2["telemetry"][0]["cache_hit"] is True
    
    # Verify cached telemetry totals
    telemetry = await cache.get_all_telemetry()
    assert telemetry["total_workflow_runs"] == 2.0
    assert telemetry["cache_hits"] == 1.0
    assert telemetry["cache_misses"] == 1.0


@pytest.mark.asyncio
async def test_node_failure_not_breaking():
    """Verify that node exceptions are raised cleanly through executor."""
    def faulty_func():
        raise ZeroDivisionError("division by zero")
        
    node = CodeNode("FaultyNode", faulty_func, [], ["result"])
    executor = DAGExecutor([node])
    
    with pytest.raises(ZeroDivisionError, match="division by zero"):
        await executor.execute({}, {})


@pytest.mark.asyncio
@patch("src.infrastructure.llm.resilient_pipeline.ResilientLLMPipeline.execute", new_callable=AsyncMock)
@patch("src.infrastructure.llm.llm_config_chain.build_config_chain")
@patch("src.utils.prompt_utils.load_agent_prompt")
async def test_agent_node_execution(mock_load_prompt, mock_build_chain, mock_pipeline_execute):
    """Verify AgentNode initializes pipeline, loads prompt, and parses response correctly."""
    mock_load_prompt.return_value = "System prompt template"
    mock_build_chain.return_value = [MagicMock()]
    mock_pipeline_execute.return_value = ("Final response report text", {"cost": 0.001})
    
    agent_node = AgentNode(
        name="TestAgentNode",
        agent_name="Momentum Scout",
        input_keys=["filtered_portfolio"],
        output_keys=["momentum_scout_result"],
        tier="fast",
        ttl=3600
    )
    
    context = {"user_id": "test_user_123"}
    res = await agent_node.execute({"filtered_portfolio": [{"symbol": "TSLA"}]}, context)
    
    assert res == {"momentum_scout_result": "Final response report text"}
    mock_pipeline_execute.assert_called_once()
