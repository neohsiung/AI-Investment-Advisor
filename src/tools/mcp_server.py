import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Union, Awaitable
import json
import inspect

class McpTool:
    def __init__(self, name: str, description: str, func: Callable, schema: Dict[str, Any] = None):
        self.name = name
        self.description = description
        self.func = func
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
        return self.func(**kwargs)
    
    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema
        }

class McpServer:
    def __init__(self, name="LocalMCP"):
        self.name = name
        self.tools: Dict[str, McpTool] = {}

    def register_tool(self, tool: McpTool):
        self.tools[tool.name] = tool

    def list_tools(self) -> List[Dict]:
        return [t.to_dict() for t in self.tools.values()]

    def call_tool(self, name: str, arguments: Dict[str, Any]):
        if name not in self.tools:
            raise ValueError(f"Tool {name} not found.")
        
        # Log or validate here
        return self.tools[name].execute(**arguments)
