import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union, Awaitable
import json
import asyncio
import inspect

class McpTool:
    def __init__(self, name: str, description: str, func: Callable, schema: Dict[str, Any] = None, category: str = ""):
        self.name = name
        self.description = description
        self.func = func
        self.category = category
        self.is_async = asyncio.iscoroutinefunction(func)
        self.schema = schema or self._generate_schema(func)

    def _generate_schema(self, func) -> Dict[str, Any]:
        """
        Simple auto-schema generation from type hints.
        """
        sig = inspect.signature(func)
        parameters = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self': continue
            
            param_type = "string"
            if param.annotation == int: param_type = "integer"
            elif param.annotation == float: param_type = "number"
            elif param.annotation == bool: param_type = "boolean"
            elif param.annotation == dict: param_type = "object"
            elif param.annotation == list: param_type = "array"
            
            parameters[param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}" 
            }
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
                
        return {
            "type": "object",
            "properties": parameters,
            "required": required
        }

    def execute(self, **kwargs):
        """Synchronous execution (blocks on async skills)."""
        if self.is_async:
            # Handle async functions in sync context
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return loop.run_in_executor(pool, lambda: asyncio.run(self.func(**kwargs)))
            except RuntimeError:
                return asyncio.run(self.func(**kwargs))
        return self.func(**kwargs)

    async def async_execute(self, **kwargs):
        """Async execution (preferred for async skills)."""
        if self.is_async:
            return await self.func(**kwargs)
        return self.func(**kwargs)
    
    def to_dict(self):
        result = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema
        }
        if self.category:
            result["category"] = self.category
        return result

class McpServer:
    def __init__(self, name="LocalMCP"):
        self.name = name
        self.tools: Dict[str, McpTool] = {}

    def register_tool(self, tool: McpTool):
        self.tools[tool.name] = tool

    def unregister_tool(self, name: str):
        """Unregister a tool (hot-unplug)."""
        if name in self.tools:
            del self.tools[name]

    def clear_tools(self):
        """Clear all registered tools."""
        self.tools.clear()

    def list_tools(self) -> List[Dict]:
        return [t.to_dict() for t in self.tools.values()]

    def call_tool(self, name: str, arguments: Dict[str, Any]):
        if name not in self.tools:
            raise ValueError(f"Tool {name} not found.")
        return self.tools[name].execute(**arguments)

    async def async_call_tool(self, name: str, arguments: Dict[str, Any]):
        """Async tool invocation (preferred for async skills)."""
        if name not in self.tools:
            raise ValueError(f"Tool {name} not found.")
        return await self.tools[name].async_execute(**arguments)

    def list_tools_by_category(self, category: str) -> List[Dict]:
        """List tools filtered by category."""
        return [
            t.to_dict() for t in self.tools.values()
            if t.category == category
        ]
