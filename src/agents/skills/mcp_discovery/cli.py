import sys
import argparse
import logging
import os
import json

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.utils.logger import setup_logger

logger = setup_logger("mcp_discovery_cli")

def main():
    parser = argparse.ArgumentParser(description="Discover external MCP servers.")
    parser.add_argument("--user_id", required=True, help="User ID context")
    parser.add_argument("--query", required=True, help="Query for missing capability")
    
    args = parser.parse_args()
    
    try:
        # 1. Base Recommendations
        mcp_registry = [
            {"name": "Twitter MCP", "capability": "Social media, posting, search", "url": "https://github.com/mcp-servers/twitter"},
            {"name": "Slack MCP", "capability": "Messaging, notification", "url": "https://github.com/mcp-servers/slack"},
            {"name": "PostgreSQL MCP", "capability": "Database management, complex queries", "url": "https://github.com/mcp-servers/postgres"},
            {"name": "Google Maps MCP", "capability": "Location services, place search", "url": "https://github.com/modelcontextprotocol/servers/tree/main/src/google-maps"}
        ]
        
        # 2. Check local installed MCPs (Optional)
        installed_mcps = []
        config_path = "mcp_config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    installed_mcps = list(config.get("mcpServers", {}).keys())
            except Exception as e:
                logger.warning(f'Exception in cli.py: {e}', exc_info=True)

        query_lower = args.query.lower()
        recommendations = [m for m in mcp_registry if any(keyword in m["capability"].lower() or keyword in m["name"].lower() for keyword in query_lower.split())]
        
        # Filter out already installed ones if name matches
        recommendations = [m for m in recommendations if m["name"].lower().split()[0] not in [i.lower() for i in installed_mcps]]
        
        if recommendations:
            res = {
                "status": "found",
                "recommendations": recommendations,
                "installed_context": installed_mcps,
                "message": f"Found {len(recommendations)} potential MCP server(s) to fulfill: '{args.query}'."
            }
        else:
            res = {
                "status": "not_found",
                "recommendations": [],
                "installed_context": installed_mcps,
                "message": f"No immediate MCP matches found for '{args.query}'."
            }
            
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        logger.error(f"CLI mcp_discovery failed: {e}")
        print(json.dumps({"error": str(e), "status": "error"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
