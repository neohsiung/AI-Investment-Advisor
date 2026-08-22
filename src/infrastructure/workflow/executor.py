import logging
import asyncio
from typing import Any, Dict, List, Optional, Set
from src.infrastructure.workflow.base import BaseNode
from src.infrastructure.workflow.cache import WorkflowCache

logger = logging.getLogger(__name__)

class DAGExecutor:
    """
    Orchestrates the topological sorting and parallel execution of DAG nodes.
    Supports multi-level caching telemetry.
    """
    def __init__(self, nodes: List[BaseNode], cache: Optional[WorkflowCache] = None):
        self.nodes = nodes
        self.cache = cache
        self.layers: List[List[BaseNode]] = []
        self._build_dependency_layers()

    def _build_dependency_layers(self):
        """
        Build dependency tree using Kahn's algorithm to resolve node layers for parallel execution.
        """
        # Map output keys to the producing node
        key_to_node: Dict[str, BaseNode] = {}
        for node in self.nodes:
            for ok in node.output_keys:
                if ok in key_to_node:
                    raise ValueError(
                        f"Duplicate output key '{ok}' found. "
                        f"Produced by both node '{key_to_node[ok].name}' and '{node.name}'."
                    )
                key_to_node[ok] = node

        # Build dependency adjacency mapping
        dependencies: Dict[BaseNode, Set[BaseNode]] = {}
        for node in self.nodes:
            deps = set()
            for ik in node.input_keys:
                # If the key is produced by another node in the DAG, mark it as dependency
                if ik in key_to_node:
                    deps.add(key_to_node[ik])
            dependencies[node] = deps

        # Perform topological sorting and layer grouping
        layers = []
        unvisited = set(self.nodes)

        while unvisited:
            current_layer = []
            for node in list(unvisited):
                # Node is ready if all dependencies are resolved (no longer in unvisited set)
                resolved = True
                for dep in dependencies[node]:
                    if dep in unvisited:
                        resolved = False
                        break
                if resolved:
                    current_layer.append(node)

            if not current_layer:
                raise ValueError("Cyclic dependency or unresolved input key detected in DAG nodes.")

            layers.append(current_layer)
            for node in current_layer:
                unvisited.remove(node)

        self.layers = layers
        logger.info(f"DAGExecutor initialized. Resolved {len(self.layers)} execution layer(s).")

    async def execute(self, initial_inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute DAG nodes layer by layer. Independent nodes inside a layer are run concurrently.
        """
        flow_data = dict(initial_inputs)
        
        # Increment total workflow runs
        if self.cache:
            try:
                await self.cache.increment_metric("total_workflow_runs")
            except Exception as e:
                logger.warning(f"DAGExecutor: Failed to increment runs metric: {e}")
        
        # Telemetry bucket initialization
        if "telemetry" not in context:
            context["telemetry"] = []

        for layer_idx, layer in enumerate(self.layers):
            logger.debug(f"DAGExecutor: Starting layer {layer_idx + 1}/{len(self.layers)} with {len(layer)} node(s)")
            
            # Execute all nodes in the current layer in parallel
            async def run_node(node_to_run: BaseNode):
                try:
                    node_outputs = await node_to_run.execute(flow_data, context, cache=self.cache)
                    return node_outputs, None
                except Exception as e:
                    logger.error(f"DAGExecutor: Node '{node_to_run.name}' failed during execution: {e}", exc_info=True)
                    return None, e

            results = await asyncio.gather(*(run_node(node) for node in layer))
            
            # Update flow data and raise first exception if encountered
            for node, (outputs, error) in zip(layer, results):
                if error:
                    # Implement failsafe: fallback to empty outputs or propagate
                    raise error
                if outputs:
                    flow_data.update(outputs)

        return flow_data
