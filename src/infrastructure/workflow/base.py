import time
import json
import logging
import inspect
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Callable, Optional, Union
from src.infrastructure.workflow.cache import WorkflowCache

logger = logging.getLogger(__name__)

class BaseNode(ABC):
    """
    Abstract base class for all DAG workflow nodes.
    Supports input/output validation, execution telemetry, and node-level caching.
    """
    def __init__(
        self,
        name: str,
        input_keys: List[str],
        output_keys: List[str],
        ttl: int = 3600
    ):
        self.name = name
        self.input_keys = input_keys
        self.output_keys = output_keys
        self.ttl = ttl

    async def execute(
        self,
        inputs: Dict[str, Any],
        context: Dict[str, Any],
        cache: Optional[WorkflowCache] = None
    ) -> Dict[str, Any]:
        """
        Validates inputs, handles caching checks, records latency, and executes the node.
        """
        # 1. Validate inputs
        missing_inputs = [k for k in self.input_keys if k not in inputs]
        if missing_inputs:
            raise ValueError(
                f"Node '{self.name}' missing required inputs: {missing_inputs}. "
                f"Available inputs: {list(inputs.keys())}"
            )

        # Filter inputs to only what this node expects to guarantee cache key uniqueness
        node_inputs = {k: inputs[k] for k in self.input_keys}
        
        start_time = time.perf_counter()
        cache_hit = False
        outputs = None

        # 2. Check Cache
        if cache and self.ttl > 0:
            try:
                cached_outputs = await cache.get(self.name, node_inputs)
                if cached_outputs is not None:
                    # Validate cached outputs match output_keys
                    missing_cached_outputs = [k for k in self.output_keys if k not in cached_outputs]
                    if not missing_cached_outputs:
                        outputs = cached_outputs
                        cache_hit = True
            except Exception as e:
                logger.warning(f"Node '{self.name}': Cache lookup failed: {e}")

        # 3. Execute actual logic if cache missed
        if not cache_hit:
            logger.debug(f"Node '{self.name}': Cache Miss. Running execution...")
            outputs = await self._run(node_inputs, context)
            
            # Validate outputs
            if not isinstance(outputs, dict):
                raise TypeError(f"Node '{self.name}' execution did not return a dictionary. Got: {type(outputs)}")
            
            missing_outputs = [k for k in self.output_keys if k not in outputs]
            if missing_outputs:
                raise ValueError(f"Node '{self.name}' execution failed to return outputs: {missing_outputs}")

            # Update Cache
            if cache and self.ttl > 0:
                try:
                    await cache.set(self.name, node_inputs, outputs, self.ttl)
                except Exception as e:
                    logger.warning(f"Node '{self.name}': Cache save failed: {e}")

        latency = time.perf_counter() - start_time
        
        # Update Cache metrics
        if cache and self.ttl > 0:
            try:
                if cache_hit:
                    await cache.increment_metric("cache_hits")
                    # Calculate saved cost if this is an AgentNode
                    if isinstance(self, AgentNode):
                        saved_amount = 0.002 # default fast
                        if self.tier == "smart":
                            saved_amount = 0.015
                        elif self.tier == "nano":
                            saved_amount = 0.0005
                        await cache.increment_metric("saved_cost_usd", saved_amount)
                else:
                    await cache.increment_metric("cache_misses")
            except Exception as metric_e:
                logger.warning(f"Node '{self.name}': Failed to record metrics: {metric_e}")

        # Record Node Telemetry
        node_telemetry = {
            "node_name": self.name,
            "latency": latency,
            "cache_hit": cache_hit,
        }
        
        if "telemetry" not in context:
            context["telemetry"] = []
        context["telemetry"].append(node_telemetry)

        logger.info(
            f"Node '{self.name}' completed in {latency:.4f}s. "
            f"Cache hit: {cache_hit}"
        )
        return outputs

    @abstractmethod
    async def _run(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Actual logic of the node to be implemented by sub-classes."""
        pass


class AgentNode(BaseNode):
    """
    DAG node wrapper around LLM agent invocations (using ResilientLLMPipeline).
    """
    def __init__(
        self,
        name: str,
        agent_name: str,
        input_keys: List[str],
        output_keys: List[str],
        tier: str = "fast",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        ttl: int = 3600
    ):
        super().__init__(name, input_keys, output_keys, ttl)
        self.agent_name = agent_name
        self.tier = tier
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def _run(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        # Resolve tier dynamically
        resolved_tier = context.get(f"{self.name}_tier") or (context.get("consensus_tier") if self.agent_name == "CIO" else None) or self.tier
        
        council_service = context.get("council_service")
        if council_service:
            # Call the service's own method, which is already mocked/patched in existing tests
            logger.debug(f"AgentNode '{self.name}': Invoking via council_service._call_agent_llm with tier={resolved_tier}")
            response = await council_service._call_agent_llm(
                self.agent_name, 
                inputs, 
                tier=resolved_tier,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
        else:
            user_id = context.get("user_id", "system")
            
            # Load configs and execute agent call
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.utils.prompt_utils import load_agent_prompt
            from src.domain.interfaces import Message

            chain = build_config_chain(user_id, resolved_tier)
            if not chain:
                raise ValueError(f"No LLM model configured for tier={resolved_tier} user={user_id}")

            pipeline = ResilientLLMPipeline(
                config_chain=chain,
                user_id=user_id,
                agent_name=self.agent_name,
                tier=resolved_tier,
            )

            # 1. Load agent system prompt
            system_prompt = load_agent_prompt(self.agent_name)
            
            # 2. Formulate user prompt using the input parameters passed to the node
            user_content = json.dumps(inputs, default=str)
            
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_content)
            ]

            logger.debug(f"AgentNode '{self.name}': Calling {self.agent_name} via tier={self.tier}")
            response, _ = await pipeline.execute(
                messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
        
        # Map response to output_keys (if single key, assign response directly)
        if len(self.output_keys) == 1:
            return {self.output_keys[0]: response}
        else:
            # If multiple keys, expect JSON response to parse keys, or raise error
            try:
                parsed = json.loads(response)
                if isinstance(parsed, dict):
                    return {k: parsed.get(k) for k in self.output_keys}
            except Exception as e:
                logger.warning(f'Exception in base.py: {e}', exc_info=True)
            raise ValueError(
                f"AgentNode '{self.name}' expected JSON object matching outputs {self.output_keys}, "
                f"but got unparseable response: {response}"
            )


class CodeNode(BaseNode):
    """
    DAG node wrapper around deterministic Python function calls.
    Supports standard callable functions/methods and coroutines.
    """
    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        input_keys: List[str],
        output_keys: List[str],
        ttl: int = 300
    ):
        super().__init__(name, input_keys, output_keys, ttl)
        self.func = func

    async def _run(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        # Merge node inputs and full context (if the function accepts it)
        # Check function signature
        sig = inspect.signature(self.func)
        kwargs = {}
        has_var_keyword = False
        
        for name, param in sig.parameters.items():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                # Function accepts **kwargs — pass all remaining inputs
                has_var_keyword = True
                continue
            if name in inputs:
                kwargs[name] = inputs[name]
            elif name == "context":
                kwargs["context"] = context
            elif param.default is not inspect.Parameter.empty:
                # Use default value
                pass
            else:
                raise ValueError(f"CodeNode '{self.name}': Missing parameter '{name}' in inputs/context.")

        # If the function has **kwargs, pass all inputs that weren't already mapped
        if has_var_keyword:
            for key, value in inputs.items():
                if key not in kwargs:
                    kwargs[key] = value

        # Execute
        if inspect.iscoroutinefunction(self.func):
            result = await self.func(**kwargs)
        else:
            result = self.func(**kwargs)

        # Map result to output_keys
        if isinstance(result, dict):
            return {k: result.get(k) for k in self.output_keys}
        elif len(self.output_keys) == 1:
            return {self.output_keys[0]: result}
        else:
            if isinstance(result, tuple) and len(result) == len(self.output_keys):
                return {k: v for k, v in zip(self.output_keys, result)}
            else:
                raise TypeError(
                    f"CodeNode '{self.name}' returned type {type(result)} but expected dict or tuple "
                    f"matching outputs {self.output_keys}"
                )
