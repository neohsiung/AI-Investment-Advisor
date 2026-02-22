"""
MCP Service Main Entry
"""
from services.mcp_server.src.app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104
