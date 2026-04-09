import json
import logging
import os
from typing import Dict, List, Any, Optional
from src.tools.mcp_client_adapter import get_mcp_client
from src.tools.mcp_server import McpTool

logger = logging.getLogger(__name__)

class McpToolLoader:
    """
    Registry for external MCP servers defined in mcp.json.
    解析 mcp.json 並連接外部 MCP 伺服器，將其工具註冊給 Agent。
    """
    
    def __init__(self, config_path: str = "config/mcp.json"):
        self.config_path = config_path
        self.servers_config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load external MCP server configurations."""
        if not os.path.exists(self.config_path):
            logger.warning(f"MCP config not found at {self.config_path}")
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f).get("mcpServers", {})
        except Exception as e:
            logger.error(f"Failed to load MCP config: {e}")
            return {}

    async def get_tools_for_agent(self, user_id: str) -> List[McpTool]:
        """
        Connect to configured servers and discover tools.
        為特定 User 建立相應的 MCP 客戶端並獲取工具。
        """
        all_tools = []
        for server_name, config in self.servers_config.items():
            try:
                # Determine connection parameters
                sse_url = config.get("url")
                command = config.get("command")
                args = config.get("args", [])
                
                # Expand environment variables in the env config
                raw_env = config.get("env", {})
                resolved_env = os.environ.copy()
                for k, v in raw_env.items():
                    resolved_env[k] = os.path.expandvars(str(v))
                
                # Get or create client (B2C isolated)
                client = await get_mcp_client(
                    user_id=user_id,
                    sse_url=sse_url,
                    command=command,
                    args=args,
                    env=resolved_env
                )
                
                # Wrapped discovery
                mcp_tools = client.list_tools()
                for t in mcp_tools:
                    # Wrap the MCP tool into our local McpTool format
                    # so the AgentLoop can call it natively.
                    wrapped_tool = McpTool(
                        name=t.name,
                        description=t.description,
                        func=lambda _name=t.name, _args=None, _client=client: _client.call_tool(_name, _args or {}),
                        schema=t.inputSchema,
                        category=f"MCP:{server_name}"
                    )
                    all_tools.append(wrapped_tool)
                    
                logger.info(f"McpToolLoader: Discovered {len(mcp_tools)} tools from server '{server_name}'")
            except Exception as e:
                logger.error(f"Failed to load tools from MCP server '{server_name}': {e}")
                
        return all_tools
