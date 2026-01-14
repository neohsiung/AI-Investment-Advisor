from typing import Dict, Any, List
from src.tools.mcp_server import McpServer, McpTool
from src.data.providers.fmp_provider import FMPProvider

def register_fmp_tools(server: McpServer, provider: FMPProvider):
    """
    Registers FMP data endpoints as tools on the MCP server.
    Enables agents to query Sector Performance, Peers, and basic Company Info.
    """
    
    # 1. Sector Performance
    def get_sector_performance() -> str:
        """Get current performance of all market sectors."""
        data = provider.fetch_sector_performance()
        if not data:
            return "No data available."
        # Format as simple text list
        lines = ["**Sector Performance**:"]
        for item in data:
            sec = item.get('sector', 'Unknown')
            chg = item.get('changesPercentage', '0%')
            lines.append(f"- {sec}: {chg}")
        return "\n".join(lines)

    server.register_tool(McpTool(
        name="get_sector_performance",
        description="Returns real-time percentage change for all stock market sectors (e.g., Technology, Energy). Useful for Sector Rotation analysis.",
        func=get_sector_performance
    ))

    # 2. Stock Peers (Supply Chain Proxy)
    def get_stock_peers(ticker: str) -> str:
        """Find competitors/peers for a given stock ticker."""
        peers = provider.fetch_stock_peers(ticker)
        if not peers:
            return f"No peers found for {ticker}."
        return f"Peers for {ticker}: {', '.join(peers)}"

    server.register_tool(McpTool(
        name="get_stock_peers",
        description="Finds competitor/peer stocks for a given ticker. Useful for identifying industry trends or supply chain relationships.",
        func=get_stock_peers
    ))
    
    # 3. Company Profile
    def get_company_profile(ticker: str) -> str:
        """Get basic profile (Sector, Industry, CEO)."""
        info = provider.fetch_info(ticker)
        if not info:
             return f"No info found for {ticker}."
        return f"**{ticker} Profile**:\n- Sector: {info.get('sector')}\n- Industry: {info.get('industry')}\n- Market Cap: {info.get('market_cap')}\n- CEO: {info.get('ceo')}"

    server.register_tool(McpTool(
        name="get_company_profile",
        description="Get fundamental profile (Sector, Industry, Market Cap) for a stock.",
        func=get_company_profile
    ))
